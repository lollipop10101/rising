from __future__ import annotations

from datetime import timezone

from loguru import logger

from rising.data.price_fetcher import DexScreenerClient
from rising.execution.paper_trader import PaperTrader
from rising.intelligence.token_history_checker import TokenHistoryChecker
from rising.models import TradeDecision, utc_now
from rising.monitoring.notifier import TelegramNotifier
from rising.parsing.address_extractor import extract_solana_addresses
from rising.position.position_manager import ExitConfig, PositionManager
from rising.risk.risk_engine import RiskEngine
from rising.settings import EnvSettings, load_yaml_config, nested_get
from rising.storage.database import Database
from rising.strategy.trade_decision import StrategyEngine


class RisingApp:
    def __init__(self, env: EnvSettings, config_path: str = "config.yaml") -> None:
        self.env = env
        self.config = load_yaml_config(config_path)
        self.db = Database(env.database_url)
        self.price = DexScreenerClient()
        self.history = TokenHistoryChecker(
            self.db,
            recent_repeat_minutes=int(nested_get(self.config, "history.recent_repeat_minutes", 10)),
            old_address_minutes=int(nested_get(self.config, "history.old_address_minutes", 60)),
        )
        self.risk = RiskEngine(
            min_liquidity_usd=float(nested_get(self.config, "risk.min_liquidity_usd", 5000)),
            min_volume_5m_usd=float(nested_get(self.config, "risk.min_volume_5m_usd", 1000)),
            max_pump_5m_pct=float(nested_get(self.config, "risk.max_pump_5m_pct", 200)),
        )
        self.strategy = StrategyEngine(
            allocation_pct=float(nested_get(self.config, "trading.allocation_pct", 0.1)),
            max_risk_score=int(nested_get(self.config, "risk.max_risk_score", 70)),
        )
        self.paper = PaperTrader(
            self.db,
            default_balance=float(nested_get(self.config, "trading.paper_balance", 100)),
            balance_floor=float(nested_get(self.config, "trading.paper_balance_floor", 50)),
        )
        self.positions = PositionManager(
            self.db,
            ExitConfig(
                stop_loss_pct=float(nested_get(self.config, "exit.stop_loss_pct", -30)),
                tp1_pct=float(nested_get(self.config, "exit.tp1_pct", 25)),
                tp1_sell_pct=float(nested_get(self.config, "exit.tp1_sell_pct", 50)),
                tp2_pct=float(nested_get(self.config, "exit.tp2_pct", 75)),
                tp2_sell_pct=float(nested_get(self.config, "exit.tp2_sell_pct", 30)),
                max_hold_minutes=float(nested_get(self.config, "exit.max_hold_minutes", 20)),
            ),
            self.price,
            self.paper,
            min_liquidity_usd=float(nested_get(self.config, "risk.min_liquidity_usd", 5000)),
        )
        self.notifier = TelegramNotifier(env.telegram_bot_token, env.telegram_report_chat_id)

    async def process_message(self, message: str, source_chat: str | None = None) -> None:
        addresses = extract_solana_addresses(message)
        if not addresses:
            return

        for address in addresses:
            await self.process_token(address, message, source_chat)

    async def process_token(self, token_address: str, message: str, source_chat: str | None = None) -> None:
        now = utc_now()
        signal_type = self.history.classify(token_address, now)
        snapshot = await self.price.fetch_token(token_address)
        self.db.upsert_token_seen(token_address, now, snapshot.price_usd, snapshot.liquidity_usd)
        self.db.add_signal(token_address, message, source_chat, now, signal_type.value)

        risk = self.risk.score(snapshot)
        open_positions = len(self.db.get_open_trades())
        max_open = int(nested_get(self.config, "trading.max_open_positions", 3))
        decision = self.strategy.decide(signal_type, risk, open_positions, max_open, self.paper.get_balance())

        logger.info("{} signal={} risk={} decision={} reasons={}", token_address, signal_type, risk.score, decision.decision, decision.reasons)

        if decision.decision == TradeDecision.BUY and snapshot.price_usd:
            trade_id = self.paper.buy(token_address, snapshot.price_usd, decision.position_size_usd, now)
            await self.notifier.send(
                f"🟢 Rising paper BUY\nToken: {token_address}\nPrice: ${snapshot.price_usd}\nSize: ${decision.position_size_usd}\nRisk: {risk.score}\nTrade ID: {trade_id}"
            )
        else:
            await self.notifier.send(
                f"⚪ Rising skip/track\nToken: {token_address}\nSignal: {signal_type.value}\nDecision: {decision.decision.value}\nRisk: {risk.score}\nReasons: {', '.join(decision.reasons[:3])}"
            )

    async def monitor_once(self) -> None:
        for trade in self.db.get_open_trades():
            snapshot = await self.price.fetch_token(trade["token_address"])
            if not snapshot.price_usd:
                continue
            event = await self.positions.evaluate_trade(trade, snapshot.price_usd, utc_now())
            if event:
                await self.notifier.send(f"📍 Rising exit event: {event}\nToken: {trade['token_address']}\nPrice: ${snapshot.price_usd}")

# Smart wallet helpers are attached to RisingApp without changing the Telegram path.
from rising.smart_wallets.helius_client import HeliusEnhancedClient  # noqa: E402
from rising.smart_wallets.wallet_analyzer import WalletAnalyzer  # noqa: E402
from rising.smart_wallets.copy_signal import CopySignalEngine  # noqa: E402
from rising.smart_wallets.wallet_tracker import SmartWalletTracker  # noqa: E402


def build_smart_wallet_tracker(app: RisingApp) -> SmartWalletTracker:
    helius = HeliusEnhancedClient(app.env.helius_api_key)
    analyzer = WalletAnalyzer(app.db, helius)
    copy_engine = CopySignalEngine(
        db=app.db,
        price_client=app.price,
        risk_engine=app.risk,
        strategy=app.strategy,
        paper=app.paper,
        min_wallet_score=int(nested_get(app.config, "smart_wallets.min_wallet_score", 70)),
        min_copyability_score=int(nested_get(app.config, "smart_wallets.min_copyability_score", 60)),
        alert_only_for_single_wallet=bool(nested_get(app.config, "smart_wallets.alert_only_for_single_wallet", True)),
    )
    return SmartWalletTracker(
        db=app.db,
        helius=helius,
        analyzer=analyzer,
        copy_engine=copy_engine,
        notifier=app.notifier,
        poll_seconds=int(nested_get(app.config, "smart_wallets.poll_seconds", 20)),
    )
