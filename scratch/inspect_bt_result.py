"""Quick diagnostic to inspect BacktestResult trade structure."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.strategy.smc_confluence import run_confluence_backtest, SMCConfluenceStrategy, SMCConfluenceConfig
from src.backtesting.engine import BacktestConfig
from src.smc.engine import analyze_smc, SMCConfig
import pandas as pd

m15 = pd.read_csv(ROOT / "data/processed/XAUUSD_M15_clean.csv")
m15["time"] = pd.to_datetime(m15["time"], utc=True)
h4 = pd.read_csv(ROOT / "data/processed/XAUUSD_H4_clean.csv")
h4["time"] = pd.to_datetime(h4["time"], utc=True)
news = ROOT / "data/news/usd_high_impact_news.csv"

smc_res = analyze_smc(m15, symbol="XAUUSD", timeframe="M15", config=SMCConfig())
cfg = SMCConfluenceConfig(
    enable_htf_bias=True, enable_session_filter=False,
    enable_news_filter=False, enable_atr_stop=True, enable_breakeven=False
)
strategy = SMCConfluenceStrategy(h4_df=h4, news_calendar_source=news, config=cfg)
accepted, funnel, audit = strategy.generate_candidates(m15, timeframe="M15", smc_result=smc_res)
print(f"Accepted candidates: {len(accepted)}")

bconfig = BacktestConfig(
    initial_capital=10000, risk_fraction=0.005,
    fallback_spread_usd=0.20, slippage_per_side_usd=0.05
)
bt = run_confluence_backtest(m15, accepted, config=bconfig)
print(f"Trades count: {len(bt.trades)}")

if bt.trades:
    t0 = bt.trades[0]
    print(f"Trade[0] keys: {list(t0.keys())}")
    print(f"Trade[0] full: {t0}")

# Also check metrics
print(f"\nbt.metrics keys: {list(bt.metrics.keys()) if bt.metrics else 'None'}")
if bt.metrics:
    for k, v in bt.metrics.items():
        print(f"  {k}: {v}")
