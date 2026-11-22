"""Maintain the local data store and sync the Athens council directory."""
import argparse
import shutil

from civiconnect import storage as db
from civiconnect.opencouncil.directory import GROUPS, sync_athens
from civiconnect.opencouncil.evidence import ENTITIES, INDEX, sync_evidence
from civiconnect.search.civic_index import INDEX_FILE, build_index


def reset():
    with db.LOCK:
        for folder in (
            db.UPLOADS / "photos",
            db.DATA / "claim_photos",
        ):
            if not folder.exists():
                continue
            if folder.is_symlink() or folder.resolve() != folder:
                raise RuntimeError(f"Refusing to reset redirected folder: {folder}")
            for path in folder.iterdir():
                if path.is_symlink() or path.is_file():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
        db.JOURNAL.unlink(missing_ok=True)
        for name in (db.PEOPLE, db.CONTACTS):
            db.atomic_write(db.DATA / name, db.encode([]))
        (db.DATA / GROUPS).unlink(missing_ok=True)
        for name in (ENTITIES, INDEX, INDEX_FILE, "topic_cache.json"):
            (db.DATA / name).unlink(missing_ok=True)
    print("Runtime records and uploads cleared.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync-athens", help="Refresh representatives and municipal groups from OpenCouncil.")
    commands.add_parser("sync-athens-evidence", help="Download one year of public meetings and rebuild search.")
    commands.add_parser("build-athens-search", help="Rebuild search from the OpenCouncil evidence already on disk.")
    commands.add_parser("reset", help="Clear active application data and uploads. Preserve historical submissions.")
    command = parser.parse_args().command
    db.initialize()
    db.configuration()
    if command == "reset":
        reset()
    elif command == "sync-athens":
        people, groups = sync_athens()
        print(f"Synced {people} Athens representatives and {groups} municipal groups.")
    else:
        if command == "sync-athens-evidence":
            records, meetings = sync_evidence()
            print(f"Downloaded {records} Athens evidence records from {meetings} meetings.")
        with db.transaction() as tx:
            rows = tx.read(INDEX)
        print(f"Indexed {build_index(rows)} searchable passages.")
