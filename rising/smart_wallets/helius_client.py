from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from rising.smart_wallets.models import WalletSwap


class HeliusEnhancedClient:
    """Small wrapper around Helius Enhanced Transactions API.

    Docs: https://www.helius.dev/docs/enhanced-transactions/transaction-history
    Endpoint used:
      https://api-mainnet.helius-rpc.com/v0/addresses/{wallet}/transactions?api-key=...&type=SWAP
    """

    BASE = "https://api-mainnet.helius-rpc.com/v0/addresses/{wallet}/transactions"

    def __init__(self, api_key: str | None, timeout_seconds: int = 12) -> None:
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def fetch_swaps(self, wallet_address: str, limit: int = 30, before_signature: str | None = None) -> list[WalletSwap]:
        if not self.api_key:
            raise RuntimeError("HELIUS_API_KEY is required for smart wallet mode")

        params: dict[str, Any] = {"api-key": self.api_key, "type": "SWAP", "limit": min(max(limit, 1), 100)}
        if before_signature:
            params["before"] = before_signature

        url = self.BASE.format(wallet=wallet_address)
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(url, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()

        if not isinstance(data, list):
            return []
        return [s for tx in data for s in self._parse_swap_tx(wallet_address, tx)]

    def _parse_swap_tx(self, wallet_address: str, tx: dict[str, Any]) -> list[WalletSwap]:
        signature = str(tx.get("signature") or "")
        timestamp = datetime.fromtimestamp(int(tx.get("timestamp") or 0), tz=timezone.utc)
        source = tx.get("source")
        events = tx.get("events") or {}
        swap = events.get("swap") or {}

        token_inputs = swap.get("tokenInputs") or []
        token_outputs = swap.get("tokenOutputs") or []
        native_input = swap.get("nativeInput") or {}
        native_output = swap.get("nativeOutput") or {}

        parsed: list[WalletSwap] = []

        # Heuristic: if wallet spends SOL/USDC and receives a token, this is a BUY.
        for out in token_outputs:
            token_account_owner = out.get("userAccount") or out.get("toUserAccount")
            if token_account_owner and token_account_owner != wallet_address:
                continue
            mint = out.get("mint")
            if not mint:
                continue
            parsed.append(
                WalletSwap(
                    wallet_address=wallet_address,
                    token_address=mint,
                    side="BUY",
                    signature=signature,
                    timestamp=timestamp,
                    token_amount=_safe_float(out.get("tokenAmount")),
                    amount_usd=_safe_float(native_input.get("amountUsd") or out.get("amountUsd")),
                    price_usd=_safe_float(out.get("priceUsd")),
                    dex=source,
                    source=source,
                    raw=tx,
                )
            )

        # Heuristic: if wallet sends a token out and receives SOL/USDC, this is a SELL.
        for inp in token_inputs:
            token_account_owner = inp.get("userAccount") or inp.get("fromUserAccount")
            if token_account_owner and token_account_owner != wallet_address:
                continue
            mint = inp.get("mint")
            if not mint:
                continue
            parsed.append(
                WalletSwap(
                    wallet_address=wallet_address,
                    token_address=mint,
                    side="SELL",
                    signature=signature,
                    timestamp=timestamp,
                    token_amount=_safe_float(inp.get("tokenAmount")),
                    amount_usd=_safe_float(native_output.get("amountUsd") or inp.get("amountUsd")),
                    price_usd=_safe_float(inp.get("priceUsd")),
                    dex=source,
                    source=source,
                    raw=tx,
                )
            )
        return parsed


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
