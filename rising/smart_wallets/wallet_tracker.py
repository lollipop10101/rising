from __future__ import annotations

import asyncio
from datetime import datetime

from loguru import logger

from rising.monitoring.notifier import TelegramNotifier
from rising.smart_wallets.copy_signal import CopySignalEngine
from rising.smart_wallets.helius_client import HeliusEnhancedClient
from rising.smart_wallets.models import CopyDecision, WalletSwap
from rising.smart_wallets.wallet_analyzer import WalletAnalyzer
from rising.storage.database import Database


class SmartWalletTracker:
    def __init__(
        self,
        db: Database,
        helius: HeliusEnhancedClient,
        analyzer: WalletAnalyzer,
        copy_engine: CopySignalEngine,
        notifier: TelegramNotifier,
        poll_seconds: int = 20,
    ) -> None:
        self.db = db
        self.helius = helius
        self.analyzer = analyzer
        self.copy_engine = copy_engine
        self.notifier = notifier
        self.poll_seconds = poll_seconds

    async def scan_once(self) -> None:
        wallets = self.db.list_active_smart_wallets()
        if not wallets:
            logger.warning("No active smart wallets configured. Add wallets with: python -m rising.main add-wallet WALLET --label name")
            return

        for wallet in wallets:
            address = wallet["wallet_address"]
            await self.scan_wallet_once(address)

    async def scan_wallet_once(self, wallet_address: str) -> None:
        swaps = await self.helius.fetch_swaps(wallet_address, limit=10)
        if not swaps:
            return
        score = await self.analyzer.analyze_wallet(wallet_address, swaps=swaps)

        # Process newest first, but only unseen signatures.
        for swap in sorted(swaps, key=lambda s: s.timestamp):
            if self.db.wallet_trade_exists(swap.signature, swap.wallet_address, swap.token_address, swap.side):
                continue
            self.db.upsert_wallet_trade(swap)
            if swap.side != "BUY":
                continue
            result = await self.copy_engine.process_buy(swap, score)
            await self._notify(swap, result.decision.value, result.reasons, score.score, score.copyability_score)

    async def run_forever(self) -> None:
        while True:
            await self.scan_once()
            await asyncio.sleep(self.poll_seconds)

    async def _notify(self, swap: WalletSwap, decision: str, reasons: list[str], score: int, copyability: int) -> None:
        msg = (
            f"🐋 Rising smart-wallet signal\n"
            f"Wallet: {swap.wallet_address}\n"
            f"Token: {swap.token_address}\n"
            f"Decision: {decision}\n"
            f"Wallet score: {score} | Copyability: {copyability}\n"
            f"Reason: {', '.join(reasons[:3])}\n"
            f"Tx: {swap.signature}"
        )
        await self.notifier.send(msg)
