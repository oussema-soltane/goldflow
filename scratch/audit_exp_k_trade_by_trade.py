"""
Detailed Trade-by-Trade Reconciliation for EXP_K 10-Fold Walk-Forward
=====================================================================
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
H4_PATH = Path("data/processed/XAUUSD_H4_clean.csv")
NEWS_PATH = Path("data/news/usd_high_impact_news.csv")

m15_df = pd.read_csv(EXTENDED_M15_PATH)
m15_df["time"] = pd.to_datetime(m15_df["time"], utc=True)
h4_df = pd.read_csv(H4_PATH)
h4_df["time"] = pd.to_datetime(h4_df["time"], utc=True)

exp_k_cfg = SMCConfluenceConfig(
    enable_htf_bias=True,
    enable_session_filter=True,
    enable_news_filter=True,
    enable_atr_stop=True,
    enable_breakeven=True,
)

BASE_BCONFIG = BacktestConfig(
    initial_capital=10_000.0,
    risk_fraction=0.005,
    fallback_spread_usd=0.20,
    slippage_per_side_usd=0.05,
    commission_per_lot_per_side=0.0,
)

initial_is_bars = 13_388
fold_oos_bars = 2_000
n_folds = 10

all_oos_trades = []

print("Running trade-level walk-forward extraction for EXP_K...")
for fold_i in range(1, n_folds + 1):
    is_end_idx = initial_is_bars + (fold_i - 1) * fold_oos_bars
    oos_start_idx = is_end_idx
    oos_end_idx = min(oos_start_idx + fold_oos_bars, len(m15_df))

    oos_sub = m15_df.iloc[oos_start_idx:oos_end_idx].copy().reset_index(drop=True)

    smc_oos = analyze_smc(oos_sub, symbol="XAUUSD", timeframe="M15", config=SMCConfig())
    strat_oos = SMCConfluenceStrategy(h4_df=h4_df, news_calendar_source=NEWS_PATH, config=exp_k_cfg)
    acc_oos, _, _ = strat_oos.generate_candidates(oos_sub, timeframe="M15", smc_result=smc_oos)
    bt_oos = run_confluence_backtest(oos_sub, acc_oos, config=BASE_BCONFIG, enable_breakeven=True)

    trades = [t for t in (bt_oos.trades or []) if t.get("exit_reason") not in ("END_OF_DATA", None) and t.get("entry_time") is not None]
    
    for t_idx, t in enumerate(trades, 1):
        pnl = float(t.get("net_pnl", 0.0))
        entry_price = float(t.get("entry_price", 0.0))
        exit_price = float(t.get("exit_price", 0.0))
        spread_paid = float(t.get("spread_usd", 0.20))
        slippage_paid = float(t.get("slippage_usd", 0.10))
        direction = t.get("direction", "UNKNOWN")
        size = float(t.get("size", 0.0))
        exit_reason = t.get("exit_reason", "")
        
        all_oos_trades.append({
            "fold": fold_i,
            "trade_in_fold": t_idx,
            "trade_id": f"EXP_K_WF_F{fold_i:02d}_T{t_idx:02d}",
            "direction": direction,
            "entry_time": str(t.get("entry_time")),
            "exit_time": str(t.get("exit_time")),
            "entry_price": round(entry_price, 3),
            "exit_price": round(exit_price, 3),
            "lot_size": round(size, 4),
            "spread_usd": round(spread_paid, 2),
            "slippage_usd": round(slippage_paid, 2),
            "commission_usd": 0.0,
            "gross_profit": round(pnl, 2) if pnl > 0 else 0.0,
            "gross_loss": round(abs(pnl), 2) if pnl < 0 else 0.0,
            "net_pnl": round(pnl, 2),
            "exit_reason": exit_reason
        })

df_trades = pd.DataFrame(all_oos_trades)
df_trades.to_csv("scratch/EXP_K_OOS_INDIVIDUAL_TRADES.csv", index=False)
print(f"Total individual OOS trades extracted: {len(df_trades)}")
print(df_trades.to_string())

# Verification of sums
gp_total = df_trades["gross_profit"].sum()
gl_total = df_trades["gross_loss"].sum()
net_total = df_trades["net_pnl"].sum()
pf_total = gp_total / gl_total if gl_total > 0 else 999.0

print("\n" + "="*70)
print("INDEPENDENT TRADE-LEVEL OOS TOTALS:")
print(f"Total Gross Profit: ${gp_total:.2f}")
print(f"Total Gross Loss:   ${gl_total:.2f}")
print(f"Total Net P&L:      ${net_total:.2f}")
print(f"OOS Profit Factor:  {pf_total:.4f}")
print("="*70)

