# Rising real-wallet trading design

Real trading is intentionally disabled by default.

## Safety checklist

1. Use a new hot wallet only.
2. Fund it with a tiny amount first.
3. Keep `REAL_TRADING_ENABLED=false` until paper trading works.
4. Start with `LIVE_DRY_RUN=true`.
5. Use strict limits:
   - `MAX_TRADE_USD=5`
   - `MAX_OPEN_POSITIONS=1`
   - `MAX_DAILY_LOSS_USD=10`
6. Never store the wallet key in GitHub.

## Environment

```bash
REAL_TRADING_ENABLED=false
LIVE_DRY_RUN=true
TRADE_MODE=paper
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_PRIVATE_KEY_PATH=/secure/path/hot-wallet.json
MAX_TRADE_USD=5
MAX_DAILY_LOSS_USD=10
JUPITER_SLIPPAGE_BPS=800
```

To test live signing without sending:

```bash
TRADE_MODE=live_dry_run
REAL_TRADING_ENABLED=true
LIVE_DRY_RUN=true
python run_trading.py
```

Only after many dry runs:

```bash
TRADE_MODE=live
REAL_TRADING_ENABLED=true
LIVE_DRY_RUN=false
python run_trading.py
```

## Integration point

Replace direct `self.paper.buy(...)` calls with `TradeRouter.buy(...)` after a strategy decision is accepted.

Pseudo:

```python
route = await self.trade_router.buy(address, snap.price_usd, dec.position_size_usd)
```

## Notes

This implementation uses Jupiter swap API transaction responses, signs a versioned transaction, and sends it through Solana RPC. It does not bypass your risk engine. Real execution must only happen after:

- token freshness check
- DexScreener liquidity/risk check
- max open position check
- max daily loss check
- wallet balance check
