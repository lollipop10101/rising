from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

def utc_now() -> datetime:
    return datetime.now(timezone.utc)
class SignalType(StrEnum):
    NEW_TOKEN='NEW_TOKEN'; RECENT_REPEAT='RECENT_REPEAT'; ALREADY_TRADED='ALREADY_TRADED'; OLD_TRACKING='OLD_TRACKING'; RECHECK_CAUTION='RECHECK_CAUTION'
class TradeDecision(StrEnum):
    BUY='BUY'; SKIP='SKIP'; TRACK_ONLY='TRACK_ONLY'
@dataclass(slots=True)
class MarketSnapshot:
    token_address:str; dex_url:str|None; pair_address:str|None; base_symbol:str|None; price_usd:float|None; liquidity_usd:float|None; volume_5m_usd:float|None; price_change_5m_pct:float|None; fetched_at:datetime
@dataclass(slots=True)
class RiskResult:
    score:int; blocked:bool; reasons:list[str]
@dataclass(slots=True)
class DecisionResult:
    decision:TradeDecision; reasons:list[str]; position_size_usd:float
