"""
Phase 3I-D: Controlled Backtest Comparison - Complete vs All M15 Intervals
==========================================================================
Compares backtest performance of EXP_H and EXP_K:
1. With all 33,388 bars (including 135 partial session-boundary intervals)
2. With only 33,253 complete 3-bar intervals (partial intervals dropped)
"""
import pandas as pd
import numpy as np
from pathlib import Path
import sys

ROOT = Path('.').resolve()
sys.path.insert(0, str(ROOT))

from src.backtesting.engine import BacktestConfig
from src.smc.engine import analyze_smc, SMCConfig
from src.strategy.smc_confluence import (
    SMCConfluenceConfig,
    SMCConfluenceStrategy,
    run_confluence_backtest,
)

EXTENDED_M15_PATH = Path("data/research/phase3/processed/XAUUSD_M15_extended.csv")
AUDIT_CSV_PATH = Path("scratch/PHASE3I_M15_PARTIAL_CANDLE_AUDIT.csv")
H4_PATH = Path("data/processed/XAUUSD_H4_clean.csv")
NEWS_PATH = Path("data/news/usd_high_impact_news.csv")

m15_all = pd.read_csv(EXTENDED_M15_PATH)
m15_all["time"] = pd.to_datetime(m15_all["time"], utc=True)
audit_df = pd.read_csv(AUDIT_CSV_PATH)
audit_df["time"] = pd.to_datetime(audit_df["time"], utc=True)

# Merge completeness flag
m15_all["is_complete"] = audit_df["is_complete"]

# Filtered DataFrame with only complete intervals
m15_complete = m15_all[m15_all["is_complete"]].copy().reset_index(drop=True)

h4_df = pd.read_csv(H4_PATH)
h4_df["time"] = pd.to_datetime(h4_df["time"], utc=True)

BASE_BCONFIG = BacktestConfig(
    initial_capital=10_000.0,
    risk_fraction=0.005,
    fallback_spread_usd=0.20,
    slippage_per_side_usd=0.05,
    commission_per_lot_per_side=0.0,
)

experiments = [
    ("EXP_H_HTF_ATR", SMCConfluenceConfig(enable_htf_bias=True, enable_session_filter=False, enable_news_filter=False, enable_atr_stop=True, enable_breakeven=False), False),
    ("EXP_K_FULL", SMCConfluenceConfig(enable_htf_bias=True, enable_session_filter=True, enable_news_filter=True, enable_atr_stop=True, enable_breakeven=True), True),
]

comparison_rows = []

for exp_name, cfg, be_flag in experiments:
    for dataset_label, df_run in [("ALL_BARS_33388", m15_all), ("COMPLETE_ONLY_33253", m15_complete)]:
        smc_res = analyze_smc(df_run, symbol="XAUUSD", timeframe="M15", config=SMCConfig())
        strat = SMCConfluenceStrategy(h4_df=h4_df, news_calendar_source=NEWS_PATH, config=cfg)
        acc, _, _ = strat.generate_candidates(df_run, timeframe="M15", smc_result=smc_res)
        bt_res = run_confluence_backtest(df_run, acc, config=BASE_BCONFIG, enable_breakeven=be_flag)

        trades = [t for t in (bt_res.trades or []) if t.get("exit_reason") not in ("END_OF_DATA", None) and t.get("entry_time") is not None]
        n = len(trades)
        pnls = [float(t.get("net_pnl", 0.0)) for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        gp = sum(p for p in pnls if p > 0)
        gl = abs(sum(p for p in pnls if p < 0))
        net = sum(pnls)
        wr = (wins / n * 100.0) if n > 0 else 0.0
        pf = (gp / gl) if gl > 0 else (999.0 if gp > 0 else 0.0)
        exp = (net / n) if n > 0 else 0.0

        comparison_rows.append({
            "experiment": exp_name,
            "dataset": dataset_label,
            "total_bars": len(df_run),
            "trades": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate": round(wr, 2),
            "gross_profit": round(gp, 2),
            "gross_loss": round(gl, 2),
            "net_pnl": round(net, 2),
            "profit_factor": round(pf, 3),
            "expectancy": round(exp, 2),
        })

df_comp = pd.DataFrame(comparison_rows)
df_comp.to_csv("scratch/PHASE3I_PARTIAL_CANDLE_COMPARISON.csv", index=False)
print("=== CONTROLLED PARTIAL CANDLE COMPARISON ===")
print(df_comp.to_string(index=False))
