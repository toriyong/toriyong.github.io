"""진단용(3차): 확정 신고서 원본 ZIP을 base64로 로그에 출력(로컬 테스트 픽스처용, 공개 공시)."""
import base64, os, sys
sys.path.insert(0, "collect/market")
import requests
import dart_ipo as d

key = os.environ["DART_API_KEY"].strip()
s = requests.Session()
filings = d.latest_ipo_filings(d.search_equity_filings(s, key, 120))
for f in [f for f in filings if f.get("confirm_rcept_no")][:5]:
    r = f["confirm_rcept_no"]
    blob = s.get(f"{d.API}/document.xml", params={"crtfc_key": key, "rcept_no": r}, timeout=(10, 60)).content
    print(f"BEGIN {r} {len(blob)}")
    b = base64.b64encode(blob).decode()
    for i in range(0, len(b), 4000):
        print("B64 " + b[i:i + 4000])
    print(f"END {r}")
