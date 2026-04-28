from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional

class SignalType(str, Enum):
    NEW_TOKEN = "NEW_TOKEN"
    RECENT_REPEAT = "RECENT_REPEAT"
    ALREADY_TRADED = "ALREADY_TRADED"
    OLD_TRACKING = "OLD_TRACKING"
    RECHECK_CAREFUL = "RECHECK_CAREFUL"

class TokenHistoryChecker:
    def __init__(self, recent_repeat_minutes: int = 10, old_tracking_minutes: int = 60):
        self.recent_repeat_minutes = recent_repeat_minutes
        self.old_tracking_minutes = old_tracking_minutes

    def classify(self, token: Optional[Dict[str, Any]], message_time: datetime | None = None) -> SignalType:
        if token is None:
            return SignalType.NEW_TOKEN
        if int(token.get("was_traded") or 0) == 1:
            return SignalType.ALREADY_TRADED
        message_time = message_time or datetime.now(timezone.utc)
        first_seen = datetime.fromisoformat(token["first_seen_at"])
        age_minutes = (message_time - first_seen).total_seconds() / 60
        if age_minutes < self.recent_repeat_minutes:
            return SignalType.RECENT_REPEAT
        if age_minutes > self.old_tracking_minutes:
            return SignalType.OLD_TRACKING
        return SignalType.RECHECK_CAREFUL
