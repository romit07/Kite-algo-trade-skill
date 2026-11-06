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

    def run_once(self, kite: KiteLike | None) -> dict[str, Any]:
        """Compute one step. Uses historical data from Kite if available."""
        instrument = self.settings.strategy_instrument_token
        interval = self.settings.strategy_bar_interval
        fast = self.settings.ema_fast
        slow = self.settings.ema_slow

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
                    instrument, "BUY", quantity=1, last_price=last_close
                )
            elif signal == "SELL":
                execution = self.paper.place_market_order(
                    instrument, "SELL", quantity=1, last_price=last_close
                )
        else:
            if not self.settings.enable_live_orders:
                execution = {
                    "blocked": True,
                    "reason": "Live orders disabled — set ENABLE_LIVE_ORDERS=true consciously",
                }
            else:
                execution = {
                    "blocked": True,
                    "reason": (
                        "Live placement not implemented in this educational starter — "
                        "wire `kite.place_order` yourself with product/exchange validation."
                    ),
                }

        return {
            "ok": True,
            "signal": signal,
            "last_close": last_close,
            "ema_fast": last_fast,
            "ema_slow": last_slow,
            "execution": execution,
        }
