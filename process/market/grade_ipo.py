"""원천 공모주 JSON + 수동 입력값 + 등급 기준을 합쳐 화면용 ipo.json 을 만든다.

등급(코드가 규칙대로 산정, 사람이 매기지 않음)
  exclude  : 제외 조건(저경쟁률·저확약·구주매출 과다·밴드 초과) 중 min_flags 개 이상
  pending  : 경쟁률 또는 확약률이 없어 판정 보류
  scalp    : 단타 조건 3개(경쟁률·확약률·유통물량) 모두 충족
  swing    : 단타 조건 중 min_conditions_met 개 이상 충족
  watch    : 그 외

사용 예
  python process/market/grade_ipo.py --raw site/market/data/raw_ipo.json \
      --out site/market/data/ipo.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import yaml

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANUAL_FIELDS = ("market", "sector", "band", "offer_price", "demand_ratio", "lockup_ratio",
                 "float_ratio", "secondary_ratio", "retail_ratio", "listing_date", "note")


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as fp:
        return yaml.safe_load(fp) or {}


def to_date(v) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def merge_manual(item: dict, manual: dict) -> dict:
    over = manual.get(item["corp_name"]) or {}
    out = dict(item)
    for k in MANUAL_FIELDS:
        if k in over and over[k] not in (None, ""):
            out[k] = over[k]
    if out.get("listing_date"):
        d = to_date(out["listing_date"])
        out["listing_date"] = d.isoformat() if d else None
    out["manual"] = bool(over)
    return out


def status_of(item: dict, today: date) -> str:
    s, e, lst = to_date(item.get("sub_start")), to_date(item.get("sub_end")), to_date(item.get("listing_date"))
    if lst and lst < today:
        return "listed"
    if s and today < s:
        return "upcoming"
    if s and e and s <= today <= e:
        return "subscribing"
    if e and e < today:
        return "awaiting_listing"
    return "unknown"


def grade(item: dict, rule: dict) -> tuple[str, list[str]]:
    demand, lockup = num(item.get("demand_ratio")), num(item.get("lockup_ratio"))
    flt, secondary = num(item.get("float_ratio")), num(item.get("secondary_ratio"))
    band, offer = item.get("band"), num(item.get("offer_price") or item.get("price"))
    reasons: list[str] = []

    # 1) 제외 판정
    ex = rule["exclude"]
    flags = []
    if demand is not None and demand < ex["max_demand_ratio"]:
        flags.append(f"경쟁률 {demand:,.0f}:1 < {ex['max_demand_ratio']}:1")
    if lockup is not None and lockup < ex["max_lockup_ratio"]:
        flags.append(f"확약률 {lockup:.1f}% < {ex['max_lockup_ratio']}%")
    if secondary is not None and secondary >= ex["min_secondary_ratio"]:
        flags.append(f"구주매출 {secondary:.0f}% ≥ {ex['min_secondary_ratio']}%")
    if ex.get("band_above_top") and isinstance(band, list) and len(band) == 2 and offer:
        if offer > float(band[1]):
            flags.append("희망밴드 상단 초과 확정")
    if len(flags) >= ex["min_flags"]:
        return "exclude", flags

    # 2) 판정 보류
    if demand is None or lockup is None:
        if not item.get("confirmed"):
            return "pending", ["수요예측 결과 공시 전 (발행조건확정 신고서 제출 후 자동 반영)"]
        if not item.get("doc_rcept_no"):
            return "pending", ["신고서 본문 수집 대기 — 다음 자동 수집 때 반영"]
        return "pending", ["발행조건확정 신고서에서 경쟁률·확약률을 읽지 못함 — config/ipo_manual.yml 에 직접 입력"]

    # 3) 단타 조건 충족 개수
    sc = rule["scalp"]
    checks = [
        (demand >= sc["min_demand_ratio"], f"경쟁률 {demand:,.0f}:1 (기준 ≥ {sc['min_demand_ratio']:,})"),
        (lockup >= sc["min_lockup_ratio"], f"확약률 {lockup:.1f}% (기준 ≥ {sc['min_lockup_ratio']}%)"),
        (flt is not None and flt <= sc["max_float_ratio"],
         f"유통물량 {flt:.1f}% (기준 ≤ {sc['max_float_ratio']}%)" if flt is not None else "유통물량 미입력"),
    ]
    met = sum(1 for ok, _ in checks if ok)
    reasons = [("✓ " if ok else "✗ ") + text for ok, text in checks] + flags
    if met == 3:
        return "scalp", reasons
    if met >= rule["swing"]["min_conditions_met"]:
        return "swing", reasons
    return "watch", reasons


def subscribe_check(item: dict, rule: dict) -> dict | None:
    """경쟁률을 고정 구간과 비교해 청약 판단(적극/보통/신중/비추천)을 낸다."""
    cfg = rule.get("subscribe") or {}
    tiers = cfg.get("tiers") or []
    demand = num(item.get("demand_ratio"))
    if demand is None or not tiers:
        return None
    idx = next((i for i, t in enumerate(tiers) if demand >= float(t["min"])), len(tiers) - 1)
    base = tiers[idx]
    notes = []
    lockup = num(item.get("lockup_ratio"))
    if lockup is not None and cfg.get("low_lockup") is not None and lockup < float(cfg["low_lockup"]):
        notes.append(f"확약률 {lockup:.1f}% < {cfg['low_lockup']}%")
    band, offer = item.get("band"), num(item.get("offer_price"))
    if cfg.get("below_band_penalty") and isinstance(band, list) and len(band) == 2 and offer and offer < float(band[0]):
        notes.append("희망밴드 하단 미만 확정")
    final = tiers[min(idx + len(notes), len(tiers) - 1)]
    nxt = tiers[idx - 1] if idx > 0 else None
    return {
        "level": final["level"],
        "label": final["label"],
        "basis": f"경쟁률 {demand:,.1f}:1 → {base['label']} 구간(≥{float(base['min']):,.0f})",
        "to_next": f"{nxt['label']}까지 {float(nxt['min']) - demand:,.0f}:1 부족" if nxt else None,
        "notes": notes,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--grading", default=os.path.join(ROOT, "config", "grading.yml"))
    ap.add_argument("--manual", default=os.path.join(ROOT, "config", "ipo_manual.yml"))
    args = ap.parse_args()

    with open(args.raw, encoding="utf-8") as fp:
        raw = json.load(fp)
    rule, manual = load_yaml(args.grading), load_yaml(args.manual)
    today = datetime.now(KST).date()

    items = []
    spac_n = 0
    for it in raw.get("items", []):
        it = merge_manual(it, manual)
        if it.get("is_spac"):            # 스팩은 투자 대상이 아니므로 결과에서 제외
            spac_n += 1
            continue
        g, reasons = grade(it, rule)
        it.update(grade=g, reasons=reasons, status=status_of(it, today), subscribe=subscribe_check(it, rule))
        items.append(it)

    # 청약 시작일 기준 정렬(날짜 없는 항목은 뒤로)
    items.sort(key=lambda x: (x.get("sub_start") is None, x.get("sub_start") or ""))
    counts = {}
    for it in items:
        counts[it["grade"]] = counts.get(it["grade"], 0) + 1

    out = {
        "updated_at": raw.get("updated_at"),
        "processed_at": datetime.now(KST).isoformat(timespec="minutes"),
        "source": raw.get("source"),
        "sample": raw.get("sample", False),
        "stale": raw.get("stale", False),
        "stale_reason": raw.get("stale_reason"),
        "legend": rule.get("legend", {}),
        "thresholds": {k: rule[k] for k in ("scalp", "swing", "exclude")},
        "subscribe_rule": rule.get("subscribe", {}),
        "counts": counts,
        "excluded_spac": spac_n,
        "items": items,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print(f"[grade_ipo] {len(items)}건, 등급 분포 {counts} → {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
