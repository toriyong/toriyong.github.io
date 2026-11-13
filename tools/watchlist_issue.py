"""관심종목 이슈(폼) → config/watchlist.yml 수정.

GitHub 이슈 폼 본문('### 라벨' 다음 줄이 값)을 읽어 종목 추가·삭제·목표가 추가를 반영한다.
종목코드가 비어 있으면 DART corpCode.xml 에서 종목명으로 찾는다(정확히 일치 → 유일한 부분 일치).

사용: ISSUE_BODY="..." DART_API_KEY=... python tools/watchlist_issue.py --config config/watchlist.yml
결과 요약은 표준출력 마지막 줄(JSON)로 남긴다.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import requests
import yaml

KST = timezone(timedelta(hours=9))
LABELS = {"작업": "action", "종목명": "name", "종목코드 (선택)": "code", "증권사 (목표가 입력 시)": "broker",
          "목표가(원) (목표가 입력 시)": "target", "목표가 발표일 (선택, 비우면 오늘)": "date"}


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


def find_code(name: str, key: str) -> tuple[str, str]:
    r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml", params={"crtfc_key": key}, timeout=60)
    r.raise_for_status()
    if not r.content.startswith(b"PK"):
        raise ValueError("DART corpCode 응답 오류")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        root = ET.fromstring(z.read(z.namelist()[0]))
    listed = [((el.findtext("corp_name") or "").strip(), (el.findtext("stock_code") or "").strip())
              for el in root.iter("list") if (el.findtext("stock_code") or "").strip()]
    norm = lambda s: re.sub(r"\s|\(주\)|㈜", "", s).lower()
    exact = [x for x in listed if norm(x[0]) == norm(name)]
    if exact:
        return exact[0]
    part = [x for x in listed if norm(name) in norm(x[0])]
    if len(part) == 1:
        return part[0]
    raise ValueError(f"'{name}' 종목코드를 찾지 못했습니다" + (f" (후보 {len(part)}개: {', '.join(p[0] for p in part[:5])})" if part else "") + ". 종목코드를 직접 입력해 주세요.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/watchlist.yml")
    args = ap.parse_args()
    f = parse_form(os.environ.get("ISSUE_BODY", ""))
    action, name = f.get("action", ""), (f.get("name") or "").strip()
    if not name or action not in ("종목 추가", "목표가 추가", "종목 삭제"):
        raise SystemExit("폼 값이 올바르지 않습니다(작업·종목명 필수)")

    with open(args.config, encoding="utf-8") as fp:
        raw = fp.read()
    header = re.sub(r"\n{3,}", "\n\n", "".join(l + "\n" for l in raw.split("\nstocks:")[0].splitlines()))
    data = yaml.safe_load(raw) or {}
    stocks = data.get("stocks") or []

    code = re.sub(r"\D", "", f.get("code") or "")
    if code:
        code = code.zfill(6)
    found = next((s for s in stocks if (code and str(s.get("stock_code")).zfill(6) == code) or s.get("name") == name), None)

    if action == "종목 삭제":
        if not found:
            raise SystemExit(f"'{name}'은(는) 관심종목에 없습니다")
        stocks.remove(found)
        summary = f"관심종목 삭제: {found['name']} ({found['stock_code']})"
    else:
        if not found:
            if not code:
                nm, code = find_code(name, os.environ.get("DART_API_KEY", ""))
                name = nm
            found = {"name": name, "stock_code": code, "targets": []}
            stocks.append(found)
            summary = f"관심종목 추가: {name} ({code})"
        else:
            summary = f"{found['name']} ({found['stock_code']})"
        if action == "목표가 추가":
            price = int(re.sub(r"\D", "", f.get("target") or "0") or 0)
            if price <= 0:
                raise SystemExit("목표가(원)를 입력해 주세요")
            d = f.get("date") or datetime.now(KST).date().isoformat()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                raise SystemExit("발표일은 YYYY-MM-DD 형식으로 입력해 주세요")
            found.setdefault("targets", []).append({"broker": f.get("broker") or "미기재", "price": price, "date": d})
            summary += f" 목표가 추가: {f.get('broker') or '미기재'} {price:,}원 ({d})"
        elif found.get("targets") is None:
            found["targets"] = []

    # 출력: 헤더 주석 유지 + 종목별 한 줄 흐름 스타일(읽기 쉬운 형태)
    lines = [header.rstrip("\n"), "", "stocks:"]
    for s in stocks:
        lines.append(f"  - name: {s['name']}")
        lines.append(f"    stock_code: \"{str(s['stock_code']).zfill(6)}\"")
        if s.get("news_query"):
            lines.append(f"    news_query: {s['news_query']}")
        ts = s.get("targets") or []
        if not ts:
            lines.append("    targets: []")
        else:
            lines.append("    targets:")
            for t in ts:
                dt = t.get("date")
                dt = dt.isoformat() if hasattr(dt, "isoformat") else dt
                lines.append(f"      - {{ broker: {t.get('broker')}, price: {int(t['price'])}, date: {dt} }}")
    with open(args.config, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")
    yaml.safe_load(open(args.config, encoding="utf-8"))          # 결과 YAML 검증
    print(json.dumps({"summary": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
