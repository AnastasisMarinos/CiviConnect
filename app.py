"""CiviConnect HTTP API. Only the public application shell is mounted as static files."""

import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime
from threading import Lock
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

import storage as db

db.initialize()
config = db.configuration()
election = datetime.fromisoformat(config["election_datetime_iso"])
if election.tzinfo is None:
    raise ValueError("election_datetime_iso must include a timezone offset")
app = FastAPI(title="CiviConnect", docs_url=None, redoc_url=None)
signer = URLSafeTimedSerializer(config["session_secret_key"])
SESSION_TTL = 8 * 3600
STATIC = db.ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
PUBLIC_FIELDS = (
    "id",
    "name",
    "party",
    "description",
    "photo_url",
    "socials",
    "statements",
    "status",
    "created_at",
)


@app.middleware("http")
async def boundaries(request, call_next):
    if request.method in {"POST", "PATCH", "DELETE", "PUT"}:
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse(
                {"detail": "Cross-origin write rejected."}, status_code=403
            )
        length = request.headers.get("content-length")
        if request.headers.get("transfer-encoding") or (
            length and not length.isdigit()
        ):
            return JSONResponse(
                {"detail": "A fixed request size is required."}, status_code=411
            )
        if length and int(length) > 65 * 1024**2:
            return JSONResponse({"detail": "Upload exceeds 65 MB."}, status_code=413)
    result = await call_next(request)
    result.headers["X-Content-Type-Options"] = "nosniff"
    result.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    result.headers["X-Frame-Options"] = "DENY"
    result.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://i.ytimg.com; media-src 'self'; "
        "frame-src https://www.youtube-nocookie.com; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if request.url.path.startswith(
        ("/admin", "/politician", "/api/admin", "/api/politician/")
    ):
        result.headers["Cache-Control"] = "no-store"
    return result


def public_person(person):
    return {k: person[k] for k in PUBLIC_FIELDS}


def find_person(people, pid):
    for person in people:
        if person["id"] == pid:
            return person
    raise HTTPException(404, "Candidate not found.")


def joined_replies(tx):
    people = {p["id"]: p for p in tx.read(db.PEOPLE) if p["status"] == "verified"}
    return [
        dict(
            r,
            **{k: people[r["politician_id"]][k] for k in ("name", "party", "photo_url")}
        )
        for r in sorted(
            tx.read(db.REPLIES), key=lambda r: r["created_at"], reverse=True
        )
        if r["politician_id"] in people
    ]


@app.get("/api/config")
def public_config():
    return {k: config[k] for k in ("municipality_name", "election_datetime_iso")}


@app.get("/api/politicians")
def directory():
    with db.transaction() as tx:
        return [
            public_person(p) for p in tx.read(db.PEOPLE) if p["status"] == "verified"
        ]


@app.get("/api/politicians/{pid}")
def profile(pid: str):
    with db.transaction() as tx:
        person = find_person(tx.read(db.PEOPLE), pid)
        if person["status"] != "verified":
            raise HTTPException(404, "Candidate not found.")
        return public_person(person)


@app.get("/api/video-replies")
def replies():
    with db.transaction() as tx:
        return joined_replies(tx)


class Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


Short = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
]
Statement = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
]
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    ),
]


class Submission(Model):
    submission_type: Literal["question", "inquiry", "complaint"]
    topic: str = Field(default="", max_length=120)
    content: str = Field(min_length=1, max_length=3000)


@app.post("/api/submissions", status_code=201)
def submit(body: Submission):
    with db.transaction() as tx:
        row = tx.add_submission(body.submission_type, body.topic, body.content)
        return {"id": row["id"]}


class Contact(Model):
    name: Short
    email: Email
    message: str = Field(min_length=1, max_length=3000)


@app.post("/api/contact", status_code=201)
def contact(body: Contact):
    with db.transaction() as tx:
        tx.write(
            db.CONTACTS,
            [*tx.read(db.CONTACTS), dict(**body.model_dump(), submitted_at=db.now())],
        )
    return {"ok": True}


class Details(Model):
    description: str = Field(min_length=1, max_length=3000)
    statements: list[Statement] = Field(min_length=3, max_length=5)
    socials: dict[str, str] = Field(default_factory=dict)

    @field_validator("socials")
    @classmethod
    def valid_links(cls, links):
        for key, value in links.items():
            if key not in ("x", "instagram", "tiktok", "website"):
                raise ValueError("Unknown social network")
            if value:
                parsed = urlsplit(value)
                if (
                    len(value) > 512
                    or parsed.scheme not in ("http", "https")
                    or not parsed.hostname
                    or parsed.username
                    or "\\" in value
                ):
                    raise ValueError("Social links must be full http or https URLs")
        return {k: links.get(k, "") for k in ("x", "instagram", "tiktok", "website")}


class Application(Details):
    name: Short
    party: Short
    verification_email: Email


@app.post("/api/politicians/apply", status_code=201)
def apply_candidate(
    application: Annotated[str, Form()], photo: Annotated[UploadFile, File()]
):
    from pydantic import ValidationError

    try:
        body = Application.model_validate_json(application)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_context=False, include_input=False))
    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        if any(
            p["verification_email"].casefold() == body.verification_email.casefold()
            for p in people
        ):
            raise HTTPException(409, "An application already exists for this email.")
        person = dict(
            **body.model_dump(),
            id=db.slug(body.name, people),
            status="pending",
            login_username=None,
            password_hash=None,
            planner_notes={},
            created_at=db.now(),
            photo_url=db.save_profile_photo(photo)
        )
        tx.write(db.PEOPLE, [*people, person])
    return {"status": "pending"}


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=512)


# Reserve an attempt before checking credentials so simultaneous requests count.
attempts = defaultdict(deque)
attempt_lock = Lock()


def limit(key):
    with attempt_lock:
        cutoff = time.monotonic() - 300
        for saved in list(attempts):
            while attempts[saved] and attempts[saved][0] <= cutoff:
                attempts[saved].popleft()
            if not attempts[saved]:
                del attempts[saved]
        if len(attempts[key]) >= 5:
            raise HTTPException(
                429,
                "Too many attempts. Try again in five minutes.",
                headers={"Retry-After": "300"},
            )
        attempts[key].append(time.monotonic())


def fingerprint(secret):
    return hmac.new(
        config["session_secret_key"].encode(), secret.encode(), hashlib.sha256
    ).hexdigest()


@app.post("/api/{role}/login")
def login(
    role: Literal["admin", "politician"],
    body: Login,
    request: Request,
    response: Response,
):
    key = (role, request.client.host if request.client else "")
    limit(key)
    if role == "admin":
        valid = hmac.compare_digest(
            body.username.encode(), config["admin_username"].encode()
        ) and hmac.compare_digest(
            body.password.encode(), config["admin_password"].encode()
        )
        identity = {"id": "admin", "version": fingerprint(config["admin_password"])}
    else:
        with db.transaction() as tx:
            person = next(
                (
                    p
                    for p in tx.read(db.PEOPLE)
                    if p["status"] == "verified"
                    and p["login_username"] == body.username
                ),
                None,
            )
        valid = bool(person and db.verifies(body.password, person["password_hash"]))
        identity = (
            {"id": person["id"], "version": fingerprint(person["password_hash"])}
            if valid
            else {}
        )
    if not valid:
        raise HTTPException(401, "Username or password is incorrect.")
    with attempt_lock:
        attempts.pop(key, None)
    response.set_cookie(
        role + "_session",
        signer.dumps(identity, salt=role + "-auth"),
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=SESSION_TTL,
        path="/",
    )
    return {"ok": True}


def session(request, role):
    try:
        identity = signer.loads(
            request.cookies.get(role + "_session", ""),
            salt=role + "-auth",
            max_age=SESSION_TTL,
        )
    except BadSignature:
        raise HTTPException(401, "Please sign in.")
    if role == "admin":
        active = identity["version"] == fingerprint(config["admin_password"])
    else:
        with db.transaction() as tx:
            active = any(
                p["id"] == identity["id"]
                and p["status"] == "verified"
                and fingerprint(p["password_hash"]) == identity["version"]
                for p in tx.read(db.PEOPLE)
            )
    if not active:
        raise HTTPException(401, "Please sign in again.")
    return identity["id"]


def admin(request: Request):
    return session(request, "admin")


def politician(request: Request):
    return session(request, "politician")


@app.post("/api/{role}/logout")
def logout(role: Literal["admin", "politician"], response: Response):
    response.delete_cookie(role + "_session", httponly=True, samesite="strict")
    return {"ok": True}


@app.get("/api/politician/workspace")
def workspace(pid=Depends(politician)):
    with db.transaction() as tx:
        person = find_person(tx.read(db.PEOPLE), pid)
        submissions = [
            dict(
                s,
                politician_flags=(
                    {pid: s["politician_flags"][pid]}
                    if pid in s["politician_flags"]
                    else {}
                ),
            )
            for _, s in tx.submissions()
        ]
        return {
            "profile": public_person(person),
            "notes": person["planner_notes"],
            "submissions": submissions,
            "replies": [r for r in joined_replies(tx) if r["politician_id"] == pid],
        }


class Plan(Model):
    flag: Literal["planned", "answered", ""] = ""
    note: str = Field(default="", max_length=3000)


@app.put("/api/politician/planner/{sid}")
def update_plan(sid: str, body: Plan, pid=Depends(politician)):
    with db.transaction() as tx:
        filename, sub = tx.submission(sid)
        people = tx.read(db.PEOPLE)
        person = find_person(people, pid)
        if body.flag:
            sub["politician_flags"][pid] = body.flag
        else:
            sub["politician_flags"].pop(pid, None)
        if body.note:
            person["planner_notes"][sid] = body.note
        else:
            person["planner_notes"].pop(sid, None)
        tx.write(filename, sub)
        tx.write(db.PEOPLE, people)
    return {"ok": True}


def parse_youtube(url):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    pieces = parts.path.strip("/").split("/")
    vid = ""
    shorts = False
    if parts.scheme in ("https", "http") and not parts.username:
        if host == "youtu.be" and len(pieces) == 1:
            vid = pieces[0]
        elif host in ("www.youtube.com", "youtube.com", "m.youtube.com"):
            if pieces == ["watch"]:
                vid = parse_qs(parts.query).get("v", [""])[0]
            elif len(pieces) == 2 and pieces[0] == "shorts":
                vid, shorts = pieces[1], True
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
        raise HTTPException(422, "Enter a valid YouTube or Shorts URL.")
    return vid, shorts


@app.post("/api/politician/replies", status_code=201)
def publish(
    question_prompt: Annotated[str, Form(min_length=1, max_length=3000)],
    question_id: Annotated[str, Form()] = "",
    youtube_url: Annotated[str, Form(max_length=512)] = "",
    aspect_ratio: Annotated[Literal["auto", "horizontal", "vertical"], Form()] = "auto",
    video: Annotated[UploadFile | None, File()] = None,
    pid=Depends(politician),
):
    if bool(youtube_url.strip()) == bool(video) or not question_prompt.strip():
        raise HTTPException(422, "Enter a question and choose one video source.")
    yt, shorts = parse_youtube(youtube_url) if youtube_url else (None, False)
    with db.transaction() as tx:
        prompt, topic = question_prompt.strip(), ""
        if question_id:
            filename, sub = tx.submission(question_id)
            prompt, topic = sub["content"], sub["topic"]
            sub["politician_flags"][pid] = "answered"
            tx.write(filename, sub)
        record = dict(
            id=secrets.token_hex(10),
            politician_id=pid,
            question_id=question_id or None,
            question_prompt=prompt,
            topic=topic,
            source_type="upload" if video else "youtube",
            youtube_id=yt,
            video_url=db.save_reply_video(video) if video else None,
            aspect_ratio=(
                ("vertical" if shorts else "horizontal")
                if aspect_ratio == "auto"
                else aspect_ratio
            ),
            created_at=db.now(),
        )
        tx.write(db.REPLIES, [*tx.read(db.REPLIES), record])
    return {"id": record["id"]}


@app.put("/api/politician/profile")
def edit_self(body: Details, pid=Depends(politician)):
    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        find_person(people, pid).update(body.model_dump())
        tx.write(db.PEOPLE, people)
    return {"ok": True}


@app.get("/api/admin/workspace", dependencies=[Depends(admin)])
def admin_workspace():
    with db.transaction() as tx:
        people = [
            {k: v for k, v in p.items() if k not in ("password_hash", "planner_notes")}
            for p in tx.read(db.PEOPLE)
        ]
        return {
            "people": people,
            "replies": joined_replies(tx),
            "submissions": [s for _, s in tx.submissions()],
            "contacts": tx.read(db.CONTACTS)[::-1],
        }


@app.post("/api/admin/politicians/{pid}/{action}", dependencies=[Depends(admin)])
def issue(pid: str, action: Literal["approve", "regenerate"]):
    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        person = find_person(people, pid)
        if (action == "approve") != (person["status"] == "pending"):
            raise HTTPException(
                409, "This candidate's verification status has changed."
            )
        result = db.credentials(person)
        tx.write(db.PEOPLE, people)
    return result


class AdminDetails(Details):
    name: Short
    party: Short


@app.put("/api/admin/politicians/{pid}", dependencies=[Depends(admin)])
def edit_person(pid: str, body: AdminDetails):
    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        find_person(people, pid).update(body.model_dump())
        tx.write(db.PEOPLE, people)
    return {"ok": True}


@app.delete("/api/admin/politicians/{pid}", dependencies=[Depends(admin)])
def delete_person(pid: str):
    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        person = find_person(people, pid)
        replies = tx.read(db.REPLIES)
        media = [
            person["photo_url"],
            *(r["video_url"] for r in replies if r["politician_id"] == pid),
        ]
        tx.write(db.PEOPLE, [p for p in people if p["id"] != pid])
        tx.write(db.REPLIES, [r for r in replies if r["politician_id"] != pid])
        for name, sub in tx.submissions():
            if sub["politician_flags"].pop(pid, None):
                tx.write(name, sub)
    for url in media:
        db.remove_upload(url)
    return {"ok": True}


def remove_reply(rid, owner=None):
    with db.transaction() as tx:
        rows = tx.read(db.REPLIES)
        record = next(
            (
                r
                for r in rows
                if r["id"] == rid and (owner is None or r["politician_id"] == owner)
            ),
            None,
        )
        if not record:
            raise HTTPException(404, "Reply not found.")
        tx.write(db.REPLIES, [r for r in rows if r["id"] != rid])
    db.remove_upload(record["video_url"])
    return {"ok": True}


@app.delete("/api/admin/replies/{rid}", dependencies=[Depends(admin)])
def moderate(rid: str):
    return remove_reply(rid)


@app.delete("/api/politician/replies/{rid}")
def unpublish(rid: str, pid=Depends(politician)):
    return remove_reply(rid, pid)


@app.get("/api/admin/export/llm-dataset", dependencies=[Depends(admin)])
def export_dataset(format: Literal["json", "jsonl"] = "json"):
    with db.transaction() as tx:
        if format == "jsonl":
            return Response(
                (db.DATA / db.FEED).read_bytes(),
                media_type="application/x-ndjson",
                headers={
                    "Content-Disposition": 'attachment; filename="llm_research_feed.jsonl"'
                },
            )
        return JSONResponse(
            [s for _, s in tx.submissions()],
            headers={
                "Content-Disposition": 'attachment; filename="citizen-submissions.json"'
            },
        )


@app.get("/admin")
@app.get("/politician")
def dashboard(request: Request):
    role = request.url.path.strip("/")
    try:
        session(request, role)
    except HTTPException:
        return RedirectResponse("/" + role + "-login.html", status_code=303)
    return FileResponse(db.ROOT / "templates" / (role + "_dashboard.html"))


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/{page}.html")
def page(page: str):
    if page not in {
        "index",
        "politicians",
        "profile",
        "submit",
        "politician-login",
        "mission",
        "admin-login",
    }:
        raise HTTPException(404, "Page not found.")
    return FileResponse(STATIC / (page + ".html"))
