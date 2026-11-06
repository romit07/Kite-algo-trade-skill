from __future__ import annotations

from datetime import date, timedelta

from kite_starter.config import Settings
from kite_starter.db import Database
from kite_starter.live_orders import LiveOrderService
from kite_starter.paper import PaperBroker
from kite_starter.risk import RiskError
from kite_starter.strategies.demo_ema_crossover import DemoEmaCrossover


class FakeKite:
    def __init__(self) -> None:
        self.access_token = "fake"

    def historical_data(self, instrument_token, from_date, to_date, interval, continuous=False, oi=False):
        days = (to_date - from_date).days + 1
        out = []
        base = date.fromisoformat("2020-01-01")
        for i in range(days):
            d = base + timedelta(days=i)
            close = 100 + i * 0.2
            if i > days - 10:
                close -= (i - (days - 10)) * 0.5
            out.append({"date": d, "open": close, "high": close, "low": close, "close": close, "volume": 1})
        return out


def test_demo_strategy_runs_paper_buy_sell(tmp_path):
    settings = Settings(
        kite_api_key="YOUR_API_KEY",
        kite_api_secret="YOUR_API_SECRET",
        paper_trading=True,
        enable_live_orders=False,
        database_path=str(tmp_path / "t.db"),
        strategy_instrument_token=256265,
        strategy_bar_interval="day",
        ema_fast=3,
        ema_slow=5,
        max_orders_per_day=50,
        max_daily_loss_inr=1_000_000.0,
        kill_switch_path=str(tmp_path / "no-kill"),
    )
    db = Database(settings.database_path)
    paper = PaperBroker(db, settings)
    live = LiveOrderService(settings, db)
    strat = DemoEmaCrossover(settings, db, paper, live)
    kite = FakeKite()
    res = strat.run_once(kite)
    assert res["ok"] is True
    assert res["signal"] in ("BUY", "SELL", "HOLD")


def test_risk_blocks_after_order_limit(tmp_path):
    settings = Settings(
        kite_api_key="k",
        kite_api_secret="s",
        paper_trading=True,
        database_path=str(tmp_path / "t.db"),
        max_orders_per_day=1,
        max_daily_loss_inr=1_000_000.0,
        kill_switch_path=str(tmp_path / "no-kill"),
    )
    db = Database(settings.database_path)
    paper = PaperBroker(db, settings)
    paper.place_market_order(1, "BUY", 1, last_price=100.0)
    try:
        paper.place_market_order(1, "BUY", 1, last_price=100.0)
    except RiskError:
        return
    raise AssertionError("expected RiskError")
