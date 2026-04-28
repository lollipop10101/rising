from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from rising.models import MarketSnapshot


class DexScreenerClient:
    BASE = "https://api.dexscreener.com/latest/dex/tokens/{token}"

    def __init__(self, timeout_seconds: int = 8) -> None:
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def fetch_token(self, token_address: str) -> MarketSnapshot:
        url = self.BASE.format(token=token_address)
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                data = await resp.json()
        return self._parse(token_address, data)

    def _parse(self, token_address: str, data: dict[str, Any]) -> MarketSnapshot:
        pairs = [p for p in data.get("pairs") or [] if p.get("chainId") == "solana"]
        if not pairs:
            return MarketSnapshot(token_address, None, None, None, None, None, None, None, datetime.now(timezone.utc))

        def liquidity(pair: dict[str, Any]) -> float:
            return float((pair.get("liquidity") or {}).get("usd") or 0)

        pair = max(pairs, key=liquidity)
        return MarketSnapshot(
            token_address=token_address,
            dex_url=pair.get("url"),
            pair_address=pair.get("pairAddress"),
            base_symbol=(pair.get("baseToken") or {}).get("symbol"),
            price_usd=_safe_float(pair.get("priceUsd")),
            liquidity_usd=_safe_float((pair.get("liquidity") or {}).get("usd")),
            volume_5m_usd=_safe_float((pair.get("volume") or {}).get("m5")),
            price_change_5m_pct=_safe_float((pair.get("priceChange") or {}).get("m5")),
            fetched_at=datetime.now(timezone.utc),
        )


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
