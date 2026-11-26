"""Yahoo 차트 응답 → 지수 카드 변환 검증 (11/26 네이버 코스피 값 기준)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "collect", "market"))
import indices  # noqa: E402

T0 = 1795651200  # 2026-11-26 09:00 KST


def chart(price, prev, closes, start=T0, end=T0 + 23400, gmtoffset=32400):
    return {
        "meta": {
            "regularMarketPrice": price, "previousClose": prev,
            "regularMarketDayHigh": 4815.14, "regularMarketDayLow": 4697.51,
            "fiftyTwoWeekHigh": 5200.0, "fiftyTwoWeekLow": 3900.0,
            "regularMarketTime": start + 23400, "gmtoffset": gmtoffset,
            "currentTradingPeriod": {"regular": {"start": start, "end": end}},
        },
        "timestamp": [start + i * 300 for i in range(len(closes))],
        "indicators": {"quote": [{"close": closes}]},
    }


def test_kospi_closed_after_market():
    res = chart(4711.21, 4697.51, [4700.0, None, 4790.5, 4711.21])
    it = indices.parse_chart(res, "^KS11", "코스피", 1, True, now=T0 + 23400 + 3 * 3600)
    assert it["value"] == 4711.21
    assert it["diff"] == 13.70 and it["rate"] == 0.29   # 네이버: ▲13.70 (+0.29%)
    assert it["state"] == "closed"
    assert len(it["points"]) == 3                        # None 은 버림
    assert it["time"].startswith("2026-11-26T15:30")


def test_open_state_and_scale():
    res = chart(9.05, 9.0, [9.0, 9.05])
    it = indices.parse_chart(res, "JPYKRW=X", "원/100엔", 100, False, now=T0 + 23400)
    assert it["value"] == 905.0 and it["prev"] == 900.0
    assert it["state"] == "open"
    assert "points" not in it


def test_falls_back_to_chart_previous_close():
    res = chart(100.0, None, [100.0])
    res["meta"]["chartPreviousClose"] = 98.0
    it = indices.parse_chart(res, "X", "X", 1, False, now=T0)
    assert it["prev"] == 98.0 and it["diff"] == 2.0
