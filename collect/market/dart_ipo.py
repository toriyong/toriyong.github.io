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
import kind_listing  # noqa: E402  KIND 신규상장(상장일·시장)

KST = timezone(timedelta(hours=9))
API = "https://opendart.fss.or.kr/api"
DETAIL_TY_EQUITY = "C001"      # 발행공시 > 증권신고(지분증권)
MAX_WINDOW_DAYS = 89           # 회사 지정 없이 검색할 때 기간 제한(3개월)에 맞춤
REQUEST_GAP_SEC = 0.15         # 호출 간격(과도한 호출 방지)
# 신고서 원본(ZIP)은 건당 수 MB라 해외(GitHub) 러너에서 느릴 수 있다.
# 한 번 실행에서 본문 다운로드에 쓰는 총 시간을 제한하고, 못 받은 건은 다음 실행에서 이어 받는다
# (받은 건은 doc_rcept_no 캐시로 재사용되므로 몇 번의 실행 뒤에는 신규 공시만 받게 된다).
DOC_BUDGET_SEC = int(os.environ.get("DART_DOC_BUDGET_SEC", "300"))  # 실행당 본문 다운로드 총 예산
DOC_DEADLINE_SEC = 90          # 문서 1건 최대 다운로드 시간
DOC_TIMEOUT = (10, 30)         # (연결, 읽기 무응답) 초
DOC_MAX_BYTES = 40 * 1024 * 1024

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


def _is_ipo_row(r: dict, kind_idx: dict | None) -> bool:
    """비상장(E) 회사의 공시이거나, 상장 직후라 corp_cls 가 바뀌었지만 KIND 신규상장 목록에 있고
    공시일이 상장일 이전인 경우(= 그 상장을 위한 신고서)만 IPO 공시로 본다."""
    if r.get("corp_cls") == "E":
        return True
    if not kind_idx or r.get("corp_cls") not in ("K", "Y", "N"):
        return False
    m = kind_listing.match(r.get("corp_name", ""), kind_idx)
    dt = str(r.get("rcept_dt") or "")
    return bool(m and dt and f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" <= m["listing_date"])


def latest_ipo_filings(rows: list[dict], kind_idx: dict | None = None) -> list[dict]:
    """비상장사(E)의 증권신고서만 남기고, 회사별 최신 접수번호 1건으로 줄인다.
    (상장 직후 종목은 KIND 신규상장 목록으로 확인해 함께 남긴다)
    [발행조건확정] 신고서가 있으면 그 접수번호를 confirm_rcept_no 로 함께 기록(수요예측 결과가 들어 있음)."""
    latest: dict[str, dict] = {}
    confirm: dict[str, str] = {}
    withdrawn: dict[str, str] = {}          # 회사별 가장 최근 철회신고서 접수번호
    for r in rows:
        if not _is_ipo_row(r, kind_idx):
            continue
        name = r.get("report_nm") or ""
        if "철회" in name and r.get("corp_code"):
            if r.get("rcept_no", "") > withdrawn.get(r["corp_code"], ""):
                withdrawn[r["corp_code"]] = r.get("rcept_no", "")
            continue
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
    dropped = []
    for code, r in latest.items():
        # 철회: 최신 신고서 뒤에 철회신고서가 있거나, 목록 비고(rm)에 '철'(철회된 문서) 표시
        if withdrawn.get(code, "") > r.get("rcept_no", "") or "철" in str(r.get("rm") or ""):
            dropped.append(r.get("corp_name", code))
            continue
        out.append({**r, "confirm_rcept_no": confirm.get(code)})
    if dropped:
        log(f"철회된 공모 {len(dropped)}건 제외: {', '.join(dropped)}")
    return out


def fetch_document_values(session, key: str, rcept_no: str) -> dict:
    """공시서류 원본(document.xml, ZIP)을 받아 공모 핵심 수치를 해석한다."""
    time.sleep(REQUEST_GAP_SEC)
    t0 = time.monotonic()
    buf = bytearray()
    with session.get(f"{API}/document.xml", params={"crtfc_key": key, "rcept_no": rcept_no},
                     timeout=DOC_TIMEOUT, stream=True) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=256 * 1024):
            buf += chunk
            if len(buf) > DOC_MAX_BYTES:
                raise DartError(f"문서가 너무 큼(>{DOC_MAX_BYTES // 1048576}MB)")
            if time.monotonic() - t0 > DOC_DEADLINE_SEC:
                raise DartError(f"다운로드 {DOC_DEADLINE_SEC}초 초과({len(buf) // 1024}KB 수신)")
    blob = bytes(buf)
    if not blob.startswith(b"PK"):                   # ZIP이 아니면 오류 응답(XML/JSON)
        raise DartError(f"document.xml 응답이 ZIP이 아님: {blob[:120]!r}")
    vals = dart_doc.parse_offering(dart_doc.zip_to_text(blob, rcept_no))
    log(f"  본문 {rcept_no}: {len(blob) // 1024}KB, {time.monotonic() - t0:.1f}초, 항목 {len(vals)}개")
    return vals


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
    try:
        kind_idx = kind_listing.index_by_name(kind_listing.fetch_new_listings(days_back=days))
        log(f"KIND 신규상장 {len(kind_idx)}건")
    except (requests.RequestException, ValueError) as e:      # KIND 실패해도 DART 수집은 계속
        log(f"KIND 신규상장 조회 실패(상장일 없이 진행): {e}")
        kind_idx = {}
    filings = latest_ipo_filings(search_equity_filings(session, key, days), kind_idx)
    log(f"IPO 후보 공시 {len(filings)}건")
    cache = {p.get("corp_code"): p for p in (prev_items or [])}

    # 1) 기본 정보(estkRs): 가볍고 빠르다
    rows = []
    for f in filings:
        try:
            detail = fetch_detail(session, key, f, days)
        except (DartError, requests.RequestException) as e:
            log(f"상세 조회 실패 {f.get('corp_name')}: {e}")
            detail = {}
        rows.append((f, detail))

    # 2) 신고서 본문: 캐시 우선, 새로 받을 건은 '발행조건확정 → 최근 접수' 순으로 예산 안에서
    doc_of: dict[str, tuple[str | None, dict]] = {}
    todo = []
    for f, _ in rows:
        code = f.get("corp_code")
        doc_rcept = f.get("confirm_rcept_no") or f.get("rcept_no")
        prev = cache.get(code) or {}
        if (doc_rcept and prev.get("doc_rcept_no") == doc_rcept and isinstance(prev.get("doc"), dict)
                and prev.get("doc_ver") == dart_doc.PARSER_VERSION):
            doc_of[code] = (doc_rcept, prev["doc"])     # 같은 문서는 다시 받지 않음
        elif doc_rcept:
            todo.append(f)
    cached_n = len(doc_of)
    todo.sort(key=lambda f: f.get("rcept_dt") or "", reverse=True)
    todo.sort(key=lambda f: not f.get("confirm_rcept_no"))   # 안정 정렬: 확정 우선, 그 안에서 최신순
    log(f"본문 캐시 {cached_n}건 · 신규 대상 {len(todo)}건 (예산 {DOC_BUDGET_SEC}초)")

    started = time.monotonic()
    parsed_n = failed_n = deferred_n = 0
    for i, f in enumerate(todo, 1):
        if time.monotonic() - started > DOC_BUDGET_SEC:
            deferred_n = len(todo) - i + 1
            log(f"본문 예산 소진 → 남은 {deferred_n}건은 다음 실행에서 처리")
            break
        doc_rcept = f.get("confirm_rcept_no") or f.get("rcept_no")
        log(f"[{i}/{len(todo)}] {f.get('corp_name')} 본문 받는 중")
        try:
            doc_of[f.get("corp_code")] = (doc_rcept, fetch_document_values(session, key, doc_rcept))
            parsed_n += 1
        except (DartError, requests.RequestException, ValueError, OSError) as e:
            failed_n += 1
            log(f"  본문 해석 실패 {f.get('corp_name')}: {e}")

    items = []
    for f, detail in rows:
        doc_rcept, doc_vals = doc_of.get(f.get("corp_code"), (None, {}))
        confirmed = bool(f.get("confirm_rcept_no"))
        if not confirmed:                               # 확정 전에는 공모가 확정값을 쓰지 않음
            doc_vals = {k: v for k, v in doc_vals.items() if k not in ("offer_price", "demand_ratio", "lockup_ratio")}
        name = f.get("corp_name", "")
        link_rcept = f.get("confirm_rcept_no") or f.get("rcept_no")
        lst = kind_listing.match(name, kind_idx)
        if lst and detail.get("sub_end") and lst["listing_date"] < detail["sub_end"]:
            lst = None                                  # 청약 전 상장일 → 다른 회사로 보고 버림
        listing = {"listing_date": lst["listing_date"], "market": lst.get("market"),
                   "sector": lst.get("industry")} if lst else {}
        items.append({
            "corp_name": name,
            "corp_code": f.get("corp_code"),
            "rcept_no": f.get("rcept_no"),
            "rcept_dt": f.get("rcept_dt"),
            "report_nm": (f.get("report_nm") or "").strip(),
            "is_spac": "스팩" in name or "기업인수목적" in name,
            "dart_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={link_rcept}",
            **detail,
            "confirmed": confirmed,
            "doc_rcept_no": doc_rcept,                  # None 이면 다음 실행에서 다시 시도
            "doc": doc_vals,
            "doc_ver": dart_doc.PARSER_VERSION if doc_rcept else None,
            **doc_vals,                                 # offer_price·band·경쟁률·확약률·유통물량·구주매출
            **listing,                                  # KIND: 상장일·시장·업종
        })
    log(f"본문 해석 {parsed_n}건(신규) · {cached_n}건(캐시) · 실패 {failed_n}건 · 이월 {deferred_n}건 "
        f"· 소요 {time.monotonic() - started:.0f}초")
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
