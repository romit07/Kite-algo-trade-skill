from __future__ import annotations

from pathlib import Path

from .config import Settings
from .db import Database, pnl_snapshot


class RiskError(Exception):
    """Raised when a risk rule blocks an order."""


def kill_switch_active(settings: Settings) -> bool:
    return Path(settings.kill_switch_path).exists()


def assert_can_trade(settings: Settings, db: Database) -> None:
    """Raise `RiskError` when limits block new activity."""
    if kill_switch_active(settings):
        raise RiskError("Kill-switch file present — new orders blocked.")

    snap = pnl_snapshot(db)
    if snap.orders_placed >= settings.max_orders_per_day:
        raise RiskError("Max orders per day reached.")

    if snap.realized_pnl <= -abs(settings.max_daily_loss_inr):
        raise RiskError("Max daily loss limit reached.")
