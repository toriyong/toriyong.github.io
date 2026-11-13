"""관심종목: 목표가 도달률 · 최근 뉴스 제목 · DART 공시.

- 종목 목록·목표가: config/watchlist.yml (직접 입력)
- 현재가: 공공데이터포털 '금융위원회_주식시세정보' (DATA_GO_KR_KEY 있을 때)
- 공시: OpenDART list.json (DART_API_KEY, corpCode.xml 로 종목코드→고유번호 변환)
- 뉴스: Google 뉴스 RSS 검색(제목·언론사·링크·날짜만, 본문 미수집)

사용: python collect/market/watchlist.py --out site/market/data/watchlist.json [--prev ...]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from urllib.parse import quote
from xml.etree import ElementTree as ET

import feedparser
import requests
import yaml

KST = timezone(timedelta(hours=9))
DART = "https://opendart.fss.or.kr/api"
PRICE_API = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"
UA = "toriyong.github.io data collector"
NEWS_DAYS, NEWS_MAX, DISC_DAYS, DISC_MAX, TARGET_DAYS = 7, 8, 30, 8, 90


def log(msg: str) -> None:
    print(f"[watchlist] {msg}", file=sys.stderr)


def now_kst() -> datetime:
    return datetime.now(KST)


def to_int(v):
    try:
        return int(str(v).replace(",", "")) if v not in (None, "") else None
    except ValueError:
        return None


def corp_codes(session, key: str, wanted: set[str]) -> dict[str, str]:
    """corpCode.xml(전체 기업 고유번호 ZIP)에서 필요한 종목코드만 고유번호로 바꾼다."""
    r = session.get(f"{DART}/corpCode.xml", params={"crtfc_key": key}, timeout=60)
    r.raise_for_status()
    if not r.content.startswith(b"PK"):
        raise RuntimeError(f"corpCode 응답이 ZIP이 아님: {r.content[:120]!r}")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        root = ET.fromstring(z.read(z.namelist()[0]))
    out = {}
    for el in root.iter("list"):
        sc = (el.findtext("stock_code") or "").strip()
        if sc in wanted:
            out[sc] = (el.findtext("corp_code") or "").strip()
    return out


def disclosures(session, key: str, corp_code: str) -> list[dict]:
    end = now_kst().date()
    r = session.get(f"{DART}/list.json", timeout=20, params={
        "crtfc_key": key, "corp_code": corp_code, "page_count": 30,
        "bgn_de": (end - timedelta(days=DISC_DAYS)).strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
    })
    r.raise_for_status()
    data = r.json()
    if data.get("status") not in ("000", "013"):          # 013 = 조회 결과 없음
        raise RuntimeError(f"DART {data.get('status')} {data.get('message')}")
    out = []
    for it in (data.get("list") or [])[:DISC_MAX]:
        d = it.get("rcept_dt", "")
        out.append({"title": (it.get("report_nm") or "").strip(), "date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                    "filer": it.get("flr_nm"), "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={it.get('rcept_no')}"})
    return out


def news(query: str) -> list[dict]:
    url = (f"https://news.google.com/rss/search?q={quote(query + f' when:{NEWS_DAYS}d')}"
           "&hl=ko&gl=KR&ceid=KR:ko")
    feed = feedparser.parse(url, agent=UA)
    out, seen = [], set()
    for e in feed.entries:
        title = re.sub(r"\s+-\s+[^-]+$", "", e.get("title", "")).strip()   # 끝의 ' - 언론사' 제거
        key = re.sub(r"\W", "", title)[:40]
        if not title or key in seen:
            continue
        seen.add(key)
        src = (e.get("source") or {}).get("title") if isinstance(e.get("source"), dict) else None
        pub = e.get("published_parsed")
        out.append({"title": title, "source": src, "url": e.get("link"),
                    "date": time.strftime("%Y-%m-%d", pub) if pub else None})
        if len(out) >= NEWS_MAX:
            break
    return out


def last_price(session, key: str, stock_code: str) -> dict | None:
    end = now_kst().date()
    r = session.get(PRICE_API, timeout=20, params={
        "serviceKey": key, "resultType": "json", "numOfRows": "20", "pageNo": "1",
        "likeSrtnCd": stock_code, "beginBasDt": (end - timedelta(days=14)).strftime("%Y%m%d"),
        "endBasDt": end.strftime("%Y%m%d"),
    })
    r.raise_for_status()
    try:
        items = (r.json()["response"]["body"].get("items") or {}).get("item") or []
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"시세 응답 해석 실패: {r.text[:160]!r}") from e
    if isinstance(items, dict):
        items = [items]
    items = [i for i in items if str(i.get("srtnCd", "")).endswith(stock_code)]
    if not items:
        return None
    it = max(items, key=lambda i: i.get("basDt", ""))
    d = it["basDt"]
    return {"price": to_int(it.get("clpr")), "change_pct": float(it["fltRt"]) if it.get("fltRt") not in (None, "") else None,
            "date": f"{d[:4]}-{d[4:6]}-{d[6:]}"}


def target_summary(targets: list[dict], price: int | None) -> dict:
    since = (now_kst().date() - timedelta(days=TARGET_DAYS)).isoformat()
    rows = []
    for t in targets or []:
        p = to_int(t.get("price"))
        if not p:
            continue
        d = str(t.get("date") or "")[:10]
        rows.append({"broker": t.get("broker"), "price": p, "date": d or None,
                     "attain": round(price / p * 100, 1) if price else None})
    rows.sort(key=lambda r: r["date"] or "", reverse=True)
    recent = [r["price"] for r in rows if (r["date"] or "") >= since] or [r["price"] for r in rows]
    avg_t = round(mean(recent)) if recent else None
    return {"targets": rows, "avg_target": avg_t,
            "attain": round(price / avg_t * 100, 1) if price and avg_t else None,
            "upside": round((avg_t / price - 1) * 100, 1) if price and avg_t else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/watchlist.yml")
    ap.add_argument("--out", default="site/market/data/watchlist.json")
    ap.add_argument("--prev")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as fp:
        stocks = (yaml.safe_load(fp) or {}).get("stocks") or []
    prev = {}
    if args.prev and os.path.exists(args.prev):
        try:
            with open(args.prev, encoding="utf-8") as fp:
                prev = {s.get("stock_code"): s for s in json.load(fp).get("stocks", [])}
        except (OSError, ValueError):
            prev = {}

    dart_key = os.environ.get("DART_API_KEY", "").strip()
    price_key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    s = requests.Session()
    s.headers["User-Agent"] = UA
    errors = []

    codes = {}
    if dart_key and stocks:
        try:
            codes = corp_codes(s, dart_key, {str(x.get("stock_code", "")).zfill(6) for x in stocks})
        except (requests.RequestException, RuntimeError, zipfile.BadZipFile, ET.ParseError) as e:
            errors.append(f"DART 고유번호: {e}")

    out = []
    for st in stocks:
        code = str(st.get("stock_code", "")).zfill(6)
        name = st.get("name") or code
        old = prev.get(code) or {}
        row = {"name": name, "stock_code": code, "corp_code": codes.get(code)}
        try:
            row["price"] = last_price(s, price_key, code) if price_key else None
        except (requests.RequestException, RuntimeError) as e:
            errors.append(f"{name} 현재가: {e}")
            row["price"] = old.get("price")
        try:
            row["disclosures"] = disclosures(s, dart_key, row["corp_code"]) if row["corp_code"] else []
        except (requests.RequestException, RuntimeError, ValueError) as e:
            errors.append(f"{name} 공시: {e}")
            row["disclosures"] = old.get("disclosures", [])
        try:
            row["news"] = news(st.get("news_query") or name)
        except Exception as e:                               # feedparser 는 예외 종류가 다양함
            errors.append(f"{name} 뉴스: {e}")
            row["news"] = old.get("news", [])
        row.update(target_summary(st.get("targets") or [], (row.get("price") or {}).get("price")))
        out.append(row)
        time.sleep(0.2)

    payload = {"updated_at": now_kst().strftime("%Y-%m-%dT%H:%M+09:00"), "has_prices": bool(price_key),
               "errors": errors, "stocks": out}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=1)
    log(f"{len(out)}종목 · 오류 {len(errors)}건 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
