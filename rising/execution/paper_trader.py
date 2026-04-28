from __future__ import annotations

from datetime import datetime

from rising.storage.database import Database


class PaperTrader:
    def __init__(self, db: Database) -> None:
        self.db = db

    def buy(self, token_address: str, entry_price: float, size_usd: float, now: datetime) -> int:
        if entry_price <= 0:
            raise ValueError("entry_price must be > 0")
        return self.db.open_trade(token_address, entry_price, size_usd, now)
