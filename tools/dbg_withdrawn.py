import os, sys
sys.path.insert(0, "collect/market")
import requests, dart_ipo as d
key = os.environ["DART_API_KEY"].strip(); s = requests.Session()
rows = d.search_equity_filings(s, key, 120)
for r in rows:
    if r.get("corp_code") == "02038432" or "철회" in (r.get("report_nm") or ""):
        print("C001", r.get("corp_name"), r.get("report_nm"), r.get("rcept_no"), "rm=", repr(r.get("rm")))
data = d.call(s, "list.json", {"corp_code": "02038432", "bgn_de": "20260901", "end_de": "20261113", "page_count": 100}, key)
for r in data.get("list", []):
    print("ALL", r.get("report_nm"), r.get("rcept_no"), "rm=", repr(r.get("rm")), r.get("corp_cls"))
