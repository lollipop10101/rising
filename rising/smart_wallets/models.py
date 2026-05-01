from __future__ import annotations
from dataclasses import dataclass,field
from datetime import datetime
from enum import StrEnum
class WalletTier(StrEnum): A='A_TIER_SMART_TRADER'; B='B_TIER_MOMENTUM_TRADER'; C='C_TIER_INSIDER_SUSPECT'; D='D_TIER_NOISE'
class CopyDecision(StrEnum): PAPER_BUY='PAPER_BUY'; ALERT_ONLY='ALERT_ONLY'; SKIP='SKIP'
@dataclass(slots=True)
class WalletSwap: wallet_address:str; token_address:str; side:str; signature:str; timestamp:datetime; token_amount:float|None=None; amount_usd:float|None=None; price_usd:float|None=None; dex:str|None=None; source:str|None=None; raw:dict|None=field(default=None,repr=False)
@dataclass(slots=True)
class WalletScore: wallet_address:str; score:int; copyability_score:int; insider_score:int; win_rate:float; realized_pnl_usd:float; trade_count:int; tier:WalletTier; reasons:list[str]
@dataclass(slots=True)
class CopySignalResult: decision:CopyDecision; reasons:list[str]; wallet_score:WalletScore|None=None; trade_id:int|None=None
