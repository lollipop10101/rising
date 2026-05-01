from __future__ import annotations
import asyncio

class SmartWalletTracker:
    def __init__(self, db, helius, analyzer, copy_engine, notifier, poll_seconds=20):
        self.db=db; self.helius=helius; self.analyzer=analyzer; self.copy_engine=copy_engine; self.notifier=notifier; self.poll_seconds=poll_seconds
    async def scan_once(self):
        for w in self.db.list_active_smart_wallets():
            await self.scan_wallet_once(w['wallet_address'])
    async def scan_wallet_once(self, wallet):
        swaps=await self.helius.fetch_swaps(wallet, limit=10)
        if not swaps:
            return
        score=await self.analyzer.analyze_wallet(wallet, limit=50)
        for s in sorted(swaps, key=lambda x: x.timestamp):
            if self.db.wallet_trade_exists(s.signature, s.wallet_address, s.token_address, s.side):
                continue
            self.db.upsert_wallet_trade(s)
            if s.side == 'BUY':
                res=await self.copy_engine.process_buy(s, score)
                await self.notifier.send(f'🐋 Rising smart-wallet signal\nWallet: {s.wallet_address}\nToken: {s.token_address}\nDecision: {res.decision.value}')
    async def run_forever(self):
        while True:
            await self.scan_once()
            await asyncio.sleep(self.poll_seconds)
