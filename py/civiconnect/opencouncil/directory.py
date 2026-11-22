"""Import current Athens municipal and community representatives from OpenCouncil."""
import json
from datetime import datetime
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from .. import storage as db

BASE = "https://opencouncil.gr/api/cities/athens/"
GROUPS = "opencouncil_parties.json"


def fetch(resource):
    with urlopen(BASE + resource, timeout=15) as response:
        rows = json.load(response)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"OpenCouncil returned no {resource}; existing data kept.")
    return rows


def active(row, today, start, end):
    return (not row.get(start) or row[start][:10] <= today) and (
        not row.get(end) or row[end][:10] >= today
    )


def office_type(role):
    if role.get("name_en") == "Mayor" or role.get("name") == "Δήμαρχος":
        return "mayor"
    return (role.get("administrativeBody") or {}).get("type")


def sync_athens():
    parties = {
        row["id"]: {"id": row["id"], "name": row["name"]}
        for row in fetch("parties") if row["cityId"] == "athens"
    }
    today = datetime.now(ZoneInfo("Europe/Athens")).date().isoformat()
    representatives = {}
    for row in fetch("people"):
        if row["cityId"] != "athens" or not active(row, today, "activeFrom", "activeTo"):
            continue
        roles = [role for role in row["roles"]
                 if active(role, today, "startDate", "endDate")]
        priority = {"mayor": 4, "council": 3, "community": 2, "committee": 1}
        offices = [role for role in roles if office_type(role) in priority]
        if not offices:
            continue
        role = max(offices, key=lambda item: (
            priority[office_type(item)], item["startDate"] or ""
        ))
        body = (role.get("administrativeBody") or {}).get("name")
        title = " · ".join(part for part in (role.get("name"), body) if part)
        # OpenCouncil sometimes stores the faction on a separate, body-less role.
        affiliation = max(
            (item for item in roles if not item["administrativeBodyId"] and item["partyId"]),
            key=lambda item: item["startDate"] or "",
            default={},
        )
        party_id = role["partyId"] or affiliation.get("partyId")
        representatives[row["id"]] = {
            "name": row["name"],
            "party": parties.get(party_id, {}).get("name", "Χωρίς δημοτική παράταξη"),
            "party_id": party_id,
            "role": title,
            "opencouncil_id": row["id"],
            "source_active": True,
        }
    if not parties or not representatives:
        raise ValueError("No Athens groups or representatives found; existing data kept.")

    with db.transaction() as tx:
        people = tx.read(db.PEOPLE)
        known = {p["opencouncil_id"]: p for p in people if p.get("opencouncil_id")}
        for source_id, fields in representatives.items():
            if source_id in known:
                known[source_id].update(fields)
                continue
            people.append(dict(
                fields, id=db.slug(f"athens-{source_id}", people), status="unclaimed",
                description="", statements=[], photo_url="", socials={},
                verification_email="", login_username=None, password_hash=None,
                created_at=db.now(),
            ))
        for source_id in known.keys() - representatives.keys():
            known[source_id]["source_active"] = False
        tx.write(db.PEOPLE, people)
        tx.write(GROUPS, list(parties.values()))
    return len(representatives), len(parties)
