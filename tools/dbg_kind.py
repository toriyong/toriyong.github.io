import re, requests
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 toriyong.github.io collector"
url = "https://kind.krx.co.kr/listinvstg/listingcompany.do"
data = {"method": "searchListingTypeSub", "currentPageSize": "50", "pageIndex": "1", "orderMode": "1", "orderStat": "D",
        "forward": "listingtype_sub", "listTypeArrStr": "01|", "choicTypeArrStr": "", "fromDate": "2026-09-01", "toDate": "2026-11-30",
        "repIsuSrtCd": "", "isurCd": "", "marketType": ""}
r = s.post(url, data=data, timeout=30)
print("status", r.status_code, len(r.text))
txt = re.sub(r"<[^>]+>", " ", r.text); txt = re.sub(r"\s+", " ", txt)
print(txt[:3000])
r2 = s.get("https://kind.krx.co.kr/listinvstg/pubofrprogcom.do?method=searchPubofrProgComMain", timeout=30)
print("pubofr", r2.status_code, len(r2.text))
