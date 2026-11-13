import os, re, requests
key = os.environ["DATA_GO_KR_KEY"].strip()
urls = [
 "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo",
 "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService/getStockPriceInfo",
 "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2",
 "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService_V2/getStockPriceInfo",
 "https://apis.data.go.kr/1160100/GetSecuritiesProductInfoService_V2/getETFPriceInfo_V2",
 "https://apis.data.go.kr/1160100/GetSecuritiesProductInfoService_V2/getETFPriceInfo",
]
for u in urls:
    r = requests.get(u, params={"serviceKey": key, "resultType": "json", "numOfRows": "2", "pageNo": "1", "likeSrtnCd": "005930"}, timeout=30)
    body = re.sub(r"(?i)serviceKey=[^&\s\"']+", "serviceKey=***", r.text)
    print("CASE", u.split("1160100/")[1], r.status_code, re.sub(r"\s+", " ", body)[:300])
