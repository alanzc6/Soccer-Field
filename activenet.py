"""Read field availability from an ActiveNet (activecommunities.com) site.

Uses the same public endpoints the site's own "Reserve a facility" pages call,
so no login is needed. Produces facilities and weeks in the same shape as the
PerfectMind reader in scrape.py.
"""
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

WORKERS = 8
UA = "Mozilla/5.0 (field-finder; +https://alanzc6.github.io/Soccer-Field/)"


def is_activenet(link):
    return urllib.parse.urlparse(link).netloc.endswith("activecommunities.com")


def is_field(kind):
    """Athletic fields and futsal courts; skip picnic sites, tents, tennis."""
    return "field" in kind.lower() or "futsal" in kind.lower()


class Site:
    def __init__(self, link):
        u = urllib.parse.urlparse(link)
        org = u.path.strip("/").split("/")[0]
        # apm.activecommunities.com only serves the page shell; the API lives on anc.apm.
        self.base = f"https://anc.apm.activecommunities.com/{org}"

    def get(self, path, **params):
        params["locale"] = "en-US"
        url = f"{self.base}/rest/{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
        if body["headers"]["response_code"] != "0000":
            raise RuntimeError(body["headers"]["response_message"])
        return body["body"]

    def facilities(self):
        ids = [f["id"] for f in self.get("reservation/resource/searchoptions")["facilities"]]
        with ThreadPoolExecutor(WORKERS) as pool:
            details = list(pool.map(lambda i: self.get(f"reservation/resource/detail/{i}")["resource_detail"], ids))
        out = []
        for d in details:
            g = d["general_information"]
            if not is_field(g["facility_type"]):
                continue
            lead = [int(n) for r in d.get("advanced_restrictions", [])
                    for n in re.findall(r"at least (\d+) day", r)]
            phone = g.get("phone") or ""
            out.append({
                "id": str(g["facility_id"]),
                "name": g["facility_name"].strip(),
                "park": g["center_name"].strip(),
                "type": g["facility_type"],
                "bookingUrl": f"{self.base}/reservation/landing/search/detail/{g['facility_id']}",
                "bookAheadDays": min(lead) if lead else 0,
                "bookingNote": f"Call {phone} to Request" if g.get("no_internet_permits") and phone else "",
                "eventTypeId": d.get("default_event_type_id") or 0,
            })
        return out

    def week(self, f, start):
        """{YYYY-MM-DD: [[startMin, endMin], ...]} of open time for 7 days from start."""
        end = (date.fromisoformat(start) + timedelta(days=6)).isoformat()
        body = self.get(f"reservation/resource/availability/daily/{f['id']}", start_date=start, end_date=end,
                        customer_id=0, company_id=0, event_type_id=f["eventTypeId"], attendee=0, no_cache="true")
        days = {}
        for day in body["details"]["daily_details"]:
            days[day["date"]] = [[minutes(t["start_time"]), minutes(t["end_time"])]
                                 for t in day["times"] if t.get("available")]
        return days


def minutes(hms):
    h, m = hms.split(":")[:2]
    return int(h) * 60 + int(m)
