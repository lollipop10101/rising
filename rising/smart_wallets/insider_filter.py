from __future__ import annotations
class InsiderFilter:
    def evaluate(self,swaps):
        buys=[s for s in swaps if s.side=='BUY']; sells=[s for s in swaps if s.side=='SELL']; p=0; r=[]
        if sells and not buys: p+=60; r.append('wallet mostly sells without observed public buys')
        if len([s for s in buys if not s.amount_usd or s.amount_usd<=0])>=3: p+=25; r.append('many buys have missing/zero cost; possible transfers/private allocation')
        if len({s.token_address for s in swaps})<=1 and len(swaps)>5: p+=20; r.append('activity concentrated in one token')
        return min(100,p),r
