from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .db import Database, pnl_snapshot
from .live_pnl import extract_net_day_pnl

if TYPE_CHECKING:
    from .config import Settings
    from .kite_client import KiteLike

log = logging.getLogger(__name__)


class RiskError(Exception):
    """Raised when a risk rule blocks an order."""


def kill_switch_active(settings: "Settings") -> bool:
    return Path(settings.kill_switch_path).exists()


def assert_can_trade(
    settings: "Settings",
    db: Database,
    *,
    kite: KiteLike | None = None,
    paper_mode: bool = True,
    allow_despite_kill_switch: bool = False,
) -> None:
    """Raise `RiskError` when limits block new activity."""
    if kill_switch_active(settings) and not allow_despite_kill_switch:
        raise RiskError("Kill-switch file present — new orders blocked.")

    if not paper_mode and kite is not None:
        try:
            positions = kite.positions()
            net = extract_net_day_pnl(positions)
            db.sync_live_day_pnl(net)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not sync live day P&L: %s", exc)

    snap = pnl_snapshot(db)
    if snap.orders_placed >= settings.max_orders_per_day:
        raise RiskError("Max orders per day reached.")

    if snap.realized_pnl <= -abs(settings.max_daily_loss_inr):
        raise RiskError("Max daily loss limit reached.")
