from __future__ import annotations
from datetime import datetime
from rising.storage.database import Database
class PaperTrader:
    def __init__(self,db:Database,entry_slippage_pct:float=0.0,max_exposure_per_trade_pct:float=0.10,max_total_exposure_pct:float=0.30,min_trade_size_usd:float=1.0):
        self.db=db; self.entry_slippage_pct=entry_slippage_pct
        self.max_exposure_per_trade_pct=max_exposure_per_trade_pct
        self.max_total_exposure_pct=max_total_exposure_pct
        self.min_trade_size_usd=min_trade_size_usd

    def buy(self,token_address:str,market_price:float,size_usd:float,now:datetime=None)->int:
        if market_price<=0: raise ValueError('market_price must be > 0')
        if now is None: now=datetime.utcnow()
        balance=self.db.get_balance()
        open_trades=self.db.get_open_trades()
        open_count=len(open_trades)
        max_per_trade=balance*self.max_exposure_per_trade_pct
        max_total=balance*self.max_total_exposure_pct
        used_by_opens=sum(t['initial_size_usd'] for t in open_trades)
        available=max_total-used_by_opens
        slots_left=max(1,self.max_total_exposure_pct and int(max_total/(balance*self.max_exposure_per_trade_pct)) or open_count)
        actual_size=min(size_usd,max_per_trade,max(available/slots_left if slots_left>0 else available,1.0))
        actual_size=max(actual_size,self.min_trade_size_usd)
        return self.db.open_trade(token_address,market_price*(1+self.entry_slippage_pct/100),actual_size,now)
