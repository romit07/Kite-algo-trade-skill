from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..db import Database
from ..kite_client import KiteClientFactory
from ..paper import PaperBroker
from ..strategies.demo_ema_crossover import DemoEmaCrossover


@dataclass
class AppState:
    settings: Settings
    db: Database
    kite_factory: KiteClientFactory
    paper: PaperBroker
    strategy: DemoEmaCrossover

    @classmethod
    def from_settings(cls, settings: Settings) -> AppState:
        db = Database(settings.database_path)
        factory = KiteClientFactory(api_key=settings.kite_api_key)
        paper = PaperBroker(db, settings)
        strategy = DemoEmaCrossover(settings, db, paper)
        return cls(
            settings=settings,
            db=db,
            kite_factory=factory,
            paper=paper,
            strategy=strategy,
        )

    def kite_with_token(self):
        tokens = self.db.get_session_tokens() or {}
        access = tokens.get("access_token")
        return self.kite_factory.build(access)
