"""포트폴리오 페이지 데이터 빌드.

- 입력: config/portfolio.yml (소개·기술·자격증·프로젝트)
        config/exams.yml    (준비 중 자격증의 시험 일정)
        content/study/*.yml (학습 단원 수)
        공부 계획            (Secret STUDY_PLAN 또는 config/study.example.yml)
- 출력: site/about/data.json

학습 현황은 '완료 체크'(브라우저에 저장되어 남에게는 보이지 않는 값)가 아니라
시작일과 커리큘럼 길이로 계산한 경과 주차를 쓴다.

사용: python tools/build_portfolio.py [--out site/about/data.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import yaml

KST = timezone(timedelta(hours=9))


def log(msg: str) -> None:
    print(f"[portfolio] {msg}", file=sys.stderr)


def load(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fp:
        return yaml.safe_load(fp) or default


def iso(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    if isinstance(v, list):
        return [iso(x) for x in v]
    return v


def plan() -> dict:
    """공부 계획 — Secret 이 있으면 그것을, 없으면 예시 파일을."""
    raw = os.environ.get("STUDY_PLAN", "").strip()
    if raw:
        try:
            return yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            log("STUDY_PLAN 을 읽지 못해 예시 계획을 씁니다.")
    return load("config/study.example.yml", {}) or {}


def exam_index(exams: dict) -> dict:
    """{(시험id, 회차): {name, org, url, practical, estimated}}"""
    out = {}
    for e in (exams or {}).get("exams", []):
        for r in e.get("rounds", []):
            out[(e["id"], str(r.get("round")))] = {
                "exam_name": e.get("name"), "org": e.get("org"), "url": e.get("url"),
                "practical": iso(r.get("practical")), "estimated": bool(r.get("estimated")),
            }
    return out


def study_status(p: dict, exams: dict) -> dict:
    """시작일·시험일과 단원 수로 학습 현황을 만든다."""
    start = p.get("start")
    start = date.fromisoformat(iso(start)) if start else None
    today = datetime.now(KST).date()

    units = {}
    for ex in ("eis", "eip"):
        data = load(f"content/study/{ex}.yml")
        if data:
            units[ex] = len(data.get("units") or [])

    targets = []
    idx = exam_index(exams)
    for t in p.get("targets", []):
        key = (t.get("exam"), str(t.get("round")))
        info = idx.get(key, {})
        pr = info.get("practical")
        end = pr[1] if isinstance(pr, list) else pr
        targets.append({
            "exam": t.get("exam"), "round": t.get("round"),
            "exam_name": info.get("exam_name"), "org": info.get("org"),
            "exam_date": (pr[0] if isinstance(pr, list) else pr),
            "estimated": info.get("estimated", False),
            "units": units.get(t.get("exam")),
            "d_day": (date.fromisoformat(end) - today).days if end else None,
        })

    weeks_total, week_now = None, None
    if start:
        last = max([t["exam_date"] for t in targets if t["exam_date"]] or [None])
        if last:
            weeks_total = max(1, round((date.fromisoformat(last) - start).days / 7))
        week_now = max(0, (today - start).days // 7 + 1) if today >= start else 0

    return {
        "start": start.isoformat() if start else None,
        "started": bool(start and today >= start),
        "week_now": week_now, "weeks_total": weeks_total,
        "hours": iso(p.get("hours")), "past_days": p.get("past_days"),
        "targets": targets,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/about/data.json")
    args = ap.parse_args()

    pf = load("config/portfolio.yml")
    if not pf:
        log("config/portfolio.yml 이 없어 건너뜁니다.")
        return 1
    exams = load("config/exams.yml", {})

    # 준비 중 자격증에 시험 일정을 붙인다
    idx = exam_index(exams)
    certs = []
    for c in pf.get("certifications") or []:
        c = dict(c)
        info = idx.get((c.get("exam"), str(c.get("round"))))
        if info:
            pr = info["practical"]
            c["exam_date"] = pr[0] if isinstance(pr, list) else pr
            c["estimated"] = info["estimated"]
            c["org"] = info["org"]
        certs.append(iso(c))

    data = {
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "profile": iso(pf.get("profile") or {}),
        "education": iso(pf.get("education") or []),
        "skills": iso(pf.get("skills") or []),
        "certifications": certs,
        "projects": iso(pf.get("projects") or []),
        "study": study_status(plan(), exams),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    log(f"프로젝트 {len(data['projects'])}개, 자격증 {len(certs)}개 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
