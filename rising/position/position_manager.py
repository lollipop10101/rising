from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from rising.storage.database import RisingDB
from rising.data.price_fetcher import DexScreenerClient

class PositionManager:
    def __init__(self, db: RisingDB, price_client: DexScreenerClient, cfg):
        self.db = db
        self.price_client = price_client
        self.cfg = cfg

    async def monitor_once(self) -> None:
        trades = await self.db.open_trades()
        for t in trades:
            market = await self.price_client.get_solana_token(t["token_address"])
            if not market or market.price_usd is None or not t["entry_price"]:
                continue
            pnl_pct = ((market.price_usd - t["entry_price"]) / t["entry_price"]) * 100
            pnl_usd = t["quote_usd"] * pnl_pct / 100
            entry_time = datetime.fromisoformat(t["entry_time"])
            age_min = (datetime.now(timezone.utc) - entry_time).total_seconds() / 60
            reason = None
            if pnl_pct <= self.cfg.stop_loss_pct:
                reason = f"Stop loss hit {pnl_pct:.2f}%"
            elif pnl_pct >= self.cfg.tp2_pct:
                reason = f"TP2 hit {pnl_pct:.2f}%"
            elif age_min >= self.cfg.max_hold_minutes:
                reason = f"Time exit after {age_min:.1f} min, pnl {pnl_pct:.2f}%"
            if reason:
                await self.db.close_trade(t["id"], market.price_usd, pnl_usd, pnl_pct, reason)

    async def run_forever(self) -> None:
        while True:
            await self.monitor_once()
            await asyncio.sleep(self.cfg.poll_seconds)
