"""학습 페이지 데이터 빌드 + 암호화 (B 방식: 비밀번호로만 열리는 정적 페이지).

- 입력: config/exams.yml(공개 시험 일정) + 공부 계획(Secret STUDY_PLAN 의 YAML, 없으면 config/study.example.yml)
- 출력: site/study/data.enc.json — AES-256-GCM 암호문만 기록(평문은 절대 파일로 쓰지 않음)
  · 키 = PBKDF2-HMAC-SHA256(STUDY_PASSWORD, 무작위 salt 16B, 600,000회) → 브라우저 WebCrypto 로 복호화
- STUDY_PASSWORD 가 없으면 암호문 대신 {"missing_password": true} 만 기록

사용: STUDY_PASSWORD=... python tools/build_study.py [--out site/study/data.enc.json]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
from datetime import date, datetime, timedelta, timezone

import yaml
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

KST = timezone(timedelta(hours=9))
ITERATIONS = 600_000          # OWASP 2023 권고(PBKDF2-HMAC-SHA256)
MIN_PASSWORD_LEN = 12


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


def encrypt(payload: dict, password: str) -> dict:
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(password.encode())
    ct = AESGCM(key).encrypt(iv, json.dumps(payload, ensure_ascii=False).encode(), None)
    b64 = lambda b: base64.b64encode(b).decode()
    return {"v": 1, "kdf": "PBKDF2-SHA256", "iter": ITERATIONS, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exams", default="config/exams.yml")
    ap.add_argument("--example", default="config/study.example.yml")
    ap.add_argument("--out", default="site/study/data.enc.json")
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
    })

    password = os.environ.get("STUDY_PASSWORD", "")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    if not password:
        out = {"missing_password": True}
        log("STUDY_PASSWORD 없음 → 데이터 없이 잠금 화면만 배포")
    else:
        if len(password) < MIN_PASSWORD_LEN:
            log(f"경고: 비밀번호가 {MIN_PASSWORD_LEN}자 미만입니다. 무차별 대입에 약하니 16자 이상 랜덤 비밀번호를 권장합니다.")
        out = encrypt(payload, password)
        log(f"암호화 완료(계획 출처: {plan_src}, 시험 {len(payload['exams'])}종)")
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(out, fp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
