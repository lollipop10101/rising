from __future__ import annotations

from rising.smart_wallets.models import WalletSwap


class InsiderFilter:
    """Heuristic checks to avoid dev/insider wallets.

    v0.3 does not claim to prove insider status. It only blocks obvious patterns
    that are bad for copy trading.
    """

    def evaluate(self, swaps: list[WalletSwap]) -> tuple[int, list[str]]:
        reasons: list[str] = []
        penalty = 0
        buys = [s for s in swaps if s.side == "BUY"]
        sells = [s for s in swaps if s.side == "SELL"]

        if sells and not buys:
            penalty += 60
            reasons.append("wallet mostly sells without observed public buys")

        zero_amount_buys = [s for s in buys if not s.amount_usd or s.amount_usd <= 0]
        if len(zero_amount_buys) >= 3:
            penalty += 25
            reasons.append("many buys have missing/zero cost; possible transfers/private allocation")

        unique_tokens = len({s.token_address for s in swaps})
        if unique_tokens <= 1 and len(swaps) > 5:
            penalty += 20
            reasons.append("activity concentrated in one token")

        return min(100, penalty), reasons
