from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Any, Dict
import httpx

@dataclass
class TokenMarket:
    address: str
    price_usd: Optional[float]
    liquidity_usd: Optional[float]
    volume_5m: Optional[float]
    volume_1h: Optional[float]
    price_change_5m: Optional[float]
    pair_address: Optional[str]
    dex_id: Optional[str]
    url: Optional[str]
    symbol: Optional[str] = None
    token_name: Optional[str] = None

class DexScreenerClient:
    BASE = "https://api.dexscreener.com/latest/dex/tokens"

    async def get_solana_token(self, token_address: str) -> Optional[TokenMarket]:
        url = f"{self.BASE}/{token_address}"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "solana"]
        if not pairs:
            return None
        # choose highest-liquidity pair
        pair: Dict[str, Any] = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
        base = pair.get("baseToken", {}) or {}
        volume = pair.get("volume") or {}
        pc = pair.get("priceChange") or {}
        return TokenMarket(
            address=token_address,
            price_usd=_float(pair.get("priceUsd")),
            liquidity_usd=_float((pair.get("liquidity") or {}).get("usd")),
            volume_5m=_float(volume.get("m5")),
            volume_1h=_float(volume.get("h1")),
            price_change_5m=_float(pc.get("m5")),
            pair_address=pair.get("pairAddress"),
            dex_id=pair.get("dexId"),
            url=pair.get("url"),
            symbol=base.get("symbol"),
            token_name=base.get("name"),
        )

def _float(x: Any) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None
