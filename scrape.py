#!/usr/bin/env python3
"""Snapshot field availability for every city in cities.json.

Usage:
  python3 scrape.py            # refresh every city, writing data/<id>.json
  python3 scrape.py menlo-park # refresh one city

Each city needs a PerfectMind "BookMe4FacilityList" booking link, like
https://<something>.perfectmind.com/<org>/Clients/BookMe4FacilityList/List?widgetId=...&calendarId=...
"""
import json
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import server

HERE = Path(__file__).resolve().parent
WEEKS = 8
PACIFIC = timezone(timedelta(hours=-8))  # close enough to pick "today" on the West Coast


def configure(link):
    """Point the server module at one city's PerfectMind booking widget."""
    u = urllib.parse.urlparse(link)
    q = urllib.parse.parse_qs(u.query)
    parts = u.path.strip("/").split("/")
    if "perfectmind.com" not in u.netloc or "Clients" not in parts or not q.get("widgetId") or not q.get("calendarId"):
        raise ValueError("Not a PerfectMind booking link with widgetId and calendarId")
    server.BASE = f"{u.scheme}://{u.netloc}"
    server.ORG = "/" + "/".join(parts[:parts.index("Clients") + 1])
    server.WIDGET_ID = q["widgetId"][0]
    server.CALENDAR_ID = q["calendarId"][0]
    server.site = server.Site()
    server.cache.clear()


def snapshot(city):
    configure(city["bookingLink"])
    facilities = server.fetch_facilities()
    today = datetime.now(PACIFIC).date()
    starts = [(today + timedelta(days=7 * i)).isoformat() for i in range(WEEKS)]
    jobs = [(f, s) for s in starts for f in facilities if f.get("serviceId")]

    def one(job):
        f, s = job
        try:
            week = server.fetch_week(f, s)["days"]
        except Exception as e:
            return s, f["id"], {"error": str(e)}
        return s, f["id"], {d: server.free_ranges(st, int(f["duration"])) for d, st in week.items()}

    weeks = {s: {} for s in starts}
    with ThreadPoolExecutor(server.WORKERS) as pool:
        for s, fid, days in pool.map(one, jobs):
            weeks[s][fid] = days

    keep = ("id", "name", "park", "type", "bookingUrl", "bookAheadDays", "bookingNote")
    return {
        "city": city["name"],
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "facilities": [{k: f.get(k) for k in keep} for f in facilities],
        "weeks": weeks,
    }


def main():
    cities = json.loads((HERE / "cities.json").read_text())
    only = set(sys.argv[1:])
    (HERE / "data").mkdir(exist_ok=True)
    failed = []
    for city in cities:
        if only and city["id"] not in only:
            continue
        try:
            snap = snapshot(city)
            if not snap["facilities"]:
                raise ValueError("no fields found")
        except Exception as e:
            print(f"{city['name']}: FAILED ({e})", file=sys.stderr)
            failed.append(city["name"])
            continue
        out = HERE / "data" / f"{city['id']}.json"
        out.write_text(json.dumps(snap, separators=(",", ":")))
        print(f"{city['name']}: {len(snap['facilities'])} fields", file=sys.stderr)
    if failed and len(failed) == len(only or cities):
        sys.exit(1)


if __name__ == "__main__":
    main()
