from __future__ import annotations

from rising.data.price_fetcher import DexScreenerClient
from rising.execution.paper_trader import PaperTrader
from rising.models import TradeDecision, utc_now
from rising.risk.risk_engine import RiskEngine
from rising.smart_wallets.models import CopyDecision, CopySignalResult, WalletScore, WalletSwap
from rising.storage.database import Database
from rising.strategy.trade_decision import StrategyEngine


class CopySignalEngine:
    def __init__(
        self,
        db: Database,
        price_client: DexScreenerClient,
        risk_engine: RiskEngine,
        strategy: StrategyEngine,
        paper: PaperTrader,
        min_wallet_score: int = 70,
        min_copyability_score: int = 60,
        alert_only_for_single_wallet: bool = True,
    ) -> None:
        self.db = db
        self.price = price_client
        self.risk = risk_engine
        self.strategy = strategy
        self.paper = paper
        self.min_wallet_score = min_wallet_score
        self.min_copyability_score = min_copyability_score
        self.alert_only_for_single_wallet = alert_only_for_single_wallet

    async def process_buy(self, swap: WalletSwap, score: WalletScore) -> CopySignalResult:
        reasons: list[str] = []
        if swap.side != "BUY":
            return CopySignalResult(CopyDecision.SKIP, ["not a buy swap"], score)
        if score.score < self.min_wallet_score:
            return CopySignalResult(CopyDecision.SKIP, [f"wallet score too low: {score.score}"], score)
        if score.copyability_score < self.min_copyability_score:
            return CopySignalResult(CopyDecision.SKIP, [f"copyability too low: {score.copyability_score}"], score)

        snapshot = await self.price.fetch_token(swap.token_address)
        risk = self.risk.score(snapshot)
        if risk.blocked:
            return CopySignalResult(CopyDecision.SKIP, ["token risk blocked", *risk.reasons[:3]], score)

        open_positions = len(self.db.get_open_trades())
        decision = self.strategy.decide_signal_only(risk=risk, open_positions=open_positions, max_open=3)
        if decision.decision != TradeDecision.BUY or not snapshot.price_usd:
            return CopySignalResult(CopyDecision.ALERT_ONLY, decision.reasons, score)

        # v0.3 conservative default: first new buy from one wallet alerts only.
        if self.alert_only_for_single_wallet:
            self.db.add_copy_signal(swap, score, risk.score, CopyDecision.ALERT_ONLY.value, "single wallet confirmation")
            return CopySignalResult(CopyDecision.ALERT_ONLY, ["single smart wallet buy; alert only"], score)

        trade_id = self.paper.buy(swap.token_address, snapshot.price_usd, decision.position_size_usd, utc_now())
        self.db.add_copy_signal(swap, score, risk.score, CopyDecision.PAPER_BUY.value, "paper copied smart wallet", trade_id)
        return CopySignalResult(CopyDecision.PAPER_BUY, reasons or ["paper copied smart wallet"], score, trade_id)
