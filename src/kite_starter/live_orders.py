from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import kiteconnect.exceptions as kex

from .config import Settings
from .db import Database
from .kite_client import KiteLike
from .live_pnl import extract_net_day_pnl
from .risk import RiskError, assert_can_trade

log = logging.getLogger(__name__)

VARIETY_REGULAR = "regular"

ORDER_TYPES_F = frozenset({"MARKET", "LIMIT", "SL", "SL-M"})
PRODUCTS_F = frozenset({"MIS", "NRML", "CNC"})
EXCHANGES_F = frozenset({"NSE", "NFO", "BSE", "BFO", "MCX"})


def _order_tag(settings: Settings, suffix: str = "") -> str:
    base = settings.order_tag_prefix.strip() or "ks"
    suf = suffix or uuid.uuid4().hex[:8]
    tag = f"{base}-{suf}"[:20]
    return tag


def _find_orders_by_tag(orders: list[dict[str, Any]], tag: str) -> list[dict[str, Any]]:
    return [o for o in orders if isinstance(o, dict) and o.get("tag") == tag]


def _terminal_status(status: str | None) -> bool:
    if not status:
        return False
    u = status.upper()
    return u in ("COMPLETE", "REJECTED", "CANCELLED")


@dataclass
class PlaceParams:
    exchange: str
    tradingsymbol: str
    transaction_type: str
    quantity: int
    product: str
    order_type: str
    price: float | None = None
    trigger_price: float | None = None
    validity: str = "DAY"
    market_protection: int | None = -1


class LiveOrderService:
    """Guarded live order placement, logging, polling, and risk."""

    def __init__(self, settings: Settings, db: Database) -> None:
        self._settings = settings
        self._db = db

    def live_mode(self) -> bool:
        return not self._settings.paper_trading and self._settings.enable_live_orders

    def _assert_limits(
        self,
        kite: KiteLike,
        quantity: int,
        *,
        allow_despite_kill_switch: bool = False,
    ) -> None:
        assert_can_trade(
            self._settings,
            self._db,
            kite=kite,
            paper_mode=False,
            allow_despite_kill_switch=allow_despite_kill_switch,
        )
        if quantity <= 0:
            raise RiskError("Quantity must be positive.")
        if quantity > self._settings.max_order_quantity:
            raise RiskError(f"Quantity {quantity} exceeds MAX_ORDER_QUANTITY.")

    def _validate_params(self, p: PlaceParams) -> None:
        if p.exchange not in EXCHANGES_F:
            raise ValueError(f"Unsupported exchange: {p.exchange}")
        if p.product not in PRODUCTS_F:
            raise ValueError(f"Unsupported product: {p.product}")
        if p.order_type not in ORDER_TYPES_F:
            raise ValueError(f"Unsupported order type: {p.order_type}")
        if p.order_type in ("LIMIT", "SL") and p.price is None:
            raise ValueError("price required for LIMIT and SL orders")
        if p.order_type in ("SL", "SL-M") and p.trigger_price is None:
            raise ValueError("trigger_price required for SL and SL-M orders")

    def log_order_event(
        self,
        *,
        kind: str,
        order_id: str | None,
        tag: str | None,
        request: dict[str, Any],
        response: Any,
        error: str | None = None,
    ) -> None:
        self._db.add_live_order_event(
            kind=kind,
            order_id=order_id,
            tag=tag,
            request_json=request,
            response_json=response if not isinstance(response, Exception) else str(response),
            error=error,
        )

    def poll_until_terminal(
        self,
        kite: KiteLike,
        order_id: str,
        *,
        tag: str | None,
        interval: float | None = None,
        max_wait: float | None = None,
    ) -> dict[str, Any]:
        interval = interval if interval is not None else self._settings.order_poll_interval_sec
        max_wait = max_wait if max_wait is not None else self._settings.order_poll_max_wait_sec
        deadline = time.monotonic() + max_wait
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            try:
                hist = kite.order_history(order_id)
            except Exception as exc:  # noqa: BLE001
                log.warning("order_history failed for %s: %s", order_id, exc)
                time.sleep(interval)
                continue
            if isinstance(hist, list) and hist:
                last = hist[-1] if isinstance(hist[-1], dict) else {}
            elif isinstance(hist, dict):
                last = hist
            status = last.get("status") if isinstance(last, dict) else None
            if _terminal_status(str(status) if status is not None else None):
                self.log_order_event(
                    kind="poll",
                    order_id=order_id,
                    tag=tag,
                    request={"order_id": order_id},
                    response=hist,
                )
                return {"ok": True, "final": last, "history": hist}
            time.sleep(interval)
        self.log_order_event(
            kind="poll_timeout",
            order_id=order_id,
            tag=tag,
            request={"order_id": order_id},
            response=last,
            error="timeout waiting for terminal status",
        )
        return {"ok": False, "error": "poll timeout", "last": last}

    def place_order(
        self,
        kite: KiteLike,
        params: PlaceParams,
        *,
        tag_suffix: str | None = None,
        allow_despite_kill_switch: bool = False,
    ) -> dict[str, Any]:
        if not self.live_mode():
            raise RiskError("Live orders disabled — enable PAPER_TRADING=false and ENABLE_LIVE_ORDERS=true")
        if not getattr(kite, "access_token", None):
            raise RiskError("Not authenticated — exchange request_token first")

        self._validate_params(params)
        self._assert_limits(
            kite,
            params.quantity,
            allow_despite_kill_switch=allow_despite_kill_switch,
        )

        tag = _order_tag(self._settings, tag_suffix or "")

        place_kwargs: dict[str, Any] = {
            "variety": VARIETY_REGULAR,
            "exchange": params.exchange,
            "tradingsymbol": params.tradingsymbol,
            "transaction_type": params.transaction_type,
            "quantity": params.quantity,
            "product": params.product,
            "order_type": params.order_type,
            "validity": params.validity,
            "tag": tag,
        }
        if params.price is not None:
            place_kwargs["price"] = params.price
        if params.trigger_price is not None:
            place_kwargs["trigger_price"] = params.trigger_price
        if params.order_type == "MARKET" and params.market_protection is not None:
            place_kwargs["market_protection"] = params.market_protection

        def _post_with_optional_network_retry() -> str:
            attempt = 0
            while True:
                try:
                    oid = kite.place_order(**place_kwargs)
                    return oid
                except kex.NetworkException as e:
                    attempt += 1
                    if attempt > self._settings.network_retry_attempts:
                        raise
                    time.sleep(self._settings.network_retry_delay_sec)

        try:
            order_id = _post_with_optional_network_retry()
        except kex.InputException as e:
            self.log_order_event(
                kind="place_error",
                order_id=None,
                tag=tag,
                request=place_kwargs,
                response=None,
                error=str(e),
            )
            raise
        except kex.TokenException as e:
            self.log_order_event(
                kind="place_error",
                order_id=None,
                tag=tag,
                request=place_kwargs,
                response=None,
                error=f"TokenException: {e}",
            )
            raise
        except kex.NetworkException as e:
            orders = []
            try:
                orders = kite.orders()
            except Exception:  # noqa: BLE001
                pass
            dupes = _find_orders_by_tag(orders if isinstance(orders, list) else [], tag)
            if dupes:
                recovered_id = str(dupes[0].get("order_id", ""))
                self.log_order_event(
                    kind="place_recovered_by_tag",
                    order_id=recovered_id,
                    tag=tag,
                    request=place_kwargs,
                    response=dupes[0],
                )
                self._db.increment_orders()
                order_id = recovered_id
            else:
                self.log_order_event(
                    kind="place_error",
                    order_id=None,
                    tag=tag,
                    request=place_kwargs,
                    response=None,
                    error=f"NetworkException: {e}",
                )
                raise

        self._db.increment_orders()
        self.log_order_event(
            kind="place",
            order_id=str(order_id),
            tag=tag,
            request=place_kwargs,
            response={"order_id": order_id},
        )

        market_rejected = False
        poll = self.poll_until_terminal(kite, str(order_id), tag=tag)
        final = poll.get("final") or {}
        if isinstance(final, dict):
            rej = str(final.get("status_message", "")).lower()
            if final.get("status") == "REJECTED" and (
                "market" in rej or "protection" in rej or "circuit" in rej
            ):
                market_rejected = True

        if market_rejected and params.order_type == "MARKET":
            return self._fallback_limit_after_market_rejection(kite, params, tag, place_kwargs)

        return {"ok": True, "order_id": str(order_id), "tag": tag, "poll": poll}

    def _fallback_limit_after_market_rejection(
        self,
        kite: KiteLike,
        params: PlaceParams,
        original_tag: str,
        original_request: dict[str, Any],
    ) -> dict[str, Any]:
        """Place LIMIT at buffer off LTP when MARKET is rejected (best-effort)."""
        quote_key = f"{params.exchange}:{params.tradingsymbol}"
        ltp = None
        try:
            q = kite.quote(quote_key)
            depth = q.get(quote_key) or (next(iter(q.values())) if isinstance(q, dict) else {})
            if isinstance(depth, dict):
                ltp = depth.get("last_price") or depth.get("ohlc", {}).get("close")
        except Exception as exc:  # noqa: BLE001
            self.log_order_event(
                kind="fallback_limit_skip",
                order_id=None,
                tag=original_tag,
                request=original_request,
                response=None,
                error=f"quote failed: {exc}",
            )
            return {
                "ok": False,
                "error": "market rejected and quote failed for limit fallback",
            }

        if ltp is None:
            return {"ok": False, "error": "market rejected — could not read LTP for limit fallback"}

        buf = self._settings.market_fallback_limit_buffer_pct / 100.0
        if params.transaction_type == "BUY":
            limit_px = float(ltp) * (1.0 + buf)
        else:
            limit_px = float(ltp) * (1.0 - buf)

        tag2 = _order_tag(self._settings, "fb")
        fb_kwargs = {
            "variety": VARIETY_REGULAR,
            "exchange": params.exchange,
            "tradingsymbol": params.tradingsymbol,
            "transaction_type": params.transaction_type,
            "quantity": params.quantity,
            "product": params.product,
            "order_type": "LIMIT",
            "validity": params.validity,
            "price": round(limit_px, 2),
            "tag": tag2,
        }
        try:
            oid = kite.place_order(**fb_kwargs)
        except kex.NetworkException as e:
            orders = []
            try:
                orders = kite.orders()
            except Exception:  # noqa: BLE001
                pass
            dupes = _find_orders_by_tag(orders if isinstance(orders, list) else [], tag2)
            if dupes:
                oid = str(dupes[0].get("order_id", ""))
            else:
                self.log_order_event(
                    kind="fallback_limit_error",
                    order_id=None,
                    tag=tag2,
                    request=fb_kwargs,
                    response=None,
                    error=str(e),
                )
                raise
        self._db.increment_orders()
        self.log_order_event(
            kind="place_fallback_limit",
            order_id=str(oid),
            tag=tag2,
            request=dict(original_request, **fb_kwargs, original_tag=original_tag),
            response={"order_id": oid},
        )
        poll = self.poll_until_terminal(kite, str(oid), tag=tag2)
        return {"ok": True, "order_id": str(oid), "tag": tag2, "poll": poll, "fallback": True}

    def modify_order(
        self,
        kite: KiteLike,
        *,
        order_id: str,
        quantity: int | None = None,
        price: float | None = None,
        order_type: str | None = None,
        trigger_price: float | None = None,
    ) -> dict[str, Any]:
        if not self.live_mode():
            raise RiskError("Live orders disabled")
        kwargs: dict[str, Any] = {"variety": VARIETY_REGULAR, "order_id": order_id}
        if quantity is not None:
            kwargs["quantity"] = quantity
        if price is not None:
            kwargs["price"] = price
        if order_type is not None:
            kwargs["order_type"] = order_type
        if trigger_price is not None:
            kwargs["trigger_price"] = trigger_price
        try:
            new_id = kite.modify_order(**kwargs)
        except kex.NetworkException as e:
            self.log_order_event(
                kind="modify_error",
                order_id=order_id,
                tag=None,
                request=kwargs,
                response=None,
                error=str(e),
            )
            raise
        self.log_order_event(
            kind="modify",
            order_id=str(new_id),
            tag=None,
            request=kwargs,
            response={"order_id": new_id},
        )
        return {"ok": True, "order_id": str(new_id)}

    def cancel_order(self, kite: KiteLike, *, order_id: str) -> dict[str, Any]:
        if not self.live_mode():
            raise RiskError("Live orders disabled")
        try:
            cid = kite.cancel_order(VARIETY_REGULAR, order_id)
        except kex.NetworkException as e:
            self.log_order_event(
                kind="cancel_error",
                order_id=order_id,
                tag=None,
                request={"order_id": order_id},
                response=None,
                error=str(e),
            )
            raise
        self.log_order_event(
            kind="cancel",
            order_id=str(cid),
            tag=None,
            request={"variety": VARIETY_REGULAR, "order_id": order_id},
            response={"order_id": cid},
        )
        return {"ok": True, "order_id": str(cid)}

    def cancel_open_orders(self, kite: KiteLike) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            book = kite.orders()
        except Exception as exc:  # noqa: BLE001
            return [{"ok": False, "error": str(exc)}]
        if not isinstance(book, list):
            return [{"ok": False, "error": "unexpected orders response"}]
        prefix = self._settings.order_tag_prefix.strip()
        if not prefix:
            return [
                {
                    "ok": False,
                    "error": "ORDER_TAG_PREFIX is empty — refusing mass cancel for safety",
                }
            ]
        for o in book:
            if not isinstance(o, dict):
                continue
            status = str(o.get("status", "")).upper()
            if status in ("COMPLETE", "REJECTED", "CANCELLED"):
                continue
            tag_o = str(o.get("tag") or "")
            if not tag_o.startswith(prefix):
                continue
            oid = o.get("order_id")
            if oid is None:
                continue
            try:
                results.append(self.cancel_order(kite, order_id=str(oid)))
            except Exception as e:  # noqa: BLE001
                results.append({"ok": False, "order_id": str(oid), "error": str(e)})
        return results

    def square_off_positions(self, kite: KiteLike) -> list[dict[str, Any]]:
        """Close net day positions (best-effort MARKET with tag)."""
        if not self.live_mode():
            raise RiskError("Live orders disabled")
        try:
            pos = kite.positions()
        except Exception as exc:  # noqa: BLE001
            return [{"ok": False, "error": str(exc)}]
        out: list[dict[str, Any]] = []
        day = []
        if isinstance(pos, dict):
            day = pos.get("day") or []
        for row in day if isinstance(day, list) else []:
            if not isinstance(row, dict):
                continue
            qty = int(row.get("quantity") or 0)
            if qty == 0:
                continue
            ex = str(row.get("exchange") or "").strip()
            sym = str(row.get("tradingsymbol") or "").strip()
            if not ex or not sym:
                out.append({"ok": False, "error": "missing exchange or tradingsymbol", "row": row})
                continue
            txn = "SELL" if qty > 0 else "BUY"
            q = abs(qty)
            p = PlaceParams(
                exchange=ex,
                tradingsymbol=sym,
                transaction_type=txn,
                quantity=q,
                product=str(row.get("product", "NRML")),
                order_type="MARKET",
                market_protection=-1,
            )
            try:
                out.append(
                    self.place_order(
                        kite,
                        p,
                        tag_suffix="sq",
                        allow_despite_kill_switch=True,
                    )
                )
            except Exception as e:  # noqa: BLE001
                out.append({"ok": False, "error": str(e), "row": row})
        return out


def touch_kill_switch(path: str) -> None:
    Path(path).write_text("1", encoding="utf-8")
