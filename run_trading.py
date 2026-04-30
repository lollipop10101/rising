#!/usr/bin/env python3
"""
Rising — Telegram signal listener + paper trader
Handles Degen-TH signals, checks risk, paper-trades.
Report after ~4 hours.
"""
from __future__ import annotations
import sys, os, asyncio, sqlite3, yaml
from pathlib import Path

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

# ── Load shared config ──────────────────────────────────────────────

_yaml_config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8")) or {}

def _cfg(path: str, default=None):
    cur = _yaml_config
    for p in path.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur

def _env(key: str, cfg_path: str, default: str) -> str:
    val = env.get(key, "")
    if val:
        return val
    cv = _cfg(cfg_path)
    if cv is not None:
        return str(cv)
    return default

# ── Config ────────────────────────────────────────────────────────────

api_id = int(env.get("TELEGRAM_API_ID", "0") or "0")
api_hash = env.get("TELEGRAM_API_HASH", "")
session = env.get("TELEGRAM_SESSION", "rising_test")
source_chat = env.get("TELEGRAM_SOURCE_CHAT", "Degen_TH")

MIN_LIQ = float(_env("MIN_LIQUIDITY_USD", "risk.min_liquidity_usd", "5000"))
MIN_VOL = float(_env("MIN_VOLUME_5M_USD", "risk.min_volume_5m_usd", "500"))
MAX_PUMP = float(_env("MAX_PUMP_5M_PCT", "risk.max_pump_5m_pct", "200"))
MAX_RISK = int(_env("MAX_RISK_SCORE", "risk.max_risk_score", "70"))
MAX_OPEN = int(_env("MAX_OPEN_POSITIONS", "trading.max_open_positions", "3"))
PAPER_BALANCE = float(_env("PAPER_BALANCE", "trading.paper_balance", "100"))
ALLOCATION_PCT = float(_env("ALLOCATION_PCT", "trading.allocation_pct", "0.1"))
PAPER_BALANCE_FLOOR = float(_env("PAPER_BALANCE_FLOOR", "trading.paper_balance_floor", "50"))
STOP_LOSS = float(_env("STOP_LOSS_PCT", "exit.stop_loss_pct", "-30"))
TP2 = float(_env("TP2_PCT", "exit.tp2_pct", "75"))
MAX_HOLD = float(_env("MAX_HOLD_MINUTES", "exit.max_hold_minutes", "20"))
TP1 = float(_env("TP1_PCT", "exit.tp1_pct", "25"))
TP1_SELL = float(_env("TP1_SELL_PCT", "exit.tp1_sell_pct", "50"))
TP2_SELL = float(_env("TP2_SELL_PCT", "exit.tp2_sell_pct", "30"))

TELEGRAM_BOT_TOKEN = env.get("TELEGRAM_BOT_TOKEN", "")
REPORT_BOT_TOKEN = TELEGRAM_BOT_TOKEN
REPORT_CHAT_ID = env.get("TELEGRAM_REPORT_CHAT_ID", "387074917")
POLL_SECONDS = int(_env("POLL_SECONDS", "exit.poll_seconds", "30"))

db = Database(env.get("DATABASE_URL", "sqlite:///data/rising.db"))
price = DexScreenerClient()
history = TokenHistoryChecker(db)
risk_engine = RiskEngine(min_liquidity_usd=MIN_LIQ, min_volume_5m_usd=MIN_VOL, max_pump_5m_pct=MAX_PUMP)
strategy = StrategyEngine(allocation_pct=ALLOCATION_PCT, max_risk_score=MAX_RISK)
paper = PaperTrader(db, default_balance=PAPER_BALANCE, balance_floor=PAPER_BALANCE_FLOOR)
positions = PositionManager(db, ExitConfig(
    stop_loss_pct=STOP_LOSS,
    tp1_pct=TP1,
    tp1_sell_pct=TP1_SELL,
    tp2_pct=TP2,
    tp2_sell_pct=TP2_SELL,
    max_hold_minutes=MAX_HOLD,
), price, paper, min_liquidity_usd=MIN_LIQ)

trade_taken = 0
skipped = 0

# ── Helpers ─────────────────────────────────────────────────────────────────

async def send(text: str) -> None:
    import httpx
    if not TELEGRAM_BOT_TOKEN:
        print(f"  [Telegram WARNING] no bot token configured, skipping send")
        return
    if not REPORT_CHAT_ID:
        print(f"  [Telegram WARNING] no report chat_id configured, skipping send")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": REPORT_CHAT_ID, "text": text},
            )
            ok = r.json().get("ok", False)
            if ok:
                print(f"  Telegram → OK (chat_id={REPORT_CHAT_ID})")
            else:
                err = r.json().get("description", "?")
                print(f"  Telegram → FAILED: {err}")
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
    decision = strategy.decide(signal_type, risk_result, open_pos, MAX_OPEN, paper.get_balance())

    if decision.decision == TradeDecision.BUY and snapshot.price_usd:
        trade_id = paper.buy(address, snapshot.price_usd, decision.position_size_usd, now)
        trade_taken += 1
    else:
        skipped += 1

# ── Main 4-hour session ────────────────────────────────────────────────────

async def run() -> None:
    await send(
        f"Rising started\nSource: {source_chat}\n"
        f"Min Liq: ${MIN_LIQ:,.0f} | Vol5m: ${MIN_VOL:,.0f}\n"
        f"Risk max: {MAX_RISK} | Max open: {MAX_OPEN}\n"
        f"Paper: ${paper.get_balance():.2f} | Alloc: {ALLOCATION_PCT * 100:.0f}% | Stop: {STOP_LOSS}%\n"
        f"Report in ~4 hours."
    )
    print("[Rising session starting — 4h, silent trades]")

    listener = TelegramSignalListener(api_id, api_hash, session, source_chat, bot_token=None)
    bot_task = asyncio.create_task(listener.run(handler))

    poll = POLL_SECONDS
    end_time = datetime.now(timezone.utc).timestamp() + 4 * 60 * 60

    while datetime.now(timezone.utc).timestamp() < end_time:
        await asyncio.sleep(poll)
        try:
            for trade in db.get_open_trades():
                snapshot = await price.fetch_token(trade["token_address"])
                if not snapshot.price_usd:
                    continue
                await positions.evaluate_trade(trade, snapshot.price_usd, datetime.now(timezone.utc))
        except Exception as e:
            print(f"Monitor error: {e}")
    # Cancel the Telegram listener first, then wait for it to clean up
    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"  Listener cleanup: {e}")

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