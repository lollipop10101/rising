from __future__ import annotations
import asyncio, os, sys
from rising.app import AppConfig,RisingApp
from rising.settings import load_yaml_config,env_or_cfg,to_float,to_int
from rising.smart_wallets.helius_client import HeliusEnhancedClient
from rising.smart_wallets.wallet_analyzer import WalletAnalyzer
from rising.smart_wallets.copy_signal import CopySignalEngine
from rising.smart_wallets.wallet_tracker import SmartWalletTracker

def build_config():
    c=load_yaml_config()
    return AppConfig(api_id=to_int(os.getenv('TELEGRAM_API_ID'),0),api_hash=os.getenv('TELEGRAM_API_HASH',''),telegram_session=os.getenv('TELEGRAM_SESSION','rising_session'),telegram_source_chat=os.getenv('TELEGRAM_SOURCE_CHAT',''),bot_token=os.getenv('TELEGRAM_BOT_TOKEN',''),report_chat_id=os.getenv('TELEGRAM_REPORT_CHAT_ID',''),database_url=os.getenv('DATABASE_URL','sqlite:///data/rising.db'),quote_usd=to_float(env_or_cfg('QUOTE_USD',c,'trading.paper_trade_usd',15),15),max_open_positions=to_int(env_or_cfg('MAX_OPEN_POSITIONS',c,'trading.max_open_positions',3),3),min_liquidity_usd=to_float(env_or_cfg('MIN_LIQUIDITY_USD',c,'risk.min_liquidity_usd',5000),5000),min_volume_5m_usd=to_float(env_or_cfg('MIN_VOLUME_5M_USD',c,'risk.min_volume_5m_usd',500),500),max_pump_5m_pct=to_float(env_or_cfg('MAX_PUMP_5M_PCT',c,'risk.max_pump_5m_pct',200),200),max_risk_score=to_int(env_or_cfg('MAX_RISK_SCORE',c,'risk.max_risk_score',70),70),stop_loss_pct=to_float(env_or_cfg('STOP_LOSS_PCT',c,'exit.stop_loss_pct',-30),-30),tp1_pct=to_float(env_or_cfg('TP1_PCT',c,'exit.tp1_pct',25),25),tp1_sell_pct=to_float(env_or_cfg('TP1_SELL_PCT',c,'exit.tp1_sell_pct',50),50),tp2_pct=to_float(env_or_cfg('TP2_PCT',c,'exit.tp2_pct',75),75),tp2_sell_pct=to_float(env_or_cfg('TP2_SELL_PCT',c,'exit.tp2_sell_pct',30),30),max_hold_minutes=to_float(env_or_cfg('MAX_HOLD_MINUTES',c,'exit.max_hold_minutes',20),20),entry_slippage_pct=to_float(os.getenv('ENTRY_SLIPPAGE_PCT','0'),0),exit_fee_pct=to_float(os.getenv('EXIT_FEE_PCT','0'),0),poll_seconds=to_int(env_or_cfg('POLL_SECONDS',c,'exit.poll_seconds',30),30))

def check(app):
    for n,o in [('Database',app.db),('DexScreenerClient',app.price),('TokenHistoryChecker',app.history),('RiskEngine',app.risk),('StrategyEngine',app.strategy),('PaperTrader',app.paper),('PositionManager',app.positions),('Notifier',app.notifier)]:
        print(f'✓ {n}: {o.__class__.__name__}')
    print('All local wiring checks passed ✅')
    return 0

async def run_wallets(app, once):
    h=HeliusEnhancedClient(os.getenv('HELIUS_API_KEY',''))
    a=WalletAnalyzer(app.db,h)
    ce=CopySignalEngine(app.db,app.price,app.risk,app.strategy,app.paper)
    tr=SmartWalletTracker(app.db,h,a,ce,app.notifier)
    await (tr.scan_once() if once else tr.run_forever())

async def analyze_wallet(app,w):
    s=await WalletAnalyzer(app.db,HeliusEnhancedClient(os.getenv('HELIUS_API_KEY',''))).analyze_wallet(w)
    print(f'{w}\nscore={s.score} copyability={s.copyability_score} insider={s.insider_score} tier={s.tier.value}')

def main():
    app=RisingApp(build_config())
    cmd=sys.argv[1] if len(sys.argv)>1 else 'check'
    if cmd=='check': return check(app)
    if cmd=='summary': print(app.build_report()); return 0
    if cmd=='telegram': asyncio.run(app.run_telegram()); return 0
    if cmd=='monitor-once': asyncio.run(app.monitor_once()); return 0
    if cmd=='add-wallet':
        if len(sys.argv)<3:
            print('Usage: python -m rising.main add-wallet WALLET --label LABEL'); return 1
        label=''
        if '--label' in sys.argv and sys.argv.index('--label')+1<len(sys.argv): label=sys.argv[sys.argv.index('--label')+1]
        app.db.add_smart_wallet(sys.argv[2],label or None)
        print(f'Added smart wallet: {sys.argv[2]}')
        return 0
    if cmd=='analyze-wallet':
        if len(sys.argv)<3:
            print('Usage: python -m rising.main analyze-wallet WALLET'); return 1
        asyncio.run(analyze_wallet(app,sys.argv[2])); return 0
    if cmd=='wallets': asyncio.run(run_wallets(app,'--once' in sys.argv)); return 0
    print('Usage: python -m rising.main [check|summary|telegram|monitor-once|add-wallet|analyze-wallet|wallets]')
    return 1

if __name__=='__main__':
    raise SystemExit(main())
