from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qer6JFhX7gL7p3ch1XdhC3zoh"

Side = Literal["BUY", "SELL"]


@dataclass(slots=True)
class LiveTradeConfig:
    enabled: bool = False
    rpc_url: str = "https://api.mainnet-beta.solana.com"
    quote_mint: str = SOL_MINT
    slippage_bps: int = 800
    max_trade_usd: float = 30.0       # 10% of ~$300 paper balance
    max_daily_loss_usd: float = 50.0  # matches paper trading max_daily_loss_usd
    max_open_positions: int = 3         # matches paper trading max_open_positions
    dry_run: bool = True
    jupiter_quote_url: str = "https://lite-api.jup.ag/swap/v1/quote"
    jupiter_swap_url: str = "https://lite-api.jup.ag/swap/v1/swap"


@dataclass(slots=True)
class LiveSwapResult:
    ok: bool
    side: Side
    token_address: str
    signature: str | None
    input_mint: str
    output_mint: str
    in_amount_raw: int
    out_amount_raw: int | None
    simulated: bool
    reason: str
    created_at: datetime


class JupiterLiveExecutor:
    """Jupiter-backed Solana swap executor.

    Safety defaults:
    - dry_run=True by default
    - enabled=False by default
    - caller must enforce strategy/risk checks before calling buy/sell
    """

    def __init__(self, keypair: Keypair, cfg: LiveTradeConfig) -> None:
        self.keypair = keypair
        self.cfg = cfg

    @property
    def wallet_address(self) -> str:
        return str(self.keypair.pubkey())

    async def buy_token_with_sol(self, token_address: str, lamports: int) -> LiveSwapResult:
        return await self._swap(
            side="BUY",
            input_mint=SOL_MINT,
            output_mint=token_address,
            amount_raw=lamports,
        )

    async def sell_token_to_sol(self, token_address: str, token_amount_raw: int) -> LiveSwapResult:
        return await self._swap(
            side="SELL",
            input_mint=token_address,
            output_mint=SOL_MINT,
            amount_raw=token_amount_raw,
        )

    async def _swap(self, side: Side, input_mint: str, output_mint: str, amount_raw: int) -> LiveSwapResult:
        now = datetime.now(timezone.utc)
        token_address = output_mint if side == "BUY" else input_mint

        if not self.cfg.enabled:
            return LiveSwapResult(False, side, token_address, None, input_mint, output_mint, amount_raw, None, True, "REAL_TRADING_ENABLED=false", now)
        if self.cfg.dry_run:
            return LiveSwapResult(True, side, token_address, None, input_mint, output_mint, amount_raw, None, True, "dry-run: no transaction sent", now)
        if amount_raw <= 0:
            return LiveSwapResult(False, side, token_address, None, input_mint, output_mint, amount_raw, None, False, "amount_raw must be > 0", now)

        async with httpx.AsyncClient(timeout=20) as client:
            quote = await self._get_quote(client, input_mint, output_mint, amount_raw)
            swap_tx_b64 = await self._get_swap_transaction(client, quote)

        signed_tx = self._sign_jupiter_transaction(swap_tx_b64)
        raw_tx = bytes(signed_tx)

        async with AsyncClient(self.cfg.rpc_url) as rpc:
            resp = await rpc.send_raw_transaction(raw_tx)

        sig = str(resp.value) if getattr(resp, "value", None) else None
        out_raw = _safe_int(quote.get("outAmount"))
        return LiveSwapResult(True, side, token_address, sig, input_mint, output_mint, amount_raw, out_raw, False, "sent", now)

    async def _get_quote(self, client: httpx.AsyncClient, input_mint: str, output_mint: str, amount_raw: int) -> dict[str, Any]:
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount_raw),
            "slippageBps": str(self.cfg.slippage_bps),
        }
        r = await client.get(self.cfg.jupiter_quote_url, params=params)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(f"Jupiter quote error: {data['error']}")
        return data

    async def _get_swap_transaction(self, client: httpx.AsyncClient, quote: dict[str, Any]) -> str:
        body = {
            "quoteResponse": quote,
            "userPublicKey": self.wallet_address,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
        }
        r = await client.post(self.cfg.jupiter_swap_url, json=body)
        r.raise_for_status()
        data = r.json()
        tx = data.get("swapTransaction")
        if not tx:
            raise RuntimeError(f"Jupiter swap response missing swapTransaction: {data}")
        return tx

    def _sign_jupiter_transaction(self, swap_tx_b64: str) -> VersionedTransaction:
        raw = base64.b64decode(swap_tx_b64)
        unsigned = VersionedTransaction.from_bytes(raw)
        signature = self.keypair.sign_message(bytes(unsigned.message))
        return VersionedTransaction.populate(unsigned.message, [signature])


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None
