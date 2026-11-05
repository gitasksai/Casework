"""Turn a case captured by the Chrome extension into a reviewable import plan.

The extension sends what it could read from the Salesforce case page:

    {
      "caseNumber": "480570091",
      "userName": "Sathishkumar Ashok",          # the engineer (optional)
      "capturedAt": "2026-11-05T10:15:00Z",
      "fields": [{"label": "Status", "value": "Working"}, ...],
      "feed":   [{"author": "...", "timeText": "20h ago", "timeTitle": "...", "text": "..."}, ...]
    }

`build_plan()` maps the fields onto Casework's case fields and sorts every feed item into
one of the case tabs, or marks it ignored (follow-ups, acknowledgements, automation...).
Everything here is pure Python so it can be unit-tested and tuned without a browser.
"""

import hashlib
import re
from datetime import date, datetime, timedelta, timezone

from .models import STATUSES

# --------------------------------------------------------------------------- tunables
# Edit these lists to tune what gets ignored / how items are classified.

AUTOMATION_AUTHORS = [
    "automation", "system", "auto-response", "autoresponse", "no-reply", "noreply",
    "do not reply", "workflow", "process builder", "integration user",
]
AUTOMATION_TEXT = [
    r"system generated feed", r"this is an automated (message|response|email)",
    r"do not reply to this (email|message)", r"auto[- ]?generated",
]
STATUS_CHANGE_TEXT = [
    r"changed (the )?(status|sub-status|owner|priority|severity)", r"\bstatus changed\b",
    r"changed .+ from .+ to ", r"\bcreated this case\b", r"\bowner changed\b",
]
FOLLOW_UP_TEXT = [
    r"\bjust (a )?(quick |gentle )?(follow(ing)?[- ]?up|checking in)",
    r"\bfollow(ing)?[- ]?up on\b", r"\b(gentle|friendly|quick) (reminder|follow[- ]?up)\b",
    r"\bany updates?\b", r"\bchecking in\b", r"\bdid you (get|have) (a|the) chance\b",
    r"\b(have not|haven'?t|not) heard back\b", r"\bawaiting your (reply|response|update)\b",
    r"\bplease (provide|share) (an|the|your) update\b", r"\bwanted to check (if|whether)\b",
    r"\b(will|going to) (close|archive) (this|the) case\b", r"\bcase (will be|has been) (auto[- ]?)?closed\b",
    r"\bclosing (this|the) case\b", r"\bis it ok(ay)? (if we|to) close\b",
]
ACKNOWLEDGEMENT_TEXT = [
    r"\bthank(s| you)( very much| so much)? for (the |your )?(update|reply|response|sharing|details|"
    r"information|info|logs|files|confirmation|time|patience)",
    r"\bI will (check|review|look into|analy[sz]e|go through|get back|update you)",
    r"\bwe will (check|review|look into|analy[sz]e|get back|update you)",
    r"\b(noted|received|got it|sounds good|works for me)\b",
    r"\b(I|we) (have )?received (the|your)\b",
]
MEETING_TEXT = [
    r"\b(remote|screen[- ]?share|zoom|webex|teams|gotomeeting|google meet) (session|call|meeting)\b",
    r"\bmeeting (summary|notes|minutes|recap)\b", r"\bcall (summary|notes|recap)\b",
    r"\bas discussed (on|during|in) (the|our) (call|meeting|session)\b",
    r"\b(on|during) (the|our) (call|meeting|session) (today|yesterday|we)\b",
    r"\battendees\s*:", r"\bsummary of (the|our|today'?s) (call|meeting|session)\b",
]
TECHNICAL_TEXT = [
    r"\blogs?\b", r"\berror", r"\bexception", r"\bstack ?trace", r"\brepro(duc\w*)?\b",
    r"\btest(ed|ing)?\b", r"\btried\b", r"\bworkaround", r"\broot cause", r"\bbug\b",
    r"\bdebug", r"\bconfig(uration)?\b", r"\bdriver", r"\bsteps?\b", r"\bfiddler\b", r"\bhar\b",
    r"\bsaml\b", r"\bsso\b", r"\bcertificate", r"\bproxy\b", r"\bfirewall\b", r"\bregistry\b",
    r"\bversion\b", r"\bupgrade", r"\bpatch", r"\bconnection\b", r"\btimeout\b", r"\bcrash",
    r"\bqueries?\b", r"\bperformance\b", r"\bkb\d+|\bknowledge article\b", r"\bescalat",
]
SIGN_OFF = re.compile(
    r"^(best|kind|warm|warmest)?\s*regards\b.*$|^thanks?( (and|&) regards)?[,!.]?$|^thank you[,!.]?$|"
    r"^many thanks[,!.]?$|^cheers[,!.]?$|^sincerely[,!.]?$|^br[,.]?$|^--\s*$|^__+$",
    re.I,
)
QUOTE_START = re.compile(
    r"^on .{5,200} wrote:$|^-{2,}\s*original message|^-{2,}\s*forwarded message|"
    r"^from:\s.+|^sent:\s.+|^\s*>|^ref:[_!]|^thread::",
    re.I,
)
GREETING = re.compile(r"^(hi|hello|hey|dear|good (morning|afternoon|evening))\b[^.!?]{0,60}[,!.]?$", re.I)
UI_NOISE = re.compile(
    r"^(comment|like|liked|share|reply|reply all|forward|more|less|show more|show less|see more|"
    r"collapse post|expand post|edit|delete|bookmark|view more|view all|copy link|"
    r"actions for this (post|email|item).*|\d+ (comments?|likes?|views?)|write a comment\.*|"
    r"to: (all|internal|all with access)|internal|public|email|post|you|\.\.\.|·)$",
    re.I,
)
TIME_TEXT = re.compile(
    r"^(\d+\s*(s|sec|m|min|mins|h|hr|hrs|d|day|days|w|wk|wks)\s*ago|just now|yesterday.*|today.*|"
    r"[A-Z][a-z]+ \d{1,2},? \d{4}.*|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}.*)$",
    re.I,
)

FIELD_ALIASES = {
    "case_number": ["case number", "case no", "case #", "case id"],
    "title": ["subject", "case subject", "title"],
    "problem_description": ["description", "case description", "problem description", "issue description"],
    "status": ["status", "case status"],
    "sub_status": ["sub-status", "sub status", "substatus"],
    "severity": ["severity", "priority", "case severity", "case priority"],
    "product": ["product & topic", "product and topic", "product", "product name", "product/topic"],
    "product_feature": ["product feature", "feature", "topic", "component"],
    "version": ["version", "product version", "software version", "tableau version", "release"],
    "operating_system": ["operating system", "os", "platform", "os version", "operating system version"],
    "customer": ["account name", "account", "company", "customer", "organization"],
    "opened_on": ["date/time opened", "date time opened", "opened date", "date opened",
                  "created date", "case created date", "opened"],
}
CASE_FIELD_LABELS = {
    "case_number": "Case number", "title": "Title", "customer": "Customer", "product": "Product",
    "version": "Version", "operating_system": "Operating system", "severity": "Severity",
    "status": "Status", "opened_on": "Opened on", "problem_description": "Problem description",
}

CATEGORIES = ["initial_response", "scoping", "troubleshooting", "meeting", "note"]


def _any(patterns, text):
    return any(re.search(p, text, re.I) for p in patterns)


# --------------------------------------------------------------------------- fields

def _norm_label(label):
    label = re.sub(r"[*:]+", " ", label or "")
    label = re.sub(r"\b(help|info|edit)\b.*$", "", label, flags=re.I)
    return re.sub(r"\s+", " ", label).strip().lower()


def _clean_value(value):
    lines = [ln.strip() for ln in (value or "").splitlines()]
    lines = [ln for ln in lines if ln and not re.match(r"^(edit|change|open|help|view|preview)\b.{0,60}$", ln, re.I)]
    return "\n".join(lines).strip()


def map_fields(fields):
    """Map Salesforce label/value pairs onto Casework field names. First match wins."""
    by_label = {}
    for f in fields or []:
        label, value = _norm_label(f.get("label")), _clean_value(f.get("value"))
        if label and value and label not in by_label:
            by_label[label] = value
    mapped = {}
    for name, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in by_label:
                mapped[name] = by_label[alias]
                break
    return mapped, by_label


def map_status(value):
    v = (value or "").strip().lower()
    for s in STATUSES:
        if v == s.lower():
            return s
    if not v:
        return None
    if v in ("new", "open", "unassigned"):
        return "New"
    if "customer" in v or "pending" in v or "waiting" in v or "on hold" in v:
        return "Waiting on Customer"
    if "closed" in v:
        return "Closed"
    if "resolved" in v or "solution" in v or "solved" in v:
        return "Resolved"
    if "swarm" in v:
        return "Swarm"
    if "investigation" in v:
        return "Structured Investigation"
    return "In Progress"


def map_severity(value):
    v = (value or "").lower()
    if not v:
        return None
    if re.search(r"\b1\b|critical|urgent|sev ?1|p1", v):
        return "1 - Critical"
    if re.search(r"\b2\b|high|sev ?2|p2", v):
        return "2 - High"
    if re.search(r"\b3\b|medium|normal|sev ?3|p3", v):
        return "3 - Medium"
    if re.search(r"\b4\b|low|sev ?4|p4", v):
        return "4 - Low"
    return None


VERSION_RE = re.compile(
    r"\b(?:version|ver\.?|release)\s*[:#-]?\s*(\d{1,4}(?:\.\d+){1,3})\b|\b(20\d\d\.\d(?:\.\d+)?)\b", re.I
)
OS_RE = re.compile(
    r"\b(windows server \d{4}(?: r2)?|windows (?:10|11|7|8\.1)|mac ?os(?: x)?(?: \d+(?:\.\d+)*| [a-z]+)?|"
    r"os x [\d.]+|ubuntu(?: \d+\.\d+)?|rhel ?\d*(?:\.\d+)?|red hat(?: enterprise linux)?(?: \d+(?:\.\d+)?)?|"
    r"centos(?: \d+)?|amazon linux(?: \d+)?|linux|ios \d+|android \d+)\b",
    re.I,
)


def _guess_version(*texts):
    for t in texts:
        m = VERSION_RE.search(t or "")
        if m:
            return m.group(1) or m.group(2)
    return None


def _guess_os(*texts):
    for t in texts:
        m = OS_RE.search(t or "")
        if m:
            return m.group(1)
    return None


MONTH_FIRST = ["%m/%d/%Y, %I:%M %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y, %H:%M", "%m/%d/%Y %H:%M", "%m/%d/%Y"]
DAY_FIRST = ["%d/%m/%Y, %I:%M %p", "%d/%m/%Y %I:%M %p", "%d/%m/%Y, %H:%M", "%d/%m/%Y %H:%M", "%d/%m/%Y",
             "%d.%m.%Y, %H:%M", "%d.%m.%Y %H:%M", "%d.%m.%Y"]
DATE_FORMATS = [
    "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%B %d, %Y at %I:%M %p",
    "%B %d, %Y, %I:%M %p", "%B %d, %Y %I:%M %p", "%b %d, %Y, %I:%M %p", "%b %d, %Y at %I:%M %p",
    "%B %d, %Y", "%b %d, %Y", "%d %B %Y at %H:%M", "%d %b %Y, %H:%M", "%d %B %Y", "%d %b %Y",
    "%d-%b-%Y %H:%M", "%d-%b-%Y",
]


def parse_datetime(text, now, day_first=False):
    """Parse an absolute or relative Salesforce timestamp. Returns naive local datetime or None.

    `day_first` decides how 2/11/2026 is read (see detect_day_first)."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"\s*\((GMT|UTC)[^)]*\)$", "", t)
    t = re.sub(r"\s+(GMT|UTC|[A-Z]{2,4}T)([+-]\d{1,2}(:?\d{2})?)?$", "", t)
    if not t:
        return None
    m = re.match(r"^(\d+)\s*(s|sec|secs|m|min|mins|h|hr|hrs|d|day|days|w|wk|wks)\s*ago$", t, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}[unit[0]]
        return now - timedelta(**{delta: n})
    if t.lower() == "just now":
        return now
    m = re.match(r"^(today|yesterday)(?: at)? (\d{1,2}:\d{2}(?: ?[AP]M)?)$", t, re.I)
    if m:
        base = now.date() - timedelta(days=1 if m.group(1).lower() == "yesterday" else 0)
        clock = m.group(2).upper().replace(" ", "")
        for fmt in ("%I:%M%p", "%H:%M"):
            try:
                return datetime.combine(base, datetime.strptime(clock, fmt).time())
            except ValueError:
                pass
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        pass
    numeric = (DAY_FIRST + MONTH_FIRST) if day_first else (MONTH_FIRST + DAY_FIRST)
    for fmt in numeric + DATE_FORMATS:
        try:
            parsed = datetime.strptime(t, fmt)
        except ValueError:
            continue
        # Something that already happened can't be in the future: try day and month swapped.
        if fmt in numeric and parsed > now + timedelta(days=1) and parsed.day <= 12:
            swapped = parsed.replace(month=parsed.day, day=parsed.month)
            if swapped <= now + timedelta(days=1):
                return swapped
        return parsed
    return None


NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b")
RELATIVE = re.compile(r"^\d+\s*[a-z]+\s*ago$|^(today|yesterday)\b", re.I)


def detect_day_first(payload, now):
    """Work out whether this Salesforce shows dates as day/month or month/day."""
    texts = [f.get("value") or "" for f in payload.get("fields") or []]
    texts += [i.get("timeTitle") or "" for i in payload.get("feed") or []]
    for t in texts:
        for a, b, _ in NUMERIC_DATE.findall(t):
            if int(a) > 12 >= int(b):
                return True
            if int(b) > 12 >= int(a):
                return False
    # Compare each post's exact date with its "3d ago" label: only one reading will agree.
    votes = 0
    for i in payload.get("feed") or []:
        rel, title = i.get("timeText") or "", i.get("timeTitle") or ""
        if not (RELATIVE.match(rel.strip()) and NUMERIC_DATE.search(title)):
            continue
        approx = parse_datetime(rel, now)
        md, dm = parse_datetime(title, now, False), parse_datetime(title, now, True)
        if approx and md and dm and md != dm:
            votes += 1 if abs(dm - approx) < abs(md - approx) else -1
    return votes > 0


# --------------------------------------------------------------------------- feed items

def _lines(text):
    return [re.sub(r"[ \t ]+", " ", ln).strip() for ln in (text or "").replace("\r", "").split("\n")]


def strip_noise(text, author=None):
    """Remove feed chrome (author, 'To: All', timestamps, Like/Comment buttons) from an item's text."""
    out = []
    a = (author or "").strip().lower()
    for i, ln in enumerate(_lines(text)):
        if not ln:
            out.append("")
            continue
        if UI_NOISE.match(ln) or (a and ln.lower() == a and i < 4) or (i < 6 and TIME_TEXT.match(ln)):
            continue
        out.append(ln)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_email_header(text):
    """If the item is an email, return (headers dict, body). Otherwise ({}, text)."""
    lines = text.split("\n")
    headers, i = {}, 0
    while i < len(lines) and i < 12:
        m = re.match(r"^(from|to|cc|bcc|subject|sent|date)\s*:\s*(.*)$", lines[i], re.I)
        if m:
            headers[m.group(1).lower()] = m.group(2).strip()
        elif lines[i].strip() and headers:
            break
        i += 1
    if "from" in headers or "subject" in headers:
        return headers, "\n".join(lines[i:]).strip()
    return {}, text


def clean_body(text):
    """Drop greeting, quoted earlier messages and the signature, keeping the actual message."""
    kept = []
    for ln in text.split("\n"):
        s = ln.strip()
        if kept and QUOTE_START.match(s):
            break
        if s.startswith(">"):
            continue
        if SIGN_OFF.match(s) and any(k.strip() for k in kept):
            break
        kept.append(ln)
    while kept and (not kept[0].strip() or GREETING.match(kept[0].strip())):
        kept.pop(0)
    body = "\n".join(kept).strip()
    return re.sub(r"\n{3,}", "\n\n", body)


def extract_questions(text):
    qs = []
    asks = re.search(r"\b(please (provide|confirm|share|send|let (me|us) know|check)|could you|can you)\b", text, re.I)
    for ln in text.split("\n"):
        s = ln.strip()
        if len(s) < 8:
            continue
        if s.endswith("?") or (asks and re.match(r"^(\d+[.)]|[-*•])\s+\S", s)):
            qs.append(s)
    return qs


def _words(text):
    return len(re.findall(r"\w+", text))


def item_key(item):
    raw = "|".join([
        (item.get("author") or "").strip().lower(),
        (item.get("timeTitle") or item.get("timeText") or "").strip().lower(),
        re.sub(r"\s+", " ", (item.get("text") or "")).strip()[:400].lower(),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _title(body, fallback):
    first = next((ln.strip() for ln in body.split("\n") if ln.strip()), "")
    first = re.sub(r"\s+", " ", first)
    if not first:
        return fallback
    return first if len(first) <= 80 else first[:77].rsplit(" ", 1)[0] + "..."


def classify_item(raw, engineer, now, day_first=False):
    """Analyse one feed item. Returns a dict describing it and why it is kept or ignored."""
    author = (raw.get("author") or "").strip()
    full = raw.get("text") or ""
    visibility = None
    m = re.search(r"^\s*to:\s*(all with access|all|internal)\s*$", full, re.I | re.M)
    if m:
        visibility = "internal" if m.group(1).lower() == "internal" else "public"
    text = strip_noise(full, author)
    if not author:
        first = next((ln for ln in text.split("\n") if ln.strip()), "")
        if 2 <= len(first.split()) <= 5 and not first.endswith((".", "?", ":")):
            author, text = first.strip(), text.split("\n", 1)[1] if "\n" in text else ""
    headers, body = split_email_header(text)
    kind = "email" if headers else "post"
    if headers.get("from") and not author:
        author = re.sub(r"<.*?>", "", headers["from"]).strip()
    clean = clean_body(body)
    when = (parse_datetime(raw.get("timeTitle"), now, day_first) or parse_datetime(raw.get("timeText"), now, day_first))

    a = author.lower()
    if any(k in a for k in AUTOMATION_AUTHORS):
        direction = "system"
    elif engineer and (a == engineer.lower() or engineer.lower() in a
                       or (headers.get("from") and engineer.lower() in headers["from"].lower())):
        direction = "outbound"
    else:
        direction = "inbound"

    item = {
        "key": item_key(raw), "author": author or "Unknown", "when": when, "kind": kind,
        "visibility": visibility, "direction": direction, "subject": headers.get("subject"),
        "clean": clean, "words": _words(clean), "include": True, "reason": None,
        "category": "note", "title": None, "question": None, "response": None, "consumed_by": None,
    }

    def ignore(reason):
        item.update(include=False, reason=reason)
        return item

    if direction == "system" or _any(AUTOMATION_TEXT, full):
        return ignore("Automated / system message")
    if _any(STATUS_CHANGE_TEXT, clean) and item["words"] < 40:
        return ignore("Status or field change")
    if item["words"] < 6:
        return ignore("Too short to be useful")
    if item["words"] < 80 and _any(FOLLOW_UP_TEXT, clean):
        return ignore("Follow-up / reminder")
    if item["words"] < 60 and _any(ACKNOWLEDGEMENT_TEXT, clean) and not extract_questions(clean):
        return ignore("Acknowledgement with no new information")

    questions = extract_questions(clean)
    if _any(MEETING_TEXT, clean):
        item.update(category="meeting", title=_title(clean, "Meeting"))
    elif direction == "outbound" and questions:
        item.update(category="scoping", question="\n".join(questions))
    elif direction == "outbound" and visibility == "internal":
        item.update(category="troubleshooting" if _any(TECHNICAL_TEXT, clean) else "note",
                    title=_title(clean, "Internal note"))
    elif direction == "outbound" and _any(TECHNICAL_TEXT, clean):
        item.update(category="troubleshooting", title=_title(clean, "Troubleshooting update"))
    elif direction == "inbound":
        item.update(category="note", title=f"Customer update from {author or 'customer'}")
    else:
        item.update(category="note", title=_title(clean, "Update"))
    if questions:
        item["question"] = "\n".join(questions)
    return item


def build_plan(payload, already_imported=frozenset(), now=None):
    """Full import plan: mapped case fields + every feed item classified, oldest first."""
    now = now or datetime.now()
    # Relative times ("20h ago") are relative to when the page was captured, not to now.
    now = parse_datetime(payload.get("capturedAt") or "", now) or now

    day_first = detect_day_first(payload, now)
    mapped, raw_fields = map_fields(payload.get("fields"))
    engineer = (payload.get("userName") or "").strip() or None
    owner = raw_fields.get("case owner") or raw_fields.get("owner") or raw_fields.get("owner name")
    if not engineer and owner:
        engineer = owner.split("\n")[0].strip()

    case_number = (payload.get("caseNumber") or mapped.get("case_number") or "").strip()
    if not case_number:
        m = re.search(r"\b(\d{5,})\b", payload.get("title") or "")
        case_number = m.group(1) if m else ""

    product = mapped.get("product")
    if product and mapped.get("product_feature"):
        product = f"{product} / {mapped['product_feature']}"
    elif not product:
        product = mapped.get("product_feature")
    description = mapped.get("problem_description")
    opened = parse_datetime(mapped.get("opened_on"), now, day_first)

    case = {
        "case_number": case_number or None,
        "title": mapped.get("title"),
        "customer": (mapped.get("customer") or "").split("\n")[0] or None,
        "product": product,
        "version": mapped.get("version") or _guess_version(description, mapped.get("title")),
        "operating_system": mapped.get("operating_system") or _guess_os(description, mapped.get("title")),
        "severity": map_severity(mapped.get("severity")),
        "status": map_status(mapped.get("status")),
        "opened_on": opened.date() if opened else None,
        "problem_description": description,
    }

    # Salesforce shows newest first; reverse so ties keep chronological order, then sort by time.
    raw_items = list(reversed(payload.get("feed") or []))
    items = [classify_item(r, engineer, now, day_first) for r in raw_items]
    items.sort(key=lambda i: i["when"] or datetime.max)

    seen = set()
    for it in items:
        if it["key"] in seen:
            it.update(include=False, reason="Duplicate of another item")
        seen.add(it["key"])
        if it["key"] in already_imported:
            it.update(include=False, reason="Already imported", already=True)

    # First substantive outbound message becomes the initial response.
    first_out = next((i for i in items if i["include"] and i["direction"] == "outbound"
                      and i["visibility"] != "internal" and i["category"] != "meeting"), None)
    if first_out:
        first_out.update(category="initial_response", title=first_out["subject"] or "Initial response")

    # Pair each set of scoping questions with the customer's next reply.
    for idx, it in enumerate(items):
        if not (it["include"] and it["question"] and it["category"] in ("scoping", "initial_response")):
            continue
        for nxt in items[idx + 1:]:
            if nxt["direction"] == "outbound" and nxt["include"]:
                break
            if nxt["direction"] == "inbound" and nxt["include"] and not nxt["consumed_by"]:
                it["response"] = nxt["clean"]
                nxt.update(include=False, consumed_by=it["key"],
                           reason="Used as the answer to the scoping questions above")
                break

    return {
        "case": case,
        "engineer": engineer,
        "items": items,
        "raw_fields": raw_fields,
        "warnings": list(payload.get("warnings") or []),
        "counts": {
            "total": len(items),
            "included": sum(1 for i in items if i["include"]),
            "ignored": sum(1 for i in items if not i["include"]),
        },
    }
