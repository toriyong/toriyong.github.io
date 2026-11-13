import re, requests
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 toriyong.github.io collector"
s.get("https://kind.krx.co.kr/main.do?method=loadInitPage&scrnmode=1", timeout=30)
s.get("https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain", timeout=30)
url = "https://kind.krx.co.kr/listinvstg/listingcompany.do"
base = {"currentPageSize": "50", "pageIndex": "1", "orderMode": "1", "orderStat": "D", "searchMode": "", "searchCodeType": "",
        "repIsuSrtCd": "", "isurCd": "", "searchCorpName": "", "marketType": "", "country": "", "detailMarket": "",
        "fromDate": "2026-09-01", "toDate": "2026-11-30", "secuGrpArrStr": "0|ST|FS|MF|SC|RT|IF|DR|", "listTypeArrStr": "01|",
        "choicTypeArrStr": ""}
for meth, fwd in [("searchListingTypeSub", "listingtype_sub")]:
    r = s.post(url, data={**base, "method": meth, "forward": fwd}, headers={"Referer": "https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain", "X-Requested-With": "XMLHttpRequest"}, timeout=30)
    txt = re.sub(r"<[^>]+>", " ", r.text); txt = re.sub(r"\s+", " ", txt)
    print("TRY", meth, fwd, r.status_code, len(r.text))
    i = r.text.find("<tbody"); print("RAW", repr(r.text[i:i+2500]))
    j = r.text.find("paging"); print("PAGING", repr(r.text[j-200:j+600]))
