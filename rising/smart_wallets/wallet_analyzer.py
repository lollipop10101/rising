from __future__ import annotations

from loguru import logger

from rising.smart_wallets.helius_client import HeliusEnhancedClient
from rising.smart_wallets.insider_filter import InsiderFilter
from rising.smart_wallets.models import WalletScore, WalletSwap
from rising.smart_wallets.score import WalletScorer
from rising.storage.database import Database


class WalletAnalyzer:
    def __init__(self, db: Database, helius: HeliusEnhancedClient) -> None:
        self.db = db
        self.helius = helius
        self.scorer = WalletScorer()
        self.insider = InsiderFilter()

    async def analyze_wallet(self, wallet_address: str, limit: int = 50) -> WalletScore:
        swaps = await self.helius.fetch_swaps(wallet_address, limit=limit)
        for swap in swaps:
            self.db.upsert_wallet_trade(swap)

        score = self.scorer.score(wallet_address, swaps)
        penalty, reasons = self.insider.evaluate(swaps)
        if penalty:
            score.insider_score = min(100, score.insider_score + penalty)
            score.score = max(0, score.score - penalty)
            score.copyability_score = max(0, score.copyability_score - penalty)
            score.reasons.extend(reasons)

        self.db.upsert_smart_wallet(score)
        logger.info("wallet={} score={} copyability={} tier={}", wallet_address, score.score, score.copyability_score, score.tier.value)
        return score
