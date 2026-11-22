"""Look up public Athens records and news without sending residents' messages."""
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from functools import lru_cache
from hashlib import sha256
from html.parser import HTMLParser
import io
import json
import re
import time
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from .civic_index import normalize, tokens

CITY_ORG = "6013"
DIAVGEIA = "https://diavgeia.gov.gr/opendata"
NEWS = "https://news.google.com/rss/search"
PERSON_NEWS_LIMIT = 5
PUBLISHER_FEED = "https://www.ertnews.gr/tag/dimos-athinaion/feed/"
POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="civic-sources")

# Only these public search terms go to the upstream discovery services.
# Search phrases and stems are separate because the two services index differently.
QUERIES = {
    "Καθαριότητα και απορρίμματα": ("απορρίμματα", "απορριμ αποκομιδ ανακυκλ απορριμματοφ"),
    "Νυχτερινός θόρυβος και ωράριο μουσικής": ("ωράριο μουσικής", "μουσικ ηχορυπ ηχοεντασ"),
    "Θόρυβος και κοινή ησυχία": ("ηχορύπανση", "ηχορυπ θορυβ μουσικ ηχοεντασ"),
    "Κυκλοφορία και στάθμευση": ("στάθμευση", "σταθμευσ κυκλοφορ συγκοινων πεζοδρομ πατιν"),
    "Πάρκα και πράσινο": ("δημοτικό πράσινο", "πρασιν δεντρ φυτευσ κλαδευ παρκο"),
    "Στέγαση": ("στέγαση", "στεγαση στεγαστικ μισθωσ ενοικ"),
    "Δημοτικός φωτισμός": ("δημοτικός φωτισμός", "φωτισμ φωτιστικ ηλεκτροφωτισ"),
    "Δημόσια ασφάλεια": ("παραβατικότητα", "παραβατικ εγκλημα αστυνομευσ"),
    "Αδέσποτα ζώα": ("αδέσποτα", "αδεσποτ φιλοζω στειρωσ"),
    "Παιδικές χαρές": ("παιδικές χαρές", "παιδικεσ χαρεσ|παιδικη χαρα|παιδικων χαρων"),
    "Πεζοδρόμια και προσβασιμότητα": ("προσβασιμότητα", "προσβασιμ πεζοδρομ αμαξιδ ραμπ"),
    "Σεισμοί και αντισεισμική προστασία": ("αντισεισμικός έλεγχος", "αντισεισμ σεισμ"),
}
ADA = re.compile(r"[A-ZΑ-Ω0-9]{5,12}-[A-ZΑ-Ω0-9]{2,5}")
ADA_QUERY = re.compile(r"\b(?:ΑΔΑ|ADA)\s*[:：]?\s*(" + ADA.pattern + r")\b", re.IGNORECASE)
APPROVAL = re.compile(r"\b(?:εγκρινει|αποφασιζει|αποφασιζουμε|εγκρινεται)\b")
COMPLETION = re.compile(r"οριστικ\w* παραλαβ|βεβαιωση καλησ εκτελεσησ")
ATHENS = ZoneInfo("Europe/Athens")


class FeedText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(text):
    parser = FeedText()
    parser.feed(text or "")
    return " ".join(" ".join(parser.parts).split())


def get(url, limit, timeout=4):
    request = Request(url, headers={"User-Agent": "CiviConnect/1.0"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Source exceeded its download limit.")
    return body


def dated(timestamp):
    return datetime.fromtimestamp(timestamp / 1000, ATHENS).date().isoformat()


def related(text, stems):
    body = normalize(text)
    return any(re.search(r"\b" + re.escape(stem), body) for stem in stems)


def decision_excerpt(url, stems, exact):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(get(url, 3_000_000)))
    pages = []
    for page in reader.pages[:3]:
        text = " ".join((page.extract_text() or "").split())
        if text:
            pages.append(text)
    for text in reversed(pages):
        normalized = normalize(text)
        action = APPROVAL.search(normalized)
        if action and (exact or related(text, stems)):
            start = max(0, action.start() - 20)
            return text[start:start + 420]
    for text in pages:
        for stem in stems:
            position = normalize(text).find(stem)
            if position >= 0:
                return text[max(0, position - 80):position + 340]
    return pages[0][:420] if pages and exact else ""


@lru_cache(maxsize=64)
def decisions(term, stems, start, end, ada, bucket):
    if ada:
        result = json.loads(get(f"{DIAVGEIA}/decisions/{quote(ada)}", 750_000))
        records = [result]
    else:
        args = urlencode(dict(org=CITY_ORG, term=term, size=12, from_date=start,
                              to_date=end, from_issue_date=start, to_issue_date=end))
        records = json.loads(get(f"{DIAVGEIA}/search?{args}", 900_000))["decisions"]
    candidates = [d for d in records if d.get("organizationId") == CITY_ORG
                  and d.get("status") == "PUBLISHED" and not d.get("privateData")
                  and ADA.fullmatch(d.get("ada") or "") and d.get("issueDate")
                  and (ada or start <= dated(d["issueDate"]) <= end)]
    candidates.sort(key=lambda d: related(d.get("subject") or "", stems), reverse=True)
    output = []
    for index, decision in enumerate(candidates[:5]):
        title = plain(decision.get("subject"))
        public_id = decision["ada"]
        link = f"https://diavgeia.gov.gr/doc/{quote(public_id)}"
        passage = ""
        if index == 0:
            try:
                passage = decision_excerpt(link, stems, bool(ada))
            except Exception:
                pass  # Scans, oversized documents, or unavailable PDFs still have metadata.
        if not (ada or related(title, stems) or passage):
            continue
        operative = normalize(passage)
        output.append(dict(
            id="ada:" + public_id, kind="decision", title=title[:300],
            text=passage or title[:300], date=dated(decision["issueDate"]), source=link,
            publisher="Διαύγεια · Δήμος Αθηναίων", speaker="", party="",
            scope="document" if passage else "metadata", ada=public_id,
            approval=bool(APPROVAL.search(operative)),
            completion=bool(APPROVAL.search(operative) and COMPLETION.search(operative)),
        ))
    return output


def feed_items(xml, start, end):
    for item in ElementTree.fromstring(xml).findall("./channel/item"):
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (ValueError, TypeError):
            continue
        link = item.findtext("link") or ""
        parts = urlsplit(link)
        if parts.scheme != "https" or not parts.hostname or not start <= published.date().isoformat() <= end:
            continue
        title = plain(item.findtext("title"))
        if not title:
            continue
        yield item, published, link, title


def google_news_items(phrase, start, end):
    query = urlencode(dict(q=phrase, hl="el", gl="GR", ceid="GR:el"))
    for item, published, link, title in feed_items(get(f"{NEWS}?{query}", 800_000), start, end):
        publisher = plain(item.findtext("source"))
        suffix = " - " + publisher
        if publisher and title.endswith(suffix):
            title = title[:-len(suffix)]
        yield published, dict(title=title, source=link, date=published.date().isoformat(), publisher=publisher)


@lru_cache(maxsize=48)
def headlines(term, stems, start, end, bucket):
    return [dict(article, title=article["title"][:240])
            for _, article in google_news_items(f'"Δήμος Αθηναίων" "{term}"', start, end)
            if related(article["title"], stems)][:12]


@lru_cache(maxsize=256)
def person_headlines(name, bucket):
    name = " ".join(re.sub(r'\([^)]*\)|"', "", name).split())
    if not name:
        return []
    today = datetime.now(ATHENS).date()
    start = (today - timedelta(days=29)).isoformat()
    articles = google_news_items(f'"{name}" when:30d', start, today.isoformat())
    newest = sorted(articles, key=lambda item: item[0].timestamp(), reverse=True)
    return [dict(article, title=article["title"][:240])
            for article in distinct_stories(article for _, article in newest)[:PERSON_NEWS_LIMIT]]


@lru_cache(maxsize=2)
def publisher_feed(bucket):
    return get(PUBLISHER_FEED, 2_500_000)


def reporting(stems, start, end, bucket):
    output = []
    for item, published, link, title in feed_items(publisher_feed(bucket), start, end):
        text = plain(item.findtext("description"))
        context = normalize(title + " " + text)
        if "αθην" not in context or not related(context, stems) or len(text) < 60:
            continue
        output.append(dict(
            id="report:" + sha256(link.encode()).hexdigest()[:20], kind="report",
            title=title[:240], text=text[:380], date=published.date().isoformat(), source=link,
            publisher="ΕΡΤ", speaker="", party="", scope="publisher_excerpt",
        ))
    return output[:3]


def distinct_stories(items):
    seen = []
    output = []
    for item in items:
        terms = set(tokens(item["title"]))
        if any(item["source"] == url or (terms and len(terms & old) / len(terms | old) >= .72)
               for old, url in seen):
            continue
        seen.append((terms, item["source"]))
        output.append(item)
    return output


def lookup(label, question, start, end, public_title=""):
    mapping = [QUERIES[topic] for topic in label.split(" / ") if topic in QUERIES][:2]
    if public_title and len(mapping) < 2:
        public_title = " ".join(public_title.replace('"', "").split())[:110]
        exact_words = [word for word in tokens(public_title) if len(word) >= 5]
        if exact_words:
            mapping.append((public_title, "|".join(exact_words)))
    ref = ADA_QUERY.search(question.upper())
    ada = ref[1] if ref else ""
    if not mapping and not ada:
        return [], [], {}

    bucket = int(time.monotonic() // 900)
    def parse_stems(values):
        return tuple(values.split("|") if "|" in values else values.split())

    stems = tuple(dict.fromkeys(stem for _, values in mapping for stem in parse_stems(values)))
    jobs = {}
    if ada:
        jobs[POOL.submit(decisions, "", stems, start, end, ada, bucket)] = "decision"
    else:
        for term, values in mapping:
            jobs[POOL.submit(decisions, term, parse_stems(values), start, end, "", bucket)] = "decision"
    for term, values in mapping:
        jobs[POOL.submit(headlines, term, parse_stems(values), start, end, bucket)] = "headlines"
    if stems:
        jobs[POOL.submit(reporting, stems, start, end, bucket)] = "report"
    complete, pending = wait(jobs, timeout=8)
    for future in pending:
        future.cancel()
    grouped = {kind: [] for kind in set(jobs.values())}
    coverage = {kind: "unavailable" for kind in grouped}
    for future, kind in jobs.items():
        if future in complete:
            try:
                grouped[kind].extend(future.result())
                coverage[kind] = "searched"
            except (OSError, ValueError, KeyError, ElementTree.ParseError):
                continue
    official = list({row["id"]: row for row in grouped.get("decision", [])}.values())[:5]
    reports = distinct_stories(grouped.get("report", []))
    titles = distinct_stories(reports + grouped.get("headlines", []))[len(reports):][:4]
    return official + reports, titles, coverage
