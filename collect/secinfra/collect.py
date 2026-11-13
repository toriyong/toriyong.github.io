"""보안·인프라 페이지 데이터 수집 → site/security/data/secinfra.json

수집 항목 (출처별로 독립 실행: 한 곳이 실패해도 나머지는 계속, 실패한 항목은 직전 데이터 유지)
  news         보안 뉴스 RSS — 제목·링크·출처·시각만 저장(본문 저장 안 함), 카테고리·심각도 자동 분류
  kev          CISA KEV — 실제 악용이 확인된 취약점(최근 N일 신규)
  patches      정기 패치 일정 — MS Patch Tuesday, Oracle CPU (계산)
  eol          지원 종료 일정 — endoflife.date 공개 API
  cloud        클라우드 상태 — Azure 상태 RSS + 각 사 상태 페이지 링크

사용 예
  python collect/secinfra/collect.py --out site/security/data/secinfra.json --prev /tmp/prev.json
  python collect/secinfra/collect.py --sample --out site/security/data/secinfra.json
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

import feedparser
import requests
import yaml

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UA = "toriyong.github.io data collector (+https://toriyong.github.io/)"
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "info": 3}
CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.I)


def log(msg: str) -> None:
    print(f"[secinfra] {msg}", file=sys.stderr)


def now() -> datetime:
    return datetime.now(KST)


def http_get(url: str, timeout: int = 25) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r


# ------------------------------------------------------------------ 분류
def compile_rules(patterns: list[str]) -> list:
    out = []
    for p in patterns:
        out.append(re.compile(p, re.I) if "\\" in p else p.lower())
    return out


def hit(text: str, rules: list) -> bool:
    t = f" {text.lower()} "
    return any((r.search(t) if isinstance(r, re.Pattern) else r in t) for r in rules)


def classify(title: str, cats: dict, sev: dict, kev_ids: set) -> tuple[list[str], str]:
    tags = [name for name, rules in cats.items() if hit(title, rules)]
    cves = {c.upper() for c in CVE_RE.findall(title)}
    if cves & kev_ids or hit(title, sev["critical"]):
        level = "critical"
    elif hit(title, sev["high"]):
        level = "high"
    elif hit(title, sev["medium"]):
        level = "medium"
    else:
        level = "info"
    return tags, level


# ------------------------------------------------------------------ 수집기
def collect_news(cfg: dict, kev_ids: set) -> tuple[list[dict], list[str]]:
    cats = {k: compile_rules(v) for k, v in cfg["categories"].items()}
    sev = {k: compile_rules(v) for k, v in cfg["severity"].items()}
    cutoff = now() - timedelta(days=cfg.get("news_days", 7))
    items, errors, seen = [], [], set()
    for f in cfg["feeds"]:
        try:
            parsed = feedparser.parse(http_get(f["url"]).content)
            if parsed.bozo and not parsed.entries:
                raise ValueError(f"RSS 파싱 실패: {parsed.bozo_exception}")
            n = 0
            for e in parsed.entries:
                title = re.sub(r"\s+", " ", (e.get("title") or "")).strip()
                link = e.get("link") or ""
                if not title or not link.startswith("http"):
                    continue
                st = e.get("published_parsed") or e.get("updated_parsed")
                ts = datetime.fromtimestamp(calendar.timegm(st), timezone.utc).astimezone(KST) if st else None
                if ts and ts < cutoff:
                    continue
                key = re.sub(r"[^0-9a-z가-힣]", "", title.lower())[:80]
                if key in seen:
                    continue
                seen.add(key)
                tags, level = classify(title, cats, sev, kev_ids)
                items.append({
                    "id": hashlib.sha1(link.encode()).hexdigest()[:12],
                    "title": title, "link": link, "source": f["name"], "region": f.get("region", "global"),
                    "published": ts.isoformat(timespec="minutes") if ts else None,
                    "categories": tags, "severity": level,
                    "cves": sorted({c.upper() for c in CVE_RE.findall(title)}),
                })
                n += 1
            log(f"뉴스 {f['name']}: {n}건")
        except Exception as ex:   # 출처 하나의 실패가 전체를 막지 않게
            errors.append(f"{f['name']}: {str(ex)[:120]}")
            log(f"뉴스 {f['name']} 실패: {ex}")
    items.sort(key=lambda x: x["published"] or "", reverse=True)
    return items[: cfg.get("max_items", 150)], errors


def pick_top(news: list[dict], cfg: dict) -> list[str]:
    """최근 top_hours 시간 안에서 심각도 → 최신순으로 상위 N건(없으면 전체에서)."""
    cutoff = (now() - timedelta(hours=cfg.get("top_hours", 48))).isoformat()
    pool = [n for n in news if (n["published"] or "") >= cutoff] or news
    pool = sorted(pool, key=lambda n: (SEV_ORDER[n["severity"]], -(datetime.fromisoformat(n["published"]).timestamp() if n["published"] else 0)))
    return [n["id"] for n in pool[: cfg.get("top_count", 5)]]


def collect_kev(cfg: dict) -> tuple[dict, set]:
    data = http_get(cfg["kev"]["url"], timeout=40).json()
    vulns = data.get("vulnerabilities", [])
    all_ids = {v["cveID"].upper() for v in vulns if v.get("cveID")}
    since = (now().date() - timedelta(days=cfg["kev"].get("days", 14))).isoformat()
    recent = [{
        "cve": v.get("cveID"), "vendor": v.get("vendorProject"), "product": v.get("product"),
        "name": v.get("vulnerabilityName"), "added": v.get("dateAdded"), "due": v.get("dueDate"),
        "ransomware": (v.get("knownRansomwareCampaignUse") or "").lower() == "known",
        "action": v.get("requiredAction"),
        "url": f"https://nvd.nist.gov/vuln/detail/{v.get('cveID')}",
    } for v in vulns if (v.get("dateAdded") or "") >= since]
    recent.sort(key=lambda v: v["added"] or "", reverse=True)
    log(f"KEV: 전체 {len(all_ids)}건, 최근 {len(recent)}건")
    return {"catalog_version": data.get("catalogVersion"), "total": len(all_ids),
            "days": cfg["kev"].get("days", 14), "recent": recent}, all_ids


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def collect_patches() -> list[dict]:
    """정기 패치 일정(미국 기준 발표일). 한국 시간으로는 다음 날 새벽에 공개됨."""
    today = now().date()
    out = []
    # MS Patch Tuesday: 매월 둘째 화요일
    y, m = today.year, today.month
    for _ in range(3):
        d = nth_weekday(y, m, calendar.TUESDAY, 2)
        if d >= today - timedelta(days=1):
            out.append({"name": "Microsoft Patch Tuesday", "date": d.isoformat(),
                        "kst_note": f"한국시간 {(d + timedelta(days=1)).isoformat()} 새벽 공개",
                        "url": "https://msrc.microsoft.com/update-guide/releaseNote/"})
            break
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    # Oracle CPU: 1·4·7·10월 셋째 화요일
    for yy in (today.year, today.year + 1):
        found = False
        for mm in (1, 4, 7, 10):
            d = nth_weekday(yy, mm, calendar.TUESDAY, 3)
            if d >= today - timedelta(days=1):
                out.append({"name": "Oracle Critical Patch Update", "date": d.isoformat(),
                            "kst_note": f"한국시간 {(d + timedelta(days=1)).isoformat()} 새벽 공개",
                            "url": "https://www.oracle.com/security-alerts/"})
                found = True
                break
        if found:
            break
    for p in out:
        p["d_day"] = (date.fromisoformat(p["date"]) - today).days
    return out


def collect_eol(cfg: dict) -> tuple[list[dict], list[str]]:
    today = now().date()
    warn = cfg["eol"].get("warn_days", 180)
    out, errors = [], []
    for p in cfg["eol"]["products"]:
        try:
            cycles = http_get(f"https://endoflife.date/api/{p['id']}.json").json()
            rows = []
            for c in cycles:
                eol = c.get("eol")
                eol_date = date.fromisoformat(eol) if isinstance(eol, str) else None
                if eol is True or (eol_date and eol_date < today - timedelta(days=30)):
                    continue                       # 이미 종료된 지 30일 지난 버전은 제외
                days_left = (eol_date - today).days if eol_date else None
                rows.append({
                    "cycle": str(c.get("cycle")), "latest": c.get("latest"),
                    "eol": eol_date.isoformat() if eol_date else None, "days_left": days_left,
                    "lts": bool(c.get("lts")),
                    "status": "ended" if days_left is not None and days_left < 0
                              else "warn" if days_left is not None and days_left <= warn else "ok",
                })
            out.append({"id": p["id"], "name": p["name"],
                        "url": f"https://endoflife.date/{p['id']}",
                        "cycles": rows[: cfg["eol"].get("max_cycles", 3)]})
            time.sleep(0.2)
        except Exception as ex:
            errors.append(f"EOL {p['name']}: {str(ex)[:120]}")
            log(f"EOL {p['name']} 실패: {ex}")
    return out, errors


def collect_cloud(cfg: dict) -> tuple[dict, list[str]]:
    incidents, errors = [], []
    cutoff = now() - timedelta(days=7)
    for f in cfg["cloud_status"].get("feeds", []):
        try:
            parsed = feedparser.parse(http_get(f["url"]).content)
            for e in parsed.entries[:20]:
                st = e.get("published_parsed") or e.get("updated_parsed")
                ts = datetime.fromtimestamp(calendar.timegm(st), timezone.utc).astimezone(KST) if st else None
                if ts and ts < cutoff:
                    continue
                incidents.append({"provider": f["name"], "title": (e.get("title") or "").strip(),
                                  "link": e.get("link"), "published": ts.isoformat(timespec="minutes") if ts else None})
        except Exception as ex:
            errors.append(f"상태 {f['name']}: {str(ex)[:120]}")
            log(f"상태 {f['name']} 실패: {ex}")
    return {"incidents": incidents, "links": cfg["cloud_status"].get("links", [])}, errors


# ------------------------------------------------------------------ 예시 데이터
def sample(cfg: dict) -> dict:
    t = now()
    iso = lambda h: (t - timedelta(hours=h)).isoformat(timespec="minutes")
    titles = [
        ("[예시] 웹 서버 모듈 제로데이 실제 악용 확인, 긴급 패치 권고", "보안뉴스", "kr", 3),
        ("[Sample] Ransomware gang claims breach of global logistics firm", "BleepingComputer", "global", 5),
        ("[Sample] Critical RCE flaw CVE-2026-00001 in popular PHP framework", "The Hacker News", "global", 8),
        ("[예시] 대형 게임사 회원정보 유출 정황… 개인정보보호위원회 조사 착수", "데일리시큐", "kr", 12),
        ("[Sample] Malicious npm packages target cloud credentials", "SecurityWeek", "global", 20),
        ("[Sample] Kubernetes container escape vulnerability patched", "The Hacker News", "global", 30),
        ("[예시] 생성형 AI 악용한 딥페이크 피싱 증가", "보안뉴스", "kr", 40),
        ("[Sample] CISA releases ICS advisories", "CISA Advisories", "global", 50),
    ]
    cats = {k: compile_rules(v) for k, v in cfg["categories"].items()}
    sev = {k: compile_rules(v) for k, v in cfg["severity"].items()}
    news = []
    for i, (ti, src, reg, h) in enumerate(titles):
        tags, lvl = classify(ti, cats, sev, set())
        news.append({"id": f"s{i}", "title": ti, "link": "https://example.com/", "source": src, "region": reg,
                     "published": iso(h), "categories": tags, "severity": lvl, "cves": CVE_RE.findall(ti)})
    d = lambda n: (t.date() - timedelta(days=n)).isoformat()
    return {
        "news": news,
        "kev": {"catalog_version": "sample", "total": 1500, "days": 14, "recent": [
            {"cve": "CVE-2026-00001", "vendor": "Example", "product": "Web Framework", "name": "Example RCE Vulnerability",
             "added": d(1), "due": d(-20), "ransomware": True, "action": "Apply mitigations per vendor instructions.",
             "url": "https://nvd.nist.gov/"},
            {"cve": "CVE-2026-00002", "vendor": "Example", "product": "VPN Gateway", "name": "Example Auth Bypass",
             "added": d(5), "due": d(-16), "ransomware": False, "action": "Apply updates.", "url": "https://nvd.nist.gov/"},
        ]},
        "eol": [
            {"id": "rocky-linux", "name": "Rocky Linux", "url": "https://endoflife.date/rocky-linux", "cycles": [
                {"cycle": "10", "latest": "10.0", "eol": "2035-05-31", "days_left": 3100, "lts": False, "status": "ok"},
                {"cycle": "9", "latest": "9.6", "eol": "2032-05-31", "days_left": 2000, "lts": False, "status": "ok"},
                {"cycle": "8", "latest": "8.10", "eol": "2029-05-31", "days_left": 900, "lts": False, "status": "ok"}]},
            {"id": "azure-kubernetes-service", "name": "AKS", "url": "https://endoflife.date/azure-kubernetes-service", "cycles": [
                {"cycle": "1.35", "latest": None, "eol": d(-300), "days_left": 300, "lts": False, "status": "ok"},
                {"cycle": "1.34", "latest": None, "eol": d(-120), "days_left": 120, "lts": False, "status": "warn"}]},
        ],
        "cloud": {"incidents": [{"provider": "Azure", "title": "[Sample] Mitigated - Networking in Korea Central",
                                 "link": "https://azure.status.microsoft/", "published": iso(30)}],
                  "links": cfg["cloud_status"]["links"]},
    }


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--prev")
    ap.add_argument("--config", default=os.path.join(ROOT, "config", "secinfra.yml"))
    ap.add_argument("--sample", action="store_true")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as fp:
        cfg = yaml.safe_load(fp)
    prev = {}
    if args.prev and os.path.exists(args.prev):
        try:
            with open(args.prev, encoding="utf-8") as fp:
                prev = json.load(fp)
        except (OSError, ValueError):
            prev = {}

    errors: list[str] = []
    stale: list[str] = []
    if args.sample:
        parts = sample(cfg)
    else:
        parts = {}
        kev_ids: set = set()
        try:
            parts["kev"], kev_ids = collect_kev(cfg)
        except Exception as ex:
            errors.append(f"KEV: {str(ex)[:120]}")
            parts["kev"] = prev.get("kev") or {"recent": [], "total": None}
            kev_ids = {v["cve"].upper() for v in parts["kev"].get("recent", []) if v.get("cve")}
            stale.append("kev")
        news, errs = collect_news(cfg, kev_ids)
        errors += errs
        if not news and prev.get("news"):
            news, _ = prev["news"], stale.append("news")
        parts["news"] = news
        eol, errs = collect_eol(cfg)
        errors += errs
        if not eol and prev.get("eol"):
            eol, _ = prev["eol"], stale.append("eol")
        parts["eol"] = eol
        parts["cloud"], errs = collect_cloud(cfg)
        errors += errs

    news = parts["news"]
    payload = {
        "updated_at": now().isoformat(timespec="minutes"),
        "sample": args.sample,
        "errors": errors,
        "stale_sections": stale,
        "top": pick_top(news, cfg) if news else [],
        "news": news,
        "summary": {
            "news_total": len(news),
            "critical": sum(1 for n in news if n["severity"] == "critical"),
            "high": sum(1 for n in news if n["severity"] == "high"),
            "by_category": {c: sum(1 for n in news if c in n["categories"]) for c in cfg["categories"]},
            "kev_recent": len(parts["kev"].get("recent", [])),
            "kev_ransomware": sum(1 for v in parts["kev"].get("recent", []) if v.get("ransomware")),
        },
        "kev": parts["kev"],
        "patches": collect_patches(),
        "eol": parts["eol"],
        "cloud": parts["cloud"],
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=1)
    log(f"뉴스 {len(news)}건, KEV 최근 {payload['summary']['kev_recent']}건, 오류 {len(errors)}건 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
