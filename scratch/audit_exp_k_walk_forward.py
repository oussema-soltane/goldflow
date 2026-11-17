"""
10-Fold Chronological Walk-Forward Audit for EXP_K_FULL
======================================================
Evaluates EXP_K_FULL across the identical 10 chronological folds
used for EXP_H_HTF_ATR to establish its true out-of-sample performance.
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

wf_k_rows = []

print("Running 10-Fold Walk-Forward on EXP_K_FULL...")
for fold_i in range(1, n_folds + 1):
    is_end_idx = initial_is_bars + (fold_i - 1) * fold_oos_bars
    oos_start_idx = is_end_idx
    oos_end_idx = min(oos_start_idx + fold_oos_bars, len(m15_df))

    is_sub = m15_df.iloc[:is_end_idx].copy().reset_index(drop=True)
    oos_sub = m15_df.iloc[oos_start_idx:oos_end_idx].copy().reset_index(drop=True)

    # IS
    smc_is = analyze_smc(is_sub, symbol="XAUUSD", timeframe="M15", config=SMCConfig())
    strat_is = SMCConfluenceStrategy(h4_df=h4_df, news_calendar_source=NEWS_PATH, config=exp_k_cfg)
    acc_is, _, _ = strat_is.generate_candidates(is_sub, timeframe="M15", smc_result=smc_is)
    bt_is = run_confluence_backtest(is_sub, acc_is, config=BASE_BCONFIG, enable_breakeven=True)
    
    # OOS
    smc_oos = analyze_smc(oos_sub, symbol="XAUUSD", timeframe="M15", config=SMCConfig())
    strat_oos = SMCConfluenceStrategy(h4_df=h4_df, news_calendar_source=NEWS_PATH, config=exp_k_cfg)
    acc_oos, _, _ = strat_oos.generate_candidates(oos_sub, timeframe="M15", smc_result=smc_oos)
    bt_oos = run_confluence_backtest(oos_sub, acc_oos, config=BASE_BCONFIG, enable_breakeven=True)

    def get_summary(bt_res):
        trades = [t for t in (bt_res.trades or []) if t.get("exit_reason") not in ("END_OF_DATA", None) and t.get("entry_time") is not None]
        n = len(trades)
        pnls = [float(t.get("net_pnl", 0.0)) for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        gp = sum(p for p in pnls if p > 0)
        gl = abs(sum(p for p in pnls if p < 0))
        net = sum(pnls)
        wr = (wins / n * 100.0) if n > 0 else 0.0
        pf = (gp / gl) if gl > 0 else (999.0 if gp > 0 else 0.0)
        return n, wins, wr, net, pf

    is_n, is_w, is_wr, is_net, is_pf = get_summary(bt_is)
    oos_n, oos_w, oos_wr, oos_net, oos_pf = get_summary(bt_oos)

    is_pos = (oos_net > 0)
    print(f"Fold {fold_i:2d}: IS trades={is_n:2d}, PF={is_pf:.2f}, Net=${is_net:6.2f} | OOS trades={oos_n:2d}, PF={oos_pf:.2f}, Net=${oos_net:6.2f} | Pos={is_pos}")

    wf_k_rows.append({
        "fold": fold_i,
        "is_trades": is_n,
        "is_net": round(is_net, 2),
        "is_pf": round(is_pf, 3),
        "oos_trades": oos_n,
        "oos_wins": oos_w,
        "oos_wr": round(oos_wr, 2),
        "oos_net": round(oos_net, 2),
        "oos_pf": round(oos_pf, 3),
        "oos_positive": is_pos
    })

df_wf_k = pd.DataFrame(wf_k_rows)
df_wf_k.to_csv("scratch/EXP_K_WALK_FORWARD_RESULTS.csv", index=False)

pos_k = (df_wf_k['oos_positive'] == True).sum()
tot_oos_trades_k = df_wf_k['oos_trades'].sum()
tot_oos_net_k = df_wf_k['oos_net'].sum()
print("\n" + "="*60)
print(f"EXP_K WALK-FORWARD SUMMARY:")
print(f"  Positive Folds: {pos_k} / 10 ({pos_k/10*100:.1f}%)")
print(f"  Total OOS Trades: {tot_oos_trades_k}")
print(f"  Total OOS Net P&L: ${tot_oos_net_k:.2f}")
print("="*60)

