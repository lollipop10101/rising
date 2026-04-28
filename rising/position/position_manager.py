from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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
    def __init__(self, db: Database, config: ExitConfig) -> None:
        self.db = db
        self.config = config

    def evaluate_trade(self, trade, current_price: float, now: datetime) -> str | None:
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
            self.db.update_trade(trade_id, 0.0, realized + pnl, "CLOSED", now, "STOP_LOSS", current_price)
            return "STOP_LOSS"

        if age_min >= self.config.max_hold_minutes:
            pnl = self._pnl_for_pct(size, remaining, pnl_pct)
            self.db.add_trade_event(trade_id, "TIME_EXIT", now, current_price, remaining, pnl, "full exit")
            self.db.update_trade(trade_id, 0.0, realized + pnl, "CLOSED", now, "TIME_EXIT", current_price)
            return "TIME_EXIT"

        # TP2 first in case price jumps past both thresholds.
        if pnl_pct >= self.config.tp2_pct and remaining > (100 - self.config.tp1_sell_pct - self.config.tp2_sell_pct):
            qty = min(self.config.tp2_sell_pct, remaining)
            pnl = self._pnl_for_pct(size, qty, pnl_pct)
            new_remaining = remaining - qty
            self.db.add_trade_event(trade_id, "TP2", now, current_price, qty, pnl, "partial exit")
            status = "MOONBAG" if new_remaining > 0 else "CLOSED"
            self.db.update_trade(trade_id, new_remaining, realized + pnl, status, None if new_remaining > 0 else now, "TP2" if new_remaining == 0 else None, current_price)
            return "TP2"

        if pnl_pct >= self.config.tp1_pct and remaining > (100 - self.config.tp1_sell_pct):
            qty = min(self.config.tp1_sell_pct, remaining)
            pnl = self._pnl_for_pct(size, qty, pnl_pct)
            self.db.add_trade_event(trade_id, "TP1", now, current_price, qty, pnl, "partial exit")
            self.db.update_trade(trade_id, remaining - qty, realized + pnl)
            return "TP1"

        return None

    @staticmethod
    def _pnl_for_pct(initial_size_usd: float, qty_pct: float, pnl_pct: float) -> float:
        return initial_size_usd * (qty_pct / 100.0) * (pnl_pct / 100.0)
