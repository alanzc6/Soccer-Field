#!/usr/bin/env python3
"""Snapshot field availability for the next several weeks as JSON.

Usage: python3 scrape.py [weeks] > snapshot.json
Output: {"updatedAt", "facilities": [...], "weeks": {"YYYY-MM-DD": {fieldId: {date: [[start,end],...]}}}}
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import server

WEEKS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
PACIFIC = timezone(timedelta(hours=-8))  # close enough to pick "today" in Menlo Park


def main():
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

    keep = ("id", "name", "park", "type", "bookingUrl", "bookAheadDays")
    json.dump({
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "facilities": [{k: f.get(k) for k in keep} for f in facilities],
        "weeks": weeks,
    }, sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
