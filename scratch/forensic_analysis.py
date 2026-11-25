"""
Forensic Strategy Loss Decomposition Script for GoldFlow.
Audits trade ledgers across timeframes, variants, sessions, regimes, costs, and setup types.
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd


def analyze_ledger(csv_path: str, label: str):
    p = Path(csv_path)
    if not p.exists():
        print(f"File not found: {csv_path}")
        return
    
    df = pd.read_csv(p)
    print(f"\n{'='*80}\nAUDIT OF {label} ({p.name})\n{'='*80}")
    print(f"Total Rows: {len(df)}")
    if "status" in df.columns:
        print("Status Counts:", df["status"].value_counts().to_dict())
    
    closed = df[df["status"] == "CLOSED"].copy()
    if len(closed) == 0:
        print("No closed trades.")
        return

    closed["is_win"] = closed["net_pnl"] > 0
    closed["entry_time"] = pd.to_datetime(closed["entry_time"], utc=True)
    closed["hour"] = closed["entry_time"].dt.hour
    closed["dayofweek"] = closed["entry_time"].dt.day_name()
    closed["month"] = closed["entry_time"].dt.to_period("M")

    # Timeframe breakdown
    print(f"\n--- TIMEFRAME SUMMARY ---")
    for tf in sorted(closed["timeframe"].unique()):
        sub = closed[closed["timeframe"] == tf]
        wins = sub[sub["is_win"]]
        losses = sub[~sub["is_win"]]
        net = sub["net_pnl"].sum()
        gross = sub["gross_pnl"].sum()
        costs = sub["total_transaction_costs"].sum()
        wr = len(wins) / len(sub)
        avg_win = wins["net_pnl"].mean() if len(wins) else 0.0
        avg_loss = abs(losses["net_pnl"].mean()) if len(losses) else 0.0
        b_ratio = avg_win / avg_loss if avg_loss > 0 else np.nan
        breakeven_wr = 1.0 / (1.0 + b_ratio) if b_ratio > 0 else np.nan
        pf = (wins["net_pnl"].sum() / abs(losses["net_pnl"].sum())) if len(losses) and losses["net_pnl"].sum() != 0 else np.nan
        avg_r = sub["R_multiple"].mean() if "R_multiple" in sub.columns else np.nan
        avg_bars = sub["bars_held"].mean() if "bars_held" in sub.columns else np.nan
        
        print(f"[{tf:4s}] {len(sub):4d} trades | Gross: ${gross:9.2f} | Costs: ${costs:8.2f} | Net: ${net:9.2f} | "
              f"WR: {wr*100:5.2f}% (BE: {breakeven_wr*100:5.2f}%) | Payoff: {b_ratio:5.2f} | PF: {pf:5.3f} | "
              f"Avg R: {avg_r:6.3f} | Avg Bars: {avg_bars:5.1f}")

    # Directional Breakdown on M5
    m5 = closed[closed["timeframe"] == "M5"]
    if len(m5) > 0:
        print(f"\n--- M5 DIRECTION (LONG vs SHORT) ---")
        for side in ["LONG", "SHORT"]:
            sub = m5[m5["side"] == side]
            wins = sub[sub["is_win"]]
            losses = sub[~sub["is_win"]]
            wr = len(wins) / len(sub) if len(sub) else 0.0
            net = sub["net_pnl"].sum()
            pf = (wins["net_pnl"].sum() / abs(losses["net_pnl"].sum())) if len(losses) and losses["net_pnl"].sum() != 0 else np.nan
            print(f"[{side:5s}] {len(sub):4d} trades | Net: ${net:9.2f} | WR: {wr*100:5.2f}% | PF: {pf:5.3f} | "
                  f"Gross: ${sub['gross_pnl'].sum():9.2f} | Costs: ${sub['total_transaction_costs'].sum():8.2f}")

        print(f"\n--- M5 TARGET SOURCE ---")
        for ts, group in m5.groupby("target_source"):
            wins = group[group["is_win"]]
            losses = group[~group["is_win"]]
            wr = len(wins) / len(group)
            net = group["net_pnl"].sum()
            pf = (wins["net_pnl"].sum() / abs(losses["net_pnl"].sum())) if len(losses) and losses["net_pnl"].sum() != 0 else np.nan
            print(f"[{ts:25s}] {len(group):4d} trades | Net: ${net:9.2f} | WR: {wr*100:5.2f}% | PF: {pf:5.3f} | Avg R: {group['R_multiple'].mean():6.3f}")

        # Session Analysis
        def get_session(h):
            if 0 <= h < 7: return "Asian (00-07 UTC)"
            elif 7 <= h < 13: return "London (07-13 UTC)"
            elif 13 <= h < 17: return "NY Overlap (13-17 UTC)"
            elif 17 <= h < 21: return "NY Afternoon (17-21 UTC)"
            else: return "Daily Close (21-24 UTC)"

        m5["session"] = m5["hour"].apply(get_session)
        print(f"\n--- M5 TRADING SESSION DECOMPOSITION ---")
        for sess in ["Asian (00-07 UTC)", "London (07-13 UTC)", "NY Overlap (13-17 UTC)", "NY Afternoon (17-21 UTC)", "Daily Close (21-24 UTC)"]:
            group = m5[m5["session"] == sess]
            if len(group) == 0: continue
            wins = group[group["is_win"]]
            losses = group[~group["is_win"]]
            wr = len(wins) / len(group)
            net = group["net_pnl"].sum()
            gross = group["gross_pnl"].sum()
            costs = group["total_transaction_costs"].sum()
            pf = (wins["net_pnl"].sum() / abs(losses["net_pnl"].sum())) if len(losses) and losses["net_pnl"].sum() != 0 else np.nan
            print(f"[{sess:22s}] {len(group):4d} trades | Gross: ${gross:8.2f} | Costs: ${costs:7.2f} | Net: ${net:8.2f} | WR: {wr*100:5.2f}% | PF: {pf:5.3f}")

        # Exit Reason Breakdown
        print(f"\n--- M5 EXIT REASON DECOMPOSITION ---")
        for r, group in m5.groupby("exit_reason"):
            net = group["net_pnl"].sum()
            avg_pnl = group["net_pnl"].mean()
            print(f"[{r:25s}] {len(group):4d} trades ({len(group)/len(m5)*100:5.1f}%) | Total Net: ${net:9.2f} | Mean: ${avg_pnl:6.2f}")

        # Cost Impact
        print(f"\n--- M5 COST DRAG ANALYSIS ---")
        total_gross = m5["gross_pnl"].sum()
        total_spread = m5["spread_cost"].sum()
        total_slip = m5["slippage_cost"].sum()
        total_costs = m5["total_transaction_costs"].sum()
        total_net = m5["net_pnl"].sum()
        print(f"Gross P&L:               ${total_gross:9.2f}")
        print(f"Spread Cost:             ${total_spread:9.2f} ({total_spread/abs(total_gross)*100:.1f}% of gross)")
        print(f"Slippage Cost:           ${total_slip:9.2f} ({total_slip/abs(total_gross)*100:.1f}% of gross)")
        print(f"Total Friction:          ${total_costs:9.2f}")
        print(f"Net P&L:                 ${total_net:9.2f}")
        print(f"Friction Drag per Trade: ${total_costs/len(m5):6.2f}")


if __name__ == "__main__":
    analyze_ledger("reports/smc_backtest_trades_full_history.csv", "Full History Backtest")
    analyze_ledger("reports/smc_mtf_trades.csv", "MTF Experiment Backtest")

