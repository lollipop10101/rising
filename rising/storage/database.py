from __future__ import annotations
import sqlite3, json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

def _to_iso(dt: datetime | None)->str|None:
    if dt is None: return None
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
class Database:
    def __init__(self,database_url:str='sqlite:///data/rising.db'):
        if not database_url.startswith('sqlite:///'): raise ValueError('Only sqlite:/// URLs are supported')
        self.path=Path(database_url.replace('sqlite:///','')); self.path.parent.mkdir(parents=True, exist_ok=True); self.init_schema()
    @contextmanager
    def connect(self)->Iterator[sqlite3.Connection]:
        c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row
        try: yield c; c.commit()
        finally: c.close()
    def init_schema(self):
        with self.connect() as c:
            c.executescript('''
CREATE TABLE IF NOT EXISTS tokens(token_address TEXT PRIMARY KEY, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, seen_count INTEGER NOT NULL DEFAULT 1, first_seen_price REAL, last_seen_price REAL, first_seen_liquidity REAL, last_seen_liquidity REAL, was_traded INTEGER NOT NULL DEFAULT 0, trade_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'seen');
CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY AUTOINCREMENT, token_address TEXT NOT NULL, message TEXT, source_chat TEXT, seen_at TEXT NOT NULL, signal_type TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT, token_address TEXT NOT NULL, opened_at TEXT NOT NULL, closed_at TEXT, entry_price REAL NOT NULL, avg_exit_price REAL, initial_size_usd REAL NOT NULL, remaining_pct REAL NOT NULL DEFAULT 100, realized_pnl_usd REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'OPEN', exit_reason TEXT);
CREATE TABLE IF NOT EXISTS trade_events(id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id INTEGER NOT NULL, event_at TEXT NOT NULL, event_type TEXT NOT NULL, price_usd REAL, qty_pct REAL, pnl_usd REAL, note TEXT);
CREATE TABLE IF NOT EXISTS smart_wallets(wallet_address TEXT PRIMARY KEY, label TEXT, source TEXT, score INTEGER NOT NULL DEFAULT 0, copyability_score INTEGER NOT NULL DEFAULT 0, insider_score INTEGER NOT NULL DEFAULT 0, win_rate REAL NOT NULL DEFAULT 0, realized_pnl_usd REAL NOT NULL DEFAULT 0, trade_count INTEGER NOT NULL DEFAULT 0, tier TEXT NOT NULL DEFAULT 'D_TIER_NOISE', status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, reasons TEXT);
CREATE TABLE IF NOT EXISTS wallet_trades(id INTEGER PRIMARY KEY AUTOINCREMENT, wallet_address TEXT NOT NULL, token_address TEXT NOT NULL, side TEXT NOT NULL, tx_signature TEXT NOT NULL, price_usd REAL, amount_usd REAL, token_amount REAL, timestamp TEXT NOT NULL, dex TEXT, source TEXT, UNIQUE(wallet_address, token_address, side, tx_signature));
CREATE TABLE IF NOT EXISTS copy_signals(id INTEGER PRIMARY KEY AUTOINCREMENT, wallet_address TEXT NOT NULL, token_address TEXT NOT NULL, signal_time TEXT NOT NULL, tx_signature TEXT NOT NULL, wallet_score INTEGER, copyability_score INTEGER, token_risk_score INTEGER, decision TEXT NOT NULL, reason TEXT, paper_trade_id INTEGER);
''')
    def get_token(self,a):
        with self.connect() as c: return c.execute('SELECT * FROM tokens WHERE token_address=?',(a,)).fetchone()
    def upsert_token_seen(self,a,now,price=None,liquidity=None):
        e=self.get_token(a)
        with self.connect() as c:
            if e is None: c.execute('INSERT INTO tokens(token_address,first_seen_at,last_seen_at,first_seen_price,last_seen_price,first_seen_liquidity,last_seen_liquidity) VALUES(?,?,?,?,?,?,?)',(a,_to_iso(now),_to_iso(now),price,price,liquidity,liquidity))
            else: c.execute('UPDATE tokens SET last_seen_at=?, seen_count=seen_count+1, last_seen_price=COALESCE(?,last_seen_price), last_seen_liquidity=COALESCE(?,last_seen_liquidity) WHERE token_address=?',(_to_iso(now),price,liquidity,a))
    def add_signal(self,a,msg,chat,seen_at,signal_type):
        with self.connect() as c: c.execute('INSERT INTO signals(token_address,message,source_chat,seen_at,signal_type) VALUES(?,?,?,?,?)',(a,msg,chat,_to_iso(seen_at),signal_type))
    def open_trade(self,a,entry_price,size_usd,opened_at):
        if entry_price<=0: raise ValueError('entry_price must be > 0')
        with self.connect() as c:
            cur=c.execute('INSERT INTO trades(token_address,opened_at,entry_price,initial_size_usd) VALUES(?,?,?,?)',(a,_to_iso(opened_at),entry_price,size_usd)); tid=int(cur.lastrowid)
            c.execute('UPDATE tokens SET was_traded=1, trade_count=trade_count+1 WHERE token_address=?',(a,)); c.execute('INSERT INTO trade_events(trade_id,event_at,event_type,price_usd,qty_pct,note) VALUES(?,?,"OPEN",?,100,?)',(tid,_to_iso(opened_at),entry_price,f'paper buy ${size_usd:.2f}')); return tid
    def get_open_trades(self):
        with self.connect() as c: return list(c.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY opened_at ASC").fetchall())
    def add_trade_event(self,tid,event_type,event_at,price_usd,qty_pct,pnl_usd,note=''):
        with self.connect() as c: c.execute('INSERT INTO trade_events(trade_id,event_at,event_type,price_usd,qty_pct,pnl_usd,note) VALUES(?,?,?,?,?,?,?)',(tid,_to_iso(event_at),event_type,price_usd,qty_pct,pnl_usd,note))
    def update_trade(self,tid,remaining_pct,realized_pnl_usd,status='OPEN',closed_at=None,exit_reason=None,avg_exit_price=None):
        with self.connect() as c: c.execute('UPDATE trades SET remaining_pct=?, realized_pnl_usd=?, status=?, closed_at=COALESCE(?,closed_at), exit_reason=COALESCE(?,exit_reason), avg_exit_price=COALESCE(?,avg_exit_price) WHERE id=?',(remaining_pct,realized_pnl_usd,status,_to_iso(closed_at),exit_reason,avg_exit_price,tid))
    def summary(self):
        with self.connect() as c:
            r=c.execute('SELECT COUNT(*) n, COALESCE(SUM(realized_pnl_usd),0) pnl FROM trades').fetchone(); o=c.execute("SELECT COUNT(*) n FROM trades WHERE status='OPEN'").fetchone(); return {'trades':r['n'],'realized_pnl_usd':r['pnl'],'open_trades':o['n']}
    def add_smart_wallet(self,w,label=None,source='manual',status='active'):
        now=_to_iso(datetime.now(timezone.utc))
        with self.connect() as c: c.execute('INSERT INTO smart_wallets(wallet_address,label,source,status,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(wallet_address) DO UPDATE SET label=COALESCE(excluded.label,label), status=excluded.status, updated_at=excluded.updated_at',(w,label,source,status,now,now))
    def list_active_smart_wallets(self):
        with self.connect() as c: return list(c.execute("SELECT * FROM smart_wallets WHERE status='active' ORDER BY score DESC, updated_at DESC").fetchall())
    def upsert_smart_wallet(self,score):
        now=_to_iso(datetime.now(timezone.utc))
        with self.connect() as c: c.execute('''INSERT INTO smart_wallets(wallet_address,score,copyability_score,insider_score,win_rate,realized_pnl_usd,trade_count,tier,status,created_at,updated_at,reasons) VALUES(?,?,?,?,?,?,?,?, 'active',?,?,?) ON CONFLICT(wallet_address) DO UPDATE SET score=excluded.score,copyability_score=excluded.copyability_score,insider_score=excluded.insider_score,win_rate=excluded.win_rate,realized_pnl_usd=excluded.realized_pnl_usd,trade_count=excluded.trade_count,tier=excluded.tier,updated_at=excluded.updated_at,reasons=excluded.reasons''',(score.wallet_address,score.score,score.copyability_score,score.insider_score,score.win_rate,score.realized_pnl_usd,score.trade_count,score.tier.value,now,now,json.dumps(score.reasons)))
    def wallet_trade_exists(self,sig,w,tok,side):
        with self.connect() as c: return c.execute('SELECT 1 FROM wallet_trades WHERE tx_signature=? AND wallet_address=? AND token_address=? AND side=?',(sig,w,tok,side)).fetchone() is not None
    def upsert_wallet_trade(self,swap):
        with self.connect() as c: c.execute('INSERT OR IGNORE INTO wallet_trades(wallet_address,token_address,side,tx_signature,price_usd,amount_usd,token_amount,timestamp,dex,source) VALUES(?,?,?,?,?,?,?,?,?,?)',(swap.wallet_address,swap.token_address,swap.side,swap.signature,swap.price_usd,swap.amount_usd,swap.token_amount,_to_iso(swap.timestamp),swap.dex,swap.source))
    def add_copy_signal(self,swap,score,token_risk_score,decision,reason,paper_trade_id=None):
        with self.connect() as c: c.execute('INSERT INTO copy_signals(wallet_address,token_address,signal_time,tx_signature,wallet_score,copyability_score,token_risk_score,decision,reason,paper_trade_id) VALUES(?,?,?,?,?,?,?,?,?,?)',(swap.wallet_address,swap.token_address,_to_iso(swap.timestamp),swap.signature,score.score,score.copyability_score,token_risk_score,decision,reason,paper_trade_id))
