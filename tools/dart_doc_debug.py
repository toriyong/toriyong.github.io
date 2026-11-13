"""진단용: 확정 신고서 본문을 텍스트로 바꾼 뒤 수요예측·확약·유통 구간만 로그로 출력한다(키·전문 미출력)."""
import os, re, sys
sys.path.insert(0, "collect/market")
import requests
import dart_ipo as d
import dart_doc as dd

key = os.environ["DART_API_KEY"].strip()
s = requests.Session()
filings = d.latest_ipo_filings(d.search_equity_filings(s, key, 120))
targets = [f for f in filings if f.get("confirm_rcept_no")][:4]
KW = ["수요예측 참여 내역", "수요예측 참여내역", "경쟁률", "의무보유확약", "확약기간별", "유통가능", "상장예정주식"]
for f in targets:
    r = f["confirm_rcept_no"]
    blob = s.get(f"{d.API}/document.xml", params={"crtfc_key": key, "rcept_no": r}, timeout=(10, 60)).content
    text = dd.zip_to_text(blob, r)
    print(f"\n######## {f['corp_name']} {r} text={len(text)}자")
    print("PARSED:", dd.parse_offering(text))
    for kw in KW:
        idx = [m.start() for m in re.finditer(re.escape(kw), text)]
        print(f"--- '{kw}' 위치 {len(idx)}개: {idx[:12]}")
    # 수요예측 결과 표, 확약 표 구간(마지막 등장 기준) 출력
    for kw, n in (("수요예측 참여 내역", 2200), ("수요예측 참여내역", 2200), ("확약기간별", 2600), ("유통가능", 700)):
        idx = [m.start() for m in re.finditer(re.escape(kw), text)]
        for i in idx[-2:]:
            print(f"\n=== [{kw} @ {i}] ===")
            print(repr(text[max(0, i - 150): i + n]))
