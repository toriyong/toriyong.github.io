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
# 공공데이터포털이 서비스 주소를 _V2 형태로 바꾸는 중이라 후보를 순서대로 시도한다.
# (증권상품시세정보는 이미 /1160100/GetSecuritiesProductInfoService_V2 로 바뀜)
PRICE_APIS = [u for u in [os.environ.get("DATA_GO_KR_PRICE_URL", "").strip()] if u] + [
    "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2",
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
    """동작하는 주소를 한 번 찾으면 계속 그 주소를 쓴다.

    공공데이터포털 오류 코드: 12 = 없는/폐기된 서비스(다음 후보 시도),
    30 = 등록되지 않은 서비스키(해당 API 활용신청이 안 됐거나 승인·반영 전).
    """
    last, denied = None, None
    for url in (_working_api or PRICE_APIS):
        try:
            r = session.get(url, params=params, timeout=20)
        except requests.RequestException as e:
            last = e
            continue
        head = r.text[:400]
        if r.status_code == 404 or "NO_OPENAPI_SERVICE" in head or "API not found" in head or "Unexpected errors" in head:
            last = RuntimeError(f"{url.split('1160100/')[-1]} → 없는 서비스")
            continue
        if r.status_code in (401, 403) or "SERVICE_KEY_IS_NOT_REGISTERED" in head:
            denied = "등록되지 않은 서비스키" if "NOT_REGISTERED" in head else f"HTTP {r.status_code}"
            last = RuntimeError(f"{url.split('1160100/')[-1]} → {denied}")
            continue
        if not _working_api:
            _working_api.append(url)
            print(f"[price] 시세 API 주소: {url}", file=sys.stderr)
        return r
    if denied:
        raise RuntimeError(f"권한 없음({denied}) — 공공데이터포털에서 '금융위원회_주식시세정보' 활용신청이 "
                           "승인됐는지 확인하세요(승인 후 반영까지 1~2시간)")
    raise RuntimeError(f"시세 API 주소를 찾지 못함: {redact(last)}")
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
    r = price_get(session, {
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
        # 자동 추출은 자릿수를 잘못 읽는 일이 있다. 현재가와 지나치게 동떨어진 값은 버린다.
        if price and not (price * 0.3 <= p <= price * 3):
            continue
        d = str(t.get("date") or "")[:10]
        rows.append({"broker": t.get("broker"), "price": p, "date": d or None,
                     "url": t.get("url"),
                     "attain": round(price / p * 100, 1) if price else None})
    rows.sort(key=lambda r: r["date"] or "", reverse=True)
    # 컨센서스 평균: 최근 TARGET_DAYS 일 안의 값만, 증권사별로 최신 1건만 반영한다.
    # (같은 증권사가 분기마다 내는 리포트를 모두 더하면 그 증권사 비중이 커진다)
    fresh = [r for r in rows if (r["date"] or "") >= since] or rows
    latest: dict[str, dict] = {}
    for r in fresh:                                   # rows 는 최신순이므로 처음 만난 것이 최신
        latest.setdefault((r["broker"] or "").strip() or f"_{len(latest)}", r)
    used = list(latest.values())
    prices = [r["price"] for r in used]
    avg_t = round(mean(prices)) if prices else None
    for r in rows:                                    # 평균에 쓰인 건을 화면에서 구분
        r["used"] = r in used
    return {"targets": rows, "avg_target": avg_t,
            "target_brokers": len(prices), "target_min": min(prices) if prices else None,
            "target_max": max(prices) if prices else None,
            "attain": round(price / avg_t * 100, 1) if price and avg_t else None,
            "upside": round((avg_t / price - 1) * 100, 1) if price and avg_t else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/watchlist.yml")
    ap.add_argument("--out", default="site/market/data/watchlist.json")
    ap.add_argument("--prev")
    ap.add_argument("--targets", help="research.py 가 모은 목표가 JSON(있으면 yml 값과 합침)")
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

    auto_targets = {}
    if args.targets and os.path.exists(args.targets):
        try:
            with open(args.targets, encoding="utf-8") as fp:
                auto_targets = (json.load(fp) or {}).get("targets") or {}
        except (OSError, ValueError):
            auto_targets = {}

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
            errors.append(f"DART 고유번호: {redact(e)}")

    out = []
    for st in stocks:
        code = str(st.get("stock_code", "")).zfill(6)
        name = st.get("name") or code
        old = prev.get(code) or {}
        row = {"name": name, "stock_code": code, "corp_code": codes.get(code)}
        # 리포트에서 모은 목표가 + yml 에 직접 적은 값 (증권사·날짜가 같으면 한 건으로)
        merged, seen = [], set()
        for t in (auto_targets.get(code) or []) + (st.get("targets") or []):
            k = ((t.get("broker") or "").strip(), str(t.get("date") or "")[:10])
            if k in seen:
                continue
            seen.add(k)
            merged.append(t)
        st = {**st, "targets": merged}
        try:
            row["price"] = last_price(s, price_key, code) if price_key else None
        except (requests.RequestException, RuntimeError) as e:
            errors.append(f"{name} 현재가: {redact(e)}")
            row["price"] = old.get("price")
        try:
            row["disclosures"] = disclosures(s, dart_key, row["corp_code"]) if row["corp_code"] else []
        except (requests.RequestException, RuntimeError, ValueError) as e:
            errors.append(f"{name} 공시: {redact(e)}")
            row["disclosures"] = old.get("disclosures", [])
        try:
            row["news"] = news(st.get("news_query") or name)
        except Exception as e:                               # feedparser 는 예외 종류가 다양함
            errors.append(f"{name} 뉴스: {redact(e)}")
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
