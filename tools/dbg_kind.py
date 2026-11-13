import re, requests
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 toriyong.github.io collector"
for u in ["https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain",
          "https://kind.krx.co.kr/listinvstg/pubofrprogcom.do?method=searchPubofrProgComMain"]:
    t = s.get(u, timeout=30).text
    print("PAGE", u, len(t))
    for m in re.finditer(r'<input[^>]+name="([^"]+)"[^>]*?(?:value="([^"]*)")?', t):
        print("  INPUT", m.group(1), "=", m.group(2))
    for m in re.finditer(r"method\s*[:=]\s*['\"]?(\w+)", t):
        print("  METHOD", m.group(1))
    for m in re.finditer(r"(url\s*:\s*['\"][^'\"]+['\"]|action=\"[^\"]+\")", t):
        print("  URL", m.group(1))
    for m in re.finditer(r"forward[\"']?\s*[,:=]\s*[\"']?(\w+)", t):
        print("  FWD", m.group(1))
