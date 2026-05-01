from __future__ import annotations
from datetime import datetime
from rising.storage.database import Database
class PaperTrader:
    def __init__(self,db:Database,entry_slippage_pct:float=0.0): self.db=db; self.entry_slippage_pct=entry_slippage_pct
    def buy(self,token_address:str,market_price:float,size_usd:float,now:datetime)->int:
        if market_price<=0: raise ValueError('market_price must be > 0')
        return self.db.open_trade(token_address,market_price*(1+self.entry_slippage_pct/100),size_usd,now)
