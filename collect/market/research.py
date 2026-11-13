"""증권사 리포트에서 관심종목의 목표주가를 모은다.

네이버 금융 '종목분석 리포트' 목록(공개)에서 관심종목 리포트를 찾고,
리포트 PDF 본문에서 '목표주가 00,000원' 형태의 숫자만 뽑아 쓴다.
원문은 저장하지도 보여주지도 않는다 — 목표가·증권사·날짜·원문 링크만 남긴다.

수집 전에 그 사이트의 robots.txt 를 읽어 허용 여부를 확인하고,
허용되지 않으면 아무것도 가져오지 않고 그대로 끝낸다.

- 출력: site/market/data/targets.json
    {"updated_at": ..., "allowed": true/false, "targets": {"005930": [{broker, price, date, url}]}}

사용: python collect/market/research.py --config config/watchlist.yml
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timedelta, timezone

import requests
import yaml

KST = timezone(timedelta(hours=9))
BASE = "https://finance.naver.com"
LIST = f"{BASE}/research/company_list.naver"
UA = "toriyong.github.io data collector (+https://toriyong.github.io)"
DAYS = 120            # 이 기간 안의 리포트만
MAX_PAGES = 8         # 목록 페이지 수 (한 페이지 30건)
MAX_PDF = 40          # 한 번에 열어 볼 PDF 수 상한
SLEEP = 0.4           # 요청 간격(상대 서버 배려)

ROW = re.compile(
    r"<tr[^>]*>\s*<td[^>]*class=\"type2\"[^>]*>(.*?)</td>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
LINK = re.compile(r"href=\"([^\"]*company_read[^\"]*)\"")
PDF = re.compile(r"href=\"(https?://[^\"]+\.pdf)\"", re.I)
DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{2})")

# "목표주가 79,000원", "목표주가를 158,000원으로", "TP 79,000원"
TARGET = re.compile(
    r"(?:목표\s*주가|목표가|적정\s*주가|TP)\s*(?:를|은|는|:)?\s*"
    r"([0-9][0-9,\.]{2,})\s*(원|KRW)?", re.I)


def log(msg: str) -> None:
    print(f"[research] {msg}", file=sys.stderr)


def text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).replace("\xa0", " ").strip()


def robots_ok(session: requests.Session, url: str, timeout: int = 15) -> bool:
    """그 사이트의 robots.txt 가 이 경로를 허용하는지 확인한다."""
    parts = urllib.parse.urlsplit(url)
    robots = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        r = session.get(robots, timeout=timeout)
    except requests.RequestException as e:
        log(f"robots.txt 를 읽지 못했습니다({type(e).__name__}) → 수집하지 않습니다.")
        return False
    if r.status_code == 404:
        log("robots.txt 없음 → 제한 없음으로 봅니다.")
        return True
    if r.status_code != 200:
        log(f"robots.txt HTTP {r.status_code} → 수집하지 않습니다.")
        return False
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(r.text.splitlines())
    ok = rp.can_fetch(UA, url) and rp.can_fetch("*", url)
    log(f"robots.txt 판정: {parts.path} → {'허용' if ok else '거부'}")
    return ok


def parse_price(s: str) -> int | None:
    v = re.sub(r"[,\s]", "", s or "")
    if "." in v:                      # 23.5(만원) 같은 표기는 쓰지 않는다
        return None
    try:
        n = int(v)
    except ValueError:
        return None
    return n if 100 <= n <= 100_000_000 else None


def list_reports(session: requests.Session, pages: int, timeout: int) -> list[dict]:
    """목록에서 (종목명, 증권사, 날짜, 상세 링크)를 모은다."""
    out, since = [], (datetime.now(KST).date() - timedelta(days=DAYS))
    for page in range(1, pages + 1):
        r = session.get(LIST, params={"page": page}, timeout=timeout)
        r.raise_for_status()
        body = r.content.decode("euc-kr", errors="replace")
        rows = 0
        for first, rest in ROW.findall(body):
            cells = [text(c) for c in CELL.findall(rest)]
            name = text(first)
            if not name or len(cells) < 3:
                continue
            m = DATE.search(" ".join(cells))
            if not m:
                continue
            y, mo, d = (2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
            try:
                day = datetime(y, mo, d).date()
            except ValueError:
                continue
            if day < since:
                return out                      # 목록은 최신순이라 더 볼 필요 없다
            href = LINK.search(rest)
            broker = next((c for c in cells if c.endswith("증권") or "투자" in c), "")
            out.append({"name": name, "broker": broker, "date": day.isoformat(),
                        "url": urllib.parse.urljoin(BASE + "/research/", href.group(1)) if href else ""})
            rows += 1
        if not rows:
            break
        time.sleep(SLEEP)
    return out


def target_from_pdf(session: requests.Session, url: str, timeout: int) -> int | None:
    """리포트 PDF 본문에서 목표주가 숫자만 뽑는다(원문은 저장하지 않는다)."""
    try:
        import pdfplumber
    except ImportError:
        return None
    try:
        r = session.get(url, timeout=timeout)
        r.raise_for_status()
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            body = "\n".join((p.extract_text() or "") for p in pdf.pages[:2])
    except Exception:
        return None
    cands = [parse_price(m.group(1)) for m in TARGET.finditer(body)]
    cands = [c for c in cands if c]
    if not cands:
        return None
    return max(set(cands), key=cands.count)     # 가장 자주 나온 값


def pdf_url(session: requests.Session, page_url: str, timeout: int) -> str | None:
    try:
        r = session.get(page_url, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException:
        return None
    m = PDF.search(r.content.decode("euc-kr", errors="replace"))
    return m.group(1) if m else None


def collect(names: dict[str, str], timeout: int = 30) -> dict:
    """names: {종목명: 종목코드}"""
    s = requests.Session()
    s.headers["User-Agent"] = UA
    out = {"updated_at": datetime.now(KST).isoformat(timespec="seconds"),
           "allowed": False, "targets": {}, "errors": []}

    if not robots_ok(s, LIST, timeout):
        out["errors"].append("robots.txt 가 허용하지 않아 수집하지 않았습니다.")
        return out
    out["allowed"] = True

    try:
        reports = list_reports(s, MAX_PAGES, timeout)
    except requests.RequestException as e:
        out["errors"].append(f"목록: {type(e).__name__}")
        return out
    log(f"리포트 목록 {len(reports)}건")

    mine = [r for r in reports if r["name"] in names][:MAX_PDF]
    log(f"관심종목 리포트 {len(mine)}건")
    for r in mine:
        if not r["url"]:
            continue
        link = pdf_url(s, r["url"], timeout)
        time.sleep(SLEEP)
        price = target_from_pdf(s, link, timeout) if link else None
        time.sleep(SLEEP)
        if not price:
            continue
        code = names[r["name"]]
        out["targets"].setdefault(code, []).append(
            {"broker": r["broker"] or None, "price": price, "date": r["date"], "url": link})
    log(f"목표가 추출 {sum(len(v) for v in out['targets'].values())}건")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/watchlist.yml")
    ap.add_argument("--out", default="site/market/data/targets.json")
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as fp:
        stocks = (yaml.safe_load(fp) or {}).get("stocks") or []
    names = {str(x.get("name")): str(x.get("stock_code", "")).zfill(6) for x in stocks if x.get("name")}
    if not names:
        log("관심종목이 없습니다.")
        return 0

    data = collect(names, timeout=args.timeout)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
