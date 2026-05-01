from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import aiohttp
from rising.models import MarketSnapshot
class DexScreenerClient:
    BASE='https://api.dexscreener.com/latest/dex/tokens/{token}'
    def __init__(self, timeout_seconds:int=8): self.timeout=aiohttp.ClientTimeout(total=timeout_seconds)
    async def fetch_token(self, token_address:str)->MarketSnapshot:
        async with aiohttp.ClientSession(timeout=self.timeout) as s:
            async with s.get(self.BASE.format(token=token_address)) as r:
                r.raise_for_status(); data=await r.json()
        return self._parse(token_address,data)
    def _parse(self, token_address:str, data:dict[str,Any])->MarketSnapshot:
        pairs=[p for p in data.get('pairs') or [] if p.get('chainId')=='solana']
        if not pairs: return MarketSnapshot(token_address,None,None,None,None,None,None,None,datetime.now(timezone.utc))
        pair=max(pairs, key=lambda p: float((p.get('liquidity') or {}).get('usd') or 0))
        return MarketSnapshot(token_address,pair.get('url'),pair.get('pairAddress'),(pair.get('baseToken') or {}).get('symbol'),_sf(pair.get('priceUsd')),_sf((pair.get('liquidity') or {}).get('usd')),_sf((pair.get('volume') or {}).get('m5')),_sf((pair.get('priceChange') or {}).get('m5')),datetime.now(timezone.utc))
def _sf(v:Any)->float|None:
    try: return None if v is None else float(v)
    except (TypeError,ValueError): return None
