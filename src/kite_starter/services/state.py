from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..db import Database
from ..kite_client import KiteClientFactory
from ..live_orders import LiveOrderService
from ..paper import PaperBroker
from ..strategies.demo_ema_crossover import DemoEmaCrossover


@dataclass
class AppState:
    settings: Settings
    db: Database
    kite_factory: KiteClientFactory
    paper: PaperBroker
    live_orders: LiveOrderService
    strategy: DemoEmaCrossover

    @classmethod
    def from_settings(cls, settings: Settings) -> AppState:
        db = Database(settings.database_path)
        factory = KiteClientFactory(api_key=settings.kite_api_key)
        paper = PaperBroker(db, settings)
        live_orders = LiveOrderService(settings, db)
        strategy = DemoEmaCrossover(settings, db, paper, live_orders)
        return cls(
            settings=settings,
            db=db,
            kite_factory=factory,
            paper=paper,
            live_orders=live_orders,
            strategy=strategy,
        )

    def kite_with_token(self):
        tokens = self.db.get_session_tokens() or {}
        access = tokens.get("access_token")
        return self.kite_factory.build(access)
