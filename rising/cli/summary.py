from __future__ import annotations

import asyncio

from rising.settings import EnvSettings
from rising.storage.database import Database
from rising.data.price_fetcher import DexScreenerClient


MIN_LIQUIDITY = 5000


async def _run() -> None:
    env = EnvSettings()
    db = Database(env.database_url)
    price_client = DexScreenerClient()

    summary = db.summary()
    print(f"=== Rising Summary ===")
    print(f"Total trades : {summary['trades']}")
    print(f"Open trades  : {summary['open_trades']}")
    print(f"Realized PnL : ${summary['realized_pnl_usd']:.4f}")

    open_trades = db.get_open_trades()
    if open_trades:
        print("\n--- Open Positions ---")
        for t in open_trades:
            snapshot = await price_client.fetch_token(t["token_address"])
            liq = snapshot.liquidity_usd if snapshot else None
            flag = " ⚠️ ILLIQUID" if liq and liq < MIN_LIQUIDITY else ""
            print(f"  #{t['id']} {t['token_address'][:10]}.. entry: ${t['entry_price']} liq: ${liq:,.0f}{flag}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
