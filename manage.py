"""Seed a fictional election or explicitly clear the local runtime store."""

import argparse
import shutil
from datetime import datetime, timedelta, timezone

import storage as db

NAMES = [
    ("Elena Brooks", "Civic Alliance", "a neighborhood housing advocate"),
    ("Marcus Reed", "Forward Riverton", "a former transit planner"),
    ("Priya Shah", "Green Coalition", "a community garden coordinator"),
    ("Daniel Wright", "Independent", "a civil engineer"),
    ("Sofia Ortiz", "Civic Alliance", "a small business owner"),
    ("Grace Chen", "Forward Riverton", "a public librarian"),
    ("Oliver Hayes", "Independent", "a youth sports volunteer"),
    ("Amir Mansour", "Green Coalition", "an environmental educator"),
    ("Robin Ellis", "Independent", "a neighborhood organizer"),
    ("Alex Morgan", "Civic Alliance", "a community volunteer"),
]
TOPICS = [
    (
        "Housing",
        "How can Riverton make housing more affordable?",
        "housing",
        "Publish a neighborhood housing inventory and expand affordable homes near transit.",
    ),
    (
        "Public transit",
        "Can we make public transport more reliable?",
        "transit",
        "Use route-level reliability reports to guide bus and tram improvements.",
    ),
    (
        "Green spaces",
        "How will you protect our green spaces?",
        "parks",
        "Budget for park maintenance and identify neighborhoods with limited access to green space.",
    ),
    (
        "Safer streets",
        "What would make our streets safer to walk?",
        "streets",
        "Prioritize accessible crossings and sidewalk repairs around schools and transit stops.",
    ),
    (
        "Local economy",
        "How can the city support local businesses?",
        "economy",
        "Simplify permits and give small businesses a single point of contact at city hall.",
    ),
    (
        "Education",
        "Could our libraries offer more after-school programs?",
        "education",
        "Work with library staff and families to pilot additional after-school hours.",
    ),
]
EXTRA = [
    (
        "Budget",
        "Where can residents see the annual neighborhood spending breakdown?",
    ),
    (
        "Accessibility",
        "The curb ramp by Central Station is blocked most afternoons.",
    ),
    ("Sports", "Could community teams use the school field on weekends?"),
    ("Public meetings", "Will evening council meetings have live captions?"),
    (
        "Waste collection",
        "Our recycling pickup has missed Elm Street twice this month.",
    ),
    ("Water", "How will the city share drinking water test results?"),
    (
        "Town services",
        "Is there a single place to check the status of repair requests?",
    ),
    ("Lighting", "Several lights along the river path are broken."),
    ("Volunteering", "How can students help with neighborhood projects?"),
]


def print_accounts(accounts):
    print("Fictional demo candidates. Store these temporary passwords privately.")
    for account in accounts:
        print(f"{account['login_username']}  {account['temporary_password']}")


def seed():
    access = []
    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        if any(p.get("demo") for p in people):
            # Reopening the demo preserves submissions and rotates only demo logins.
            existing = [
                p for p in people if p.get("demo") and p["status"] == "verified"
            ]
            access = [db.credentials(person) for person in existing]
            tx.write(db.PEOPLE, people)
            print_accounts(access)
            return
        stamp = datetime.now(timezone.utc)
        demos = []
        for i, (name, party, bio) in enumerate(NAMES):
            position = TOPICS[i % len(TOPICS)][3]
            person = dict(
                id=db.slug(name, people),
                name=name,
                party=party,
                description=f"{name} is {bio} in Riverton. Their work brings residents and city staff together to improve everyday public services.",
                photo_url=f"/static/demo/person-{(i % 8) + 1}.jpg",
                socials=dict(x="", instagram="", tiktok="", website=""),
                statements=[
                    position,
                    "Publish progress updates residents can check each quarter.",
                    "Hold accessible neighborhood meetings throughout the year.",
                ],
                verification_email=f"candidate{i+1}@example.invalid",
                status="pending",
                login_username=None,
                password_hash=None,
                planner_notes={},
                created_at=db.now(),
                demo=True,
            )
            if i < 8:
                access.append(db.credentials(person))
            people.append(person)
            demos.append(person)
        tx.write(db.PEOPLE, people)
        replies = tx.read(db.REPLIES)
        for i, (topic, question, media, _) in enumerate(TOPICS):
            sub = tx.add_submission(topic, question)
            sub["politician_flags"][demos[i]["id"]] = "answered"
            replies.append(
                dict(
                    id=f"demo-reply-{i+1}",
                    politician_id=demos[i]["id"],
                    question_id=sub["id"],
                    question_prompt=question,
                    topic=topic,
                    source_type="upload",
                    youtube_id=None,
                    video_url=f"/static/demo/{media}.mp4",
                    poster_url=f"/static/demo/{media}.jpg",
                    aspect_ratio="vertical" if i % 2 else "horizontal",
                    created_at=(stamp - timedelta(hours=i + 1)).isoformat(),
                )
            )
        tx.write(db.REPLIES, replies)
        for topic, question in EXTRA:
            tx.add_submission(topic, question)
    print_accounts(access)


def reset():
    # Keep configuration intact. Remove only data and media under the known roots.
    with db.LOCK:
        for folder in (
            db.DATA / "submissions",
            db.UPLOADS / "photos",
            db.UPLOADS / "videos",
        ):
            if folder.is_symlink() or folder.resolve() != folder:
                raise RuntimeError(f"Refusing to reset redirected folder: {folder}")
            for path in folder.iterdir():
                if path.is_symlink() or path.is_file():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
        db.JOURNAL.unlink(missing_ok=True)
        for name in (db.PEOPLE, db.REPLIES, db.CONTACTS):
            db.atomic_write(db.DATA / name, db.encode([]))
        db.atomic_write(db.DATA / db.FEED, b"")
    print("Runtime records and uploads cleared.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("demo", "reset"))
    command = parser.parse_args().command
    db.initialize()
    db.configuration()
    (seed if command == "demo" else reset)()
