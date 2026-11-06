from __future__ import annotations

"""Generic **demo** strategy: EMA crossover on OHLC candles.

**Educational only — not financial advice.** Replace instruments and parameters with
your own research; this module exists to show how a signal might be wired.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from ..config import Settings
from ..db import Database
from ..kite_client import KiteLike
from ..live_orders import LiveOrderService, PlaceParams
from ..paper import PaperBroker


def _ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    out: list[float] = []
    sma = sum(values[:period]) / period
    out.append(sma)
    prev = sma
    for v in values[period:]:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


@dataclass
class DemoEmaCrossover:
    """Long-only demo: BUY when fast EMA crosses above slow; SELL when it crosses below."""

    settings: Settings
    db: Database
    paper: PaperBroker
    live_orders: LiveOrderService

    def run_once(self, kite: KiteLike | None) -> dict[str, Any]:
        """Compute one step. Uses historical data from Kite if available."""
        instrument = self.settings.strategy_instrument_token
        interval = self.settings.strategy_bar_interval
        fast = self.settings.ema_fast
        slow = self.settings.ema_slow
        qty = self.settings.strategy_order_quantity

        if fast >= slow:
            return {"ok": False, "error": "ema_fast must be smaller than ema_slow"}

        if kite is None or not kite.access_token:
            return {
                "ok": False,
                "error": "Not logged in — set access token via /api/auth/exchange",
            }

        to_d = date.today()
        from_d = to_d - timedelta(days=max(slow * 5, 120))

        try:
            candles = kite.historical_data(
                instrument_token=instrument,
                from_date=from_d,
                to_date=to_d,
                interval=interval,
                continuous=False,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced to dashboard
            return {"ok": False, "error": f"historical_data failed: {exc}"}

        closes = [float(c["close"]) for c in candles if c.get("close") is not None]
        if len(closes) < slow + 2:
            return {"ok": False, "error": "insufficient candles"}

        ema_f = _ema(closes, fast)
        ema_s = _ema(closes, slow)
        if len(ema_f) < 2 or len(ema_s) < 2:
            return {"ok": False, "error": "could not compute EMAs"}

        prev_fast = ema_f[-2]
        last_fast = ema_f[-1]
        prev_slow = ema_s[-2]
        last_slow = ema_s[-1]
        last_close = closes[-1]

        signal = "HOLD"
        if prev_fast <= prev_slow and last_fast > last_slow:
            signal = "BUY"
        elif prev_fast >= prev_slow and last_fast < last_slow:
            signal = "SELL"

        self.db.set_last_signal(signal)

        execution: dict[str, Any] = {"mode": "none"}

        if self.settings.paper_trading:
            if signal == "BUY":
                execution = self.paper.place_market_order(
                    instrument, "BUY", quantity=qty, last_price=last_close
                )
            elif signal == "SELL":
                execution = self.paper.place_market_order(
                    instrument, "SELL", quantity=qty, last_price=last_close
                )
        elif self.live_orders.live_mode():
            if signal in ("BUY", "SELL"):
                params = PlaceParams(
                    exchange=self.settings.strategy_exchange,
                    tradingsymbol=self.settings.strategy_tradingsymbol,
                    transaction_type=signal,
                    quantity=qty,
                    product=self.settings.strategy_product,
                    order_type="MARKET",
                    market_protection=-1,
                )
                try:
                    execution = self.live_orders.place_order(kite, params, tag_suffix="demo")
                except Exception as exc:  # noqa: BLE001
                    execution = {"ok": False, "error": str(exc), "live": True}
            else:
                execution = {"mode": "live", "skipped": "HOLD"}
        else:
            execution = {
                "blocked": True,
                "reason": "Live orders disabled — set ENABLE_LIVE_ORDERS=true and PAPER_TRADING=false",
            }

        return {
            "ok": True,
            "signal": signal,
            "last_close": last_close,
            "ema_fast": last_fast,
            "ema_slow": last_slow,
            "execution": execution,
        }
