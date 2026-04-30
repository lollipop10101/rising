from __future__ import annotations

from datetime import datetime

from rising.storage.database import Database


class PaperTrader:
    def __init__(self, db: Database, default_balance: float = 100.0, balance_floor: float = 50.0) -> None:
        self.db = db
        self.default_balance = default_balance
        self.balance_floor = balance_floor

    def get_balance(self) -> float:
        return self.db.get_paper_balance(self.default_balance)

    def buy(self, token_address: str, entry_price: float, size_usd: float, now: datetime) -> int:
        if entry_price <= 0:
            raise ValueError("entry_price must be > 0")
        return self.db.open_trade(token_address, entry_price, size_usd, now)

    def close_trade_for_balance(self, trade_id: int, realized_pnl: float) -> float:
        balance = self.get_balance() + realized_pnl
        balance = max(self.balance_floor, balance)
        self.db.set_paper_balance(balance)
        return balance
