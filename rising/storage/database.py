from __future__ import annotations
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import os

class RisingDB:
    def __init__(self, db_path: str = "rising.db", log_dir: str = "logs"):
        self.db_path = db_path
        self.log_dir = log_dir
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_address TEXT NOT NULL,
                    signal_price REAL,
                    entry_price REAL,
                    quote_usd REAL NOT NULL,
                    slippage_pct REAL DEFAULT 20,
                    notes TEXT,
                    entry_time TEXT NOT NULL,
                    status TEXT DEFAULT 'open',
                    exit_price REAL,
                    pnl_usd REAL,
                    pnl_pct REAL,
                    exit_reason TEXT,
                    exit_time TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS token_history (
                    token_address TEXT PRIMARY KEY,
                    first_seen_at TEXT NOT NULL,
                    was_traded INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_address TEXT NOT NULL,
                    signal_price REAL,
                    symbol TEXT,
                    liquidity_usd REAL,
                    volume_5m REAL,
                    risk_score INTEGER,
                    decision TEXT,
                    reason TEXT,
                    trade_taken INTEGER DEFAULT 0,
                    signal_time TEXT NOT NULL
                )
            """)

    def log_signal(self, token_address: str, signal_price: float, symbol: str,
                   liquidity_usd: float, volume_5m: float,
                   risk_score: int, decision: str, reason: str, trade_taken: bool):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO signals
                   (token_address, signal_price, symbol, liquidity_usd, volume_5m,
                    risk_score, decision, reason, trade_taken, signal_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (token_address, signal_price, symbol, liquidity_usd, volume_5m,
                 risk_score, decision, reason, int(trade_taken),
                 datetime.now(timezone.utc).isoformat())
            )
        self._jsonl_append("signal", {
            "token_address": token_address,
            "signal_price": signal_price,
            "symbol": symbol,
            "liquidity_usd": liquidity_usd,
            "volume_5m": volume_5m,
            "risk_score": risk_score,
            "decision": decision,
            "reason": reason,
            "trade_taken": trade_taken,
            "signal_time": datetime.now(timezone.utc).isoformat(),
        })

    def _jsonl_append(self, event_type: str, data: Dict[str, Any]):
        log_file = os.path.join(self.log_dir, f"{event_type}s.jsonl")
        with open(log_file, "a") as f:
            f.write(json.dumps({"event": event_type, **data}) + "\n")

    def create_trade(self, token_address: str, signal_price: float,
                     entry_price: float, quote_usd: float,
                     slippage_pct: float, notes: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO trades
                   (token_address, signal_price, entry_price, quote_usd, slippage_pct, notes, entry_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (token_address, signal_price, entry_price, quote_usd, slippage_pct,
                 notes, datetime.now(timezone.utc).isoformat())
            )
            conn.execute(
                "INSERT OR IGNORE INTO token_history (token_address, first_seen_at) VALUES (?, ?)",
                (token_address, datetime.now(timezone.utc).isoformat())
            )
            conn.execute(
                "UPDATE token_history SET was_traded = 1 WHERE token_address = ?",
                (token_address,)
            )
            trade_id = cursor.lastrowid
        self._jsonl_append("trade", {
            "trade_id": trade_id,
            "token_address": token_address,
            "signal_price": signal_price,
            "entry_price": entry_price,
            "quote_usd": quote_usd,
            "slippage_pct": slippage_pct,
            "notes": notes,
            "entry_time": datetime.now(timezone.utc).isoformat(),
        })
        return trade_id

    def open_trades(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT * FROM trades WHERE status = 'open'"
            ).fetchall()

    def close_trade(self, trade_id: int, exit_price: float,
                    pnl_usd: float, pnl_pct: float, reason: str,
                    market_price_at_exit: float, slippage_pct_exit: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE trades SET status = 'closed', exit_price = ?,
                   pnl_usd = ?, pnl_pct = ?, exit_reason = ?, exit_time = ?
                   WHERE id = ?""",
                (exit_price, pnl_usd, pnl_pct, reason,
                 datetime.now(timezone.utc).isoformat(), trade_id)
            )
        self._jsonl_append("exit", {
            "trade_id": trade_id,
            "exit_price": exit_price,
            "market_price_at_exit": market_price_at_exit,
            "slippage_pct_exit": slippage_pct_exit,
            "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct,
            "reason": reason,
            "exit_time": datetime.now(timezone.utc).isoformat(),
        })

    def get_token(self, token_address: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM token_history WHERE token_address = ?", (token_address,)
            ).fetchone()
            return dict(row) if row else None
