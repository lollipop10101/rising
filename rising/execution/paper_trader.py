from __future__ import annotations
from rising.storage.database import RisingDB

class PaperTrader:
    def __init__(self, db: RisingDB, quote_usd: float):
        self.db = db
        self.quote_usd = quote_usd

    async def buy(self, token_address: str, entry_price: float, notes: str) -> int:
        return await self.db.create_trade(token_address, entry_price, self.quote_usd, notes)
