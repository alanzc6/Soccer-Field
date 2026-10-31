#!/usr/bin/env python3
"""Menlo Park field availability checker.

Run:  python3 server.py
Then open http://localhost:8765 in your browser.

Uses only the Python standard library. It talks to the City of Menlo Park
PerfectMind booking site on your behalf (browsers block that directly).
"""
import json
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
import http.cookiejar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8765
BASE = "https://cityofmenlopark.perfectmind.com"
ORG = "/26116/Clients"
WIDGET_ID = "9024d6fc-902b-4a85-a0ee-ea558c32ea15"
CALENDAR_ID = "87ac3aab-1f9e-4f81-867f-dbce9bc1bd37"
HERE = Path(__file__).resolve().parent

FACILITY_TTL = 6 * 3600   # field list rarely changes
AVAIL_TTL = 5 * 60        # availability is cached for 5 minutes
WORKERS = 6

TOKEN_RE = re.compile(r'id="AjaxAntiForgeryForm".*?name="__RequestVerificationToken" type="hidden" value="([^"]+)"', re.S)


class Site:
    """A cookie-holding session against the booking site."""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [("User-Agent", "Mozilla/5.0 (field-checker)")]
        self.token = None
        self.lock = threading.Lock()

    def get(self, path):
        with self.opener.open(BASE + path, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    def post(self, path, fields, ajax=True):
        if ajax:
            fields = list(fields) + [("__RequestVerificationToken", self.get_token())]
        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(BASE + path, data=data)
        if ajax:
            req.add_header("X-Requested-With", "XMLHttpRequest")
        with self.opener.open(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    def get_token(self, refresh=False):
        with self.lock:
            if refresh or not self.token:
                html = self.get(list_path())
                m = TOKEN_RE.search(html)
                if not m:
                    raise RuntimeError("Could not find the site's security token")
                self.token = m.group(1)
            return self.token


def list_path():
    return f"{ORG}/BookMe4FacilityList/List?widgetId={WIDGET_ID}&calendarId={CALENDAR_ID}&embed=False"


def booking_url(fid):
    return f"{BASE}{ORG}/BookMe4LandingPages/Facility?facilityId={fid}&widgetId={WIDGET_ID}&calendarId={CALENDAR_ID}"


def extract_json_after(html, marker):
    i = html.find(marker)
    if i < 0:
        return None
    value, _ = json.JSONDecoder().raw_decode(html[i + len(marker):].lstrip())
    return value


site = Site()
cache = {}
cache_lock = threading.Lock()


def cached(key, ttl, fn):
    with cache_lock:
        hit = cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    value = fn()
    with cache_lock:
        cache[key] = (time.time(), value)
    return value


def load_facility_details(f):
    """Read a field's booking page for the info needed to ask about open times."""
    html = site.get(f"{ORG}/BookMe4LandingPages/Facility?facilityId={f['id']}&widgetId={WIDGET_ID}&calendarId={CALENDAR_ID}")
    services = extract_json_after(html, "services:") or []
    service = next((s for s in services if any(c.get("Id") == CALENDAR_ID for c in s.get("Calendars") or [])),
                   services[0] if services else None)
    if service and service.get("Durations"):
        dur = min(service["Durations"], key=lambda d: d["Duration"])
        f["serviceId"] = service["ID"]
        f["duration"] = dur["Duration"]
        f["durationIds"] = dur["DurationIDs"]
        f["feeType"] = dur.get("FeeType", 0)
        f["startsEvery"] = service.get("StartsEvery") or 30
    hours = extract_json_after(html, "workingHours:") or []
    # DayOfWeek: 0 = Sunday ... 6 = Saturday; Start/End carry the time of day.
    f["hours"] = {}
    for h in hours:
        s, e = h["Start"][11:16], h["End"][11:16]
        f["hours"].setdefault(str(h["DayOfWeek"]), []).append([s, "24:00" if h.get("IsFullDay") else e])
    return f


def fetch_facilities():
    raw = json.loads(site.post(f"{ORG}/BookMe4FacilityList/GetFacilities", [
        ("calendarId", CALENDAR_ID), ("widgetId", WIDGET_ID),
        ("page", 1), ("pageSize", 200), ("take", 200), ("skip", 0)]))
    groups = raw["facilities"]

    def expand(g):
        if not g.get("IsFacilityMap"):
            return [g]
        sub = json.loads(site.post(f"{ORG}/BookMe4FacilityMap/GetFacilities", [
            ("calendarId", CALENDAR_ID), ("widgetId", WIDGET_ID),
            ("mapId", g["ID"]), ("filtersLoaded", "false"),
            ("page", 1), ("pageSize", 200), ("take", 200), ("skip", 0)]))
        out = sub.get("facilities") or []
        for s in out:
            s["_group"] = g["Name"]
        return out

    with ThreadPoolExecutor(WORKERS) as pool:
        items = [f for lst in pool.map(expand, groups) for f in lst]

    facilities, seen = [], set()
    for x in items:
        if x["ID"] in seen:
            continue
        seen.add(x["ID"])
        facilities.append({
            "id": x["ID"],
            "name": x["Name"],
            "group": x.get("_group") or x["Name"],
            "park": x.get("LocationName") or "",
            "type": x.get("FacilityType") or "Other",
            "image": ("https:" + x["Image"]) if (x.get("Image") or "").startswith("//") else x.get("Image"),
            "bookingUrl": booking_url(x["ID"]),
            "bookingNote": x.get("MinDaysInAdvanceBtnLabel"),
            "bookAheadDays": x.get("BookFutureEventsStartPaddingInDays"),
        })

    with ThreadPoolExecutor(WORKERS) as pool:
        facilities = list(pool.map(load_facility_details, facilities))
    facilities.sort(key=lambda f: (f["park"], f["name"]))
    return facilities


def get_facilities():
    return cached("facilities", FACILITY_TTL, fetch_facilities)


def to_min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fetch_week(f, start):
    """Open start times for one field over 7 days starting at `start` (YYYY-MM-DD)."""
    if not f.get("serviceId"):
        return {"error": "This field can't be booked online"}
    fields = [
        ("facilityId", f["id"]),
        ("date", f"{start}T00:00:00.000Z"),
        ("daysCount", 7),
        ("duration", int(f["duration"])),
        ("serviceId", f["serviceId"]),
        ("calendarId", CALENDAR_ID),
        ("feeType", f["feeType"]),
    ] + [("durationIds[]", d) for d in f["durationIds"]]
    body = site.post(f"{ORG}/BookMe4LandingPages/FacilityAvailability", fields)
    try:
        data = json.loads(body)
    except ValueError:
        site.get_token(refresh=True)
        data = json.loads(site.post(f"{ORG}/BookMe4LandingPages/FacilityAvailability", fields[:]))
    days = {}
    for day in data.get("availabilities") or []:
        ms = int(re.search(r"-?\d+", day["Date"]).group())
        date = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        starts = []
        for g in day.get("BookingGroups") or []:
            for s in g.get("AvailableSpots") or []:
                if not s.get("IsDisabled"):
                    starts.append(s["Time"]["Hours"] * 60 + s["Time"]["Minutes"])
        days[date] = sorted(set(starts))
    return {"days": days}


def free_ranges(starts, duration):
    """Merge 'a booking can start at t' into contiguous free [start, end) minute ranges."""
    ranges = []
    for s in starts:
        e = s + duration
        if ranges and s <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1], e)
        else:
            ranges.append([s, e])
    return ranges


def get_availability(start):
    facilities = get_facilities()

    def one(f):
        try:
            week = cached(("week", f["id"], start), AVAIL_TTL, lambda: fetch_week(f, start))
        except Exception as e:  # keep the rest of the grid working
            week = {"error": str(e)}
        out = {"id": f["id"]}
        if "error" in week:
            out["error"] = week["error"]
        else:
            out["days"] = {d: free_ranges(st, int(f["duration"])) for d, st in week["days"].items()}
        return out

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(one, facilities))
    return {"start": start, "fetchedAt": datetime.now().isoformat(timespec="seconds"), "fields": results}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("  " + (fmt % args) + "\n")

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                return self.send(200, (HERE / "index.html").read_bytes(), "text/html")
            if url.path == "/api/facilities":
                return self.send(200, json.dumps(get_facilities()))
            if url.path == "/api/availability":
                start = (q.get("start") or [datetime.now().strftime("%Y-%m-%d")])[0]
                datetime.strptime(start, "%Y-%m-%d")
                if q.get("refresh"):
                    with cache_lock:
                        for k in [k for k in cache if isinstance(k, tuple) and k[2] == start]:
                            del cache[k]
                return self.send(200, json.dumps(get_availability(start)))
            self.send(404, json.dumps({"error": "not found"}))
        except Exception as e:
            self.send(502, json.dumps({"error": f"{type(e).__name__}: {e}"}))


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Field checker running at http://localhost:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
