from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SignalType(str, Enum):
    NEW_TOKEN = "NEW_TOKEN"
    ALREADY_TRADED = "ALREADY_TRADED"
    RECENT_REPEAT = "RECENT_REPEAT"
    OLD_TRACKING = "OLD_TRACKING"
    RECHECK_CAUTION = "RECHECK_CAUTION"


class TradeDecision(str, Enum):
    BUY = "BUY"
    TRACK_ONLY = "TRACK_ONLY"
    SKIP = "SKIP"


@dataclass
class MarketSnapshot:
    token_address: str
    dex_url: str | None
    pair_address: str | None
    base_symbol: str | None
    price_usd: float | None
    liquidity_usd: float | None
    volume_5m_usd: float | None
    price_change_5m_pct: float | None
    fetched_at: datetime


@dataclass
class RiskResult:
    score: int
    blocked: bool
    reasons: list[str]


@dataclass
class DecisionResult:
    action: TradeDecision
    reasons: list[str]
    paper_trade_amount: float  # 0 if SKIP or TRACK_ONLY
