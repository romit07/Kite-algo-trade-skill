from __future__ import annotations

import kiteconnect.exceptions as kex

from kite_starter.config import Settings
from kite_starter.db import Database
from kite_starter.live_orders import LiveOrderService, PlaceParams


def _settings(tmp_path, **kw):
    base = dict(
        kite_api_key="k",
        kite_api_secret="s",
        database_path=str(tmp_path / "d.db"),
        paper_trading=False,
        enable_live_orders=True,
        max_orders_per_day=10,
        max_order_quantity=5,
        max_daily_loss_inr=1000.0,
        kill_switch_path=str(tmp_path / "ks"),
        order_tag_prefix="ks",
        order_poll_interval_sec=0.01,
        order_poll_max_wait_sec=0.5,
    )
    base.update(kw)
    return Settings(**base)


def test_gating_requires_both_flags(tmp_path):
    s = _settings(tmp_path, paper_trading=True, enable_live_orders=True)
    db = Database(s.database_path)
    srv = LiveOrderService(s, db)
    kite = _MinimalKite()
    p = PlaceParams("NSE", "TEST", "BUY", 1, "MIS", "MARKET")
    try:
        srv.place_order(kite, p)
    except Exception as exc:
        assert "Live orders disabled" in str(exc)
    else:
        raise AssertionError("expected error")


def test_max_qty_blocked(tmp_path):
    s = _settings(tmp_path)
    db = Database(s.database_path)
    srv = LiveOrderService(s, db)
    kite = _MinimalKite()
    p = PlaceParams("NSE", "TEST", "BUY", 99, "MIS", "MARKET")
    try:
        srv.place_order(kite, p)
    except Exception as exc:
        assert "MAX_ORDER_QUANTITY" in str(exc)
    else:
        raise AssertionError("expected error")


def test_live_daily_loss_blocks(tmp_path):
    s = _settings(tmp_path, max_daily_loss_inr=50.0)
    db = Database(s.database_path)
    srv = LiveOrderService(s, db)
    kite = _MinimalKite()
    p = PlaceParams("NSE", "TEST", "BUY", 1, "MIS", "MARKET")
    try:
        srv.place_order(kite, p)
    except Exception as exc:
        assert "Max daily loss" in str(exc)
    else:
        raise AssertionError("expected error")


def test_network_failure_recovered_by_tag_scan(tmp_path):
    s = _settings(tmp_path, network_retry_attempts=0, network_retry_delay_sec=0.01)

    class Kite:
        access_token = "t"

        def __init__(self) -> None:
            self.last_tag: str | None = None

        def positions(self):
            return {"day": [{"pnl": 0.0}]}

        def place_order(self, **kwargs):
            self.last_tag = kwargs.get("tag")
            raise kex.NetworkException("timeout", 0)

        def orders(self):
            return [{"order_id": "recovered", "tag": self.last_tag}]

        def order_history(self, order_id):
            return [{"status": "COMPLETE", "order_id": order_id}]

    db = Database(s.database_path)
    srv = LiveOrderService(s, db)
    kite = Kite()
    p = PlaceParams("NSE", "TEST", "BUY", 1, "MIS", "MARKET")
    res = srv.place_order(kite, p)
    assert res["ok"] is True
    assert res["order_id"] == "recovered"


def test_input_exception_no_order_increment(tmp_path):
    s = _settings(tmp_path)

    class BadKite(_MinimalKite):
        def place_order(self, **kwargs):
            raise kex.InputException("bad params", 0)

    db = Database(s.database_path)
    srv = LiveOrderService(s, db)
    kite = BadKite()
    p = PlaceParams("NSE", "TEST", "BUY", 1, "MIS", "MARKET")
    try:
        srv.place_order(kite, p)
    except kex.InputException:
        assert db.today_counters()[0] == 0
        return
    raise AssertionError("expected InputException")


def test_market_rejection_triggers_limit_fallback(tmp_path):
    s = _settings(tmp_path)

    class RejectKite(_MinimalKite):
        def __init__(self) -> None:
            super().__init__()
            self._n = 0

        def positions(self):
            return {"day": [{"pnl": 0.0}]}

        def place_order(self, **kwargs):
            self._n += 1
            self.placed.append(kwargs)
            return f"oid-{self._n}"

        def order_history(self, order_id):
            if str(order_id).startswith("oid-1"):
                return [{"status": "REJECTED", "status_message": "market order rejected"}]
            return [{"status": "COMPLETE"}]

        def quote(self, *_):
            return {"NSE:TEST": {"last_price": 100.0}}

    db = Database(s.database_path)
    srv = LiveOrderService(s, db)
    kite = RejectKite()
    p = PlaceParams("NSE", "TEST", "BUY", 1, "MIS", "MARKET")
    res = srv.place_order(kite, p)
    assert res.get("fallback") is True
    assert any(x.get("order_type") == "LIMIT" for x in kite.placed)


def test_kill_switch_blocks_new_orders(tmp_path):
    s = _settings(tmp_path)
    p_ks = tmp_path / "kill"
    p_ks.write_text("1", encoding="utf-8")
    s = _settings(tmp_path, kill_switch_path=str(p_ks))
    db = Database(s.database_path)
    srv = LiveOrderService(s, db)
    kite = _MinimalKite()
    p = PlaceParams("NSE", "TEST", "BUY", 1, "MIS", "MARKET")
    try:
        srv.place_order(kite, p)
    except Exception as exc:
        assert "Kill-switch" in str(exc)
        return
    raise AssertionError("expected error")


class _MinimalKite:
    access_token = "t"
    placed: list

    def __init__(self) -> None:
        self.placed = []

    def positions(self):
        return {"day": [{"pnl": -100.0}]}

    def orders(self):
        return []

    def place_order(self, **kwargs):
        self.placed.append(kwargs)
        return "oid-1"

    def order_history(self, order_id):
        return [{"status": "COMPLETE", "order_id": order_id}]

    def quote(self, *_):
        return {"NSE:TEST": {"last_price": 100.0}}
