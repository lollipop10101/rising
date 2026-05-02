from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from rising.data.price_fetcher import DexScreenerClient
from rising.execution.paper_trader import PaperTrader
from rising.ingestion.telegram_listener import TelegramSignalListener
from rising.intelligence.token_history_checker import TokenHistoryChecker
from rising.models import TradeDecision
from rising.monitoring.notifier import TelegramNotifier
from rising.parsing.address_extractor import extract_solana_addresses
from rising.position.position_manager import ExitConfig, PositionManager
from rising.risk.risk_engine import RiskEngine
from rising.storage.database import Database
from rising.strategy.trade_decision import StrategyEngine

@dataclass
class AppConfig:
    api_id:int=0; api_hash:str=''; telegram_session:str='rising_session'; telegram_source_chat:str=''; bot_token:str=''; report_chat_id:str=''; database_url:str='sqlite:///data/rising.db'; quote_usd:float=15; max_open_positions:int=3; min_liquidity_usd:float=5000; min_volume_5m_usd:float=500; max_pump_5m_pct:float=200; max_risk_score:int=70; stop_loss_pct:float=-30; tp1_pct:float=25; tp1_sell_pct:float=50; tp2_pct:float=75; tp2_sell_pct:float=30; max_hold_minutes:float=20; entry_slippage_pct:float=0; exit_fee_pct:float=0; poll_seconds:int=30; recent_repeat_minutes:int=10; old_address_minutes:int=60; 

class RisingApp:
    def __init__(self, cfg: AppConfig):
        self.cfg=cfg
        self.db=Database(cfg.database_url)
        self.price=DexScreenerClient()
        self.history=TokenHistoryChecker(self.db,self.cfg.recent_repeat_minutes,self.cfg.old_address_minutes)
        self.risk=RiskEngine(cfg.min_liquidity_usd,cfg.min_volume_5m_usd,cfg.max_pump_5m_pct)
        self.strategy=StrategyEngine(cfg.quote_usd,cfg.max_risk_score)
        self.paper=PaperTrader(self.db,cfg.entry_slippage_pct)
        self.positions=PositionManager(self.db,ExitConfig(cfg.stop_loss_pct,cfg.tp1_pct,cfg.tp1_sell_pct,cfg.tp2_pct,cfg.tp2_sell_pct,cfg.max_hold_minutes,cfg.exit_fee_pct),self.price,cfg.min_liquidity_usd)
        self.notifier=TelegramNotifier(cfg.bot_token,cfg.report_chat_id)
    async def handle_message(self, text, chat):
        for address in extract_solana_addresses(text):
            now=datetime.now(timezone.utc)
            signal=self.history.classify(address,now)
            snap=await self.price.fetch_token(address)
            self.db.upsert_token_seen(address,now,snap.price_usd if snap else None,snap.liquidity_usd if snap else None)
            self.db.add_signal(address,text,chat,now,signal.value)
            risk=self.risk.score(snap)
            dec=self.strategy.decide(signal,risk,len(self.db.get_open_trades()),self.cfg.max_open_positions)
            print(f'{address[:12]}.. signal={signal.value} risk={risk.score} decision={dec.decision.value}')
            if dec.decision==TradeDecision.BUY and snap and snap.price_usd:
                tid=self.paper.buy(address,snap.price_usd,dec.position_size_usd,now)
                await self.notifier.send(f'🟢 Rising PAPER BUY\nToken: {address}\nTrade ID: {tid}\nPrice: ${snap.price_usd}')
    async def monitor_once(self):
        now=datetime.now(timezone.utc)
        for t in self.db.get_open_trades():
            snap=await self.price.fetch_token(t['token_address'])
            if snap and snap.price_usd:
                ev=await self.positions.evaluate_trade(t,snap.price_usd,now)
                if ev:
                    await self.notifier.send(f'📍 Rising exit: {ev}\nToken: {t["token_address"]}\nPrice: ${snap.price_usd}')
    async def run_telegram(self):
        if not self.cfg.api_id or not self.cfg.api_hash or not self.cfg.telegram_source_chat:
            raise RuntimeError('TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_SOURCE_CHAT are required')
        from datetime import datetime, timezone
        import asyncio
        listener = TelegramSignalListener(self.cfg.api_id,self.cfg.api_hash,self.cfg.telegram_session,self.cfg.telegram_source_chat)
        listener_task = asyncio.create_task(listener.run(self.handle_message))
        last_report_at = datetime.now(timezone.utc).timestamp()
        REPORT_EVERY_SECONDS = int(self.cfg.poll_seconds * 60 * 4)  # 4 hours default
        while True:
            await asyncio.sleep(self.cfg.poll_seconds)
            await self.monitor_once()
            now_ts = datetime.now(timezone.utc).timestamp()
            if now_ts - last_report_at >= REPORT_EVERY_SECONDS:
                report = self.build_report()
                await self.notifier.send(report)
                last_report_at = now_ts
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass
    def build_report(self):
        from datetime import datetime, timezone
        with self.db.connect() as c:
            c.row_factory=sqlite3.Row
            closed=c.execute("SELECT * FROM trades WHERE status='CLOSED' ORDER BY opened_at ASC").fetchall()
            all_trades=c.execute("SELECT * FROM trades ORDER BY opened_at DESC").fetchall()
        wins=sorted([t for t in closed if (t['realized_pnl_usd'] or 0)>0],key=lambda x:x['opened_at'], reverse=True)
        losses=sorted([t for t in closed if (t['realized_pnl_usd'] or 0)<=0],key=lambda x:x['opened_at'], reverse=True)
        total=sum((t['realized_pnl_usd'] or 0) for t in closed)
        closed_n=len(closed)
        win_n=len(wins)
        loss_n=len(losses)
        open_n=len([t for t in all_trades if t['status']=='OPEN'])
        avg_win=sum((t['realized_pnl_usd'] or 0) for t in wins)/win_n if win_n>0 else 0
        avg_loss=sum((t['realized_pnl_usd'] or 0) for t in losses)/loss_n if loss_n>0 else 0
        lines=['🧊 Rising Report','━━━━━━━━━━━━━━━━',f'PnL: ${total:.2f} | Open: {open_n} | Closed: {closed_n}',f'Win: {win_n} | Loss: {loss_n}']
        if closed_n>0:
            lines.append(f"Win rate: {win_n*100/closed_n:.0f}% | Avg win: +${avg_win:.2f} | Avg loss: ${avg_loss:.2f}")
        lines.append('━━━━━━━━━━━━━━━━')
        if wins:
            lines.append(f'✅ WINNERS ({win_n})')
            for t in wins[:10]:
                ts=datetime.fromisoformat(t['opened_at'].replace('Z','+00:00')).strftime('%m/%d %H:%M')
                lines.append(f"  +${(t['realized_pnl_usd'] or 0):.2f} | {ts} | {t['token_address'][:10]}.. | {t['exit_reason'] or '—'}")
        if losses:
            lines.append(f'❌ LOSERS ({loss_n})')
            for t in losses[:10]:
                ts=datetime.fromisoformat(t['opened_at'].replace('Z','+00:00')).strftime('%m/%d %H:%M')
                lines.append(f"  ${(t['realized_pnl_usd'] or 0):.2f} | {ts} | {t['token_address'][:10]}.. | {t['exit_reason'] or '—'}")
        open_trades=[t for t in all_trades if t['status']=='OPEN']
        if open_trades:
            lines.append(f'🟢 OPEN ({len(open_trades)})')
            for t in sorted(open_trades,key=lambda x:x['opened_at'], reverse=True)[:5]:
                ts=datetime.fromisoformat(t['opened_at'].replace('Z','+00:00')).strftime('%m/%d %H:%M')
                lines.append(f"  {t['token_address'][:10]}.. | entry ${t['entry_price']} | {ts}")
        return '\n'.join(lines)
