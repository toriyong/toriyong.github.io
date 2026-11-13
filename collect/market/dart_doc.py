"""DART 증권신고서(지분증권) 본문에서 공모 핵심 수치를 읽어 온다.

본문 API: https://opendart.fss.or.kr/api/document.xml (공시서류 원본, ZIP 안의 XML)
→ 표는 '행=줄바꿈, 칸=탭' 형태의 텍스트로 바꾼 뒤 정규식으로 찾는다.

주의: [발행조건확정] 신고서에는 '정정 전'과 '정정 후'가 모두 들어 있다.
      값은 항상 문서에서 마지막에 나오는 것(=정정 후)을 쓴다.

뽑는 값
  offer_price      확정 공모가          "(라) 주당 확정공모가액의 결정 … 11,000원으로"
  band             희망 공모가 밴드     "공모희망가액인 9,400원 ~ 11,000원"
  demand_ratio     기관 수요예측 경쟁률  "(가) 수요예측 참여 내역" 표의 '경쟁률' 행 합계
  lockup_ratio     의무보유확약 비율(%)  "(다) 의무보유확약기간별" 표 합계 열: 확약 수량 ÷ 전체 수량
  float_ratio      상장 직후 유통가능(%) "상장예정주식수 … 중 34.81%에 해당하는 … 유통가능"
  secondary_ratio  구주매출 비중(%)      "구주매출 500,000주(공모주식의 21.74%)"
"""
from __future__ import annotations

import html
import io
import re
import zipfile

NUM = r"[\d,]+(?:\.\d+)?"

# 해석 규칙이 바뀌면 올린다 → 캐시된 이전 해석값을 버리고 다시 받는다
PARSER_VERSION = 2


def to_num(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


# ------------------------------------------------------------------ XML → 텍스트
def xml_to_text(raw: bytes) -> str:
    """DART XML(dart4.xsd)을 '행=줄바꿈, 칸=탭' 텍스트로 변환."""
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            s = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        s = raw.decode("utf-8", errors="ignore")
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    # 원본 XML의 소스 줄바꿈은 의미가 없다(표 칸·강조 SPAN 사이마다 들어 있음).
    # 먼저 공백 하나로 접은 뒤, 구조 태그로만 칸(탭)·행(줄바꿈)을 만든다.
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(?i)</(TD|TH|TE|TU)\s*>", "\t", s)           # 칸 끝 → 탭
    s = re.sub(r"(?i)<(/TR|/P|BR|/TITLE|/SECTION-\d|/LIBRARY|/TABLE)[^>]*>", "\n", s)  # 행·문단 끝 → 줄바꿈
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    lines = []
    for line in s.split("\n"):
        cells = [re.sub(r"[  　]+", " ", c).strip() for c in line.split("\t")]
        lines.append("\t".join(c for c in cells if c != "") if any(cells) else "")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


CORR_MARK = re.compile(r"\(주\s*(\d+)\s*\)\s*정정\s*(전|후)")


def drop_before_correction(text: str) -> str:
    """'(주N) 정정 전' ~ '(주N) 정정 후' 구간(정정 전 원문)을 지운다.

    [발행조건확정] 신고서 본문은 바뀐 부분마다 '정정 전' 원문과 '정정 후' 내용을 나란히 싣는다.
    앞쪽 정정 대비표의 짧은 표시(전·후가 붙어 있음)는 지워도 영향이 없다.
    """
    marks = [(m.start(), m.group(1), m.group(2)) for m in CORR_MARK.finditer(text)]
    cut: list[tuple[int, int]] = []
    for i, (pos, no, kind) in enumerate(marks):
        if kind != "전":
            continue
        end = next((p for p, n, k in marks[i + 1:] if n == no and k == "후"), None)
        if end is not None:
            cut.append((pos, end))
    if not cut:
        return text
    out, last = [], 0
    for a, b in cut:
        if a < last:
            continue
        out.append(text[last:a])
        last = b
    out.append(text[last:])
    return "".join(out)


def zip_to_text(blob: bytes, rcept_no: str | None = None) -> str:
    """document.xml 응답(ZIP)에서 본문 XML을 꺼내 텍스트로. 본문 파일(접수번호.xml)을 우선."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".xml")]
        main = [n for n in names if rcept_no and n.startswith(rcept_no)] or names
        return drop_before_correction("\n".join(xml_to_text(z.read(n)) for n in main))


# ------------------------------------------------------------------ 값 추출
def _last(pattern: str, text: str, flags=0):
    found = list(re.finditer(pattern, text, flags))
    return found[-1] if found else None


def _section(text: str, start_pat: str, end_pat: str, max_len: int = 12000) -> str | None:
    """start_pat 의 '마지막' 등장부터 end_pat 직전까지(정정 후 표를 고르기 위해)."""
    m = _last(start_pat, text)
    if not m:
        return None
    rest = text[m.start(): m.start() + max_len]
    e = re.search(end_pat, rest[len(m.group(0)):])
    return rest[: len(m.group(0)) + e.start()] if e else rest


def _row_numbers(line: str) -> list[float]:
    return [v for v in (to_num(x) for x in re.findall(NUM, line)) if v is not None]


def parse_offer_price(text: str) -> int | None:
    m = _last(rf"확정공모가액을\s*({NUM})\s*원", text)
    return int(to_num(m.group(1))) if m else None


def parse_band(text: str) -> list[int] | None:
    m = _last(rf"공모희망가액\S*\s*({NUM})\s*원\s*~\s*({NUM})\s*원", text) \
        or _last(rf"모집\(매출\)가액\(예정\)\s*:\s*({NUM})\s*원\s*~\s*({NUM})\s*원", text)
    return [int(to_num(m.group(1))), int(to_num(m.group(2)))] if m else None


def parse_demand_ratio(text: str) -> float | None:
    # '의무보유확약기간별 수요예측 참여내역'과 구분하기 위해 앞에 '기간별'이 붙은 것은 제외
    starts = [m for m in re.finditer(r"수요예측\s*참여\s*내역", text)
              if "기간별" not in text[max(0, m.start() - 12): m.start()]]
    sec = None
    if starts:
        rest = text[starts[-1].start(): starts[-1].start() + 8000]
        e = re.search(r"\(나\)|수요예측\s*신청가격\s*분포|의무보유\s*확약\s*기간별", rest[10:])
        sec = rest[: 10 + e.start()] if e else rest
    if sec:
        for line in sec.split("\n"):
            if line.strip().startswith("경쟁률"):
                nums = _row_numbers(line)
                if nums:
                    return nums[-1]                 # 마지막 칸 = 합계
    m = _last(rf"수요예측[^\n]{{0,40}}?경쟁률[^\n\d]{{0,20}}({NUM})\s*(?::|대)\s*1", text)
    return to_num(m.group(1)) if m else None


def parse_lockup_ratio(text: str, price_hint: float | None) -> float | None:
    """확약기간별 표의 합계 열에서 확약 수량 ÷ (확약 + 미확약) 수량."""
    sec = _section(text, r"의무보유\s*확약\s*기간별", r"\(라\)|주당\s*확정공모가액의\s*결정")
    if not sec:
        return None
    last_qty: dict[str, float] = {}
    for line in sec.split("\n"):
        label = re.sub(r"\s+", "", line.split("\t", 1)[0])
        if not re.fullmatch(r"(15일|1개월|2개월|3개월|6개월)확약|미확약", label):
            continue
        nums = _row_numbers(line.split("\t", 1)[1] if "\t" in line else "")
        if len(nums) < 2:
            continue
        # 마지막 묶음 = 합계 열. 맨 끝이 신청가격이면 그 앞이 수량.
        qty = nums[-1]
        if price_hint and len(nums) >= 2 and abs(nums[-1] - price_hint) <= price_hint * 0.5:
            qty = nums[-2]
        last_qty[label] = qty                       # 표가 둘로 나뉘면 뒤쪽(합계 열 포함) 값으로 덮어씀
    none = last_qty.get("미확약")
    locked = sum(v for k, v in last_qty.items() if k != "미확약")
    if none is None or locked + none <= 0:
        return None
    return round(locked / (locked + none) * 100, 2)


def parse_float_ratio(text: str) -> float | None:
    m = _last(rf"상장\s*예정\s*주식\s*수\s*({NUM})\s*주\s*중\s*({NUM})\s*%\s*에\s*해당하는\s*({NUM})\s*주는\s*상장\s*직후\s*유통\s*가능", text)
    return to_num(m.group(2)) if m else None


def parse_secondary_ratio(text: str) -> float | None:
    m = _last(rf"구주\s*매출\s*({NUM})\s*주\s*\(\s*공모\s*주식의\s*({NUM})\s*%\s*\)", text)
    if m:
        return to_num(m.group(2))
    if re.search(r"신주\s*모집\s*[\d,]+\s*주\s*\(\s*공모\s*주식의\s*100(\.0+)?\s*%", text):
        return 0.0
    return None


def parse_offering(text: str) -> dict:
    price = parse_offer_price(text)
    band = parse_band(text)
    hint = price or (band[1] if band else None)
    out = {
        "offer_price": price,
        "band": band,
        "demand_ratio": parse_demand_ratio(text),
        "lockup_ratio": parse_lockup_ratio(text, hint),
        "float_ratio": parse_float_ratio(text),
        "secondary_ratio": parse_secondary_ratio(text),
    }
    return {k: v for k, v in out.items() if v is not None}
