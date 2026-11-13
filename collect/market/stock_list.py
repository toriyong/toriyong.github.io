"""상장 종목 목록(코스피·코스닥·코넥스)을 만든다 — 관심종목 검색용.

관심종목을 등록할 때 종목명을 직접 타자하면 오타가 나기 쉬워서,
사이트에 종목 목록을 미리 깔아 두고 검색(초성 포함)으로 고르게 한다.

- 입력: 공공데이터포털 주식시세정보(getStockPriceInfo_V2) — 최근 영업일 전 종목
        (watchlist.py 가 현재가를 가져올 때 쓰는 것과 같은 API·같은 키)
- 출력: site/market/stocks.json
    → [{"c": 종목코드, "n": 종목명, "m": 시장, "p": 종가, "r": 등락률, "a": 시가총액(억원)}, ...]
  시세를 같이 담아 두면 즐겨찾기만 해도 현재가·등락률이 바로 보인다.

사용: DATA_GO_KR_KEY=... python collect/market/stock_list.py [--out site/market/stocks.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))
APIS = [u for u in [os.environ.get("DATA_GO_KR_PRICE_URL", "").strip()] if u] + [
    "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2",
    "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo",
]
UA = "Mozilla/5.0 (toriyong.github.io data collector)"
PAGE = 1000           # 한 번에 받는 건수(포털 상한)
MAX_PAGES = 12        # 상장 종목 약 2,900개 + 여유
MARKET = {"KOSPI": "코스피", "KOSDAQ": "코스닥", "KONEX": "코넥스"}
_KEY_RE = re.compile(r"(?i)\b(serviceKey|api_?key|key)=[^&\s'\"]+")


def num(v):
    """숫자 문자열을 float 로. 빈 값·이상값은 None."""
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def log(msg: str) -> None:
    print(f"[stocks] {msg}", file=sys.stderr)


def redact(msg) -> str:
    """오류 문자열에서 인증키를 지운다(로그·공개 파일에 키가 남지 않도록)."""
    s = _KEY_RE.sub(lambda m: m.group(1) + "=***", str(msg))
    return re.sub(r"for url: \S+", "", s).strip()


def fetch_page(session: requests.Session, url: str, key: str, bas_dt: str, page: int, timeout: int):
    r = session.get(url, timeout=timeout, params={
        "serviceKey": key, "resultType": "json",
        "numOfRows": str(PAGE), "pageNo": str(page), "basDt": bas_dt,
    })
    r.raise_for_status()
    body = r.json()["response"]["body"]
    items = (body.get("items") or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]
    return items, int(body.get("totalCount") or 0)


def pick_api(session: requests.Session, key: str, bas_dt: str, timeout: int) -> str:
    """동작하는 주소를 고른다(포털이 _V2 로 옮기는 중이라 후보를 순서대로 시도)."""
    last = None
    for url in APIS:
        try:
            items, total = fetch_page(session, url, key, bas_dt, 1, timeout)
            if total:
                return url
            last = RuntimeError(f"{url.split('1160100/')[-1]} → 건수 0")
        except Exception as e:
            last = RuntimeError(f"{url.split('1160100/')[-1]} → {redact(e)}")
    raise last or RuntimeError("시세 API 주소를 찾지 못함")


def collect(key: str, timeout: int = 30) -> dict:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    today = datetime.now(KST).date()
    stocks: dict[str, dict] = {}
    errors: list[str] = []
    used_dt = ""

    # 최근 영업일을 찾는다(주말·휴일이면 건수가 0으로 온다)
    for back in range(0, 10):
        bas_dt = (today - timedelta(days=back)).strftime("%Y%m%d")
        try:
            url = pick_api(s, key, bas_dt, timeout)
        except Exception as e:
            errors.append(f"{bas_dt}: {redact(e)}")
            continue
        used_dt = bas_dt
        for page in range(1, MAX_PAGES + 1):
            try:
                items, total = fetch_page(s, url, key, bas_dt, page, timeout)
            except Exception as e:
                errors.append(f"{bas_dt} p{page}: {redact(e)}")
                break
            for it in items:
                code = str(it.get("srtnCd") or "").strip()[-6:]
                name = str(it.get("itmsNm") or "").strip()
                mkt = MARKET.get(str(it.get("mrktCtg") or "").strip().upper())
                if not (re.fullmatch(r"\d{6}", code) and name and mkt):
                    continue
                row = {"c": code, "n": name, "m": mkt}
                price, rate, cap = num(it.get("clpr")), num(it.get("fltRt")), num(it.get("mrktTotAmt"))
                if price is not None:
                    row["p"] = int(price)
                if rate is not None:
                    row["r"] = round(rate, 2)
                if cap:
                    row["a"] = int(cap / 1e8)        # 억원
                stocks.setdefault(code, row)
            if page * PAGE >= total or not items:
                break
        if stocks:
            log(f"{bas_dt} 기준 {len(stocks)}종목")
            break

    return {
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "base_date": f"{used_dt[:4]}-{used_dt[4:6]}-{used_dt[6:]}" if used_dt else "",
        "count": len(stocks),
        "errors": errors[:5],
        "stocks": sorted(stocks.values(), key=lambda d: d["n"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/market/stocks.json")
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()

    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        log("DATA_GO_KR_KEY 가 없어 종목 목록을 건너뜁니다.")
        return 0 if os.path.exists(args.out) else 1

    data = collect(key, timeout=args.timeout)
    if not data["stocks"]:
        # 수집 실패 시 기존 파일을 덮어쓰지 않는다(검색이 통째로 비는 것을 막는다)
        for e in data["errors"]:
            log(e)
        log("수집된 종목이 없어 기존 파일을 유지합니다.")
        return 0 if os.path.exists(args.out) else 1
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    log(f"{data['count']}종목 ({data['base_date']}) → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
