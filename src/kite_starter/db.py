from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


class Database:
    """Minimal SQLite persistence for tokens, paper trading, and risk counters."""

    def __init__(self, path: str) -> None:
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kv (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_positions (
                  instrument_token INTEGER PRIMARY KEY,
                  quantity INTEGER NOT NULL,
                  average_price REAL NOT NULL,
                  last_updated TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_orders (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  instrument_token INTEGER NOT NULL,
                  side TEXT NOT NULL,
                  quantity INTEGER NOT NULL,
                  order_type TEXT NOT NULL,
                  status TEXT NOT NULL,
                  price REAL,
                  paper_order_id TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS risk_day (
                  day TEXT PRIMARY KEY,
                  orders_placed INTEGER NOT NULL DEFAULT 0,
                  realized_pnl REAL NOT NULL DEFAULT 0.0
                );
                CREATE TABLE IF NOT EXISTS strategy_state (
                  id INTEGER PRIMARY KEY CHECK (id = 1),
                  running INTEGER NOT NULL,
                  last_signal TEXT,
                  last_run TEXT
                );
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO strategy_state (id, running, last_signal, last_run) "
                "VALUES (1, 0, NULL, NULL)"
            )

    def kv_get(self, key: str, default: Any = None) -> Any:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
            if row is None:
                return default
            return json.loads(row["value"])

    def kv_set(self, key: str, value: Any) -> None:
        payload = json.dumps(value)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO kv(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, payload),
            )

    def set_session_tokens(self, access_token: str, refresh_token: str | None) -> None:
        self.kv_set(
            "session",
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def get_session_tokens(self) -> dict[str, Any] | None:
        return self.kv_get("session")

    def strategy_running(self) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT running FROM strategy_state WHERE id = 1").fetchone()
            return bool(row["running"]) if row else False

    def set_strategy_running(self, running: bool) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE strategy_state SET running = ?, last_run = ? WHERE id = 1",
                (1 if running else 0, datetime.now(timezone.utc).isoformat()),
            )

    def set_last_signal(self, signal: str | None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE strategy_state SET last_signal = ?, last_run = ? WHERE id = 1",
                (signal, datetime.now(timezone.utc).isoformat()),
            )

    def get_strategy_meta(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT running, last_signal, last_run FROM strategy_state WHERE id = 1").fetchone()
        return dict(row) if row else {"running": 0, "last_signal": None, "last_run": None}

    def today_counters(self) -> tuple[int, float]:
        day = date.today().isoformat()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT orders_placed, realized_pnl FROM risk_day WHERE day = ?",
                (day,),
            ).fetchone()
        if row is None:
            return 0, 0.0
        return int(row["orders_placed"]), float(row["realized_pnl"])

    def increment_orders(self) -> None:
        day = date.today().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO risk_day(day, orders_placed, realized_pnl) VALUES (?,?,?) "
                "ON CONFLICT(day) DO UPDATE SET orders_placed = risk_day.orders_placed + 1",
                (day, 1, 0.0),
            )

    def add_realized_pnl(self, delta: float) -> None:
        day = date.today().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO risk_day(day, orders_placed, realized_pnl) VALUES (?,?,?) "
                "ON CONFLICT(day) DO UPDATE SET realized_pnl = risk_day.realized_pnl + ?",
                (day, 0, delta, delta),
            )

    def upsert_paper_position(
        self, instrument_token: int, quantity: int, average_price: float
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO paper_positions(instrument_token, quantity, average_price, last_updated) "
                "VALUES (?,?,?,?) "
                "ON CONFLICT(instrument_token) DO UPDATE SET "
                "quantity = excluded.quantity, average_price = excluded.average_price, last_updated = excluded.last_updated",
                (instrument_token, quantity, average_price, now),
            )

    def get_paper_positions(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM paper_positions").fetchall()
        return [dict(r) for r in rows]

    def add_paper_order(
        self,
        instrument_token: int,
        side: str,
        quantity: int,
        order_type: str,
        status: str,
        price: float | None,
        paper_order_id: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO paper_orders(instrument_token, side, quantity, order_type, status, price, paper_order_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (instrument_token, side, quantity, order_type, status, price, paper_order_id, now),
            )

    def recent_paper_orders(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_orders ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


@dataclass
class PnLSnapshot:
    day: str
    realized_pnl: float
    orders_placed: int


def pnl_snapshot(db: Database) -> PnLSnapshot:
    d = date.today().isoformat()
    orders, pnl = db.today_counters()
    return PnLSnapshot(day=d, realized_pnl=pnl, orders_placed=orders)
