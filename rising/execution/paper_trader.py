from __future__ import annotations


class PaperTrader:
    # Realistic cost parameters
    ENTRY_SLIPPAGE_PCT = 20.0   # worst-case 20% slippage on meme coin entry
    EXIT_FEE_PCT = 1.0          # 1% Solana DEX fee on exit

    def __init__(self, db, quote_usd: float):
        self.db = db
        self.quote_usd = quote_usd

    async def buy(self, token_address: str, market_price: float, notes: str) -> int:
        """
        Execute paper BUY with realistic entry slippage.
        Signal price is market_price at time of signal.
        Effective entry price = market_price * (1 + slippage) — we get fewer tokens.
        """
        signal_price = market_price
        # We pay 20% more than the signal price — fewer tokens per dollar
        entry_price = signal_price * (1 + self.ENTRY_SLIPPAGE_PCT / 100)

        trade_id = self.db.create_trade(
            token_address=token_address,
            signal_price=signal_price,
            entry_price=entry_price,
            quote_usd=self.quote_usd,
            slippage_pct=self.ENTRY_SLIPPAGE_PCT,
            notes=notes,
        )
        return trade_id

    def calc_exit(self, market_price: float, quote_usd: float, entry_price: float):
        """
        Calculate realistic exit:
        - We receive market_price * (1 - fee) per token
        - PnL = (exit_price - entry_price) / entry_price * 100%
        Returns (exit_price, pnl_pct, pnl_usd)
        """
        exit_price = market_price * (1 - self.EXIT_FEE_PCT / 100)
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        pnl_usd = quote_usd * pnl_pct / 100
        return exit_price, pnl_pct, pnl_usd
