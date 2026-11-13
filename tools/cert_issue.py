"""자격증 이슈(폼) → config/portfolio.yml 수정.

GitHub 이슈 폼 본문('### 라벨' 다음 줄이 값)을 읽어 자격증 상태를 바꾼다.
  합격      → status: earned, date: 취득일 (exam_date·note 는 지운다)
  일정 변경  → exam_date 갱신
  추가      → preparing 으로 새로 넣는다
  삭제      → 목록에서 뺀다

사용: ISSUE_BODY="..." python tools/cert_issue.py --config config/portfolio.yml
결과 요약은 표준출력 마지막 줄(JSON)로 남긴다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone

import yaml

KST = timezone(timedelta(hours=9))
LABELS = {"작업": "action", "자격증": "name", "날짜 (선택)": "date",
          "발급 기관 (선택)": "org", "메모 (선택)": "note"}


def parse_form(body: str) -> dict:
    out, cur = {}, None
    for line in (body or "").splitlines():
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m:
            cur = LABELS.get(m.group(1).strip())
            continue
        if cur and line.strip() and line.strip() != "_No response_" and cur not in out:
            out[cur] = line.strip()
    return out


def norm(s: str) -> str:
    """이름 비교용: 공백·괄호 안 설명을 빼고 소문자로."""
    s = re.sub(r"\(.*?\)", " ", s or "")
    return re.sub(r"[\s·\-_]+", "", s).lower()


def parse_date(v: str) -> str:
    v = (v or "").strip()
    if not v:
        return datetime.now(KST).date().isoformat()
    m = re.match(r"^(\d{4})[-./](\d{1,2})(?:[-./](\d{1,2}))?$", v)
    if not m:
        raise ValueError(f"날짜 형식을 읽지 못했습니다: {v} (YYYY-MM-DD 로 적어 주세요)")
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    return date(y, mo, d).isoformat()


def dump_row(c: dict) -> str:
    """한 줄 흐름 스타일로 — 사람이 읽고 고치기 쉬운 형태를 유지한다."""
    order = ["name", "status", "date", "year", "exam", "round", "exam_date", "org", "note"]
    keys = [k for k in order if k in c] + [k for k in c if k not in order]
    parts = []
    for k in keys:
        v = c[k]
        v = v.isoformat()[:10] if isinstance(v, (date, datetime)) else str(v)
        need = any(ch in v for ch in ":#,{}[]&*?|>%@`\"'") or v.strip() != v or not v
        parts.append(f"{k}: " + (json.dumps(v, ensure_ascii=False) if need else v))
    return "{ " + ", ".join(parts) + " }\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/portfolio.yml")
    args = ap.parse_args()

    form = parse_form(__import__("os").environ.get("ISSUE_BODY", ""))
    action, name = form.get("action", ""), (form.get("name") or "").strip()
    if not action or not name:
        print("작업과 자격증 이름이 필요합니다.", file=sys.stderr)
        return 1

    with open(args.config, encoding="utf-8") as fp:
        text = fp.read()
    doc = yaml.safe_load(text) or {}
    certs = doc.get("certifications") or []

    hit = next((c for c in certs if norm(str(c.get("name"))) == norm(name)
                or norm(name) in norm(str(c.get("name")))), None)

    if action == "합격":
        if not hit:
            raise SystemExit(f"목록에 없는 자격증입니다: {name}")
        when = parse_date(form.get("date", ""))
        hit["status"] = "earned"
        hit["date"] = when
        hit.pop("exam_date", None)
        hit.pop("note", None)
        if form.get("org"):
            hit["org"] = form["org"]
        summary = f"{hit['name']} 합격 ({when})"

    elif action == "응시 일정 변경":
        if not hit:
            raise SystemExit(f"목록에 없는 자격증입니다: {name}")
        hit["exam_date"] = parse_date(form.get("date", ""))
        hit["status"] = "preparing"
        summary = f"{hit['name']} 응시 예정일 {hit['exam_date']}"

    elif action == "추가":
        if hit:
            raise SystemExit(f"이미 목록에 있습니다: {hit['name']}")
        row = {"name": name, "status": "preparing"}
        if form.get("org"):
            row["org"] = form["org"]
        if form.get("date"):
            row["exam_date"] = parse_date(form["date"])
        if form.get("note"):
            row["note"] = form["note"]
        certs.append(row)
        summary = f"{name} 추가"

    elif action == "삭제":
        if not hit:
            raise SystemExit(f"목록에 없는 자격증입니다: {name}")
        certs.remove(hit)
        summary = f"{hit['name']} 삭제"

    else:
        raise SystemExit(f"알 수 없는 작업: {action}")

    # 취득 → 준비 중 순서로 정렬(취득은 최신순)
    ordered = (
        sorted([c for c in certs if c.get("status") == "earned"],
               key=lambda c: str(c.get("date") or c.get("year") or ""), reverse=True)
        + [c for c in certs if c.get("status") != "earned"])

    # 이 파일에는 소개 문구와 주석이 들어 있다. certifications 블록만 바꿔 쓴다.
    block = "certifications:\n" + "".join("  - " + dump_row(c) for c in ordered)
    m = re.search(r"^certifications:\n(?:(?:[ \t].*)?\n)*", text, re.M)
    if not m:
        raise SystemExit("config 에서 certifications 블록을 찾지 못했습니다.")
    head = "\n".join(l for l in m.group(0).splitlines() if l.lstrip().startswith("#"))
    new = "certifications:\n" + (head + "\n" if head else "") + "".join("  - " + dump_row(c) for c in ordered)
    with open(args.config, "w", encoding="utf-8") as fp:
        fp.write(text[:m.start()] + new + "\n" + text[m.end():])

    print(json.dumps({"summary": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
