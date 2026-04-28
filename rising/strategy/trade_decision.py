from __future__ import annotations
from dataclasses import dataclass
from rising.intelligence.token_history_checker import SignalType
from rising.risk.risk_engine import RiskResult
from rising.data.price_fetcher import TokenMarket

@dataclass
class TradeDecision:
    action: str  # BUY_PAPER or SKIP
    reason: str

class StrategyEngine:
    def decide(self, signal_type: SignalType, market: TokenMarket | None, risk: RiskResult) -> TradeDecision:
        if signal_type != SignalType.NEW_TOKEN:
            return TradeDecision("SKIP", f"Not fresh: {signal_type.value}")
        if not risk.allowed:
            return TradeDecision("SKIP", f"Risk too high: {risk.score} ({'; '.join(risk.reasons)})")
        if market is None or market.price_usd is None:
            return TradeDecision("SKIP", "Missing price")
        return TradeDecision("BUY_PAPER", f"Fresh token and risk score {risk.score}")
