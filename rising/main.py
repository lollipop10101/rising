from __future__ import annotations
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from rising.ingestion.telegram_listener import TelegramSignalListener
from rising.parsing.address_extractor import extract_solana_addresses
from rising.data.price_fetcher import DexScreenerClient
from rising.intelligence.token_history_checker import TokenHistoryChecker
from rising.risk.risk_engine import RiskEngine
from rising.strategy.trade_decision import StrategyEngine
from rising.execution.paper_trader import PaperTrader
from rising.position.position_manager import PositionManager
from rising.storage.database import RisingDB

logger.remove()
logger.add(sys.stderr, level="INFO")

# ── Config ────────────────────────────────────────────────────────────────────

load_dotenv()
import os

TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "rising_session")
TELEGRAM_SOURCE_CHAT = os.getenv("TELEGRAM_SOURCE_CHAT", "")

MIN_LIQUIDITY_USD = float(os.getenv("MIN_LIQUIDITY_USD", "10000"))
MAX_RISK_SCORE = int(os.getenv("MAX_RISK_SCORE", "70"))

QUOTE_USD = float(os.getenv("QUOTE_USD", "10"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "-20"))
TP2_PCT = float(os.getenv("TP2_PCT", "100"))
MAX_HOLD_MINUTES = int(os.getenv("MAX_HOLD_MINUTES", "60"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))
DB_PATH = os.getenv("DB_PATH", "rising.db")

# ── Components ────────────────────────────────────────────────────────────────

db = RisingDB(DB_PATH)
price_client = DexScreenerClient()
history_checker = TokenHistoryChecker()
risk_engine = RiskEngine(min_liquidity_usd=MIN_LIQUIDITY_USD, max_risk_score=MAX_RISK_SCORE)
strategy = StrategyEngine()
paper_trader = PaperTrader(db, QUOTE_USD)
position_manager = PositionManager(db, price_client, type('Cfg', (), {
    'stop_loss_pct': STOP_LOSS_PCT,
    'tp2_pct': TP2_PCT,
    'max_hold_minutes': MAX_HOLD_MINUTES,
    'poll_seconds': POLL_SECONDS,
})())

# ── Token handler ────────────────────────────────────────────────────────────

async def on_token(address: str, text: str, msg_time, chat_id: str, sender_id: str):
    logger.info(f"Signal received: {address} from {chat_id}")

    token = db.get_token(address)
    signal = history_checker.classify(token, msg_time)
    market = await price_client.get_solana_token(address)
    risk = risk_engine.evaluate(market)
    decision = strategy.decide(signal, market, risk)

    logger.info(f"  signal={signal.value} risk={risk.score} decision={decision.action}")
    if decision.action == "BUY_PAPER":
        trade_id = await paper_trader.buy(
            address,
            market.price_usd if market else None,
            f"{decision.reason} | text: {text[:100]}"
        )
        logger.success(f"  PAPER BUY recorded: trade_id={trade_id}")

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        logger.error("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
        sys.exit(1)

    logger.info("Starting Rising...")
    logger.info(f"  Source chat: {TELEGRAM_SOURCE_CHAT}")
    logger.info(f"  Min liquidity: ${MIN_LIQUIDITY_USD:,.0f}")
    logger.info(f"  Max risk score: {MAX_RISK_SCORE}")

    listener = TelegramSignalListener(
        api_id=TELEGRAM_API_ID,
        api_hash=TELEGRAM_API_HASH,
        session_name=TELEGRAM_SESSION,
        source_chats=[TELEGRAM_SOURCE_CHAT] if TELEGRAM_SOURCE_CHAT else None,
        on_token=on_token,
    )

    # Run position monitor and Telegram listener concurrently
    await asyncio.gather(
        position_manager.run_forever(),
        listener.start(),
    )

if __name__ == "__main__":
    asyncio.run(main())
