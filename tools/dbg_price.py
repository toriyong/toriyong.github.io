import os, re, requests
key = os.environ["DATA_GO_KR_KEY"].strip()
base = "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo"
def show(label, params):
    r = requests.get(base, params={"serviceKey": key, **params}, timeout=30)
    body = re.sub(r"(?i)serviceKey=[^&\s\"']+", "serviceKey=***", r.text)
    print("CASE", label, r.status_code, body[:600].replace("\n", " "))
show("minimal", {"resultType": "json", "numOfRows": "3", "pageNo": "1"})
show("likeSrtnCd", {"resultType": "json", "numOfRows": "3", "pageNo": "1", "likeSrtnCd": "005930"})
show("itmsNm", {"resultType": "json", "numOfRows": "3", "pageNo": "1", "itmsNm": "삼성전자"})
show("dates", {"resultType": "json", "numOfRows": "3", "pageNo": "1", "itmsNm": "삼성전자", "beginBasDt": "20261101", "endBasDt": "20261113"})
show("basDt", {"resultType": "json", "numOfRows": "3", "pageNo": "1", "basDt": "20261112"})
show("xml", {"numOfRows": "2", "pageNo": "1", "likeSrtnCd": "005930"})
