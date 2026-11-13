"""공모주 성적표: 최근 상장 종목의 시가·종가·D+1·D+5·D+30 수익률과 섹터 주목도.

입력: 등급 처리된 site/market/data/ipo.json (상장일·공모가·경쟁률·청약 판단 포함)
주가: 공공데이터포털 '금융위원회_주식시세정보'(getStockPriceInfo) — DATA_GO_KR_KEY 가 있을 때만.
      이 API는 보통 영업일 기준 하루 늦게(다음 날 오후) 갱신된다.
출력: site/market/data/results.json
      · 이력은 직전 results.json 을 이어받아 최대 HISTORY_DAYS 일 보관(DART 120일 창보다 길게)
      · D+30 까지 다 채운 종목은 주가를 다시 조회하지 않는다.

사용:
  python collect/market/ipo_results.py --ipo site/market/data/ipo.json \
      --out site/market/data/results.json [--prev /tmp/prev_results.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from statistics import mean

import requests

KST = timezone(timedelta(hours=9))
# 공공데이터포털이 서비스 주소를 _V2 형태로 바꾸는 중이라 후보를 순서대로 시도한다.
# (증권상품시세정보는 이미 /1160100/GetSecuritiesProductInfoService_V2 로 바뀜)
PRICE_APIS = [u for u in [os.environ.get("DATA_GO_KR_PRICE_URL", "").strip()] if u] + [
    "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2",
    "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo",
    "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo",
]
_working_api: list[str] = []



_KEY_RE = re.compile(r"(?i)\b(serviceKey|crtfc_key|api_?key|access_?token|token|key)=[^&\s'\"]+")


def redact(msg) -> str:
    """오류 문자열에서 URL 쿼리의 인증키 값을 지운다(공개 JSON·로그에 키가 남지 않도록)."""
    s = _KEY_RE.sub(lambda m: m.group(1) + "=***", str(msg))
    s = re.sub(r"for url: \S+", "", s).strip()           # requests HTTPError 의 전체 URL 제거
    return s

def price_get(session, params: dict):
    """동작하는 주소를 한 번 찾으면 계속 그 주소를 쓴다(404·403·라우팅 오류면 다음 후보)."""
    last, denied = None, None
    for url in (_working_api or PRICE_APIS):
        try:
            r = session.get(url, params=params, timeout=20)
        except requests.RequestException as e:
            last = e
            continue
        if r.status_code == 404 or "API not found" in r.text[:300] or "Unexpected errors" in r.text[:300]:
            last = RuntimeError(f"{url} → {r.status_code}")
            continue
        if r.status_code in (401, 403):            # 이 주소엔 권한이 없을 수 있음 → 다음 후보도 시도
            denied = r.status_code
            last = RuntimeError(f"{url} → {r.status_code}")
            continue
        if not _working_api:
            _working_api.append(url)
            print(f"[price] 시세 API 주소: {url}", file=sys.stderr)
        return r
    if denied:
        raise RuntimeError(f"HTTP {denied} 권한 없음 — 공공데이터포털에서 '금융위원회_주식시세정보' "
                           "활용신청 승인 여부와 인증키(Decoding) 활성화(승인 후 1~2시간)를 확인하세요")
    raise RuntimeError(f"시세 API 주소를 찾지 못함: {redact(last)}")
HISTORY_DAYS = 400
TRACK = {"d1": 1, "d5": 5, "d30": 30}      # 상장일(D0) 이후 거래일 수
KEEP = ("corp_name", "corp_code", "market", "sector", "listing_date", "offer_price", "price",
        "demand_ratio", "lockup_ratio", "float_ratio", "grade", "subscribe", "dart_url", "underwriters")


def log(msg: str) -> None:
    print(f"[ipo_results] {msg}", file=sys.stderr)


def now_kst() -> datetime:
    return datetime.now(KST)


def load(path: str | None) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, ValueError):
        return {}


def to_int(v) -> int | None:
    try:
        return int(str(v).replace(",", "")) if v not in (None, "") else None
    except ValueError:
        return None


# ------------------------------------------------------------------ 주가
def fetch_prices(session, key: str, name: str, start: date, end: date) -> list[dict]:
    """종목명으로 일별 시세를 조회해 날짜순 [{d, open, close}] 로 돌려준다."""
    params = {
        "serviceKey": key, "resultType": "json", "numOfRows": "100", "pageNo": "1",
        "itmsNm": name, "beginBasDt": start.strftime("%Y%m%d"), "endBasDt": end.strftime("%Y%m%d"),
    }
    resp = price_get(session, params)
    resp.raise_for_status()
    try:
        body = resp.json()["response"]["body"]
    except (ValueError, KeyError) as e:          # 키 오류 등은 XML로 온다
        raise RuntimeError(f"시세 응답 해석 실패: {resp.text[:160]!r}") from e
    items = (body.get("items") or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]
    rows = []
    for it in items:
        d = str(it.get("basDt") or "")
        if len(d) != 8 or it.get("itmsNm") != name:
            continue
        rows.append({"d": f"{d[:4]}-{d[4:6]}-{d[6:]}", "open": to_int(it.get("mkp")), "close": to_int(it.get("clpr"))})
    return sorted(rows, key=lambda r: r["d"])


def name_candidates(name: str) -> list[str]:
    alt = re.sub(r"\(주\)|㈜|주식회사|\s", "", name or "")
    return [n for n in dict.fromkeys([name, alt]) if n]


def ret(price, base) -> float | None:
    return round((price / base - 1) * 100, 2) if price and base else None


def compute(it: dict, rows: list[dict]) -> dict:
    """상장일 이후 거래일 기준 시가·종가와 공모가 대비 수익률."""
    rows = [r for r in rows if r["d"] >= it["listing_date"] and r["close"]]
    base = it.get("offer_price") or it.get("price")
    prices, returns = {}, {}
    if rows:
        d0 = rows[0]
        prices.update(d0_date=d0["d"], d0_open=d0["open"], d0_close=d0["close"])
        returns.update(open=ret(d0["open"], base), d0=ret(d0["close"], base))
        for k, n in TRACK.items():
            if len(rows) > n:
                prices[k] = rows[n]["close"]
                prices[k + "_date"] = rows[n]["d"]
                returns[k] = ret(rows[n]["close"], base)
        prices["last"] = rows[-1]["close"]
        prices["last_date"] = rows[-1]["d"]
        returns["last"] = ret(rows[-1]["close"], base)
    return {"prices": prices, "returns": returns, "days_tracked": max(len(rows) - 1, 0) if rows else None}


# ------------------------------------------------------------------ 집계
def avg(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(mean(xs), 2) if xs else None


def sectors(items: list[dict], since: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for it in items:
        if (it.get("listing_date") or "") >= since:
            groups.setdefault(it.get("sector") or "업종 미상", []).append(it)
    out = []
    for sec, xs in groups.items():
        out.append({
            "sector": sec, "count": len(xs),
            "avg_demand": avg([x.get("demand_ratio") for x in xs]),
            "avg_lockup": avg([x.get("lockup_ratio") for x in xs]),
            "avg_d0": avg([x.get("returns", {}).get("d0") for x in xs]),
            "avg_d5": avg([x.get("returns", {}).get("d5") for x in xs]),
            "names": [x["corp_name"] for x in sorted(xs, key=lambda x: x["listing_date"], reverse=True)],
        })
    # 주목도: 상장 건수 → 평균 경쟁률 순
    return sorted(out, key=lambda s: (-s["count"], -(s["avg_demand"] or 0)))


def buckets(items: list[dict], rule_tiers: list[dict]) -> list[dict]:
    """청약 판단(적극/보통/신중/비추천)별 실제 수익률 — 기준값 검증용."""
    out = []
    for t in rule_tiers or []:
        xs = [x for x in items if (x.get("subscribe") or {}).get("level") == t.get("level")]
        out.append({
            "level": t.get("level"), "label": t.get("label"), "count": len(xs),
            "with_price": sum(1 for x in xs if x.get("returns", {}).get("d0") is not None),
            "avg_open": avg([x.get("returns", {}).get("open") for x in xs]),
            "avg_d0": avg([x.get("returns", {}).get("d0") for x in xs]),
            "avg_d5": avg([x.get("returns", {}).get("d5") for x in xs]),
            "avg_d30": avg([x.get("returns", {}).get("d30") for x in xs]),
            "win_d0": (round(sum(1 for x in xs if (x.get("returns", {}).get("d0") or 0) > 0) * 100
                             / max(1, sum(1 for x in xs if x.get("returns", {}).get("d0") is not None)), 1)
                       if any(x.get("returns", {}).get("d0") is not None for x in xs) else None),
        })
    return out


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ipo", default="site/market/data/ipo.json")
    ap.add_argument("--out", default="site/market/data/results.json")
    ap.add_argument("--prev")
    args = ap.parse_args()

    ipo = load(args.ipo)
    prev = load(args.prev)
    today = now_kst().date()
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()

    # 1) 이력 합치기: 직전 성적표 + 이번 ipo.json 의 상장 완료 종목
    hist = {x["corp_code"]: x for x in prev.get("items", []) if x.get("corp_code")}
    for it in ipo.get("items", []):
        if not it.get("listing_date") or it.get("is_spac") or it.get("grade") == "spac":
            continue
        if it["listing_date"] > today.isoformat():
            continue
        base = hist.get(it["corp_code"], {})
        hist[it["corp_code"]] = {**base, **{k: it.get(k) for k in KEEP}}
    cutoff = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    items = [x for x in hist.values() if (x.get("listing_date") or "") >= cutoff]

    # 2) 주가: D+30 까지 다 찬 종목은 건너뜀
    errors, fetched = [], 0
    if key:
        s = requests.Session()
        s.headers["User-Agent"] = "toriyong.github.io data collector"
        for it in items:
            if (it.get("returns") or {}).get("d30") is not None:
                continue
            start = date.fromisoformat(it["listing_date"])
            end = min(today, start + timedelta(days=60))
            rows = []
            try:
                for nm in name_candidates(it["corp_name"]):
                    rows = fetch_prices(s, key, nm, start, end)
                    time.sleep(0.15)
                    if rows:
                        break
            except (requests.RequestException, RuntimeError) as e:
                errors.append(f"{it['corp_name']}: {redact(e)}")
                if "권한 없음" in str(e):            # 키 문제면 나머지 종목도 같은 결과 → 중단
                    break
                continue
            if rows:
                it.update(compute(it, rows))
                fetched += 1
        log(f"시세 조회 {fetched}건 · 실패 {len(errors)}건")
    else:
        log("DATA_GO_KR_KEY 없음 → 주가 없이 상장 이력·섹터만 집계")

    items.sort(key=lambda x: x.get("listing_date") or "", reverse=True)
    rule = ipo.get("subscribe_rule") or {}
    payload = {
        "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M+09:00"),
        "has_prices": bool(key),
        "price_source": "금융위원회_주식시세정보(공공데이터포털)" if key else None,
        "errors": errors[:20],
        "items": items,
        "sectors_90d": sectors(items, (today - timedelta(days=90)).isoformat()),
        "buckets": buckets(items, rule.get("tiers") or []),
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=1)
    log(f"{len(items)}건 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
