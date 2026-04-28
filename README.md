# Rising

Solana meme coin paper trading bot.

Listens to Telegram channels for Solana token addresses, checks DexScreener for liquidity/risk, executes paper trades, and monitors positions.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in TELEGRAM_API_ID, TELEGRAM_API_HASH, SOURCE_CHAT, etc.
python -m rising.main
```

## Credentials needed

- `TELEGRAM_API_ID` — from https://my.telegram.org/apps
- `TELEGRAM_API_HASH` — from https://my.telegram.org/apps
- `TELEGRAM_SESSION` — session name (e.g. `rising_session`)
- `TELEGRAM_SOURCE_CHAT` — channel username or ID to listen to

## Risk thresholds

| Check | Score |
|-------|-------|
| No Solana pair on DexScreener | 100 (block) |
| No USD price | +30 |
| Liquidity < $min_liquidity_usd | +45 |
| No 5m volume | +15 |
| Price pumped >200% in 5m | +20 |

Trade if total score ≤ `max_risk_score` (default: 70).

## Exit rules

- Stop loss: `stop_loss_pct`
- Take profit 2: `tp2_pct`
- Max hold: `max_hold_minutes`

All trades are paper — no real money moves.
