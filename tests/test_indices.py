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


def test_prev_close_and_52w_from_daily():
    """코스닥처럼 meta.previousClose 가 틀린 경우 일봉의 전일 종가를 쓴다 (11/26 네이버: 655.71, ▲5.07)."""
    res = chart(655.71, 665.88, [660.0, 655.71])            # meta 의 전일 종가 665.88 은 틀린 값
    res["meta"].update(regularMarketDayHigh=673.57, regularMarketDayLow=654.8)
    day = 86400
    daily = {
        "timestamp": [T0 - 2 * day, T0 - day, T0],
        "indicators": {"quote": [{"close": [640.0, 650.64, 655.71],
                                  "high": [1229.42, 652.0, 673.57], "low": [618.74, 645.0, 654.8]}]},
    }
    it = indices.parse_chart(res, "^KQ11", "코스닥", 1, False, now=T0 + 23400 + 3 * 3600, daily=daily)
    assert it["prev"] == 650.64
    assert it["diff"] == 5.07 and it["rate"] == 0.78
    assert it["w52h"] == 1229.42 and it["w52l"] == 618.74


def test_closed_time_clamped_to_market_end():
    res = chart(4711.21, 4697.51, [4711.21])
    res["meta"]["regularMarketTime"] = T0 + 23400 + 4 * 3600      # 20:05 같은 사후 갱신 시각
    res["meta"]["previousClose"] = None
    res["meta"]["chartPreviousClose"] = 4697.51
    it = indices.parse_chart(res, "^KS11", "코스피", 1, False, now=T0 + 23400 + 5 * 3600)
    assert it["time"].startswith("2026-11-26T15:30")
