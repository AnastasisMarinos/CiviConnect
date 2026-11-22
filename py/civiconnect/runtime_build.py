"""Identify the server code loaded by this copy of CiviConnect."""

from hashlib import sha256
from pathlib import Path

from . import PROJECT_ROOT, PYTHON_ROOT


def build_identifier():
    package = Path(__file__).resolve().parent
    digest = sha256(str(PROJECT_ROOT).encode("utf-8"))
    files = [
        PYTHON_ROOT / "app.py",
        PROJECT_ROOT / "requirements.txt",
        *sorted(package.rglob("*.py")),
    ]
    for path in files:
        name = path.relative_to(PROJECT_ROOT).as_posix()
        digest.update(b"\0" + name.encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]
