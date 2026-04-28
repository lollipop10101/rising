from __future__ import annotations
from datetime import datetime
from rising.models import SignalType


class TokenHistoryChecker:
    def __init__(
        self,
        db,  # RisingDB or compatible
        recent_repeat_minutes: int = 10,
        old_address_minutes: int = 60,
    ) -> None:
        self.db = db
        self.recent_repeat_minutes = recent_repeat_minutes
        self.old_address_minutes = old_address_minutes

    def classify(self, token_address: str, message_time: datetime) -> SignalType:
        token = self.db.get_token(token_address)
        if token is None:
            return SignalType.NEW_TOKEN

        first_seen = datetime.fromisoformat(token["first_seen_at"])
        age_minutes = (message_time - first_seen).total_seconds() / 60.0

        if int(token.get("was_traded", 0)) == 1:
            return SignalType.ALREADY_TRADED
        if age_minutes <= self.recent_repeat_minutes:
            return SignalType.RECENT_REPEAT
        if age_minutes >= self.old_address_minutes:
            return SignalType.OLD_TRACKING
        return SignalType.RECHECK_CAUTION
