from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

class RisingDB:
    def __init__(self, db_path: str = "rising.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_address TEXT NOT NULL,
                    entry_price REAL,
                    quote_usd REAL NOT NULL,
                    notes TEXT,
                    entry_time TEXT NOT NULL,
                    status TEXT DEFAULT 'open'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS token_history (
                    token_address TEXT PRIMARY KEY,
                    first_seen_at TEXT NOT NULL,
                    was_traded INTEGER DEFAULT 0
                )
            """)

    def create_trade(self, token_address: str, entry_price: float, quote_usd: float, notes: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO trades (token_address, entry_price, quote_usd, notes, entry_time) VALUES (?, ?, ?, ?, ?)",
                (token_address, entry_price, quote_usd, notes, datetime.now(timezone.utc).isoformat())
            )
            conn.execute(
                "INSERT OR IGNORE INTO token_history (token_address, first_seen_at) VALUES (?, ?)",
                (token_address, datetime.now(timezone.utc).isoformat())
            )
            conn.execute(
                "UPDATE token_history SET was_traded = 1 WHERE token_address = ?",
                (token_address,)
            )
            return cursor.lastrowid

    def open_trades(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT * FROM trades WHERE status = 'open'"
            ).fetchall()

    def close_trade(self, trade_id: int, exit_price: float, pnl_usd: float, pnl_pct: float, reason: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE trades SET status = 'closed', exit_price = ?, pnl_usd = ?, pnl_pct = ?, exit_reason = ?, exit_time = ? WHERE id = ?",
                (exit_price, pnl_usd, pnl_pct, reason, datetime.now(timezone.utc).isoformat(), trade_id)
            )

    def get_token(self, token_address: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM token_history WHERE token_address = ?", (token_address,)
            ).fetchone()
            return dict(row) if row else None
