"""
Controlled 16-Variant Ablation Matrix with ADX Regime Gating
============================================================
Evaluates:
A. Baseline
B. HTF
C. Session
D. ATR
E. HTF + ATR
F. HTF + Session
G. HTF + ATR + Session
Each evaluated:
1. Without ADX filter (All regimes)
2. With ADX > 25 filter (Trending only)
3. With ADX <= 25 filter (Ranging only)
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

# Compute ADX
high = m15_df['high']
low = m15_df['low']
close = m15_df['close']
tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
atr = tr.ewm(alpha=1/14, min_periods=14).mean()
up = high - high.shift(1)
down = low.shift(1) - low
plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=m15_df.index)
minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=m15_df.index)
plus_di = 100 * plus_dm.ewm(alpha=1/14, min_periods=14).mean() / atr
minus_di = 100 * minus_dm.ewm(alpha=1/14, min_periods=14).mean() / atr
dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
m15_df['adx'] = dx.ewm(alpha=1/14, min_periods=14).mean()
m15_df['regime'] = np.where(m15_df['adx'] > 25.0, 'TRENDING', 'RANGING')

smc_full = analyze_smc(m15_df, symbol="XAUUSD", timeframe="M15", config=SMCConfig())

BASE_BCONFIG = BacktestConfig(
    initial_capital=10_000.0,
    risk_fraction=0.005,
    fallback_spread_usd=0.20,
    slippage_per_side_usd=0.05,
    commission_per_lot_per_side=0.0,
)

variants = [
    ("A_BASELINE", False, False, False),
    ("B_HTF", True, False, False),
    ("C_SESSION", False, True, False),
    ("D_ATR", False, False, True),
    ("E_HTF_ATR", True, False, True),
    ("F_HTF_SESSION", True, True, False),
    ("G_HTF_ATR_SESSION", True, True, True),
]

results = []

print("Running controlled filter matrix across 33,388 bars...")

for var_name, htf, sess, atr_flag in variants:
    cfg = SMCConfluenceConfig(
        enable_htf_bias=htf,
        enable_session_filter=sess,
        enable_news_filter=False,
        enable_atr_stop=atr_flag,
        enable_breakeven=False,
    )
    strat = SMCConfluenceStrategy(h4_df=h4_df, news_calendar_source=NEWS_PATH, config=cfg)
    acc, _, _ = strat.generate_candidates(m15_df, timeframe="M15", smc_result=smc_full)

    # 1. All Regimes (No ADX filter)
    bt_all = run_confluence_backtest(m15_df, acc, config=BASE_BCONFIG)
    
    # 2. Trending Regimes Only (ADX > 25 at entry)
    acc_trending = []
    acc_ranging = []
    for c in acc:
        t_entry = c.next_bar_time
        match = m15_df[m15_df['time'] == t_entry]
        if len(match) > 0 and match['regime'].iloc[0] == 'TRENDING':
            acc_trending.append(c)
        else:
            acc_ranging.append(c)

    bt_trending = run_confluence_backtest(m15_df, acc_trending, config=BASE_BCONFIG)
    bt_ranging = run_confluence_backtest(m15_df, acc_ranging, config=BASE_BCONFIG)

    def extract(bt_res, regime_label):
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
        return {
            "variant": var_name,
            "regime_filter": regime_label,
            "trades": n,
            "win_rate": round(wr, 2),
            "gross_profit": round(gp, 2),
            "gross_loss": round(gl, 2),
            "net_pnl": round(net, 2),
            "profit_factor": round(pf, 3),
            "expectancy": round(exp, 2),
        }

    r_all = extract(bt_all, "ALL_REGIMES")
    r_trend = extract(bt_trending, "TRENDING_ONLY (ADX > 25)")
    r_range = extract(bt_ranging, "RANGING_ONLY (ADX <= 25)")
    
    results.extend([r_all, r_trend, r_range])
    print(f"  {var_name:18s} | ALL: n={r_all['trades']:3d}, PF={r_all['profit_factor']:.3f}, Net=${r_all['net_pnl']:7.2f} | TREND: n={r_trend['trades']:2d}, PF={r_trend['profit_factor']:.3f}, Net=${r_trend['net_pnl']:7.2f} | RANGE: n={r_range['trades']:2d}, PF={r_range['profit_factor']:.3f}, Net=${r_range['net_pnl']:7.2f}")

df_matrix = pd.DataFrame(results)
df_matrix.to_csv("scratch/CONTROLLED_FILTER_MATRIX.csv", index=False)
print("\nSaved controlled matrix to scratch/CONTROLLED_FILTER_MATRIX.csv")

