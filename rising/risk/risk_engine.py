from __future__ import annotations
from rising.models import MarketSnapshot, RiskResult


class RiskEngine:
    def __init__(
        self,
        min_liquidity_usd: float,
        min_volume_5m_usd: float,
        max_pump_5m_pct: float,
    ) -> None:
        self.min_liquidity_usd = min_liquidity_usd
        self.min_volume_5m_usd = min_volume_5m_usd
        self.max_pump_5m_pct = max_pump_5m_pct

    def score(self, snapshot: MarketSnapshot) -> RiskResult:
        score = 0
        reasons: list[str] = []
        blocked = False

        if snapshot.pair_address is None:
            return RiskResult(
                score=100, blocked=True,
                reasons=["No Solana pair found on DexScreener"]
            )

        if snapshot.price_usd is None or snapshot.price_usd <= 0:
            score += 30
            reasons.append("No valid USD price")

        if snapshot.liquidity_usd is None or snapshot.liquidity_usd < self.min_liquidity_usd:
            score += 45
            reasons.append(f"Low liquidity: ${snapshot.liquidity_usd or 0:,.0f}")

        if snapshot.volume_5m_usd is None or snapshot.volume_5m_usd < self.min_volume_5m_usd:
            score += 15
            reasons.append(f"Low 5m volume: ${snapshot.volume_5m_usd or 0:,.0f}")

        if snapshot.price_change_5m_pct is not None and snapshot.price_change_5m_pct > self.max_pump_5m_pct:
            score += 20
            reasons.append(f"Already pumped {snapshot.price_change_5m_pct:.1f}% in 5m")

        return RiskResult(
            score=min(score, 100),
            blocked=blocked,
            reasons=reasons or ["Risk checks passed"],
        )
