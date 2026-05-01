from __future__ import annotations
from rising.smart_wallets.score import WalletScorer
from rising.smart_wallets.insider_filter import InsiderFilter
class WalletAnalyzer:
    def __init__(self,db,helius): self.db=db; self.helius=helius; self.scorer=WalletScorer(); self.insider=InsiderFilter()
    async def analyze_wallet(self,wallet_address,limit=50):
        swaps=await self.helius.fetch_swaps(wallet_address,limit=limit)
        for s in swaps: self.db.upsert_wallet_trade(s)
        score=self.scorer.score(wallet_address,swaps); pen,rea=self.insider.evaluate(swaps)
        if pen: score.insider_score=min(100,score.insider_score+pen); score.score=max(0,score.score-pen); score.copyability_score=max(0,score.copyability_score-pen); score.reasons.extend(rea)
        self.db.upsert_smart_wallet(score); return score
