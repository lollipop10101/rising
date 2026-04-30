#!/usr/bin/env python3
"""
Rising — Telegram signal listener + paper trader
Handles Degen-TH signals, checks risk, paper-trades.
Report after ~2 hours.
"""
from __future__ import annotations
import sys, os, asyncio, sqlite3

# Set CWD to this directory so session files are found correctly
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timezone
from rising.storage.database import Database
from rising.data.price_fetcher import DexScreenerClient
from rising.ingestion.telegram_listener import TelegramSignalListener
from rising.intelligence.token_history_checker import TokenHistoryChecker
from rising.risk.risk_engine import RiskEngine
from rising.strategy.trade_decision import StrategyEngine
from rising.execution.paper_trader import PaperTrader
from rising.position.position_manager import PositionManager, ExitConfig
from rising.parsing.address_extractor import extract_solana_addresses
from rising.models import TradeDecision

env = os.environ

# ── Config ─────────────────────────────────────────────────────────────────

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
TP2 = float(env.get("TP2_PCT", "75"))
MAX_HOLD = float(env.get("MAX_HOLD_MINUTES", "20"))

TELEGRAM_BOT_TOKEN = env.get("TELEGRAM_BOT_TOKEN", "")
REPORT_BOT_TOKEN = TELEGRAM_BOT_TOKEN or "7203668783:AAHuBMHEj-LVGdS8gFEXiizNNmh9wctwYzc"
REPORT_CHAT_ID = env.get("TELEGRAM_REPORT_CHAT_ID", "387074917")

db = Database(env.get("DATABASE_URL", "sqlite:///data/rising.db"))
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

trade_taken = 0
skipped = 0

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

def is_signal(text: str) -> bool:
    """Message contains at least one SOL address → treat as signal."""
    return len(extract_solana_addresses(text)) >= 1

# ── Message handler ────────────────────────────────────────────────────────

async def handler(text: str, chat_id: str | None) -> None:
    global trade_taken, skipped
    if not is_signal(text):
        return
    address = extract_solana_addresses(text)[0]
    now = datetime.now(timezone.utc)

    signal_type = history.classify(address, now)
    snapshot = await price.fetch_token(address)
    db.upsert_token_seen(address, now, snapshot.price_usd, snapshot.liquidity_usd)
    db.add_signal(address, text, chat_id, now, signal_type.value)

    risk_result = risk_engine.score(snapshot)
    open_pos = len(db.get_open_trades())
    decision = strategy.decide(signal_type, risk_result, open_pos, MAX_OPEN)

    sym = snapshot.base_symbol or "???"
    liq = snapshot.liquidity_usd or 0
    vol5m = snapshot.volume_5m_usd or 0
    price_str = f"${snapshot.price_usd:.8f}" if snapshot.price_usd else "?"
    reason_str = "; ".join(decision.reasons[:4])

    if decision.decision == TradeDecision.BUY and snapshot.price_usd:
        trade_id = paper.buy(address, snapshot.price_usd, decision.position_size_usd, now)
        trade_taken += 1
        # Silent — no per-trade alerts; summary only every 4 hours
    else:
        skipped += 1

# ── Main 2-hour session ────────────────────────────────────────────────────

async def run() -> None:
    await send(
        f"Rising started\nSource: {source_chat}\n"
        f"Min Liq: ${MIN_LIQ:,.0f} | Vol5m: ${MIN_VOL:,.0f}\n"
        f"Risk max: {MAX_RISK} | Max open: {MAX_OPEN}\n"
        f"Quote: ${QUOTE_USD}/trade | Stop: {STOP_LOSS}%\n"
        f"Report in ~4 hours."
    )
    print("[Rising session starting — 4h, silent trades]")

    # Use user session only (no bot token) — whale auth, IN Degen_TH
    listener = TelegramSignalListener(api_id, api_hash, session, source_chat, bot_token=None)
    bot_task = asyncio.create_task(listener.run(handler))

    poll = int(env.get("POLL_SECONDS", "30"))
    end_time = datetime.now(timezone.utc).timestamp() + 4 * 60 * 60

    while datetime.now(timezone.utc).timestamp() < end_time:
        await asyncio.sleep(poll)
        try:
            for trade in db.get_open_trades():
                snapshot = await price.fetch_token(trade["token_address"])
                if not snapshot.price_usd:
                    continue
                positions.evaluate_trade(trade, snapshot.price_usd, datetime.now(timezone.utc))
        except Exception as e:
            print(f"Monitor error: {e}")
    try:
        await bot_task
    except asyncio.CancelledError:
        pass

    # Final report
    with db.connect() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT COUNT(*) as n, SUM(realized_pnl_usd) as pnl, "
            "SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) as open_n FROM trades"
        ).fetchone()
        closed_n = cur["n"] - cur["open_n"]
        pnl = cur["pnl"] or 0

    report = (
        f"Rising Report\nBought: {trade_taken} | Skipped: {skipped}\n"
        f"Open: {cur['open_n']} | Closed: {closed_n}\nRealized PnL: ${pnl:.2f}"
    )
    await send(report)
    print("\n" + report)

if __name__ == "__main__":
    print("Starting Rising...")
    asyncio.run(run())