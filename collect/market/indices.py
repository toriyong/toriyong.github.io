"""국내·해외 주요 지수와 환율을 모은다 (증시 탭 상단 카드용).

- 국내: 공공데이터포털 금융위원회_지수시세정보 (DATA_GO_KR_KEY, 주식시세정보와 같은 키)
        ※ 포털 마이페이지에서 '지수시세정보' 활용신청이 따로 필요하다.
- 해외: FRED (미 세인트루이스 연방준비은행, FRED_API_KEY) — 무료, 호출 제한 사실상 없음
- 출력: site/market/data/indices.json
    {"groups": [{"id","name","items":[{"name","value","diff","rate","date","spark":[...]}]}]}

사용: DATA_GO_KR_KEY=... FRED_API_KEY=... python collect/market/indices.py
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
UA = "Mozilla/5.0 (toriyong.github.io data collector)"
KRX_APIS = [
    "https://apis.data.go.kr/1160100/service/GetMarketIndexInfoService/getStockMarketIndex",
    "https://apis.data.go.kr/1160100/GetMarketIndexInfoService_V2/getStockMarketIndex_V2",
]
FRED = "https://api.stlouisfed.org/fred/series/observations"
DAYS = 60            # 스파크라인용 과거 구간
SPARK = 30           # 스파크라인 점 개수
_KEY_RE = re.compile(r"(?i)\b(serviceKey|api_?key|key)=[^&\s'\"]+")

KR_INDICES = ["코스피", "코스닥", "코스피200"]
FRED_SERIES = [
    ("미국", "S&P 500", "SP500"),
    ("미국", "나스닥 종합", "NASDAQCOM"),
    ("미국", "다우 산업", "DJIA"),
    ("미국", "VIX", "VIXCLS"),
    ("아시아", "닛케이 225", "NIKKEI225"),
    ("통화", "원/달러", "DEXKOUS"),
]


def log(msg: str) -> None:
    print(f"[indices] {msg}", file=sys.stderr)


def redact(msg) -> str:
    s = _KEY_RE.sub(lambda m: m.group(1) + "=***", str(msg))
    return re.sub(r"for url: \S+", "", s).strip()


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def series_card(name: str, points: list[tuple[str, float]]) -> dict | None:
    """[(날짜, 값)] → 카드 한 장. 마지막 값과 직전 대비 변화."""
    points = [(d, v) for d, v in points if v is not None]
    if not points:
        return None
    points.sort(key=lambda x: x[0])
    (d1, v1) = points[-1]
    prev = points[-2][1] if len(points) > 1 else None
    spark = [round(v, 2) for _, v in points[-SPARK:]]
    return {
        "name": name, "value": round(v1, 2), "date": d1,
        "diff": round(v1 - prev, 2) if prev is not None else None,
        "rate": round((v1 / prev - 1) * 100, 2) if prev else None,
        "spark": spark,
    }


# ---------- 국내 (공공데이터포털)
def krx_indices(session: requests.Session, key: str, timeout: int) -> tuple[list[dict], list[str]]:
    end = datetime.now(KST).date()
    begin = end - timedelta(days=DAYS)
    errors, cards = [], []
    for name in KR_INDICES:
        got = None
        for url in KRX_APIS:
            try:
                r = session.get(url, timeout=timeout, params={
                    "serviceKey": key, "resultType": "json",
                    "numOfRows": "200", "pageNo": "1", "idxNm": name,
                    "beginBasDt": begin.strftime("%Y%m%d"), "endBasDt": end.strftime("%Y%m%d"),
                })
                r.raise_for_status()
                items = (r.json()["response"]["body"].get("items") or {}).get("item") or []
                if isinstance(items, dict):
                    items = [items]
                items = [i for i in items if str(i.get("idxNm", "")).strip() == name]
                if items:
                    got = items
                    break
            except Exception as e:
                errors.append(f"{name}: {redact(e)}")
        if not got:
            continue
        pts = []
        for it in got:
            d = str(it.get("basDt") or "")
            v = num(it.get("clpr"))
            if len(d) == 8 and v is not None:
                pts.append((f"{d[:4]}-{d[4:6]}-{d[6:]}", v))
        card = series_card(name, pts)
        if card:
            cards.append(card)
    return cards, errors


# ---------- 해외 (FRED)
def fred_series(session: requests.Session, key: str, sid: str, timeout: int) -> list[tuple[str, float]]:
    start = (datetime.now(KST).date() - timedelta(days=DAYS)).isoformat()
    r = session.get(FRED, timeout=timeout, params={
        "series_id": sid, "api_key": key, "file_type": "json", "observation_start": start,
    })
    r.raise_for_status()
    out = []
    for o in r.json().get("observations", []):
        v = num(o.get("value"))          # 휴장일은 "." 로 온다 → None
        if v is not None:
            out.append((o.get("date"), v))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/market/data/indices.json")
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()

    s = requests.Session()
    s.headers["User-Agent"] = UA
    groups: dict[str, list[dict]] = {}
    errors: list[str] = []

    kr_key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if kr_key:
        cards, errs = krx_indices(s, kr_key, args.timeout)
        if cards:
            groups["국내"] = cards
        errors += errs[:3]
        log(f"국내 {len(cards)}개")
    else:
        errors.append("DATA_GO_KR_KEY 없음")

    fred_key = os.environ.get("FRED_API_KEY", "").strip()
    if fred_key:
        for group, name, sid in FRED_SERIES:
            try:
                card = series_card(name, fred_series(s, fred_key, sid, args.timeout))
            except Exception as e:
                errors.append(f"{name}: {redact(e)}")
                continue
            if card:
                groups.setdefault(group, []).append(card)
        log(f"해외 {sum(len(v) for k, v in groups.items() if k != '국내')}개")
    else:
        errors.append("FRED_API_KEY 없음 (해외 지수 생략)")

    if not groups:
        for e in errors:
            log(e)
        log("수집된 지수가 없어 기존 파일을 유지합니다.")
        return 0 if os.path.exists(args.out) else 1

    order = ["국내", "미국", "아시아", "통화"]
    data = {
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "errors": errors[:5],
        "groups": [{"id": g, "name": g, "items": groups[g]} for g in order if g in groups],
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    log(f"{sum(len(g['items']) for g in data['groups'])}개 지수 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
