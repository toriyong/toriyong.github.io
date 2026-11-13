"""OpenDART에서 공모주(비상장사의 증권신고서-지분증권)를 수집해 원천 JSON을 만든다.

수집 흐름
  1) 공시검색(list.json)으로 최근 N일의 '증권신고(지분증권)' 공시를 찾는다.
     - corp_cls == 'E'(기타법인 = 비상장)만 남겨 신규상장(IPO) 후보로 본다.
     - 같은 회사의 정정 공시가 여러 건이면 가장 최근 접수번호만 쓴다.
  2) 증권신고서 주요정보(estkRs.json)로 청약일·공모가·주관사 등을 채운다.
     - 응답 필드명이 바뀌어도 죽지 않도록 후보 키 목록으로 찾고, 못 찾으면 None.
  3) 실패하면 --prev 로 넘긴 직전 데이터를 유지한다(빈 화면 방지).

키는 환경 변수 DART_API_KEY 로만 읽고, 절대 출력하지 않는다.

사용 예
  python collect/market/dart_ipo.py --out site/market/data/raw_ipo.json
  python collect/market/dart_ipo.py --sample --out site/market/data/raw_ipo.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dart_doc  # noqa: E402  신고서 본문 해석

KST = timezone(timedelta(hours=9))
API = "https://opendart.fss.or.kr/api"
DETAIL_TY_EQUITY = "C001"      # 발행공시 > 증권신고(지분증권)
MAX_WINDOW_DAYS = 89           # 회사 지정 없이 검색할 때 기간 제한(3개월)에 맞춤
REQUEST_GAP_SEC = 0.15         # 호출 간격(과도한 호출 방지)

# estkRs.json 응답에서 값을 찾을 후보 키 (앞쪽이 우선)
KEYS = {
    "sub_period": ["sbd", "sbscpn_pd", "subscription_period"],   # 청약기일
    "pay_date": ["pymd", "pymnt_de"],                           # 납입기일
    "price": ["slprc", "prc", "ofrprc"],                        # 모집(매출)가액
    "shares": ["stkcnt", "stk_cnt"],                            # 증권수량
    "total_amount": ["slta", "tot_amt"],                        # 모집(매출)총액
    "method": ["slmthn", "mth"],                                # 모집(매출)방법
    "underwriter": ["actnmn", "udtnm", "underwriter"],          # 인수인(주관사)
}


def now_kst() -> datetime:
    return datetime.now(KST)


def log(msg: str) -> None:
    print(f"[dart_ipo] {msg}", file=sys.stderr)


# ---------------------------------------------------------------- parsing utils
DATE_RE = re.compile(r"(20\d{2})\s*[.\-/년]?\s*(\d{1,2})\s*[.\-/월]?\s*(\d{1,2})")


def parse_dates(text: str | None) -> list[str]:
    """'2026년 11월 05일 ~ 2026년 11월 06일' 같은 문자열에서 ISO 날짜 목록을 뽑는다."""
    if not text:
        return []
    out = []
    for y, m, d in DATE_RE.findall(str(text)):
        try:
            out.append(date(int(y), int(m), int(d)).isoformat())
        except ValueError:
            continue
    return out


def parse_int(text) -> int | None:
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


def pick(row: dict, field: str):
    for k in KEYS[field]:
        v = row.get(k)
        if v not in (None, "", "-"):
            return v
    return None


# ---------------------------------------------------------------- API calls
class DartError(RuntimeError):
    pass


def call(session: requests.Session, endpoint: str, params: dict, key: str) -> dict:
    time.sleep(REQUEST_GAP_SEC)
    resp = session.get(f"{API}/{endpoint}", params={"crtfc_key": key, **params}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    status = data.get("status")
    if status == "013":            # 조회된 데이터 없음 → 정상
        return {"status": "013", "list": [], "group": []}
    if status != "000":
        raise DartError(f"{endpoint} status={status} message={data.get('message')}")
    return data


def search_equity_filings(session, key: str, days: int) -> list[dict]:
    """최근 days일 동안의 증권신고(지분증권) 공시 목록 (3개월 단위로 나눠 조회)."""
    end = now_kst().date()
    start = end - timedelta(days=days)
    rows: list[dict] = []
    win_end = end
    while win_end >= start:
        win_start = max(start, win_end - timedelta(days=MAX_WINDOW_DAYS))
        page = 1
        while True:
            data = call(session, "list.json", {
                "bgn_de": win_start.strftime("%Y%m%d"),
                "end_de": win_end.strftime("%Y%m%d"),
                "pblntf_detail_ty": DETAIL_TY_EQUITY,
                "page_no": page,
                "page_count": 100,
            }, key)
            rows.extend(data.get("list", []))
            total_page = int(data.get("total_page") or 1)
            if page >= total_page:
                break
            page += 1
        win_end = win_start - timedelta(days=1)
    return rows


def latest_ipo_filings(rows: list[dict]) -> list[dict]:
    """비상장사(E)의 증권신고서만 남기고, 회사별 최신 접수번호 1건으로 줄인다.
    [발행조건확정] 신고서가 있으면 그 접수번호를 confirm_rcept_no 로 함께 기록(수요예측 결과가 들어 있음)."""
    latest: dict[str, dict] = {}
    confirm: dict[str, str] = {}
    for r in rows:
        if r.get("corp_cls") != "E":
            continue
        name = r.get("report_nm") or ""
        if "증권신고서" not in name:
            continue
        code = r.get("corp_code")
        if not code:
            continue
        if code not in latest or r.get("rcept_no", "") > latest[code].get("rcept_no", ""):
            latest[code] = r
        if "발행조건확정" in name and r.get("rcept_no", "") > confirm.get(code, ""):
            confirm[code] = r["rcept_no"]
    out = []
    for code, r in latest.items():
        out.append({**r, "confirm_rcept_no": confirm.get(code)})
    return out


def fetch_document_values(session, key: str, rcept_no: str) -> dict:
    """공시서류 원본(document.xml, ZIP)을 받아 공모 핵심 수치를 해석한다."""
    time.sleep(REQUEST_GAP_SEC)
    resp = session.get(f"{API}/document.xml", params={"crtfc_key": key, "rcept_no": rcept_no}, timeout=60)
    resp.raise_for_status()
    if not resp.content.startswith(b"PK"):           # ZIP이 아니면 오류 응답(XML/JSON)
        raise DartError(f"document.xml 응답이 ZIP이 아님: {resp.content[:120]!r}")
    return dart_doc.parse_offering(dart_doc.zip_to_text(resp.content, rcept_no))


_logged_shape = False


def fetch_detail(session, key: str, filing: dict, days: int) -> dict:
    """estkRs.json 을 그룹 제목 기준으로 읽어 필요한 값만 뽑는다."""
    global _logged_shape
    end = now_kst().date()
    data = call(session, "estkRs.json", {
        "corp_code": filing["corp_code"],
        "bgn_de": (end - timedelta(days=days)).strftime("%Y%m%d"),
        "end_de": end.strftime("%Y%m%d"),
    }, key)
    groups = data.get("group") or []

    if not _logged_shape and groups:
        # 필드 매핑 점검용: 그룹 제목과 키 이름만 출력(값은 출력하지 않음)
        for g in groups:
            first = (g.get("list") or [{}])[0]
            log(f"estkRs group '{g.get('title')}' keys={sorted(first.keys())}")
        _logged_shape = True

    def rows_of(title_part: str) -> list[dict]:
        for g in groups:
            if title_part in (g.get("title") or ""):
                rows = g.get("list") or []
                same = [r for r in rows if r.get("rcept_no") == filing.get("rcept_no")]
                return same or rows
        return []

    general = (rows_of("일반사항") or [{}])[-1]
    kinds = rows_of("증권의종류")
    stock = next((r for r in kinds if "보통" in str(r.get("stksen", ""))), kinds[-1] if kinds else {})
    underwriters = sorted({str(pick(r, "underwriter")).strip()
                           for r in rows_of("인수인") if pick(r, "underwriter")})

    sub = parse_dates(pick(general, "sub_period"))
    pay = parse_dates(pick(general, "pay_date"))
    return {
        "sub_start": sub[0] if sub else None,
        "sub_end": sub[-1] if sub else None,
        "pay_date": pay[0] if pay else None,
        "price": parse_int(pick(stock, "price")),
        "shares": parse_int(pick(stock, "shares")),
        "total_amount": parse_int(pick(stock, "total_amount")),
        "method": pick(stock, "method"),
        "underwriters": underwriters,
    }


def collect(key: str, days: int, prev_items: list[dict] | None = None) -> list[dict]:
    session = requests.Session()
    session.headers["User-Agent"] = "toriyong.github.io data collector"
    filings = latest_ipo_filings(search_equity_filings(session, key, days))
    log(f"IPO 후보 공시 {len(filings)}건")
    cache = {p.get("corp_code"): p for p in (prev_items or [])}
    items = []
    parsed_n = cached_n = 0
    for f in filings:
        try:
            detail = fetch_detail(session, key, f, days)
        except (DartError, requests.RequestException) as e:
            log(f"상세 조회 실패 {f.get('corp_name')}: {e}")
            detail = {}

        # 신고서 본문 해석: 발행조건확정 신고서가 있으면 그것, 없으면 최신 신고서
        doc_rcept = f.get("confirm_rcept_no") or f.get("rcept_no")
        prev = cache.get(f.get("corp_code")) or {}
        doc_vals: dict = {}
        if prev.get("doc_rcept_no") == doc_rcept and isinstance(prev.get("doc"), dict):
            doc_vals = prev["doc"]                      # 같은 문서는 다시 받지 않음
            cached_n += 1
        elif doc_rcept:
            try:
                doc_vals = fetch_document_values(session, key, doc_rcept)
                parsed_n += 1
            except (DartError, requests.RequestException, ValueError, OSError) as e:
                log(f"본문 해석 실패 {f.get('corp_name')}: {e}")
        confirmed = bool(f.get("confirm_rcept_no"))
        if not confirmed:                               # 확정 전에는 공모가 확정값을 쓰지 않음
            doc_vals = {k: v for k, v in doc_vals.items() if k not in ("offer_price", "demand_ratio", "lockup_ratio")}

        name = f.get("corp_name", "")
        items.append({
            "corp_name": name,
            "corp_code": f.get("corp_code"),
            "rcept_no": f.get("rcept_no"),
            "rcept_dt": f.get("rcept_dt"),
            "report_nm": (f.get("report_nm") or "").strip(),
            "is_spac": "스팩" in name or "기업인수목적" in name,
            "dart_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={doc_rcept or f.get('rcept_no')}",
            **detail,
            "confirmed": confirmed,
            "doc_rcept_no": doc_rcept,
            "doc": doc_vals,
            **doc_vals,                                 # offer_price·band·경쟁률·확약률·유통물량·구주매출
        })
    log(f"본문 해석 {parsed_n}건(신규) · {cached_n}건(캐시)")
    return items


# ---------------------------------------------------------------- sample data
def sample_items() -> list[dict]:
    """키 없이 화면을 확인하기 위한 예시 데이터(가상의 회사)."""
    t = now_kst().date()

    def d(n):
        return (t + timedelta(days=n)).isoformat()

    base = [
        ("샘플AI", -1, 0, 17600, ["대신증권"]),
        ("샘플로보틱스", 3, 4, 12000, ["한국투자증권"]),
        ("샘플바이오", 8, 9, 21000, ["NH투자증권", "KB증권"]),
        ("샘플소재", 12, 13, 9500, ["미래에셋증권"]),
        ("샘플플랫폼", -9, -8, 15000, ["삼성증권"]),
        ("샘플스팩10호", 5, 6, 2000, ["신영증권"]),
    ]
    return [{
        "corp_name": n, "corp_code": f"S{i:07d}", "rcept_no": f"SAMPLE{i}",
        "rcept_dt": t.strftime("%Y%m%d"), "report_nm": "증권신고서(지분증권)",
        "is_spac": "스팩" in n, "dart_url": "https://dart.fss.or.kr/",
        "sub_start": d(s), "sub_end": d(e), "pay_date": d(e + 2),
        "price": p, "shares": 2_000_000, "total_amount": p * 2_000_000,
        "method": "일반공모", "underwriters": u,
    } for i, (n, s, e, p, u) in enumerate(base, 1)]


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--days", type=int, default=120, help="조회 기간(일)")
    ap.add_argument("--prev", help="수집 실패 시 유지할 직전 원천 JSON 경로")
    ap.add_argument("--sample", action="store_true", help="키 없이 예시 데이터 생성")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    meta = {"updated_at": now_kst().isoformat(timespec="minutes"), "source": "OpenDART"}

    if args.sample:
        payload = {**meta, "sample": True, "items": sample_items()}
    else:
        key = os.environ.get("DART_API_KEY", "").strip()
        prev_items = []
        if args.prev and os.path.exists(args.prev):
            try:
                with open(args.prev, encoding="utf-8") as fp:
                    prev_items = json.load(fp).get("items", [])
            except (OSError, ValueError):
                prev_items = []
        try:
            if not key:
                raise DartError("DART_API_KEY 환경 변수가 없습니다")
            payload = {**meta, "sample": False, "items": collect(key, args.days, prev_items)}
        except (DartError, requests.RequestException, ValueError) as e:
            log(f"수집 실패: {e}")
            if args.prev and os.path.exists(args.prev):
                shutil.copyfile(args.prev, args.out)
                with open(args.out, encoding="utf-8") as fp:
                    old = json.load(fp)
                old["stale"] = True
                old["stale_reason"] = str(e)[:200]
                with open(args.out, "w", encoding="utf-8") as fp:
                    json.dump(old, fp, ensure_ascii=False, indent=1)
                log("직전 데이터를 유지합니다")
                return 0
            log("직전 데이터도 없어 빈 결과를 씁니다")
            payload = {**meta, "sample": False, "stale": True,
                       "stale_reason": str(e)[:200], "items": []}

    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=1)
    log(f"{len(payload['items'])}건 저장 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
