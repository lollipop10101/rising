from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import aiohttp
from rising.smart_wallets.models import WalletSwap
class HeliusEnhancedClient:
    BASE='https://api-mainnet.helius-rpc.com/v0/addresses/{wallet}/transactions'
    def __init__(self,api_key:str|None,timeout_seconds:int=12): self.api_key=api_key; self.timeout=aiohttp.ClientTimeout(total=timeout_seconds)
    @property
    def configured(self): return bool(self.api_key)
    async def fetch_swaps(self,wallet_address:str,limit:int=30,before_signature:str|None=None):
        if not self.api_key: raise RuntimeError('HELIUS_API_KEY is required for smart wallet mode')
        params={'api-key':self.api_key,'type':'SWAP','limit':min(max(limit,1),100)}
        if before_signature: params['before']=before_signature
        async with aiohttp.ClientSession(timeout=self.timeout) as s:
            async with s.get(self.BASE.format(wallet=wallet_address),params=params) as r:
                r.raise_for_status(); data=await r.json()
        return [] if not isinstance(data,list) else [sw for tx in data for sw in self._parse_swap_tx(wallet_address,tx)]
    def _parse_swap_tx(self,wallet,tx):
        sig=str(tx.get('signature') or ''); ts=datetime.fromtimestamp(int(tx.get('timestamp') or 0),tz=timezone.utc); src=tx.get('source'); swap=(tx.get('events') or {}).get('swap') or {}; out=[]
        for x in swap.get('tokenOutputs') or []:
            owner=x.get('userAccount') or x.get('toUserAccount')
            if owner and owner!=wallet: continue
            mint=x.get('mint')
            if mint: out.append(WalletSwap(wallet,mint,'BUY',sig,ts,_sf(x.get('tokenAmount')),_sf((swap.get('nativeInput') or {}).get('amountUsd') or x.get('amountUsd')),_sf(x.get('priceUsd')),src,src,tx))
        for x in swap.get('tokenInputs') or []:
            owner=x.get('userAccount') or x.get('fromUserAccount')
            if owner and owner!=wallet: continue
            mint=x.get('mint')
            if mint: out.append(WalletSwap(wallet,mint,'SELL',sig,ts,_sf(x.get('tokenAmount')),_sf((swap.get('nativeOutput') or {}).get('amountUsd') or x.get('amountUsd')),_sf(x.get('priceUsd')),src,src,tx))
        return out
def _sf(v:Any):
    try: return None if v is None else float(v)
    except (TypeError,ValueError): return None
