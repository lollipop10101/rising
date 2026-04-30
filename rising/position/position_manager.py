from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from rising.execution.paper_trader import PaperTrader
from rising.storage.database import Database


@dataclass(slots=True)
class ExitConfig:
    stop_loss_pct: float
    tp1_pct: float
    tp1_sell_pct: float
    tp2_pct: float
    tp2_sell_pct: float
    max_hold_minutes: float


class PositionManager:
    def __init__(self, db: Database, config: ExitConfig, price_client, paper: PaperTrader, min_liquidity_usd: float = 5000) -> None:
        self.db = db
        self.config = config
        self.price_client = price_client
        self.paper = paper
        self.min_liquidity_usd = min_liquidity_usd

    async def evaluate_trade(self, trade, current_price: float, now: datetime) -> str | None:
        # Fetch current liquidity
        snapshot = await self.price_client.fetch_token(trade['token_address'])
        liquidity = snapshot.liquidity_usd if snapshot else None

        # Advisory: if liquidity is below threshold, flag but don't block
        if liquidity is not None and liquidity < self.min_liquidity_usd:
            self.db.add_trade_event(int(trade["id"]), "LIQUIDITY_CHECK", now, current_price, 0, 0.0,
                f"liquidity ${liquidity:,.0f} below min ${self.min_liquidity_usd:,.0f}, exit may not be realizable")

        entry = float(trade["entry_price"])
        remaining = float(trade["remaining_pct"])
        realized = float(trade["realized_pnl_usd"])
        size = float(trade["initial_size_usd"])
        opened_at = datetime.fromisoformat(trade["opened_at"])
        pnl_pct = ((current_price / entry) - 1.0) * 100.0
        age_min = (now - opened_at).total_seconds() / 60.0
        trade_id = int(trade["id"])

        if pnl_pct <= self.config.stop_loss_pct:
            pnl = self._pnl_for_pct(size, remaining, pnl_pct)
            self.db.add_trade_event(trade_id, "STOP_LOSS", now, current_price, remaining, pnl, "full exit")
            new_realized = realized + pnl
            self.db.update_trade(trade_id, 0.0, new_realized, "CLOSED", now, "STOP_LOSS", current_price)
            self.paper.close_trade_for_balance(trade_id, pnl)
            return "STOP_LOSS"

        if age_min >= self.config.max_hold_minutes:
            pnl = self._pnl_for_pct(size, remaining, pnl_pct)
            self.db.add_trade_event(trade_id, "TIME_EXIT", now, current_price, remaining, pnl, "full exit")
            new_realized = realized + pnl
            self.db.update_trade(trade_id, 0.0, new_realized, "CLOSED", now, "TIME_EXIT", current_price)
            self.paper.close_trade_for_balance(trade_id, pnl)
            return "TIME_EXIT"

        # TP2 first in case price jumps past both thresholds.
        if pnl_pct >= self.config.tp2_pct and remaining > (100 - self.config.tp1_sell_pct - self.config.tp2_sell_pct):
            qty = min(self.config.tp2_sell_pct, remaining)
            pnl = self._pnl_for_pct(size, qty, pnl_pct)
            new_remaining = remaining - qty
            self.db.add_trade_event(trade_id, "TP2", now, current_price, qty, pnl, "partial exit")
            status = "MOONBAG" if new_remaining > 0 else "CLOSED"
            self.db.update_trade(trade_id, new_remaining, realized + pnl, status, None if new_remaining > 0 else now, "TP2" if new_remaining == 0 else None, current_price)
            if status == "CLOSED":
                self.paper.close_trade_for_balance(trade_id, pnl)
            return "TP2"

        if pnl_pct >= self.config.tp1_pct and remaining > (100 - self.config.tp1_sell_pct):
            qty = min(self.config.tp1_sell_pct, remaining)
            pnl = self._pnl_for_pct(size, qty, pnl_pct)
            self.db.add_trade_event(trade_id, "TP1", now, current_price, qty, pnl, "partial exit")
            self.db.update_trade(trade_id, remaining - qty, realized + pnl, closed_at=None, exit_reason=None)
            return "TP1"

        return None

    @staticmethod
    def _pnl_for_pct(initial_size_usd: float, qty_pct: float, pnl_pct: float) -> float:
        return initial_size_usd * (qty_pct / 100.0) * (pnl_pct / 100.0)
