"""CiviConnect HTTP API. Only the public application shell is mounted as static files."""

import hashlib
import hmac
import logging
import re
import os
from time import monotonic
from xml.etree import ElementTree
import time
from collections import defaultdict, deque
from datetime import datetime
from threading import Lock
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator

from . import storage as db
from .opencouncil.directory import GROUPS
from .runtime_build import build_identifier
from .search import topic_ranker, verification
from .youtube import channel_videos

db.initialize()
config = db.configuration()
if config["election_datetime_iso"] and datetime.fromisoformat(config["election_datetime_iso"]).tzinfo is None:
    raise ValueError("election_datetime_iso must include a timezone offset")
app = FastAPI(title="CiviConnect", docs_url=None, redoc_url=None)
BUILD = build_identifier()
signer = URLSafeTimedSerializer(config["session_secret_key"])
SESSION_TTL = 8 * 3600
DEMO_PROFILE_ID = "demo-fictional-profile"
PROFILE_LINKS = ("x", "instagram", "tiktok", "facebook", "linkedin", "youtube", "website")
logger = logging.getLogger(__name__)
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
    if request.url.path.casefold().startswith("/static/uploads/videos/"):
        return Response(status_code=404)
    if request.method in {"POST", "PATCH", "DELETE", "PUT"}:
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse(
                {"detail": "Το αίτημα πρέπει να προέρχεται από το CiviConnect."}, status_code=403
            )
        length = request.headers.get("content-length")
        if request.headers.get("transfer-encoding") or (
            length and not length.isdigit()
        ):
            return JSONResponse(
                {"detail": "Το αίτημα πρέπει να δηλώνει το μέγεθος των δεδομένων."}, status_code=411
            )
        if length and int(length) > 65 * 1024**2:
            return JSONResponse({"detail": "Το μέγεθος των δεδομένων υπερβαίνει τα 65 MB."}, status_code=413)
    result = await call_next(request)
    result.headers["X-Content-Type-Options"] = "nosniff"
    result.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    result.headers["X-Frame-Options"] = "DENY"
    result.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://i.ytimg.com; media-src 'none'; "
        "frame-src https://www.youtube-nocookie.com; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if request.url.path.startswith(
        ("/admin", "/politician", "/api/admin", "/api/politician/")
    ):
        result.headers["Cache-Control"] = "no-store"
    return result


def public_person(person):
    result = {k: person[k] for k in PUBLIC_FIELDS}
    result.update({k: person.get(k) for k in ("role", "party_id", "opencouncil_id")})
    return result


def publicly_listed(person):
    return person["status"] in ("verified", "unclaimed") and person.get("source_active", True)


def find_person(people, pid):
    for person in people:
        if person["id"] == pid:
            return person
    raise HTTPException(404, "Το προφίλ δεν βρέθηκε.")


@app.get("/api/health", include_in_schema=False)
def health(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"app": "CiviConnect", "build": BUILD}


@app.get("/api/config")
def public_config():
    return {k: config[k] for k in ("municipality_name", "election_datetime_iso")}


@app.get("/api/parties")
def municipal_groups():
    with db.transaction() as tx:
        return tx.read(GROUPS) if (db.DATA / GROUPS).exists() else []


@app.get("/api/politicians")
def directory():
    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        listed = [public_person(p) for p in people if publicly_listed(p)]
        demo = demo_person(people)
        if demo:
            listed.append(demo)
        return listed


@app.get("/api/politicians/{pid}")
def profile(pid: str):
    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        if pid == DEMO_PROFILE_ID:
            demo = demo_person(people)
            if demo:
                return demo
        person = find_person(people, pid)
        if not publicly_listed(person):
            raise HTTPException(404, "Το προφίλ δεν βρέθηκε.")
        return public_person(person)


@app.get("/api/politicians/{pid}/news")
def politician_news(pid: str, limit: Annotated[int, Query(ge=1, le=verification.PERSON_NEWS_LIMIT)] = 2):
    person = profile(pid)
    try:
        return verification.person_headlines(person["name"], int(monotonic() // 900))[:limit]
    except (OSError, ValueError, ElementTree.ParseError):
        raise HTTPException(502, "Το Google News δεν είναι προσωρινά διαθέσιμο.")


@app.get("/api/video-replies")
def videos():
    channel = os.getenv("YOUTUBE_CHANNEL_ID") or config.get("youtube_channel_id", "")
    if not channel:
        return []
    if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel):
        raise HTTPException(503, "Το αναγνωριστικό του καναλιού YouTube δεν είναι έγκυρο.")
    try:
        return channel_videos(channel, int(monotonic() // 300))
    except (OSError, ValueError):
        raise HTTPException(502, "Το κανάλι YouTube δεν είναι προσωρινά διαθέσιμο.")



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


class CivicQuestion(Model):
    question: str = Field(min_length=1, max_length=3000)


@app.post("/api/athens/answer")
def civic_answer(body: CivicQuestion):
    return topic_ranker.answer(body.question, config)


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
    description: str = Field(default="", max_length=3000)
    statements: list[Statement] = Field(default_factory=list, max_length=5)
    socials: dict[str, str] = Field(default_factory=dict)

    @field_validator("socials")
    @classmethod
    def valid_links(cls, links):
        for key, value in links.items():
            if key not in PROFILE_LINKS:
                raise ValueError("Άγνωστο κοινωνικό δίκτυο.")
            if value:
                parsed = urlsplit(value)
                if (
                    len(value) > 512
                    or parsed.scheme not in ("http", "https")
                    or not parsed.hostname
                    or parsed.username
                    or "\\" in value
                ):
                    raise ValueError("Οι σύνδεσμοι πρέπει να είναι πλήρεις διευθύνσεις HTTP ή HTTPS.")
        return {key: links.get(key, "") for key in PROFILE_LINKS}


class Claim(Details):
    verification_email: Email


class DemoProfile(Details):
    enabled: bool = True
    name: Short
    party: str = Field(default="", max_length=160)
    role: str = Field(default="", max_length=160)
    photo_url: str = Field(default="", pattern=r"^(?:/static/[\w./%-]+)?$")


def demo_person(people):
    if any(person["id"] == DEMO_PROFILE_ID for person in people):
        return None
    try:
        text = (db.DATA / "demo_profile.json").read_text(encoding="utf-8-sig")
        demo = DemoProfile.model_validate_json(text)
    except FileNotFoundError:
        return None
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, error["loc"])) for error in exc.errors(include_input=False))
        logger.warning("Could not load data/demo_profile.json. Check these fields: %s.", fields)
        return None
    except (OSError, ValueError):
        logger.warning("Could not load data/demo_profile.json. Check the fields against demo-profile.example.json.")
        return None
    if not demo.enabled:
        return None
    return public_person(dict(demo.model_dump(), id=DEMO_PROFILE_ID, status="demo", created_at=None))


def parse_form(model, value):
    try:
        return model.model_validate_json(value)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_context=False, include_input=False))


@app.post("/api/politicians/{pid}/claim", status_code=201)
def request_claim(
    pid: str,
    application: Annotated[str, Form()],
    photo: Annotated[UploadFile | None, File()] = None,
):
    body = parse_form(Claim, application)
    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        person = find_person(people, pid)
        if not publicly_listed(person) or person["status"] != "unclaimed" or person.get("claim"):
            raise HTTPException(409, "Το προφίλ δεν είναι διαθέσιμο για διεκδίκηση.")
        claim = body.model_dump()
        claim["photo"] = db.save_profile_photo(photo, private=True) if photo else None
        person["claim"] = claim
        tx.write(db.PEOPLE, people)
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
                "Υπερβολικά πολλές προσπάθειες. Δοκιμάστε ξανά σε πέντε λεπτά.",
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
        raise HTTPException(401, "Το όνομα χρήστη ή ο κωδικός πρόσβασης είναι λάθος.")
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
        raise HTTPException(401, "Συνδεθείτε για να συνεχίσετε.")
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
        raise HTTPException(401, "Συνδεθείτε ξανά για να συνεχίσετε.")
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
        return {"profile": public_person(person)}


@app.put("/api/politician/profile")
def edit_self(
    profile: Annotated[str, Form()],
    photo: Annotated[UploadFile | None, File()] = None,
    pid=Depends(politician),
):
    body = parse_form(Details, profile)
    old_photo = None
    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        person = find_person(people, pid)
        if photo:
            old_photo = person["photo_url"]
            person["photo_url"] = db.save_profile_photo(photo)
        person.update(body.model_dump())
        tx.write(db.PEOPLE, people)
    db.remove_upload(old_photo)
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
            "contacts": tx.read(db.CONTACTS)[::-1],
        }


@app.get("/api/admin/politicians/{pid}/claim-photo", dependencies=[Depends(admin)])
def claim_photo(pid: str):
    with db.transaction() as tx:
        person = find_person(tx.read(db.PEOPLE), pid)
        photo = (person.get("claim") or {}).get("photo")
        if not photo:
            raise HTTPException(404)
        return FileResponse(db.DATA / "claim_photos" / photo, media_type="image/jpeg")


@app.post("/api/admin/politicians/{pid}/{action}", dependencies=[Depends(admin)])
def issue(pid: str, action: Literal["approve", "regenerate", "reject"]):
    staged_photo = None
    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        person = find_person(people, pid)
        claim = person.get("claim")
        if action == "regenerate" and person["status"] == "verified":
            result = db.credentials(person)
        elif action == "approve" and (person["status"] == "pending" or
                                      (claim and publicly_listed(person) and person["status"] == "unclaimed")):
            if claim:
                person.update({k: v for k, v in claim.items() if k != "photo"})
                if claim["photo"]:
                    filename = claim["photo"]
                    staged_photo = db.DATA / "claim_photos" / filename
                    db.atomic_write(db.UPLOADS / "photos" / filename, staged_photo.read_bytes())
                    person["photo_url"] = "/static/uploads/photos/" + filename
                person.pop("claim")
            result = db.credentials(person)
        elif action == "reject" and claim and person["status"] == "unclaimed":
            if claim["photo"]:
                staged_photo = db.DATA / "claim_photos" / claim["photo"]
            person.pop("claim")
            result = {"ok": True}
        else:
            raise HTTPException(409, "Η κατάσταση του προφίλ έχει αλλάξει.")
        tx.write(db.PEOPLE, people)
    if staged_photo:
        staged_photo.unlink(missing_ok=True)
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
        tx.write(db.PEOPLE, [p for p in people if p["id"] != pid])
    db.remove_upload(person["photo_url"])
    return {"ok": True}


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


@app.get("/submit.html", include_in_schema=False)
def old_claim_page(request: Request):
    query = request.url.query
    return RedirectResponse("/claim-profile.html" + ("?" + query if query else ""), status_code=308)


@app.get("/{page}.html")
def page(page: str):
    if page not in {
        "index",
        "politicians",
        "profile",
        "claim-profile",
        "politician-login",
        "mission",
        "admin-login",
    }:
        raise HTTPException(404, "Η σελίδα δεν βρέθηκε.")
    return FileResponse(STATIC / (page + ".html"))
