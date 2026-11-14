"""학습 > 기술 노트 데이터 빌드.

- 입력: content/notes.yml (주제·글 목록) + content/notes/<id>.md (본문)
- 출력: site/study/notes/data.json

사용: python tools/build_notes.py [--out site/study/notes/data.json]
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
    print(f"[notes] {msg}", file=sys.stderr)


def iso(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    if isinstance(v, list):
        return [iso(x) for x in v]
    if isinstance(v, dict):
        return {k: iso(x) for k, x in v.items()}
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="content/notes.yml")
    ap.add_argument("--out", default="site/study/notes/data.json")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        log(f"{args.src} 이 없어 건너뜁니다.")
        return 0
    with open(args.src, encoding="utf-8") as fp:
        doc = yaml.safe_load(fp) or {}

    topics = iso(doc.get("topics") or [])
    names = {t["id"]: t["name"] for t in topics}
    notes = []
    for n in doc.get("notes") or []:
        n = iso(dict(n))
        body_path = os.path.join("content/notes", f"{n.get('id')}.md")
        if os.path.exists(body_path):
            with open(body_path, encoding="utf-8") as fp:
                n["body"] = fp.read()
        else:
            log(f"본문 없음: {body_path}")
        n["topic_name"] = names.get(n.get("topic"), "")
        notes.append(n)

    data = {"updated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "topics": topics, "notes": notes}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    log(f"주제 {len(topics)} · 글 {len(notes)} → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
