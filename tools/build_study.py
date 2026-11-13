"""학습 페이지 데이터 빌드 (공개 페이지 — 비밀번호 없음).

- 입력: config/exams.yml(시험 일정) + 공부 계획(Secret STUDY_PLAN 의 YAML, 없으면 config/study.example.yml)
- 출력: site/study/data.json

사용: python tools/build_study.py [--out site/study/data.json]
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
    print(f"[study] {msg}", file=sys.stderr)


def jsonable(o):
    """YAML 이 읽은 date 객체를 ISO 문자열로."""
    if isinstance(o, (date, datetime)):
        return o.isoformat()[:10]
    if isinstance(o, dict):
        return {k: jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [jsonable(v) for v in o]
    return o


def load_content(folder: str) -> dict:
    """content/study/*.yml → {시험 id: [단원...]}"""
    out = {}
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        if name.endswith(".yml"):
            with open(os.path.join(folder, name), encoding="utf-8") as fp:
                d = yaml.safe_load(fp) or {}
            if d.get("exam"):
                out[d["exam"]] = d.get("units") or []
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exams", default="config/exams.yml")
    ap.add_argument("--example", default="config/study.example.yml")
    ap.add_argument("--content", default="content/study")
    ap.add_argument("--out", default="site/study/data.json")
    args = ap.parse_args()

    with open(args.exams, encoding="utf-8") as fp:
        exams = yaml.safe_load(fp) or {}
    plan_src = "secret"
    plan_text = os.environ.get("STUDY_PLAN", "").strip()
    if not plan_text:
        plan_src = "example"
        with open(args.example, encoding="utf-8") as fp:
            plan_text = fp.read()
    plan = yaml.safe_load(plan_text) or {}

    payload = jsonable({
        "updated_at": datetime.now(KST).strftime("%Y-%m-%dT%H:%M+09:00"),
        "plan_source": plan_src,
        "exams": exams.get("exams", []),
        "plan": plan,
        "content": load_content(args.content),
    })

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False)
    log(f"학습 데이터 생성(계획 출처: {plan_src}, 시험 {len(payload['exams'])}종) → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
