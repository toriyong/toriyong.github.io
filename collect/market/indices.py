"""국내·미국 주요 지수와 환율·원자재 시세를 모은다 (증시 탭 상단 지수 보드용).

- 출처: Yahoo Finance 차트 API (키 불필요). 국내 지수는 거래소 사정상 약 20분 지연, 미국 지수는 실시간에 가깝다.
  ※ 비공식 API라 응답 형식이 바뀌거나 막힐 수 있다. 종목별로 실패하면 직전 값(--prev)을 그대로 두고 stale 로 표시한다.
- 이전 출처(금융위원회 지수시세정보·FRED)는 '다음 영업일 오후'에야 전날 종가가 나와서
  당일 시세를 보여 줄 수 없었기 때문에 교체했다.
- 출력: site/market/data/indices.json
    {"updated_at", "source", "errors": [...],
     "sections": [{"id","name","main":[item...],"sub":[item...]}]}
    item = {"sym","name","value","diff","rate","prev","high","low","w52h","w52l",
            "time"(KST ISO),"state"("open"|"closed"),"tz_offset"(초),"points":[[epoch,값]...](main 만)}

사용: python collect/market/indices.py --out site/market/data/indices.json [--prev 이전파일]
     python collect/market/indices.py --sample --out ...   # 네트워크 없이 화면 확인용 예시 데이터
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

KST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
HOSTS = ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]

# (심볼, 표시 이름, 배율) — 배율은 원/100엔처럼 단위를 바꿀 때만 쓴다.
# 배치는 네이버 증시 상단과 맞췄다: 한국이 위, 미국이 아래. main 은 장중 차트가 있는 큰 카드.
SECTIONS = [
    {
        "id": "kr", "name": "국내",
        "main": [("^KS11", "코스피", 1), ("^KQ11", "코스닥", 1)],
        "sub": [("^KS200", "코스피 200", 1), ("KRW=X", "원/달러", 1), ("JPYKRW=X", "원/100엔", 100),
                ("DX-Y.NYB", "달러인덱스", 1), ("GC=F", "국제 금", 1), ("CL=F", "WTI", 1)],
    },
    {
        "id": "us", "name": "미국",
        "main": [("^GSPC", "S&P 500", 1), ("^IXIC", "나스닥 종합", 1), ("^DJI", "다우존스", 1)],
        "sub": [("^SOX", "필라델피아 반도체", 1), ("^NDX", "나스닥 100", 1),
                ("^DJT", "다우운송", 1), ("^VIX", "VIX", 1)],
    },
]


def log(msg: str) -> None:
    print(f"[indices] {msg}", file=sys.stderr)


def fnum(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def r2(v):
    return None if v is None else round(v, 2)


def fetch_chart(session: requests.Session, sym: str, timeout: int) -> dict:
    """Yahoo 차트 API (당일 5분봉). 호스트 두 곳을 번갈아 최대 3번 시도."""
    last = None
    for attempt in range(3):
        host = HOSTS[attempt % len(HOSTS)]
        try:
            r = session.get(f"{host}/v8/finance/chart/{quote(sym)}", timeout=timeout,
                            params={"range": "1d", "interval": "5m", "includePrePost": "false"})
            if r.status_code == 429:
                raise RuntimeError("429 요청 과다")
            r.raise_for_status()
            res = (r.json().get("chart") or {}).get("result") or []
            if not res:
                raise RuntimeError("빈 응답")
            return res[0]
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{sym}: {last}")


def parse_chart(res: dict, sym: str, name: str, scale: float, with_points: bool, now: float) -> dict:
    """차트 응답 → 카드 한 장. 전일 종가 대비 등락을 계산한다."""
    meta = res.get("meta") or {}
    ts = res.get("timestamp") or []
    closes = (((res.get("indicators") or {}).get("quote") or [{}])[0].get("close")) or []
    pts = [(int(t), fnum(c)) for t, c in zip(ts, closes)]
    pts = [(t, c * scale) for t, c in pts if c is not None]

    price = fnum(meta.get("regularMarketPrice"))
    price = price * scale if price is not None else (pts[-1][1] if pts else None)
    if price is None:
        raise RuntimeError(f"{sym}: 현재가 없음")
    prev = fnum(meta.get("previousClose"))
    if prev is None:
        prev = fnum(meta.get("chartPreviousClose"))
    prev = prev * scale if prev is not None else None

    def sc(k):
        v = fnum(meta.get(k))
        return v * scale if v is not None else None

    high, low = sc("regularMarketDayHigh"), sc("regularMarketDayLow")
    if pts:
        vals = [c for _, c in pts]
        high = max(vals + ([high] if high is not None else []))
        low = min(vals + ([low] if low is not None else []))

    mt = int(meta.get("regularMarketTime") or (pts[-1][0] if pts else now))
    reg = ((meta.get("currentTradingPeriod") or {}).get("regular")) or {}
    start, end = reg.get("start"), reg.get("end")
    state = "open" if start and end and start <= now <= end and now - mt < 3600 else "closed"

    item = {
        "sym": sym, "name": name,
        "value": r2(price),
        "prev": r2(prev),
        "diff": r2(price - prev) if prev is not None else None,
        "rate": r2((price / prev - 1) * 100) if prev else None,
        "high": r2(high), "low": r2(low),
        "w52h": r2(sc("fiftyTwoWeekHigh")), "w52l": r2(sc("fiftyTwoWeekLow")),
        "time": datetime.fromtimestamp(mt, KST).isoformat(timespec="minutes"),
        "state": state,
        "tz_offset": int(meta.get("gmtoffset") or 0),
    }
    if with_points:
        item["points"] = [[t, round(c, 2)] for t, c in pts]
    return item


def load_prev(path: str | None) -> dict[str, dict]:
    """직전 파일에서 심볼별 카드를 꺼낸다 (예전 groups 형식은 무시)."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fp:
            d = json.load(fp)
    except Exception:
        return {}
    out = {}
    for s in d.get("sections") or []:
        for it in (s.get("main") or []) + (s.get("sub") or []):
            if it.get("sym"):
                out[it["sym"]] = it
    return out


def sample_item(sym: str, name: str, base: float, main: bool, tz: int, seed: int) -> dict:
    """--sample 용 가짜 시세 (화면 확인 전용)."""
    import random
    rnd = random.Random(seed)
    day = datetime.now(KST).replace(hour=9, minute=0, second=0, microsecond=0)
    t0 = int(day.timestamp())
    pts, v = [], base
    for i in range(78):
        v *= 1 + rnd.uniform(-0.0012, 0.0013)
        pts.append([t0 + i * 300, round(v, 2)])
    prev = base * (1 + rnd.uniform(-0.01, 0.01))
    vals = [p[1] for p in pts]
    it = {
        "sym": sym, "name": name, "value": round(v, 2), "prev": round(prev, 2),
        "diff": round(v - prev, 2), "rate": round((v / prev - 1) * 100, 2),
        "high": max(vals), "low": min(vals), "w52h": round(base * 1.18, 2), "w52l": round(base * 0.82, 2),
        "time": datetime.fromtimestamp(pts[-1][0], KST).isoformat(timespec="minutes"),
        "state": "closed", "tz_offset": tz,
    }
    if main:
        it["points"] = pts
    return it


SAMPLE_BASE = {"^KS11": 4711, "^KQ11": 655, "^KS200": 727, "KRW=X": 1343, "JPYKRW=X": 905,
               "DX-Y.NYB": 103.6, "GC=F": 3584, "CL=F": 84.7, "^GSPC": 7182, "^IXIC": 23585,
               "^DJI": 50182, "^SOX": 8774, "^NDX": 26046, "^DJT": 20308, "^VIX": 27.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/market/data/indices.json")
    ap.add_argument("--prev", default=None, help="직전 indices.json (실패한 종목은 이 값을 유지)")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--sample", action="store_true", help="네트워크 없이 예시 데이터 생성")
    args = ap.parse_args()

    prev = load_prev(args.prev or args.out)
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    now = time.time()
    errors: list[str] = []
    ok = 0
    sections = []
    for sec in SECTIONS:
        tz = 32400 if sec["id"] == "kr" else -18000
        out = {"id": sec["id"], "name": sec["name"], "main": [], "sub": []}
        for part in ("main", "sub"):
            for i, (sym, name, scale) in enumerate(sec[part]):
                if args.sample:
                    out[part].append(sample_item(sym, name, SAMPLE_BASE.get(sym, 100), part == "main", tz, i + len(sym)))
                    ok += 1
                    continue
                try:
                    item = parse_chart(fetch_chart(s, sym, args.timeout), sym, name, scale, part == "main", now)
                    ok += 1
                except Exception as e:
                    errors.append(str(e)[:160])
                    item = prev.get(sym)
                    if item:
                        item = {**item, "name": name, "stale": True}
                if item:
                    out[part].append(item)
                time.sleep(0.3)
        sections.append(out)

    if ok == 0:
        for e in errors[:5]:
            log(e)
        log("새로 받은 시세가 없어 기존 파일을 유지합니다.")
        return 0 if os.path.exists(args.out) else 1

    data = {
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "예시 데이터" if args.sample else "Yahoo Finance",
        "errors": errors[:5],
        "sections": sections,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    log(f"{ok}개 갱신, 실패 {len(errors)}개 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
