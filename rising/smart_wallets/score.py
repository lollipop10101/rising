from __future__ import annotations
from collections import defaultdict
from rising.smart_wallets.models import WalletScore,WalletTier,WalletSwap
def clamp(v,l,h): return max(l,min(h,v))
class WalletScorer:
    def score(self,wallet_address:str,swaps:list[WalletSwap])->WalletScore:
        by=defaultdict(list)
        for s in swaps: by[s.token_address].append(s)
        pnl=0; wins=0; comp=0; buys=0; sells=0; fast=0; reasons=[]
        for ev in by.values():
            b=[e for e in ev if e.side=='BUY']; se=[e for e in ev if e.side=='SELL']; buys+=len(b); sells+=len(se)
            if b and se:
                p=sum(e.amount_usd or 0 for e in se)-sum(e.amount_usd or 0 for e in b); pnl+=p; comp+=1; wins+=1 if p>0 else 0
                if 0 <= (max(x.timestamp for x in se)-min(x.timestamp for x in b)).total_seconds() < 30: fast+=1
        tiny=20 if buys<5 else 0
        if tiny: reasons.append('too few observed buys')
        wr=wins/comp if comp else 0; insider=0; copy=60
        if buys and sells==0: insider+=15; reasons.append('only buys observed; exits unknown')
        if fast>=3: insider+=30; copy-=25; reasons.append('many sub-30s flips; difficult to copy')
        score=clamp(35+clamp(int(pnl/50),-20,35)+int(wr*25)+clamp(comp*3,0,20)-insider-tiny,0,100); copy=clamp(copy+clamp(comp*3,0,20)-insider-tiny,0,100)
        tier=WalletTier.C if insider>=45 else WalletTier.A if score>=75 and copy>=65 else WalletTier.B if score>=55 else WalletTier.D
        if pnl>0: reasons.append(f'observed realized pnl ${pnl:.2f}')
        if comp: reasons.append(f'win rate {wr:.0%} across {comp} completed tokens')
        return WalletScore(wallet_address,score,copy,insider,wr,pnl,len(swaps),tier,reasons)
