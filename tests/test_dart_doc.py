"""실제 공시(영광와이케이엠씨 발행조건확정 신고서) 조각으로 해석 결과를 검증."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "collect", "market"))
import dart_doc  # noqa: E402

TEXT = open(os.path.join(os.path.dirname(__file__), "fixtures", "ykmc_confirmed.txt"), encoding="utf-8").read()


def test_offering_values():
    r = dart_doc.parse_offering(TEXT)
    assert r["offer_price"] == 11000            # 정정 후 확정가 (정정 전 하단 9,400 아님)
    assert r["band"] == [9400, 11000]
    assert r["demand_ratio"] == 1163.35
    assert r["lockup_ratio"] == 7.21            # 142,125,000 / 1,971,691,000
    assert r["float_ratio"] == 34.81            # 정정 후 값 (정정 전 34.86 아님)
    assert r["secondary_ratio"] == 21.74


def test_xml_to_text_tables():
    xml = ("<?xml version='1.0' encoding='utf-8'?><DOCUMENT><P>확정공모가액을 12,500원으로 결정</P>"
           "<TABLE><TR><TD>경쟁률</TD><TD>10.5</TD><TE>1,234.56</TE></TR></TABLE></DOCUMENT>").encode()
    t = dart_doc.xml_to_text(xml)
    assert "경쟁률\t10.5\t1,234.56" in t
    assert dart_doc.parse_offer_price(t) == 12500


def test_missing_values_are_omitted():
    assert dart_doc.parse_offering("관계없는 문서") == {}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)


# ---- 실제 DART 원본(ZIP) 기반 회귀 테스트: 소스 줄바꿈·정정 전/후 구간 처리 확인
import os as _os
_FIX = _os.path.join(_os.path.dirname(__file__), "fixtures")


def _real(rcept):
    with open(_os.path.join(_FIX, f"dart_{rcept}.zip"), "rb") as fp:
        return dart_doc.parse_offering(dart_doc.zip_to_text(fp.read(), rcept))


def test_real_ykmc_confirmed():
    v = _real("20261103000312")          # 영광와이케이엠씨 [발행조건확정]
    assert v["offer_price"] == 11000
    assert v["band"] == [9400, 11000]
    assert v["demand_ratio"] == 1163.35
    assert v["lockup_ratio"] == 7.21
    assert v["float_ratio"] == 34.81      # 정정 후 값(정정 전 34.86 아님)
    assert v["secondary_ratio"] == 21.74


def test_real_mbd_below_band():
    v = _real("20261110000253")          # 엠비디: 밴드 하단 미만 확정, 확약 0%
    assert v["offer_price"] == 7000
    assert v["band"] == [9600, 11700]
    assert v["demand_ratio"] == 187.1
    assert v["lockup_ratio"] == 0.0


def test_real_retail_terms():
    v = _real("20261103000312")          # 영광와이케이엠씨: 대신증권 단독
    assert v["min_shares"] == 20
    assert v["max_shares"] == 57000
    assert v["margin_rate"] == 50.0
    assert v["retail_shares"] == 575000
    assert v["equal_shares"] == 287500
