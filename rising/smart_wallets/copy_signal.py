from __future__ import annotations
from rising.models import TradeDecision,utc_now
from rising.smart_wallets.models import CopyDecision,CopySignalResult
class CopySignalEngine:
    def __init__(self,db,price_client,risk_engine,strategy,paper,min_wallet_score=70,min_copyability_score=60,alert_only_for_single_wallet=True): self.db=db; self.price=price_client; self.risk=risk_engine; self.strategy=strategy; self.paper=paper; self.min_wallet_score=min_wallet_score; self.min_copyability_score=min_copyability_score; self.alert_only_for_single_wallet=alert_only_for_single_wallet
    async def process_buy(self,swap,score):
        if swap.side!='BUY': return CopySignalResult(CopyDecision.SKIP,['not a buy swap'],score)
        if score.score<self.min_wallet_score: return CopySignalResult(CopyDecision.SKIP,[f'wallet score too low: {score.score}'],score)
        if score.copyability_score<self.min_copyability_score: return CopySignalResult(CopyDecision.SKIP,[f'copyability too low: {score.copyability_score}'],score)
        snap=await self.price.fetch_token(swap.token_address); risk=self.risk.score(snap); dec=self.strategy.decide_signal_only(risk,len(self.db.get_open_trades()),3)
        if dec.decision!=TradeDecision.BUY or not snap.price_usd or self.alert_only_for_single_wallet:
            self.db.add_copy_signal(swap,score,risk.score,CopyDecision.ALERT_ONLY.value,'single wallet confirmation'); return CopySignalResult(CopyDecision.ALERT_ONLY,dec.reasons if dec.decision!=TradeDecision.BUY else ['single smart wallet buy; alert only'],score)
        tid=self.paper.buy(swap.token_address,snap.price_usd,dec.position_size_usd,utc_now()); self.db.add_copy_signal(swap,score,risk.score,CopyDecision.PAPER_BUY.value,'paper copied smart wallet',tid); return CopySignalResult(CopyDecision.PAPER_BUY,['paper copied smart wallet'],score,tid)
