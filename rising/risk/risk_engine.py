from __future__ import annotations
from rising.models import MarketSnapshot,RiskResult
class RiskEngine:
    def __init__(self,min_liquidity_usd:float,min_volume_5m_usd:float,max_pump_5m_pct:float): self.min_liquidity_usd=min_liquidity_usd; self.min_volume_5m_usd=min_volume_5m_usd; self.max_pump_5m_pct=max_pump_5m_pct
    def score(self,s:MarketSnapshot|None)->RiskResult:
        if s is None or s.pair_address is None: return RiskResult(100,True,['No Solana pair found on DexScreener'])
        score=0; reasons=[]
        if s.price_usd is None or s.price_usd<=0: score+=30; reasons.append('No valid USD price')
        if s.liquidity_usd is None or s.liquidity_usd<self.min_liquidity_usd: score+=45; reasons.append(f'Low liquidity: {s.liquidity_usd}')
        if s.volume_5m_usd is None or s.volume_5m_usd<self.min_volume_5m_usd: score+=15; reasons.append(f'Low 5m volume: {s.volume_5m_usd}')
        if s.price_change_5m_pct is not None and s.price_change_5m_pct>self.max_pump_5m_pct: score+=20; reasons.append(f'Already pumped {s.price_change_5m_pct:.1f}% in 5m')
        return RiskResult(min(score,100),False,reasons or ['Risk checks passed'])
