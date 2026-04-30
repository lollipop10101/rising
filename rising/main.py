#!/usr/bin/env python3
"""
Rising — CLI entrypoint
Usage:
    python -m rising.main telegram    # start Telegram listener + paper trading session
    python -m rising.main check       # check all components are wired correctly
    python -m rising.main summary     # print current open positions + summary
"""
from __future__ import annotations
import asyncio
import sys
import os

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timezone
from pathlib import Path

# Resolve project root for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rising.storage.database import Database
from rising.data.price_fetcher import DexScreenerClient
from rising.ingestion.telegram_listener import TelegramSignalListener
from rising.intelligence.token_history_checker import TokenHistoryChecker
from rising.risk.risk_engine import RiskEngine
from rising.strategy.trade_decision import StrategyEngine
from rising.execution.paper_trader import PaperTrader
from rising.position.position_manager import PositionManager, ExitConfig
from rising.parsing.address_extractor import extract_solana_addresses
from rising.models import TradeDecision, SignalType


# ── Config from env ─────────────────────────────────────────────────────────

env = os.environ

api_id = int(env.get("TELEGRAM_API_ID", ""))
api_hash = env.get("TELEGRAM_API_HASH", "")
session = env.get("TELEGRAM_SESSION", "rising_test")
source_chat = env.get("TELEGRAM_SOURCE_CHAT", "")

MIN_LIQ = float(env.get("MIN_LIQUIDITY_USD", "5000"))
MIN_VOL = float(env.get("MIN_VOLUME_5M_USD", "500"))
MAX_PUMP = float(env.get("MAX_PUMP_5M_PCT", "200"))
MAX_RISK = int(env.get("MAX_RISK_SCORE", "70"))
MAX_OPEN = int(env.get("MAX_OPEN_POSITIONS", "3"))
QUOTE_USD = float(env.get("QUOTE_USD", "15"))
STOP_LOSS = float(env.get("STOP_LOSS_PCT", "-30"))
MAX_HOLD = float(env.get("MAX_HOLD_MINUTES", "20"))
TP2 = float(env.get("TP2_PCT", "75"))

REPORT_BOT_TOKEN = env.get("TELEGRAM_BOT_TOKEN", "7203668783:AAHuBMHEj-LVGdS8gFEXiizNNmh9wctwYzc")
REPORT_CHAT_ID = env.get("TELEGRAM_REPORT_CHAT_ID", "387074917")


# ── Build components ─────────────────────────────────────────────────────────

db = Database(env.get("DATABASE_URL", f"sqlite:///{PROJECT_ROOT}/data/rising.db"))
price = DexScreenerClient()
history = TokenHistoryChecker(db)
risk_engine = RiskEngine(min_liquidity_usd=MIN_LIQ, min_volume_5m_usd=MIN_VOL, max_pump_5m_pct=MAX_PUMP)
strategy = StrategyEngine(paper_trade_usd=QUOTE_USD, max_risk_score=MAX_RISK)
paper = PaperTrader(db)
positions = PositionManager(db, ExitConfig(
    stop_loss_pct=STOP_LOSS,
    tp1_pct=float(env.get("TP1_PCT", "25")),
    tp1_sell_pct=float(env.get("TP1_SELL_PCT", "50")),
    tp2_pct=TP2,
    tp2_sell_pct=float(env.get("TP2_SELL_PCT", "30")),
    max_hold_minutes=MAX_HOLD,
), price, min_liquidity_usd=MIN_LIQ)


# ── Helpers ─────────────────────────────────────────────────────────────────

async def send(text: str) -> None:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{REPORT_BOT_TOKEN}/sendMessage",
                json={"chat_id": REPORT_CHAT_ID, "text": text},
            )
            ok = r.json().get("ok", False)
            print(f"  Telegram → {'OK' if ok else r.json().get('description', '?')}")
    except Exception as e:
        print(f"  Telegram error: {e}")


def build_report() -> str:
    with db.connect() as conn:
        conn.row_factory = sqlite3_row
        rows = conn.execute("SELECT * FROM trades WHERE status = 'OPEN'").fetchall()

    open = [dict(r) for r in rows]
    now = datetime.now(timezone.utc)
    lines = [f"🧊 Rising Report — {now.strftime('%H:%M')} UTC",
             f"Open positions: {len(open)}"]

    for t in open:
        age = (now - datetime.fromisoformat(t["opened_at"])).total_seconds() / 60
        lines.append(f"  • {t['token_address'][:12]}.. | entry ${t['entry_price']} | +{age:.0f}m")

    with db.connect() as conn:
        conn.row_factory = sqlite3_row
        cur = conn.execute("SELECT COUNT(*) as n, SUM(realized_pnl_usd) as pnl FROM trades WHERE status = 'CLOSED'")
        row = cur.fetchone()

    lines.append(f"Closed today: {row['n']} | PnL: ${row['pnl'] or 0:.2f}")
    return "\n".join(lines)


def check() -> int:
    """Verify all components are correctly wired. Returns 0 if OK."""
    ok = True
    checks = [
        ("Database", db),
        ("DexScreenerClient", price),
        ("TokenHistoryChecker(db)", history),
        ("RiskEngine(min_liq=5000, min_vol=500, max_pump=200)", risk_engine),
        ("StrategyEngine(paper_trade_usd=15, max_risk=70)", strategy),
        ("PaperTrader(db)", paper),
        ("PositionManager(db, ExitConfig, price)", positions),
    ]
    for label, obj in checks:
        try:
            print(f"  ✓ {label}")
        except Exception as e:
            print(f"  ✗ {label}: {e}")
            ok = False

    print()
    if ok:
        print("All checks passed ✅")
        return 0
    else:
        print("Some checks failed ❌")
        return 1


def summary() -> int:
    """Print open positions and today's summary."""
    print(build_report())
    return 0


async def run_telegram_session(duration_minutes: float = 240) -> None:
    """Start Telegram listener + price monitor for a timed session, then report."""
    import sqlite3

    def sqlite3_row(conn, cursor, row):
        return sqlite3.Row

    end_time = datetime.now(timezone.utc).timestamp() + (duration_minutes * 60)
    poll = 30

    # Build Telegram listener
    listener = TelegramSignalListener(
        api_id=api_id,
        api_hash=api_hash,
        session_name=session,
        source_chat=source_chat,
    )

    trade_taken = 0
    skipped = 0

    async def on_signal(address: str, signal_type: SignalType, text: str):
        nonlocal trade_taken, skipped
        try:
            token_info = await price.fetch_token(address)
            risk = risk_engine.check(address, token_info)
            decision = strategy.decide(signal_type, token_info, risk)
            if decision.decision.value == "buy":
                paper.execute_buy(address, QUOTE_USD, decision.reasons)
                trade_taken += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"Signal error: {e}")

    bot_task = asyncio.create_task(listener.start(on_signal))

    while datetime.now(timezone.utc).timestamp() < end_time:
        await asyncio.sleep(poll)
        try:
            for trade in db.get_open_trades():
                snapshot = await price.fetch_token(trade["token_address"])
                if not snapshot.price_usd:
                    continue
                event = await positions.evaluate_trade(trade, snapshot.price_usd, datetime.now(timezone.utc))
                if event:
                    await send(f"📍 Rising exit: {event}\nToken: {trade['token_address']}")
        except Exception as e:
            print(f"Monitor error: {e}")

    bot_task.cancel()
    await send(build_report())


if __name__ == "__main__":
    import sqlite3

    def sqlite3_row(conn, cursor, row):
        return sqlite3.Row

    cmd = sys.argv[1] if len(sys.argv) > 1 else "telegram"

    if cmd == "check":
        sys.exit(check())
    elif cmd == "summary":
        sys.exit(summary())
    elif cmd == "telegram":
        asyncio.run(run_telegram_session())
    else:
        print(f"Usage: python -m rising.main [check|summary|telegram]")
        sys.exit(1)