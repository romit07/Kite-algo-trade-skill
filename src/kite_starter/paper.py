from __future__ import annotations

import uuid
from typing import Any

from .config import Settings
from .db import Database
from .risk import assert_can_trade


class PaperBroker:
    """Minimal paper-trading simulator — **educational only**.

    Long-only illustrative model: BUY increases position; SELL reduces and realizes P&L
    against average cost.
    """

    def __init__(self, db: Database, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    def _get_position(self, instrument_token: int) -> tuple[int, float]:
        for p in self._db.get_paper_positions():
            if p["instrument_token"] == instrument_token:
                return int(p["quantity"]), float(p["average_price"])
        return 0, 0.0

    def place_market_order(
        self,
        instrument_token: int,
        side: str,
        quantity: int,
        *,
        last_price: float,
    ) -> dict[str, Any]:
        assert_can_trade(self._settings, self._db)
        self._db.increment_orders()

        side_u = side.upper()
        if side_u not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        oid = f"PAPER-{uuid.uuid4().hex[:12]}"
        pos_qty, avg_price = self._get_position(instrument_token)

        if side_u == "BUY":
            new_qty = pos_qty + quantity
            if pos_qty <= 0:
                new_avg = last_price
            else:
                new_avg = (pos_qty * avg_price + quantity * last_price) / new_qty
            self._db.upsert_paper_position(instrument_token, new_qty, new_avg)

        else:  # SELL
            sell_qty = min(quantity, pos_qty) if pos_qty > 0 else quantity
            if pos_qty > 0 and sell_qty > 0:
                realized = (last_price - avg_price) * sell_qty
                self._db.add_realized_pnl(float(realized))
            new_qty = pos_qty - sell_qty
            if new_qty <= 0:
                new_avg = 0.0
                new_qty = 0
            else:
                new_avg = avg_price
            self._db.upsert_paper_position(instrument_token, new_qty, new_avg)

        self._db.add_paper_order(
            instrument_token=instrument_token,
            side=side_u,
            quantity=quantity,
            order_type="MARKET",
            status="COMPLETE",
            price=last_price,
            paper_order_id=oid,
        )
        return {"order_id": oid, "status": "COMPLETE", "paper": True}
