from __future__ import annotations

from collections import defaultdict

from rising.smart_wallets.models import WalletScore, WalletTier, WalletSwap


class WalletScorer:
    """Scores whether a wallet is useful to copy, not just profitable.

    This is intentionally conservative. It penalizes likely insiders/devs and wallets
    with too few trades or one lucky winner.
    """

    def score(self, wallet_address: str, swaps: list[WalletSwap]) -> WalletScore:
        trades_by_token: dict[str, list[WalletSwap]] = defaultdict(list)
        for swap in swaps:
            trades_by_token[swap.token_address].append(swap)

        realized_pnl = 0.0
        wins = 0
        completed = 0
        buy_count = 0
        sell_count = 0
        fast_flip_count = 0
        tiny_history_penalty = 0
        reasons: list[str] = []

        for token, events in trades_by_token.items():
            buys = [e for e in events if e.side == "BUY"]
            sells = [e for e in events if e.side == "SELL"]
            buy_count += len(buys)
            sell_count += len(sells)
            if buys and sells:
                buy_usd = sum(e.amount_usd or 0 for e in buys)
                sell_usd = sum(e.amount_usd or 0 for e in sells)
                pnl = sell_usd - buy_usd
                realized_pnl += pnl
                completed += 1
                if pnl > 0:
                    wins += 1
                hold_seconds = (max(s.timestamp for s in sells) - min(b.timestamp for b in buys)).total_seconds()
                if 0 <= hold_seconds < 30:
                    fast_flip_count += 1

        if buy_count < 5:
            tiny_history_penalty = 20
            reasons.append("too few observed buys")

        win_rate = wins / completed if completed else 0.0
        profit_score = clamp(int(realized_pnl / 50), -20, 35)
        win_score = int(win_rate * 25)
        consistency_score = clamp(completed * 3, 0, 20)
        copyability_score = 60

        insider_score = 0
        if buy_count and sell_count == 0:
            insider_score += 15
            reasons.append("only buys observed; exits unknown")
        if fast_flip_count >= 3:
            insider_score += 30
            copyability_score -= 25
            reasons.append("many sub-30s flips; difficult to copy")
        if completed <= 1 and realized_pnl > 1000:
            insider_score += 25
            reasons.append("profit concentrated in one token")

        copyability_score = clamp(copyability_score + consistency_score - insider_score - tiny_history_penalty, 0, 100)
        raw = 35 + profit_score + win_score + consistency_score - insider_score - tiny_history_penalty
        score = clamp(raw, 0, 100)

        if insider_score >= 45:
            tier = WalletTier.C
        elif score >= 75 and copyability_score >= 65:
            tier = WalletTier.A
        elif score >= 55:
            tier = WalletTier.B
        else:
            tier = WalletTier.D

        if realized_pnl > 0:
            reasons.append(f"observed realized pnl ${realized_pnl:.2f}")
        if completed:
            reasons.append(f"win rate {win_rate:.0%} across {completed} completed tokens")

        return WalletScore(
            wallet_address=wallet_address,
            score=score,
            copyability_score=copyability_score,
            insider_score=insider_score,
            win_rate=win_rate,
            realized_pnl_usd=realized_pnl,
            trade_count=len(swaps),
            tier=tier,
            reasons=reasons,
        )


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
