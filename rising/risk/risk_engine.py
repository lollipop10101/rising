from __future__ import annotations
from dataclasses import dataclass
from typing import List
from rising.data.price_fetcher import TokenMarket

@dataclass
class RiskResult:
    score: int
    reasons: List[str]
    allowed: bool

class RiskEngine:
    def __init__(self, min_liquidity_usd: float, max_risk_score: int):
        self.min_liquidity_usd = min_liquidity_usd
        self.max_risk_score = max_risk_score

    def evaluate(self, market: TokenMarket | None) -> RiskResult:
        score = 0
        reasons: List[str] = []
        if market is None:
            return RiskResult(100, ["No Solana pair found on DexScreener"], False)
        if market.price_usd is None:
            score += 30; reasons.append("No USD price")
        liq = market.liquidity_usd or 0
        if liq < self.min_liquidity_usd:
            score += 45; reasons.append(f"Low liquidity ${liq:,.0f}")
        if (market.volume_5m or 0) <= 0:
            score += 15; reasons.append("No 5m volume")
        if (market.price_change_5m or 0) > 200:
            score += 20; reasons.append("Already pumped >200% in 5m")
        allowed = score <= self.max_risk_score
        return RiskResult(score=min(score, 100), reasons=reasons or ["Basic market checks passed"], allowed=allowed)
