from __future__ import annotations

from kite_starter.live_pnl import extract_net_day_pnl


def test_extract_net_day_pnl():
    pnl = extract_net_day_pnl({"day": [{"pnl": "10"}, {"pnl": -3.5}]})
    assert pnl == 6.5


def test_extract_empty():
    assert extract_net_day_pnl({}) == 0.0
