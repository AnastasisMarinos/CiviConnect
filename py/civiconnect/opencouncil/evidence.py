"""Build the local Athens council evidence index from public OpenCouncil records."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import re
from urllib.parse import quote
from urllib.request import urlopen

from .. import storage as db
from . import directory as oc

INDEX = "athens_1y_statements.json"
ENTITIES = "athens_entities.json"


def window():
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=365)).isoformat(), today.isoformat()


def evidence_for(meeting):
    mid = meeting["id"]
    with urlopen(oc.BASE + "meetings/" + quote(mid, safe=""), timeout=25) as response:
        detail = json.load(response)
    if detail["meeting"]["cityId"] != "athens" or detail["meeting"].get("closedToPublic"):
        return []
    date = meeting["dateTime"][:10]
    subjects = {s["id"]: s for s in detail["subjects"] if not s.get("withdrawn")}
    people = {p["id"]: p for p in detail["people"]}
    parties = {p["id"]: p["name"] for p in detail["parties"]}

    def record(key, subject, pid, text, kind):
        person = people.get(pid)
        if not person or not text.strip():
            return None
        roles = [r for r in person["roles"] if r.get("partyId") and
                 oc.active(r, date, "startDate", "endDate")]
        role = max(roles, key=lambda r: r.get("startDate") or "", default={})
        sid = subject.get("id")
        source = f"https://opencouncil.gr/athens/{quote(mid, safe='')}"
        return dict(id=key, meeting_id=mid, subject_id=sid, date=date, person_id=pid,
                    speaker=person["name"], party=parties.get(role.get("partyId"), ""),
                    title=subject.get("name") or "", text=" ".join(text.split()),
                    kind=kind, source=source + (f"/subjects/{quote(sid, safe='')}" if sid else ""))

    rows = []
    summarized = set()
    for subject in subjects.values():
        introducer = subject.get("introducedBy")
        pid = introducer.get("id") if isinstance(introducer, dict) else subject.get("personId")
        if pid:
            rows.append(record("subject:" + subject["id"], subject, pid,
                               subject.get("description") or subject["name"], "introduced"))
        if not detail.get("transcriptHiddenForReview"):
            for contribution in subject.get("contributions") or []:
                speaker = contribution.get("speakerId")
                summary = re.sub(r"\[([^\]]+)\]\(REF:[^)]+\)", r"\1", contribution.get("text") or "")
                row = record("summary:" + contribution["id"], subject, speaker, summary, "summary")
                if row:
                    summarized.add((subject["id"], speaker))
                    rows.append(row)

    if not detail.get("transcriptHiddenForReview"):
        for segment in detail.get("transcript", []):
            pid = (segment.get("speakerTag") or {}).get("personId")
            if pid not in people:
                continue
            # Keep adjacent utterances on the same subject together, without mixing speakers.
            groups = defaultdict(list)
            for utterance in segment.get("utterances", []):
                sid = utterance.get("discussionSubjectId")
                if utterance.get("text") and not utterance.get("uncertain"):
                    groups[sid].append(utterance["text"])
            for sid, turns in groups.items():
                if (sid and sid not in subjects) or (sid, pid) in summarized:
                    continue
                rows.append(record(f"{segment['id']}:{sid or ''}", subjects.get(sid, {}), pid,
                                   " ".join(turns), "statement"))
    return [row for row in rows if row]


def sync_evidence():
    start, end = window()
    meetings = [m for m in oc.fetch("meetings")
                if start <= m["dateTime"][:10] <= end
                and m.get("released") and not m.get("closedToPublic")
                and m.get("scheduleStatus") != "cancelled"]
    if not meetings:
        raise RuntimeError("OpenCouncil returned no public meetings within the date window.")
    people = {p["id"]: {"name": p["name"], "roles": [
        {k: role.get(k) for k in ("partyId", "name", "startDate", "endDate")}
        for role in p["roles"]
    ]} for p in oc.fetch("people")}
    parties = {p["id"]: p["name"] for p in oc.fetch("parties")}
    # Fetch one detail per meeting: it already contains subjects and transcript turns.
    with ThreadPoolExecutor(max_workers=3) as pool:
        by_meeting = list(pool.map(evidence_for, meetings))
    records = {row["id"]: row for rows in by_meeting for row in rows}
    if not records:
        raise RuntimeError("OpenCouncil returned no attributed evidence; existing index kept.")
    with db.transaction() as tx:
        tx.write(ENTITIES, {"people": people, "parties": parties})
        tx.write(INDEX, sorted(records.values(), key=lambda r: (r["date"], r["id"]), reverse=True))
    return len(records), len(meetings)
