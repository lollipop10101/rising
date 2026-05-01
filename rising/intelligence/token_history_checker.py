from __future__ import annotations
from datetime import datetime
from rising.models import SignalType
from rising.storage.database import Database
class TokenHistoryChecker:
    def __init__(self, db:Database, recent_repeat_minutes:int=10, old_address_minutes:int=60): self.db=db; self.recent_repeat_minutes=recent_repeat_minutes; self.old_address_minutes=old_address_minutes
    def classify(self, token_address:str, message_time:datetime)->SignalType:
        t=self.db.get_token(token_address)
        if t is None: return SignalType.NEW_TOKEN
        first=datetime.fromisoformat(t['first_seen_at']); age=(message_time-first).total_seconds()/60
        if int(t['was_traded'])==1: return SignalType.ALREADY_TRADED
        if age<=self.recent_repeat_minutes: return SignalType.RECENT_REPEAT
        if age>=self.old_address_minutes: return SignalType.OLD_TRACKING
        return SignalType.RECHECK_CAUTION
