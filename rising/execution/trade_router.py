from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from rising.execution.paper_trader import PaperTrader
from rising.execution.live_executor import JupiterLiveExecutor, LiveSwapResult


@dataclass(slots=True)
class TradeModeConfig:
    mode: str = "paper"  # paper | live_dry_run | live
    sol_usd_price: float = 150.0


class TradeRouter:
    """Routes accepted strategy decisions to paper or live execution."""

    def __init__(self, paper: PaperTrader, live: JupiterLiveExecutor | None, cfg: TradeModeConfig) -> None:
        self.paper = paper
        self.live = live
        self.cfg = cfg

    async def buy(self, token_address: str, price_usd: float, size_usd: float):
        now = datetime.now(timezone.utc)
        if self.cfg.mode == "paper":
            return {"mode": "paper", "trade_id": self.paper.buy(token_address, price_usd, size_usd, now)}

        if self.live is None:
            raise RuntimeError("Live executor not configured")

        lamports = int((size_usd / self.cfg.sol_usd_price) * 1_000_000_000)
        result: LiveSwapResult = await self.live.buy_token_with_sol(token_address, lamports)
        return {"mode": self.cfg.mode, "result": result}
