"""KRX 상장법인목록(코스피·코스닥·코넥스)을 받아 종목 검색용 목록을 만든다.

관심종목을 등록할 때 종목명을 직접 타자하면 오타가 나기 쉬워서,
사이트에 종목 목록을 미리 깔아 두고 검색(초성 포함)으로 고르게 한다.

- 입력: KIND 상장법인목록 다운로드(로그인 불필요, HTML 표로 내려온다)
- 출력: site/market/stocks.json  → [{"c": 종목코드, "n": 종목명, "m": 시장}, ...]

사용: python collect/market/stock_list.py [--out site/market/stocks.json]
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))
URL = "https://kind.krx.co.kr/corpgeneral/corpList.do"
UA = "Mozilla/5.0 (toriyong.github.io data collector)"
MARKETS = {"stockMkt": "코스피", "kosdaqMkt": "코스닥", "konexMkt": "코넥스"}
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def log(msg: str) -> None:
    print(f"[stocks] {msg}", file=sys.stderr)


def text(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).replace("\xa0", " ").strip()


def fetch_market(session: requests.Session, market: str, timeout: int = 60) -> list[dict]:
    """한 시장의 상장법인목록을 가져온다."""
    r = session.post(
        URL,
        data={"method": "download", "pageIndex": "1", "currentPageSize": "5000", "marketType": market},
        timeout=timeout,
    )
    r.raise_for_status()
    # 다운로드 응답은 euc-kr HTML 표다
    body = r.content.decode("euc-kr", errors="replace")
    out = []
    for row in ROW.findall(body):
        cells = [text(c) for c in CELL.findall(row)]
        if len(cells) < 2:
            continue
        name, code = cells[0], cells[1]
        if not re.fullmatch(r"\d{6}", code) or not name:
            continue
        out.append({"c": code, "n": name, "m": MARKETS[market]})
    return out


def collect(timeout: int = 60) -> dict:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    stocks: list[dict] = []
    errors: list[str] = []
    for market in MARKETS:
        try:
            got = fetch_market(s, market, timeout=timeout)
            log(f"{MARKETS[market]} {len(got)}종목")
            stocks.extend(got)
        except Exception as e:  # 한 시장이 실패해도 나머지는 살린다
            errors.append(f"{MARKETS[market]}: {type(e).__name__}")
            log(f"{MARKETS[market]} 실패: {e}")
    # 종목코드 중복 제거 후 이름순
    seen, uniq = set(), []
    for x in sorted(stocks, key=lambda d: d["n"]):
        if x["c"] in seen:
            continue
        seen.add(x["c"])
        uniq.append(x)
    return {
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "count": len(uniq),
        "errors": errors,
        "stocks": uniq,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/market/stocks.json")
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()

    data = collect(timeout=args.timeout)
    if not data["stocks"]:
        # 수집 실패 시 기존 파일을 덮어쓰지 않는다(검색이 통째로 비는 것을 막는다)
        log("수집된 종목이 없어 기존 파일을 유지합니다.")
        return 0 if os.path.exists(args.out) else 1
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    log(f"{data['count']}종목 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
