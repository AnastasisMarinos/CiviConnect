"""Local, crash-recoverable JSON storage and media helpers for CiviConnect."""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from filelock import FileLock
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
UPLOADS = ROOT / "static" / "uploads"
PEOPLE = "politicians.json"
REPLIES = "video_replies.json"
CONTACTS = "contact_messages.json"
FEED = "llm_research_feed.jsonl"
DATA.mkdir(exist_ok=True)
LOCK = FileLock(str(DATA / ".lock"))
JOURNAL = DATA / ".transaction.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        temp = Path(tmp.name)
        try:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        except BaseException:
            tmp.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def apply_journal(changes):
    for name, value in changes["files"].items():
        path = DATA / name
        if value is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, encode(value))
    if changes.get("append"):
        # Replay from the recorded byte offset, including after a partial write.
        offset, lines = changes["append"]
        with (DATA / FEED).open("r+b") as stream:
            stream.seek(offset)
            stream.truncate()
            stream.write(lines.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
    JOURNAL.unlink()


class Transaction:
    def __init__(self):
        self.files = {}
        self.lines = []

    def read(self, name):
        if name in self.files:
            return self.files[name]
        return json.loads((DATA / name).read_text(encoding="utf-8"))

    def write(self, name, value):
        self.files[name] = value

    def submissions(self):
        return [
            (p.relative_to(DATA).as_posix(), self.read(p.relative_to(DATA).as_posix()))
            for p in sorted((DATA / "submissions").glob("*.json"), reverse=True)
        ]

    def submission(self, sid):
        for name, record in self.submissions():
            if record["id"] == sid:
                return name, record
        raise HTTPException(404, "Submission not found.")

    def add_submission(self, kind, topic, content):
        stamp = now()
        record = dict(
            id=secrets.token_hex(10),
            submission_type=kind,
            topic=topic,
            content=content,
            submitted_at=stamp,
            llm_status="unprocessed",
            llm_cluster=None,
            llm_summary=None,
            politician_flags={},
        )
        self.write(f"submissions/{stamp.replace(':', '-')}_{record['id']}.json", record)
        self.lines.append(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def commit(self):
        if self.files or self.lines:
            changes = {"files": self.files}
            if self.lines:
                changes["append"] = [(DATA / FEED).stat().st_size, "".join(self.lines)]
            atomic_write(JOURNAL, encode(changes))
            apply_journal(changes)


@contextmanager
def transaction():
    with LOCK:
        if JOURNAL.exists():
            apply_journal(json.loads(JOURNAL.read_text(encoding="utf-8")))
        tx = Transaction()
        yield tx
        tx.commit()


def initialize():
    for directory in (DATA / "submissions", UPLOADS / "photos", UPLOADS / "videos"):
        directory.mkdir(parents=True, exist_ok=True)
    with transaction() as tx:
        for name in (PEOPLE, REPLIES, CONTACTS):
            if not (DATA / name).exists():
                tx.write(name, [])
        (DATA / FEED).touch(exist_ok=True)


def configuration():
    with LOCK:
        path = ROOT / "config.json"
        if not path.exists():
            shutil.copyfile(ROOT / "config.example.json", path)
        settings = json.loads(path.read_text(encoding="utf-8-sig"))
        updated = False
        for name in ("admin_password", "session_secret_key"):
            if not settings.get(name) and not os.getenv(name.upper()):
                settings[name] = secrets.token_urlsafe(32)
                updated = True
        if updated:
            atomic_write(path, encode(settings))
    return {k: os.getenv(k.upper()) or v for k, v in settings.items()}


def slug(name, people):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "candidate"
    taken = {p["id"] for p in people}
    result = base
    while result in taken:
        result = f"{base}-{secrets.token_hex(3)}"
    return result


def derive(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)


def credentials(person):
    password = secrets.token_urlsafe(16)
    salt = secrets.token_bytes(16)
    digest = derive(password, salt)
    person.update(
        status="verified",
        login_username=person["id"],
        password_hash=".".join(base64.b64encode(s).decode() for s in (salt, digest)),
    )
    return {"login_username": person["login_username"], "temporary_password": password}


def verifies(password, encoded):
    salt, digest = (base64.b64decode(part) for part in encoded.split("."))
    return hmac.compare_digest(derive(password, salt), digest)


def save_profile_photo(upload: UploadFile):
    """Decode and re-encode photos to discard metadata and untrusted payloads."""
    if upload.size is not None and upload.size > 8 * 1024**2:
        raise HTTPException(413, "Choose a photo smaller than 8 MB.")
    path = UPLOADS / "photos" / (secrets.token_hex(16) + ".jpg")
    try:
        with Image.open(upload.file, formats=["JPEG", "PNG", "WEBP"]) as img:
            if img.width * img.height > 24_000_000:
                raise HTTPException(422, "Choose a smaller photo.")
            img.thumbnail((1200, 1200))
            ImageOps.exif_transpose(img).convert("RGB").save(path, "JPEG", quality=88)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        path.unlink(missing_ok=True)
        raise HTTPException(422, "Choose a readable JPG, PNG, or WebP photo.")
    return "/static/uploads/photos/" + path.name


def save_reply_video(upload: UploadFile):
    suffix = Path(upload.filename or "").suffix.lower()
    header = upload.file.read(32)
    upload.file.seek(0)
    valid = (suffix == ".mp4" and header[4:8] == b"ftyp") or (
        suffix == ".webm" and header.startswith(bytes.fromhex("1a45dfa3"))
    )
    if not valid:
        raise HTTPException(422, "Choose an MP4 or WebM video.")
    if upload.size is None or upload.size > 64 * 1024**2:
        raise HTTPException(413, "Choose a video smaller than 64 MB.")
    path = UPLOADS / "videos" / (secrets.token_hex(16) + suffix)
    try:
        with path.open("xb") as stream:
            shutil.copyfileobj(upload.file, stream)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return "/static/uploads/videos/" + path.name


def remove_upload(url):
    if url and re.fullmatch(
        r"/static/uploads/(photos|videos)/[a-f0-9]{32}\.(jpg|mp4|webm)", url
    ):
        (ROOT / url.lstrip("/")).unlink(missing_ok=True)
