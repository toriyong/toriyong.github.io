"""KRX KIND '신규상장기업현황'에서 최근 신규상장 종목의 상장일·시장을 가져온다.

DART에는 상장일이 없고, 상장하면 corp_cls 가 E(비상장)에서 K/Y 등으로 바뀌어
IPO 후보 목록에서 빠진다. KIND 목록으로 상장일을 붙이고, 상장 후에도 목록에 남긴다.
공개 웹 화면(로그인 불필요)의 목록 조회 요청을 그대로 쓴다.
"""
from __future__ import annotations

import html
import re
import sys
from datetime import date, timedelta

import requests

BASE = "https://kind.krx.co.kr"
UA = "Mozilla/5.0 (toriyong.github.io data collector)"
ROW = re.compile(r"<tr[^>]*fnDetailView\('([^']*)'[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
MARKET = {"코스닥": "코스닥", "유가증권": "코스피", "코넥스": "코넥스"}


def norm_name(s: str) -> str:
    """회사명 비교용: 공백·법인 표기·괄호·특수문자 제거, 소문자."""
    s = html.unescape(s or "")
    s = re.sub(r"\(주\)|㈜|주식회사|\(유\)|유한회사", "", s)
    s = re.sub(r"(?i)\b(co\.?,?\s*ltd\.?|inc\.?|corp\.?|corporation|limited)\b", "", s)
    return re.sub(r"[^0-9a-z가-힣]", "", s.lower())


def fetch_new_listings(days_back: int = 90, days_ahead: int = 30, timeout: int = 30) -> list[dict]:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    s.get(f"{BASE}/main.do?method=loadInitPage&scrnmode=1", timeout=timeout)          # 세션 쿠키
    main = f"{BASE}/listinvstg/listingcompany.do?method=searchListingTypeMain"
    s.get(main, timeout=timeout)
    today = date.today()
    out: list[dict] = []
    page = 1
    while page <= 10:
        r = s.post(f"{BASE}/listinvstg/listingcompany.do", timeout=timeout, headers={"Referer": main, "X-Requested-With": "XMLHttpRequest"}, data={
            "method": "searchListingTypeSub", "forward": "listingtype_sub",
            "currentPageSize": "100", "pageIndex": str(page), "orderMode": "1", "orderStat": "D",
            "searchMode": "", "searchCodeType": "", "repIsuSrtCd": "", "isurCd": "", "searchCorpName": "",
            "marketType": "", "country": "", "detailMarket": "",
            "fromDate": (today - timedelta(days=days_back)).isoformat(),
            "toDate": (today + timedelta(days=days_ahead)).isoformat(),
            "secuGrpArrStr": "0|ST|FS|MF|SC|RT|IF|DR|", "listTypeArrStr": "01|", "choicTypeArrStr": "",
        })
        r.raise_for_status()
        rows = ROW.findall(r.text)
        for isur, body in rows:
            cells = CELL.findall(body)
            if len(cells) < 7:
                continue
            first = cells[0]
            name = re.search(r'title="([^"]*)"', body)
            alt = re.search(r"alt='([^']*)'", first) or re.search(r'alt="([^"]*)"', first)
            text = lambda c: html.unescape(re.sub(r"<[^>]+>", " ", c)).strip()
            d = text(cells[1])
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                continue
            out.append({
                "name": html.unescape(name.group(1)).strip() if name else text(first),
                "listing_date": d,
                "market": MARKET.get(alt.group(1) if alt else "", alt.group(1) if alt else None),
                "listing_type": text(cells[2]),
                "industry": text(cells[4]),
                "underwriter": text(cells[6]),
                "isur_cd": isur,
            })
        total = re.search(r"전체\s*<em>(\d+)</em>", r.text)
        if not rows or not total or page * 100 >= int(total.group(1)):
            break
        page += 1
    return out


def index_by_name(listings: list[dict]) -> dict[str, dict]:
    return {norm_name(x["name"]): x for x in listings if x.get("name")}


def match(corp_name: str, idx: dict[str, dict]) -> dict | None:
    """정확히 같은 이름 우선, 없으면 한쪽이 다른 쪽으로 시작하는 경우(KIND 약칭 대비, 짧은 쪽 4자 이상·후보 1개일 때만)."""
    key = norm_name(corp_name)
    if not key:
        return None
    if key in idx:
        return idx[key]
    cands = [v for k, v in idx.items() if min(len(k), len(key)) >= 4 and (key.startswith(k) or k.startswith(key))]
    return cands[0] if len(cands) == 1 else None


if __name__ == "__main__":
    xs = fetch_new_listings()
    print(len(xs), file=sys.stderr)
    for x in xs[:10]:
        print(x)
