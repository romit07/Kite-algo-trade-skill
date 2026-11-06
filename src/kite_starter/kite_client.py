from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from kiteconnect import KiteConnect


class KiteLike(Protocol):
    """Protocol for test doubles — attributes used by this starter."""

    access_token: str | None

    def profile(self) -> dict[str, Any]: ...

    def positions(self) -> dict[str, Any]: ...

    def orders(self) -> list[dict[str, Any]]: ...

    def margins(self) -> dict[str, Any]: ...

    def instruments(self, exchange: str | None = None) -> list[dict[str, Any]]: ...

    def historical_data(
        self,
        instrument_token: int,
        from_date: Any,
        to_date: Any,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict[str, Any]]: ...

    def place_order(
        self,
        variety: str,
        exchange: str,
        tradingsymbol: str,
        transaction_type: str,
        quantity: int,
        product: str,
        order_type: str,
        validity: str | None = None,
        **kwargs: Any,
    ) -> str: ...


@dataclass
class KiteClientFactory:
    """Builds a `KiteConnect` instance when an access token is available."""

    api_key: str

    def build(self, access_token: str | None) -> KiteConnect:
        kite = KiteConnect(api_key=self.api_key)
        if access_token:
            kite.set_access_token(access_token)
        return kite
