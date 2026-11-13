"""보안·인프라 페이지 데이터 수집 → site/security/data/secinfra.json

원칙: 공식 기관 발표를 우선하고, 언론 보도는 신뢰 매체의 대형 사고만 소량 보여 준다.
      제목·링크·날짜·점수만 저장한다(기사·공지 본문은 저장하지 않음).

수집 항목 (출처별 독립 실행: 한 곳이 실패해도 나머지는 계속, 실패한 항목은 직전 데이터 유지)
  official   공식 보안 공지 — KISA 보안공지, 금융보안원 보도자료·취약점 정보, CISA Advisories
  cves       최근 CVE — 국내(KISA KNVD, 한글 제목) / 글로벌(NVD Critical)
  kev        CISA KEV — 실제 악용이 확인된 취약점
  media      주요 사고 보도 — 신뢰 매체만, 같은 사건은 묶어서 보도 매체 수가 많은 순
  분류       모든 항목에 사이버 킬 체인 단계 · 제로트러스트 영역 태그
  patches    정기 패치 일정(MS Patch Tuesday, Oracle CPU)
  eol        지원 종료 일정(endoflife.date)
  cloud      클라우드 상태(Azure RSS + 각 사 상태 페이지 링크)

사용 예
  python collect/secinfra/collect.py --out site/security/data/secinfra.json --prev /tmp/prev.json
  python collect/secinfra/collect.py --sample --out site/security/data/secinfra.json
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import html
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
CVE_RE = re.compile(r"\b(?:CVE|FVE)-\d{4}-\d{4,7}\b", re.I)



_KEY_RE = re.compile(r"(?i)\b(serviceKey|crtfc_key|api_?key|access_?token|token|key)=[^&\s'\"]+")


def redact(msg) -> str:
    """오류 문자열에서 URL 쿼리의 인증키 값을 지운다(공개 JSON·로그에 키가 남지 않도록)."""
    s = _KEY_RE.sub(lambda m: m.group(1) + "=***", str(msg))
    return re.sub(r"for url: \S+", "", s).strip()

def log(msg: str) -> None:
    print(f"[secinfra] {msg}", file=sys.stderr)


def now() -> datetime:
    return datetime.now(KST)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="minutes") if dt else None


def http_get(url: str, timeout: int = 25, **kw) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, **kw)
    r.raise_for_status()
    return r


def http_post_json(url: str, body: dict, timeout: int = 25) -> dict:
    r = requests.post(url, json=body, headers={"User-Agent": UA, "Content-Type": "application/json; charset=UTF-8"}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def entry_time(e) -> datetime | None:
    st = e.get("published_parsed") or e.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(st), timezone.utc).astimezone(KST) if st else None


def uid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


# ------------------------------------------------------------------ 분류
class Classifier:
    def __init__(self, cfg: dict, kev_ids: set[str]):
        comp = lambda keys: [k.lower() for k in keys]
        self.sev = {k: comp(v) for k, v in cfg["severity"].items()}
        self.kc = [(g["id"], comp(g["keys"])) for g in cfg["killchain"]]
        self.zt = [(g["id"], comp(g["keys"])) for g in cfg["zerotrust"]]
        self.kev_ids = kev_ids

    @staticmethod
    def _hit(text: str, keys: list[str]) -> bool:
        t = f" {text.lower()} "
        return any(k in t for k in keys)

    def severity(self, text: str, cvss: float | None = None) -> str:
        if cvss is not None:
            return "critical" if cvss >= 9 else "high" if cvss >= 7 else "medium" if cvss >= 4 else "info"
        ids = {c.upper() for c in CVE_RE.findall(text)}
        if ids & self.kev_ids or self._hit(text, self.sev["critical"]):
            return "critical"
        for level in ("high", "medium"):
            if self._hit(text, self.sev[level]):
                return level
        return "info"

    def tags(self, text: str) -> dict:
        return {"killchain": [i for i, k in self.kc if self._hit(text, k)],
                "zerotrust": [i for i, k in self.zt if self._hit(text, k)]}


# ------------------------------------------------------------------ 1. 공식 보안 공지
def collect_official(cfg: dict, clf: Classifier, seen: dict) -> tuple[list[dict], list[str]]:
    items, errors = [], []
    cutoff = now() - timedelta(days=30)
    for src in cfg["official"]:
        try:
            rows = []
            if src["type"] == "rss":
                for e in feedparser.parse(http_get(src["url"]).content).entries[:30]:
                    title = re.sub(r"\s+", " ", e.get("title") or "").strip()
                    link = e.get("link") or ""
                    if title and link.startswith("http"):
                        rows.append((title, link, entry_time(e), rss_summary(e, title, 90)))
            elif src["type"] == "fsec":       # 금융보안원 홈페이지 게시판 목록 API (RSS 미제공)
                data = http_post_json(f"{src['base']}/bbs/list", {
                    "menuNo": str(src["menu"]), "pagingSearchDto": {"page": 1, "pageSize": 10, "searchContents": ""}})
                for b in (data.get("resultData") or [])[:15]:
                    title = html.unescape(re.sub(r"\s+", " ", b.get("title") or "")).strip()
                    reg = b.get("regDate")
                    ts = datetime.fromisoformat(reg).replace(tzinfo=KST) if reg else None
                    link = f"{src['base']}/bbs/detail?menuNo={src['menu']}&bbsNo={b.get('bbsNo')}"
                    if title:
                        rows.append((title, link, ts, None))
            n = 0
            for title, link, ts, summary in rows:
                ts = ts or seen.get(link) or now()          # 날짜 없는 RSS는 처음 수집한 시각
                if ts < cutoff:
                    continue
                items.append({"id": uid(link), "title": title, "link": link, "summary": summary, "org": src["org"], "source": src["name"],
                              "published": iso(ts), "dated": bool(rows) and ts is not None,
                              "severity": clf.severity(title), "cves": sorted({c.upper() for c in CVE_RE.findall(title)}),
                              **clf.tags(title)})
                n += 1
            log(f"공식 {src['name']}: {n}건")
        except Exception as ex:
            errors.append(f"{src['name']}: {redact(ex)[:120]}")
            log(f"공식 {src['name']} 실패: {ex}")
    items.sort(key=lambda x: x["published"] or "", reverse=True)
    return items[: cfg.get("official_max", 40)], errors


# ------------------------------------------------------------------ 2. 최근 CVE
KNVD_ROW = re.compile(r"\|\s*((?:CVE|FVE)-\d{4}-\d+)\s*\|\s*([\d.]+)\s*\|\s*([A-Za-z]+)\s*\|")


def collect_cve_kr(cfg: dict, clf: Classifier, seen: dict) -> list[dict]:
    c = cfg["cve"]["kr"]
    out = []
    for e in feedparser.parse(http_get(c["url"]).content).entries[: c.get("max", 20)]:
        raw = re.sub(r"\s+", " ", e.get("title") or "").strip()
        link = e.get("link") or ""
        if not raw or not link.startswith("http"):
            continue
        cve, _, title = raw.partition("|")
        cve, title = cve.strip(), (title.strip() or raw)
        m = KNVD_ROW.search(html.unescape(e.get("summary") or e.get("description") or ""))
        cvss = float(m.group(2)) if m else None
        ts = entry_time(e) or seen.get(link) or now()
        out.append({"id": cve.upper() if CVE_RE.fullmatch(cve) else uid(link), "title": title, "link": link,
                    "cvss": cvss, "severity": clf.severity(raw, cvss), "published": iso(ts),
                    "kev": cve.upper() in clf.kev_ids, "source": "KISA KNVD", **clf.tags(title)})
    return out


def collect_cve_global(cfg: dict, clf: Classifier) -> list[dict]:
    c = cfg["cve"]["global"]
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=c.get("days", 7))
    fmt = "%Y-%m-%dT%H:%M:%S.000"
    # NVD API 는 느리고 자주 시간 초과가 난다 → 3번까지 재시도(간격 늘림), API 키가 있으면 사용(호출 한도 상향)
    params = {"pubStartDate": start.strftime(fmt), "pubEndDate": end.strftime(fmt),
              "cvssV3Severity": c.get("severity", "CRITICAL"), "resultsPerPage": 100}
    headers = {"apiKey": os.environ["NVD_API_KEY"]} if os.environ.get("NVD_API_KEY") else {}
    data, last = None, None
    for attempt in range(3):
        try:
            r = requests.get(c["url"], params=params, timeout=(10, 90), headers={"User-Agent": UA, **headers})
            r.raise_for_status()
            data = r.json()
            break
        except (requests.RequestException, ValueError) as e:
            last = e
            log(f"NVD 재시도 {attempt + 1}/3: {redact(e)}")
            time.sleep(6 * (attempt + 1))
    if data is None:
        raise last
    out = []
    for v in data.get("vulnerabilities", []):
        cve = v.get("cve", {})
        cid = cve.get("id")
        desc = next((d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"), "")
        score = None
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV40"):
            mets = cve.get("metrics", {}).get(key) or []
            if mets:
                score = mets[0].get("cvssData", {}).get("baseScore")
                break
        product = None
        for conf in cve.get("configurations", []) or []:
            for node in conf.get("nodes", []):
                for mt in node.get("cpeMatch", []):
                    parts = (mt.get("criteria") or "").split(":")
                    if len(parts) > 5:
                        product = f"{parts[3]} {parts[4]}".replace("_", " ")
                        break
                if product:
                    break
            if product:
                break
        pub = cve.get("published")
        ts = datetime.fromisoformat(pub.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).astimezone(KST) if pub else None
        short = re.sub(r"\s+", " ", desc).strip()
        short = (short[:117] + "…") if len(short) > 120 else short
        out.append({"id": cid, "title": product or short.split(".")[0][:60], "summary": short,
                    "link": f"https://nvd.nist.gov/vuln/detail/{cid}", "cvss": score,
                    "severity": clf.severity(desc, score), "published": iso(ts),
                    "kev": (cid or "").upper() in clf.kev_ids, "source": "NVD", **clf.tags(f"{product or ''} {desc}")})
    out.sort(key=lambda x: x["published"] or "", reverse=True)
    return out[: c.get("max", 25)]


# ------------------------------------------------------------------ KEV
def collect_kev(cfg: dict) -> tuple[dict, set]:
    data = http_get(cfg["kev"]["url"], timeout=40).json()
    vulns = data.get("vulnerabilities", [])
    all_ids = {v["cveID"].upper() for v in vulns if v.get("cveID")}
    since = (now().date() - timedelta(days=cfg["kev"].get("days", 14))).isoformat()
    recent = [{
        "cve": v.get("cveID"), "vendor": v.get("vendorProject"), "product": v.get("product"),
        "name": v.get("vulnerabilityName"), "added": v.get("dateAdded"), "due": v.get("dueDate"),
        "ransomware": (v.get("knownRansomwareCampaignUse") or "").lower() == "known",
        "url": f"https://nvd.nist.gov/vuln/detail/{v.get('cveID')}",
    } for v in vulns if (v.get("dateAdded") or "") >= since]
    recent.sort(key=lambda v: v["added"] or "", reverse=True)
    log(f"KEV: 전체 {len(all_ids)}건, 최근 {len(recent)}건")
    return {"catalog_version": data.get("catalogVersion"), "total": len(all_ids),
            "days": cfg["kev"].get("days", 14), "recent": recent}, all_ids


# ------------------------------------------------------------------ 3. 주요 사고 보도
STOP = {"해킹", "개인정보", "유출", "피해", "확인", "보안", "정보", "고객", "기업", "사고", "공격", "논란", "조사", "발생", "의혹",
        "이름", "연락처", "등", "및", "노출", "뉴스", "단독", "속보", "종합", "중", "또", "도", "the", "a", "of", "to", "in", "and", "for"}


def tokens(title: str) -> list[str]:
    t = re.sub(r"[^\w가-힣]+", " ", title.lower())
    return [w for w in t.split() if len(w) >= 2 and w not in STOP]


def _same_word(x: str, y: str) -> bool:
    """'KB캐피탈' 과 'KB캐피탈도' 처럼 조사가 붙은 경우도 같은 단어로 본다."""
    if x == y:
        return True
    short, long_ = sorted((x, y), key=len)
    return len(short) >= 3 and long_.startswith(short) and len(long_) - len(short) <= 2


def same_story(a: list[str], b: list[str]) -> bool:
    if not a or not b:
        return False
    common = sum(1 for x in set(a) if any(_same_word(x, y) for y in set(b)))
    if common / len(set(a) | set(b)) >= 0.3:
        return True
    # 제목 앞부분의 고유명사(회사·서비스명)가 같으면 같은 사건
    return any(len(x) >= 3 and _same_word(x, y) for x in a[:3] for y in b[:3])


def rss_summary(e, title: str, limit: int) -> str | None:
    """RSS 가 제공하는 요약(description)을 한 줄 부제목으로. 본문은 가져오지 않는다."""
    raw = e.get("summary") or e.get("description") or ""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()
    if not text or text[:20] in title or title[:20] in text[:40] and len(text) < len(title) + 10:
        return None                                  # 구글 뉴스처럼 제목·링크만 반복하는 요약은 버림
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def collect_media(cfg: dict, clf: Classifier) -> tuple[list[dict], list[str]]:
    m = cfg["media"]
    trusted = set(m.get("trusted_kr", []))
    min_rank = SEV_ORDER[m.get("min_severity", "high")]
    kr_rank = SEV_ORDER[m.get("kr_min_severity", "info")]
    exclude = [x.lower() for x in m.get("exclude", [])]
    limit = m.get("summary_chars", 90)
    cutoff = now() - timedelta(hours=m.get("hours", 72))
    articles, errors = [], []
    for f in m["feeds"]:
        try:
            for e in feedparser.parse(http_get(f["url"]).content).entries[:100]:
                title = re.sub(r"\s+", " ", e.get("title") or "").strip()
                outlet = f.get("outlet") or (e.get("source") or {}).get("title") or ""
                if outlet and title.endswith(f" - {outlet}"):
                    title = title[: -len(outlet) - 3].strip()
                ts = entry_time(e)
                if not title or (ts and ts < cutoff):
                    continue
                if any(x in title.lower() for x in exclude):
                    continue
                kr = f.get("region") == "kr"
                if kr and outlet not in trusted:
                    continue
                sev = clf.severity(title)
                if SEV_ORDER[sev] > (kr_rank if kr else min_rank):
                    continue
                articles.append({"title": title, "link": e.get("link"), "outlet": outlet, "region": f.get("region"),
                                 "summary": rss_summary(e, title, limit),
                                 "published": iso(ts), "severity": sev, "tok": tokens(title)})
        except Exception as ex:
            errors.append(f"언론 {f['name']}: {redact(ex)[:120]}")
            log(f"언론 {f['name']} 실패: {redact(ex)}")
    # 같은 사건 묶기
    clusters: list[dict] = []
    for a in sorted(articles, key=lambda x: x["published"] or ""):
        for c in clusters:
            if c["region"] == a["region"] and same_story(c["tok"], a["tok"]):
                c["arts"].append(a)
                break
        else:
            clusters.append({"region": a["region"], "tok": a["tok"], "arts": [a]})
    out = []
    for c in clusters:
        arts = c["arts"]
        outlets = sorted({x["outlet"] for x in arts})
        rep = min(arts, key=lambda x: (SEV_ORDER[x["severity"]], -len(x["title"])))   # 심각도 높고 제목이 구체적인 기사
        summary = rep["summary"] or next((x["summary"] for x in arts if x["summary"]), None)
        text = " ".join(x["title"] for x in arts)
        out.append({"id": uid(rep["link"] or rep["title"]), "title": rep["title"], "link": rep["link"], "summary": summary,
                    "outlet": rep["outlet"], "outlets": outlets, "count": len(outlets), "region": c["region"],
                    "published": max(x["published"] or "" for x in arts) or None,
                    "severity": min((x["severity"] for x in arts), key=lambda s: SEV_ORDER[s]), **clf.tags(text)})
    key = lambda x: (-x["count"], SEV_ORDER[x["severity"]], -(datetime.fromisoformat(x["published"]).timestamp() if x["published"] else 0))
    kr = sorted([x for x in out if x["region"] == "kr"], key=key)
    gl = sorted([x for x in out if x["region"] != "kr"], key=key)[: m.get("global_max", 3)]
    log(f"언론: 기사 {len(articles)}건 → 사건 국내 {len(kr)} · 해외 {len(gl)}")
    return kr[: m.get("max_clusters", 12)] + gl, errors


# ------------------------------------------------------------------ 4. 인프라
def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def collect_patches() -> list[dict]:
    """정기 패치 일정(미국 기준 발표일). 한국 시간으로는 다음 날 새벽에 공개됨."""
    today = now().date()
    out = []
    y, m = today.year, today.month
    for _ in range(3):                                    # MS Patch Tuesday: 매월 둘째 화요일
        d = nth_weekday(y, m, calendar.TUESDAY, 2)
        if d >= today - timedelta(days=1):
            out.append({"name": "Microsoft Patch Tuesday", "date": d.isoformat(),
                        "kst_note": f"한국시간 {(d + timedelta(days=1)).isoformat()} 새벽 공개",
                        "url": "https://msrc.microsoft.com/update-guide/releaseNote/"})
            break
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    done = False
    for yy in (today.year, today.year + 1):               # Oracle CPU: 1·4·7·10월 셋째 화요일
        for mm in (1, 4, 7, 10):
            d = nth_weekday(yy, mm, calendar.TUESDAY, 3)
            if d >= today - timedelta(days=1):
                out.append({"name": "Oracle Critical Patch Update", "date": d.isoformat(),
                            "kst_note": f"한국시간 {(d + timedelta(days=1)).isoformat()} 새벽 공개",
                            "url": "https://www.oracle.com/security-alerts/"})
                done = True
                break
        if done:
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
            rows = []
            for c in http_get(f"https://endoflife.date/api/{p['id']}.json").json():
                eol = c.get("eol")
                eol_date = date.fromisoformat(eol) if isinstance(eol, str) else None
                if eol is True or (eol_date and eol_date < today - timedelta(days=30)):
                    continue
                days_left = (eol_date - today).days if eol_date else None
                rows.append({"cycle": str(c.get("cycle")), "latest": c.get("latest"),
                             "eol": eol_date.isoformat() if eol_date else None, "days_left": days_left,
                             "lts": bool(c.get("lts")),
                             "status": "ended" if days_left is not None and days_left < 0
                                       else "warn" if days_left is not None and days_left <= warn else "ok"})
            out.append({"id": p["id"], "name": p["name"], "url": f"https://endoflife.date/{p['id']}",
                        "cycles": rows[: cfg["eol"].get("max_cycles", 3)]})
            time.sleep(0.2)
        except Exception as ex:
            errors.append(f"EOL {p['name']}: {redact(ex)[:120]}")
            log(f"EOL {p['name']} 실패: {ex}")
    return out, errors


def collect_cloud(cfg: dict) -> tuple[dict, list[str]]:
    incidents, errors = [], []
    cutoff = now() - timedelta(days=7)
    for f in cfg["cloud_status"].get("feeds", []):
        try:
            for e in feedparser.parse(http_get(f["url"]).content).entries[:20]:
                ts = entry_time(e)
                if ts and ts < cutoff:
                    continue
                incidents.append({"provider": f["name"], "title": (e.get("title") or "").strip(),
                                  "link": e.get("link"), "published": iso(ts)})
        except Exception as ex:
            errors.append(f"상태 {f['name']}: {redact(ex)[:120]}")
            log(f"상태 {f['name']} 실패: {ex}")
    return {"incidents": incidents, "links": cfg["cloud_status"].get("links", [])}, errors


# ------------------------------------------------------------------ 예시 데이터
def sample(cfg: dict) -> dict:
    t = now()
    ago = lambda h: iso(t - timedelta(hours=h))
    clf = Classifier(cfg, {"CVE-2026-00001"})
    off = [("KISA", "KISA 보안공지", "[예시] Apache 제품 보안 업데이트 권고", 3),
           ("금융보안원", "금융보안원 보도자료", "[예시] 금융보안원, 금융권 대상 피싱 사칭 주의 당부", 20),
           ("금융보안원", "금융보안원 취약점 정보", "FVE-2026-0001 | [예시] 그룹웨어 임의 파일 업로드 취약점", 30),
           ("KISA", "KISA 보안공지", "[예시] VPN 제품 인증 우회 취약점 긴급 보안 업데이트 권고", 50),
           ("CISA", "CISA Advisories", "[Sample] CISA Releases Industrial Control Systems Advisories", 60)]
    official = [{"id": f"o{i}", "title": ti, "link": "https://example.com/", "org": org, "source": src,
                 "published": ago(h), "dated": True, "severity": clf.severity(ti), "cves": CVE_RE.findall(ti), **clf.tags(ti)}
                for i, (org, src, ti, h) in enumerate(off)]
    kr = [{"id": f"CVE-2026-0000{i}", "title": ti, "link": "https://example.com/", "cvss": s,
           "severity": clf.severity(ti, s), "published": ago(h), "kev": False, "source": "KISA KNVD", **clf.tags(ti)}
          for i, (ti, s, h) in enumerate([("[예시] 보안 솔루션 운영체제 명령어 삽입", 9.8, 4),
                                          ("[예시] NAC 제품 원격 코드 실행", 8.4, 6),
                                          ("[예시] 웹 메일 크로스사이트 스크립팅", 5.4, 26)], 2)]
    gl = [{"id": "CVE-2026-00001", "title": "example web framework", "summary": "[Sample] Unauthenticated remote code execution via crafted request.",
           "link": "https://nvd.nist.gov/", "cvss": 9.8, "severity": "critical", "published": ago(10), "kev": True,
           "source": "NVD", **clf.tags("web framework remote code execution")}]
    media = [{"id": "m1", "title": "[예시] 업무 메신저 해킹으로 개인정보 유출", "link": "https://example.com/", "outlet": "연합뉴스",
              "outlets": ["KBS 뉴스", "연합뉴스", "한겨레", "보안뉴스"], "count": 4, "region": "kr", "published": ago(2),
              "severity": "high", **clf.tags("메신저 해킹 개인정보 유출 계정")},
             {"id": "m2", "title": "[Sample] Ransomware gang claims breach of logistics firm", "link": "https://example.com/",
              "outlet": "BleepingComputer", "outlets": ["BleepingComputer"], "count": 1, "region": "global",
              "published": ago(8), "severity": "high", **clf.tags("ransomware breach")}]
    d = lambda n: (t.date() - timedelta(days=n)).isoformat()
    return {
        "official": official, "cves": {"kr": kr, "global": gl}, "media": media,
        "kev": {"catalog_version": "sample", "total": 1500, "days": 14, "recent": [
            {"cve": "CVE-2026-00001", "vendor": "Example", "product": "Web Framework", "name": "Example RCE Vulnerability",
             "added": d(1), "due": d(-20), "ransomware": True, "url": "https://nvd.nist.gov/"}]},
        "eol": [{"id": "rocky-linux", "name": "Rocky Linux", "url": "https://endoflife.date/rocky-linux", "cycles": [
                    {"cycle": "9", "latest": "9.6", "eol": "2032-05-31", "days_left": 2000, "lts": False, "status": "ok"},
                    {"cycle": "8", "latest": "8.10", "eol": "2029-05-31", "days_left": 900, "lts": False, "status": "ok"}]},
                {"id": "azure-kubernetes-service", "name": "AKS", "url": "https://endoflife.date/azure-kubernetes-service", "cycles": [
                    {"cycle": "1.35", "latest": None, "eol": d(-138), "days_left": 138, "lts": False, "status": "warn"}]}],
        "cloud": {"incidents": [], "links": cfg["cloud_status"]["links"]},
    }


# ------------------------------------------------------------------ main
def seen_index(prev: dict) -> dict:
    """직전 데이터에서 링크별 최초 수집 시각(날짜 없는 RSS 항목용)."""
    out = {}
    for it in (prev.get("official") or []) + ((prev.get("cves") or {}).get("kr") or []):
        if it.get("link") and it.get("published"):
            try:
                out[it["link"]] = datetime.fromisoformat(it["published"])
            except ValueError:
                pass
    return out


def summarize(cfg: dict, parts: dict) -> dict:
    pool = parts["official"] + parts["cves"]["kr"] + parts["cves"]["global"] + parts["media"]
    kc = {g["id"]: sum(1 for x in pool if g["id"] in x.get("killchain", [])) for g in cfg["killchain"]}
    zt = {g["id"]: sum(1 for x in pool if g["id"] in x.get("zerotrust", [])) for g in cfg["zerotrust"]}
    day_ago = iso(now() - timedelta(hours=24))
    allcve = parts["cves"]["kr"] + parts["cves"]["global"]
    return {
        "official": len(parts["official"]),
        "official_24h": sum(1 for x in parts["official"] if (x["published"] or "") >= day_ago),
        "cve_kr": len(parts["cves"]["kr"]), "cve_global": len(parts["cves"]["global"]),
        "cve_critical": sum(1 for x in allcve if x["severity"] == "critical"),
        "kev_recent": len(parts["kev"].get("recent", [])),
        "kev_ransomware": sum(1 for v in parts["kev"].get("recent", []) if v.get("ransomware")),
        "media": len(parts["media"]), "killchain": kc, "zerotrust": zt,
    }


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

    errors, stale = [], []
    if args.sample:
        parts = sample(cfg)
    else:
        parts = {}
        try:
            parts["kev"], kev_ids = collect_kev(cfg)
        except Exception as ex:
            errors.append(f"KEV: {redact(ex)[:120]}")
            parts["kev"] = prev.get("kev") or {"recent": [], "total": None}
            kev_ids = {v["cve"].upper() for v in parts["kev"].get("recent", []) if v.get("cve")}
            stale.append("kev")
        clf = Classifier(cfg, kev_ids)
        seen = seen_index(prev)

        parts["official"], errs = collect_official(cfg, clf, seen)
        errors += errs
        if not parts["official"] and prev.get("official"):
            parts["official"] = prev["official"]
            stale.append("official")

        parts["cves"] = {}
        for key, fn in (("kr", lambda: collect_cve_kr(cfg, clf, seen)), ("global", lambda: collect_cve_global(cfg, clf))):
            try:
                parts["cves"][key] = fn()
                log(f"CVE {key}: {len(parts['cves'][key])}건")
            except Exception as ex:
                errors.append(f"CVE {key}: {redact(ex)[:120]}")
                parts["cves"][key] = (prev.get("cves") or {}).get(key) or []
                stale.append(f"cve_{key}")

        parts["media"], errs = collect_media(cfg, clf)
        errors += errs
        if not parts["media"] and prev.get("media"):
            parts["media"] = prev["media"]
            stale.append("media")

        parts["eol"], errs = collect_eol(cfg)
        errors += errs
        if not parts["eol"] and prev.get("eol"):
            parts["eol"] = prev["eol"]
            stale.append("eol")
        parts["cloud"], errs = collect_cloud(cfg)
        errors += errs

    payload = {
        "updated_at": iso(now()),
        "sample": args.sample,
        "errors": errors,
        "stale_sections": stale,
        "frameworks": {
            "killchain": [{k: g[k] for k in ("id", "name", "desc")} for g in cfg["killchain"]],
            "zerotrust": [{k: g[k] for k in ("id", "name", "check")} for g in cfg["zerotrust"]],
        },
        "summary": summarize(cfg, parts),
        "official": parts["official"],
        "cves": parts["cves"],
        "kev": parts["kev"],
        "media": parts["media"],
        "patches": collect_patches(),
        "eol": parts["eol"],
        "cloud": parts["cloud"],
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=1)
    s = payload["summary"]
    log(f"공식 {s['official']} · CVE 국내 {s['cve_kr']}/글로벌 {s['cve_global']} · KEV {s['kev_recent']} · 언론 {s['media']} · 오류 {len(errors)} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
