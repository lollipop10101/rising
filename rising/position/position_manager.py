from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from rising.storage.database import Database
@dataclass(slots=True)
class ExitConfig:
    stop_loss_pct:float; tp1_pct:float; tp1_sell_pct:float; tp2_pct:float; tp2_sell_pct:float; max_hold_minutes:float; exit_fee_pct:float=0.0
class PositionManager:
    def __init__(self,db:Database,config:ExitConfig,price_client=None,min_liquidity_usd:float=5000): self.db=db; self.config=config; self.price_client=price_client; self.min_liquidity_usd=min_liquidity_usd
    async def evaluate_trade(self,trade,current_price:float,now:datetime)->str|None:
        entry=float(trade['entry_price']); rem=float(trade['remaining_pct']); real=float(trade['realized_pnl_usd']); size=float(trade['initial_size_usd']); tid=int(trade['id']); opened=datetime.fromisoformat(trade['opened_at'])
        net=current_price*(1-self.config.exit_fee_pct/100); pnl_pct=((net/entry)-1)*100; age=(now-opened).total_seconds()/60
        if pnl_pct>=self.config.tp1_pct and rem>(100-self.config.tp1_sell_pct):
            qty=min(self.config.tp1_sell_pct,rem); pnl=self._pnl(size,qty,pnl_pct); self.db.add_trade_event(tid,'TP1',now,net,qty,pnl,'partial exit'); self.db.update_trade(tid,rem-qty,real+pnl); return 'TP1'
        if pnl_pct>=self.config.tp2_pct and rem>(100-self.config.tp1_sell_pct-self.config.tp2_sell_pct):
            qty=min(self.config.tp2_sell_pct,rem); pnl=self._pnl(size,qty,pnl_pct); new=rem-qty; self.db.add_trade_event(tid,'TP2',now,net,qty,pnl,'partial exit'); self.db.update_trade(tid,new,real+pnl,'MOONBAG' if new>0 else 'CLOSED',None if new>0 else now,'TP2' if new==0 else None,net); return 'TP2'
        # Trailing stop: if peak > +15%, raise SL to -10%
        peak=float(trade.get('peak_price') or entry)
        if net>peak: peak=net
        trailing_sl_pct=self.config.stop_loss_pct
        if (peak/entry-1)*100>=15: trailing_sl_pct=max(trailing_sl_pct,-10)
        if pnl_pct<=trailing_sl_pct:
            pnl=self._pnl(size,rem,pnl_pct); self.db.add_trade_event(tid,'STOP_LOSS',now,net,rem,pnl,'full exit'); self.db.update_trade(tid,0,real+pnl,'CLOSED',now,'STOP_LOSS',net); return 'STOP_LOSS'
        if age>=self.config.max_hold_minutes:
            pnl=self._pnl(size,rem,pnl_pct); self.db.add_trade_event(tid,'TIME_EXIT',now,net,rem,pnl,'full exit'); self.db.update_trade(tid,0,real+pnl,'CLOSED',now,'TIME_EXIT',net); return 'TIME_EXIT'
        return None
    @staticmethod
    def _pnl(size,qty_pct,pnl_pct): return size*(qty_pct/100)*(pnl_pct/100)
