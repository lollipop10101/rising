#!/usr/bin/env python3
"""
Rising — CLI entrypoint (corrected for v0.3 module APIs)
Usage:
    python -m rising.main telegram  # start Telegram listener + paper trading
    python -m rising.main check      # verify all components wire correctly
    python -m rising.main summary   # print open positions + today's summary
"""
from __future__ import annotations
import asyncio
import sqlite3
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
from rising.models import SignalType


# ── Config from env ─────────────────────────────────────────────────────────

env = os.environ

api_id_str = env.get("TELEGRAM_API_ID", "0") or "0"
api_id = int(api_id_str) if api_id_str not in ("", "0") else 0
api_hash = env.get("TELEGRAM_API_HASH", "")
session = env.get("TELEGRAM_SESSION", "rising_test")
source_chat = env.get("TELEGRAM_SOURCE_CHAT", "Degen_TH")
bot_token = env.get("TELEGRAM_BOT_TOKEN", "")

MIN_LIQ = float(env.get("MIN_LIQUIDITY_USD", "5000"))
MIN_VOL = float(env.get("MIN_VOLUME_5M_USD", "500"))
MAX_PUMP = float(env.get("MAX_PUMP_5M_PCT", "200"))
MAX_RISK = int(env.get("MAX_RISK_SCORE", "70"))
MAX_OPEN = int(env.get("MAX_OPEN_POSITIONS", "3"))
QUOTE_USD = float(env.get("QUOTE_USD", "15"))
STOP_LOSS = float(env.get("STOP_LOSS_PCT", "-30"))
TP1 = float(env.get("TP1_PCT", "25"))
TP2 = float(env.get("TP2_PCT", "75"))
MAX_HOLD = float(env.get("MAX_HOLD_MINUTES", "20"))
REPORT_BOT_TOKEN = env.get("TELEGRAM_BOT_TOKEN", "")
REPORT_CHAT_ID = env.get("TELEGRAM_REPORT_CHAT_ID", "387074917")

DB_URL = env.get("DATABASE_URL", f"sqlite:///{PROJECT_ROOT}/data/rising.db")


# ── Build components ─────────────────────────────────────────────────────────

db = Database(DB_URL)
price = DexScreenerClient()
history = TokenHistoryChecker(db)
risk_engine = RiskEngine(min_liquidity_usd=MIN_LIQ, min_volume_5m_usd=MIN_VOL, max_pump_5m_pct=MAX_PUMP)
strategy = StrategyEngine(paper_trade_usd=QUOTE_USD, max_risk_score=MAX_RISK)
paper = PaperTrader(db)
positions = PositionManager(db, ExitConfig(
    stop_loss_pct=STOP_LOSS,
    tp1_pct=TP1,
    tp1_sell_pct=float(env.get("TP1_SELL_PCT", "50")),
    tp2_pct=TP2,
    tp2_sell_pct=float(env.get("TP2_SELL_PCT", "30")),
    max_hold_minutes=MAX_HOLD,
), price, min_liquidity_usd=MIN_LIQ)


# ── Telegram message handler ─────────────────────────────────────────────────

async def handle_message(text: str, chat: str | None) -> None:
    """Called by TelegramSignalListener for each received message."""
    if not text.strip():
        return
    print(f"  Telegram msg: {text[:80]}")

    addresses = extract_solana_addresses(text)
    if not addresses:
        return

    now = datetime.now(timezone.utc)
    for address in addresses:
        # Record token seen
        snapshot = await price.fetch_token(address)
        db.upsert_token_seen(address, now, snapshot.price_usd if snapshot else None, snapshot.liquidity_usd if snapshot else None)

        # Classify signal
        signal_type = history.classify(address, now)
        db.add_signal(address, text, chat, now, signal_type.value)

        # Risk check
        risk = risk_engine.score(snapshot)

        # Trading decision
        open_pos = len(db.get_open_trades())
        decision = strategy.decide(signal_type, risk, open_positions=open_pos, max_open_positions=MAX_OPEN)

        print(f"    {address[:16]}.. | signal={signal_type.value} | risk={risk.score} | decision={decision.decision.value}")

        if decision.decision.value == "BUY" and snapshot and snapshot.price_usd:
            trade_id = paper.buy(address, snapshot.price_usd, decision.position_size_usd, now)
            print(f"    → PAPER BUY trade_id={trade_id}")
        else:
            print(f"    → SKIP: {', '.join(decision.reasons[:2])}")


# ── Report builder ───────────────────────────────────────────────────────────

def build_report() -> str:
    """Build the end-of-session summary string."""
    now = datetime.now(timezone.utc)

    with db.connect() as conn:
        conn.row_factory = sqlite3.Row
        open_rows = conn.execute("SELECT * FROM trades WHERE status = 'OPEN'").fetchall()

    open_trades = [dict(r) for r in open_rows]
    lines = [
        f"🧊 Rising Report — {now.strftime('%H:%M')} UTC",
        f"Open: {len(open_trades)} | Session: 4h",
    ]

    for t in open_trades:
        age = (now - datetime.fromisoformat(t["opened_at"])).total_seconds() / 60.0
        lines.append(f"  • {t['token_address'][:12]}.. | ${t['entry_price']} | +{age:.0f}m")

    with db.connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT COUNT(*) as n, SUM(realized_pnl_usd) as pnl FROM trades WHERE status = 'CLOSED'").fetchone()

    lines.append(f"Closed: {row['n']} | PnL: ${row['pnl'] or 0:.2f}")
    return "\n".join(lines)


# ── Helpers ─────────────────────────────────────────────────────────────────

async def send(text: str) -> None:
    import httpx
    if not REPORT_BOT_TOKEN:
        print(f"  [Telegram] no bot token configured, skipping send")
        return
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


# ── CLI commands ────────────────────────────────────────────────────────────

def check() -> int:
    """Verify all components are correctly wired."""
    ok = True
    checks = [
        ("Database", db),
        ("DexScreenerClient", price),
        ("TokenHistoryChecker(db)", history),
        ("RiskEngine(min_liq, min_vol, max_pump)", risk_engine),
        ("StrategyEngine(paper_trade_usd, max_risk)", strategy),
        ("PaperTrader(db)", paper),
        ("PositionManager(db, ExitConfig, price, min_liq)", positions),
    ]
    for label, obj in checks:
        try:
            _ = str(obj)
            print(f"  ✓ {label}")
        except Exception as e:
            print(f"  ✗ {label}: {e}")
            ok = False
    print()
    if ok:
        print("All checks passed ✅")
        return 0
    print("Some checks failed ❌")
    return 1


def summary() -> int:
    """Print current open positions and today's closed summary."""
    print(build_report())
    return 0


async def run_telegram_session(duration_minutes: float = 240) -> None:
    """Start Telegram listener + price monitor for a timed session, then send report."""
    end_time = datetime.now(timezone.utc).timestamp() + (duration_minutes * 60)
    poll = 30
    trade_count = 0

    listener = TelegramSignalListener(
        api_id=api_id,
        api_hash=api_hash,
        session=session,
        source_chat=source_chat,
        bot_token=bot_token or None,
    )

    listener_task = asyncio.create_task(listener.run(handle_message))

    while datetime.now(timezone.utc).timestamp() < end_time:
        await asyncio.sleep(poll)
        try:
            for trade in db.get_open_trades():
                snapshot = await price.fetch_token(trade["token_address"])
                if not snapshot or not snapshot.price_usd:
                    continue
                event = await positions.evaluate_trade(trade, snapshot.price_usd, datetime.now(timezone.utc))
                if event:
                    await send(f"📍 Rising exit: {event}\nToken: {trade['token_address'][:20]}\nPrice: ${snapshot.price_usd}")
        except Exception as e:
            print(f"  Monitor error: {e}")

    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass

    report = build_report()
    print(f"\n{report}")
    await send(report)


# ── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "telegram"

    if cmd == "check":
        sys.exit(check())
    elif cmd == "summary":
        sys.exit(summary())
    elif cmd == "telegram":
        if not api_id or not api_hash:
            print("Error: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
            sys.exit(1)
        asyncio.run(run_telegram_session())
    else:
        print(f"Usage: python -m rising.main [check|summary|telegram]")
        sys.exit(1)