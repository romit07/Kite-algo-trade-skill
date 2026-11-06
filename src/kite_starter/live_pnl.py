from __future__ import annotations

from typing import Any


def extract_net_day_pnl(positions_response: dict[str, Any] | list[Any] | Any) -> float:
    """Sum `day` P&amp;L from Kite `positions()` response (best-effort across shapes)."""
    if isinstance(positions_response, dict):
        day_total = 0.0
        for key in ("day", "net"):
            seg = positions_response.get(key)
            if isinstance(seg, list):
                for row in seg:
                    if isinstance(row, dict) and "pnl" in row:
                        try:
                            day_total += float(row["pnl"])
                        except (TypeError, ValueError):
                            continue
        return day_total
    return 0.0
