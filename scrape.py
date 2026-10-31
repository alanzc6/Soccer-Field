#!/usr/bin/env python3
"""Snapshot field availability for every city in cities.json.

Usage:
  python3 scrape.py            # refresh every city, writing data/<id>.json
  python3 scrape.py menlo-park # refresh one city

Each city's bookingLink picks the reader:
  PerfectMind: https://<something>.perfectmind.com/<org>/Clients/BookMe4FacilityList/List?widgetId=...&calendarId=...
  ActiveNet:   https://anc.apm.activecommunities.com/<org>/reservation/search
"""
import json
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import activenet
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


def perfectmind(link):
    """(facilities, fetch_week(f, start) -> {day: ranges}, workers) for a PerfectMind city."""
    configure(link)
    facilities = [f for f in server.fetch_facilities() if f.get("serviceId")]

    def week(f, start):
        days = server.fetch_week(f, start)["days"]
        return {d: server.free_ranges(st, int(f["duration"])) for d, st in days.items()}

    return facilities, week, server.WORKERS


def active_net(link):
    site = activenet.Site(link)
    return site.facilities(), site.week, activenet.WORKERS


def snapshot(city):
    reader = active_net if activenet.is_activenet(city["bookingLink"]) else perfectmind
    facilities, fetch_week, workers = reader(city["bookingLink"])
    today = datetime.now(PACIFIC).date()
    starts = [(today + timedelta(days=7 * i)).isoformat() for i in range(WEEKS)]
    jobs = [(f, s) for s in starts for f in facilities]

    def one(job):
        f, s = job
        try:
            return s, f["id"], fetch_week(f, s)
        except Exception as e:
            return s, f["id"], {"error": str(e)}

    weeks = {s: {} for s in starts}
    with ThreadPoolExecutor(workers) as pool:
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
