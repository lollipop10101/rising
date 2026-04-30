from __future__ import annotations

from rising.models import DecisionResult, RiskResult, SignalType, TradeDecision


class StrategyEngine:
    def __init__(self, allocation_pct: float, max_risk_score: int, min_position_size_usd: float = 3.0) -> None:
        self.allocation_pct = allocation_pct
        self.max_risk_score = max_risk_score
        self.min_position_size_usd = min_position_size_usd

    def _position_size(self, paper_balance: float) -> float:
        return paper_balance * self.allocation_pct

    def decide(self, signal_type: SignalType, risk: RiskResult, open_positions: int, max_open_positions: int, paper_balance: float) -> DecisionResult:
        reasons: list[str] = []

        if signal_type != SignalType.NEW_TOKEN:
            return DecisionResult(TradeDecision.TRACK_ONLY, [f"Not fresh: {signal_type.value}"], 0.0)

        if open_positions >= max_open_positions:
            return DecisionResult(TradeDecision.SKIP, ["Max open positions reached"], 0.0)

        if risk.blocked:
            return DecisionResult(TradeDecision.SKIP, ["Risk blocked", *risk.reasons], 0.0)

        if risk.score > self.max_risk_score:
            return DecisionResult(TradeDecision.SKIP, [f"Risk too high: {risk.score}", *risk.reasons], 0.0)

        position_size_usd = self._position_size(paper_balance)
        if position_size_usd < self.min_position_size_usd:
            return DecisionResult(TradeDecision.SKIP, [f"Allocation below minimum: ${position_size_usd:.2f}"], 0.0)

        reasons.append(f"Risk accepted: {risk.score}")
        reasons.append(f"Paper balance: ${paper_balance:.2f}")
        return DecisionResult(TradeDecision.BUY, reasons, position_size_usd)

    def decide_signal_only(self, risk: RiskResult, open_positions: int, max_open: int, paper_balance: float) -> DecisionResult:
        """Decision path for non-Telegram sources such as smart-wallet buys."""
        if open_positions >= max_open:
            return DecisionResult(TradeDecision.SKIP, ["Max open positions reached"], 0.0)
        if risk.blocked:
            return DecisionResult(TradeDecision.SKIP, ["Risk blocked", *risk.reasons], 0.0)
        if risk.score > self.max_risk_score:
            return DecisionResult(TradeDecision.SKIP, [f"Risk too high: {risk.score}", *risk.reasons], 0.0)

        position_size_usd = self._position_size(paper_balance)
        if position_size_usd < self.min_position_size_usd:
            return DecisionResult(TradeDecision.SKIP, [f"Allocation below minimum: ${position_size_usd:.2f}"], 0.0)

        return DecisionResult(TradeDecision.BUY, [f"Risk accepted: {risk.score}", f"Paper balance: ${paper_balance:.2f}"], position_size_usd)
