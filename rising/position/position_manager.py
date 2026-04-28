from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from rising.storage.database import RisingDB
from rising.data.price_fetcher import DexScreenerClient
from rising.models import TradeDecision


class PositionManager:
    def __init__(self, db: RisingDB, price_client: DexScreenerClient, cfg) -> None:
        self.db = db
        self.price_client = price_client
        self.cfg = cfg

    async def monitor_once(self) -> None:
        trades = self.db.open_trades()
        for t in trades:
            market = await self.price_client.fetch_token(t["token_address"])
            if not market or market.price_usd is None or not t["entry_price"]:
                continue

            entry_price = t["entry_price"]
            quote_usd = t["quote_usd"]

            # Realistic exit: apply 1% fee
            _, pnl_pct, pnl_usd = self._calc_exit(market.price_usd, quote_usd, entry_price)

            entry_time = datetime.fromisoformat(t["entry_time"])
            age_min = (datetime.now(timezone.utc) - entry_time).total_seconds() / 60
            reason = None

            if pnl_pct <= self.cfg.stop_loss_pct:
                reason = f"Stop loss {pnl_pct:.1f}%"
            elif pnl_pct >= self.cfg.tp2_pct:
                reason = f"TP2 {pnl_pct:.1f}%"
            elif age_min >= self.cfg.max_hold_minutes:
                reason = f"Time out {age_min:.0f}min, pnl {pnl_pct:.1f}%"

            if reason:
                exit_price = market.price_usd * (1 - 1.0 / 100)
                self.db.close_trade(
                    t["id"], exit_price, pnl_usd, pnl_pct, reason,
                    market_price_at_exit=market.price_usd,
                    slippage_pct_exit=1.0,
                )

    def _calc_exit(self, market_price: float, quote_usd: float, entry_price: float):
        exit_price = market_price * (1 - 1.0 / 100)  # 1% fee
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        pnl_usd = quote_usd * pnl_pct / 100
        return exit_price, pnl_pct, pnl_usd

    async def run_forever(self) -> None:
        while True:
            await self.monitor_once()
            await asyncio.sleep(self.cfg.poll_seconds)
