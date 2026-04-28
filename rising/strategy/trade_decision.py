from __future__ import annotations

from rising.models import DecisionResult, RiskResult, SignalType, TradeDecision


class StrategyEngine:
    def __init__(self, paper_trade_usd: float, max_risk_score: int) -> None:
        self.paper_trade_usd = paper_trade_usd
        self.max_risk_score = max_risk_score

    def decide(self, signal_type: SignalType, risk: RiskResult, open_positions: int, max_open_positions: int) -> DecisionResult:
        reasons: list[str] = []

        if signal_type != SignalType.NEW_TOKEN:
            return DecisionResult(TradeDecision.TRACK_ONLY, [f"Not fresh: {signal_type.value}"], 0.0)

        if open_positions >= max_open_positions:
            return DecisionResult(TradeDecision.SKIP, ["Max open positions reached"], 0.0)

        if risk.blocked:
            return DecisionResult(TradeDecision.SKIP, ["Risk blocked", *risk.reasons], 0.0)

        if risk.score > self.max_risk_score:
            return DecisionResult(TradeDecision.SKIP, [f"Risk too high: {risk.score}", *risk.reasons], 0.0)

        reasons.append(f"Risk accepted: {risk.score}")
        return DecisionResult(TradeDecision.BUY, reasons, self.paper_trade_usd)

    def decide_signal_only(self, risk: RiskResult, open_positions: int, max_open: int) -> DecisionResult:
        """Decision path for non-Telegram sources such as smart-wallet buys."""
        if open_positions >= max_open:
            return DecisionResult(TradeDecision.SKIP, ["Max open positions reached"], 0.0)
        if risk.blocked:
            return DecisionResult(TradeDecision.SKIP, ["Risk blocked", *risk.reasons], 0.0)
        if risk.score > self.max_risk_score:
            return DecisionResult(TradeDecision.SKIP, [f"Risk too high: {risk.score}", *risk.reasons], 0.0)
        return DecisionResult(TradeDecision.BUY, [f"Risk accepted: {risk.score}"], self.paper_trade_usd)
