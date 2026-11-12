#!/usr/bin/env python3
"""Summarise Tableau logs so an on-call engineer sees the important errors first.

Reads folders, single files and .zip archives (zip members are read in memory,
never extracted). Understands Tableau's JSON log lines (ts/sev/k/v/req/sess),
Apache-style httpd/gateway access logs, and plain-text logs (ERROR/FATAL/Exception).
Standard library only.

Usage:
  python scan_logs.py PATH [PATH ...] [--since "2026-11-12 10:00"] [--until ...]
                      [--grep TEXT] [--req REQUEST_ID] [--top N]
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime

TEXT_EXT = {".txt", ".log", ".json", ".out", ""}
MAX_LINE = 20000
SEV_RANK = {"fatal": 0, "error": 1, "warn": 2, "warning": 2}

TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")
APACHE_TS_RE = re.compile(r"\[(\d{2}/\w{3}/\d{4}):(\d{2}:\d{2}:\d{2})")
HTTP_RE = re.compile(r'"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS) (\S+) HTTP/[\d.]+" (\d{3})')
TEXT_SEV_RE = re.compile(r"\b(FATAL|SEVERE|ERROR|Exception|WARN(?:ING)?)\b")
NORMALISE = [
    (re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"), "<guid>"),
    (re.compile(r"\b[0-9A-Za-z_-]{20,}\b"), "<id>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<hex>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[.,]?\d*"), "<ts>"),
    (re.compile(r"\b\d+(\.\d+)?\b"), "<n>"),
]
MSG_KEYS = ("msg", "message", "error", "error-message", "exception", "what", "reason", "desc", "summary")


def parse_time(text):
    """Turn a timestamp in a log line into a datetime, or None."""
    m = TS_RE.search(text)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    m = APACHE_TS_RE.search(text)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d/%b/%Y %H:%M:%S")
        except ValueError:
            return None
    return None


def parse_arg_time(text):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    sys.exit(f"Could not read time {text!r}; use e.g. '2026-11-12 10:00'")


def signature(text):
    """Collapse ids, numbers and times so repeats of one error group together."""
    text = text.strip()[:300]
    for rx, rep in NORMALISE:
        text = rx.sub(rep, text)
    return re.sub(r"\s+", " ", text)


def message_of(v):
    """Pick the human-readable part of a JSON log payload."""
    if isinstance(v, dict):
        for key in MSG_KEYS:
            if key in v and v[key]:
                val = v[key]
                text = val if isinstance(val, str) else json.dumps(val)[:300]
                code = v.get("code") or v.get("error-code")
                return f"{text} (code {code})" if code else text
        return json.dumps(v, sort_keys=True)[:300]
    return str(v)


def component(name):
    """Service folder (vizqlserver, backgrounder...) or file stem."""
    parts = re.split(r"[\\/]", name)
    for p in reversed(parts[:-1]):
        if p and p.lower() not in ("logs", "log", "tabsvc", "data", "nativeapi"):
            return p
    return re.sub(r"[_.-]?\d.*$", "", os.path.splitext(parts[-1])[0]) or parts[-1]


def iter_sources(paths):
    """Yield (display name, text line iterator) for every log file found."""
    for path in paths:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for f in sorted(files):
                    yield from iter_sources([os.path.join(root, f)])
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = f"{path}!{info.filename}"
                    ext = os.path.splitext(info.filename)[1].lower()
                    if ext == ".zip":
                        data = io.BytesIO(zf.read(info))
                        if zipfile.is_zipfile(data):
                            with zipfile.ZipFile(data) as inner:
                                for i2 in inner.infolist():
                                    if not i2.is_dir() and os.path.splitext(i2.filename)[1].lower() in TEXT_EXT:
                                        yield f"{name}!{i2.filename}", io.TextIOWrapper(inner.open(i2), errors="replace")
                        continue
                    if ext in TEXT_EXT or re.search(r"\.(log|txt)\.\d+$", info.filename):
                        yield name, io.TextIOWrapper(zf.open(info), errors="replace")
        elif os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in TEXT_EXT or re.search(r"\.(log|txt)\.\d+$", path):
                yield path, open(path, errors="replace")
        else:
            print(f"! not found: {path}", file=sys.stderr)


def scan(args):
    since = parse_arg_time(args.since) if args.since else None
    until = parse_arg_time(args.until) if args.until else None
    grep = args.grep.lower() if args.grep else None

    files = 0
    lines_total = 0
    tmin = tmax = None
    sev_by_comp = defaultdict(Counter)
    sigs = {}
    http_5xx = Counter()
    http_status = Counter()
    slow = []
    req_lines = []
    grep_lines = []

    for name, fh in iter_sources(args.paths):
        files += 1
        comp = component(name.split("!")[-1] if "!" in name else name)
        with fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw[:MAX_LINE].rstrip("\n")
                if not line.strip():
                    continue
                lines_total += 1
                rec = None
                if line.startswith("{"):
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        rec = None
                ts = parse_time(rec.get("ts", "")) if isinstance(rec, dict) and isinstance(rec.get("ts"), str) else parse_time(line[:80])
                if ts:
                    if since and ts < since:
                        continue
                    if until and ts > until:
                        continue
                    tmin = ts if tmin is None or ts < tmin else tmin
                    tmax = ts if tmax is None or ts > tmax else tmax
                where = f"{name}:{lineno}"

                if args.req and args.req in line:
                    req_lines.append((ts, where, line[:400]))
                if grep and grep in line.lower():
                    grep_lines.append((ts, where, line[:400]))

                sev = None
                text = None
                if isinstance(rec, dict):
                    sev = str(rec.get("sev", "")).lower()
                    key = rec.get("k", "")
                    text = f"[{key}] {message_of(rec.get('v', ''))}"
                    v = rec.get("v")
                    if isinstance(v, dict) and key in ("end-query", "qp-batch-summary", "end-request", "end-protocol.query"):
                        el = v.get("elapsed") or v.get("elapsed-sum") or v.get("elapsed-ms")
                        try:
                            slow.append((float(el), where, key, rec.get("req", "-")))
                        except (TypeError, ValueError):
                            pass
                else:
                    m = HTTP_RE.search(line)
                    if m:
                        status = int(m.group(3))
                        http_status[status // 100 * 100] += 1
                        if status >= 500:
                            http_5xx[(status, m.group(1), re.sub(r"\?.*", "", m.group(2))[:120])] += 1
                        continue
                    m = TEXT_SEV_RE.search(line)
                    if m:
                        word = m.group(1).lower()
                        sev = "fatal" if word in ("fatal", "severe") else "warn" if word.startswith("warn") else "error"
                        text = line[m.start():]
                if sev in SEV_RANK:
                    sev = "warn" if sev == "warning" else sev
                    sev_by_comp[comp][sev] += 1
                    sig = (sev, comp, signature(text or line))
                    s = sigs.get(sig)
                    if s is None:
                        sigs[sig] = s = {"count": 0, "first": ts, "last": ts, "where": where, "example": (text or line)[:240]}
                    s["count"] += 1
                    if ts:
                        s["first"] = ts if s["first"] is None or ts < s["first"] else s["first"]
                        s["last"] = ts if s["last"] is None or ts > s["last"] else s["last"]

    fmt = lambda t: t.strftime("%Y-%m-%d %H:%M:%S") if t else "?"
    print(f"Scanned {files} files, {lines_total} lines. Time range: {fmt(tmin)} -> {fmt(tmax)}")
    if since or until:
        print(f"Filtered to: {fmt(since)} -> {fmt(until)}")
    if not files:
        print("No log files found.")
        return

    print("\n== Errors and warnings by component ==")
    if not sev_by_comp:
        print("  none found")
    for comp, c in sorted(sev_by_comp.items(), key=lambda kv: (-kv[1]["fatal"], -kv[1]["error"], -kv[1]["warn"])):
        print(f"  {comp:<28} fatal {c['fatal']:>5}  error {c['error']:>6}  warn {c['warn']:>6}")

    print(f"\n== Top {args.top} error signatures (fatal/error first) ==")
    ranked = sorted(sigs.items(), key=lambda kv: (SEV_RANK[kv[0][0]], -kv[1]["count"]))
    shown = [kv for kv in ranked if kv[0][0] != "warn"][: args.top] or ranked[: args.top]
    for (sev, comp, _), s in shown:
        print(f"  {s['count']:>6}x {sev.upper():<5} {comp}  first {fmt(s['first'])}  last {fmt(s['last'])}")
        print(f"          {s['example']}")
        print(f"          at {s['where']}")

    if http_status:
        print("\n== HTTP status (access logs) ==")
        print("  " + "  ".join(f"{k // 100}xx: {v}" for k, v in sorted(http_status.items())))
        for (status, method, url), n in http_5xx.most_common(args.top):
            print(f"  {n:>6}x {status} {method} {url}")

    if slow:
        print("\n== Slowest queries/requests (elapsed as logged) ==")
        for el, where, key, req in sorted(slow, reverse=True)[: min(args.top, 10)]:
            print(f"  {el:>10.3f}  {key:<18} req={req}  at {where}")

    for title, rows in ((f"Lines with request {args.req}", req_lines), (f"Lines containing '{args.grep}'", grep_lines)):
        if rows:
            print(f"\n== {title} ({len(rows)}) ==")
            for ts, where, line in sorted(rows, key=lambda r: r[0] or datetime.min)[:40]:
                print(f"  {fmt(ts)}  {where}\n      {line[:300]}")
            if len(rows) > 40:
                print(f"  ... {len(rows) - 40} more")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="+", help="log file, folder, or .zip (e.g. a ziplogs archive)")
    p.add_argument("--since", help="ignore lines before this time (log's own clock)")
    p.add_argument("--until", help="ignore lines after this time")
    p.add_argument("--grep", help="also list lines containing this text (case-insensitive)")
    p.add_argument("--req", help="also list every line with this request/session/job id")
    p.add_argument("--top", type=int, default=10, help="how many signatures to show (default 10)")
    scan(p.parse_args())


if __name__ == "__main__":
    main()
