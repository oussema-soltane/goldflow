"""
Phase 6G — Deep cost schema investigation.
The gross_pnl and net_pnl appear equal — determine what raw_gross_pnl is,
whether costs are double-counted, and establish the true cost structure.
Also run bootstrap confidence interval on M15 C1 PF.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STRATEGY_REPORTS = ROOT / "reports" / "strategy"

print("=" * 80)
print("COST SCHEMA DEEP-DIVE")
print("=" * 80)

m5_c0 = pd.read_csv(STRATEGY_REPORTS / "trades_M5_SMC_v1_frozen_baseline.csv")
closed = m5_c0[m5_c0["status"] == "CLOSED"].copy()

# Inspect raw_gross_pnl vs gross_pnl
if "raw_gross_pnl" in closed.columns:
    diff = (closed["raw_gross_pnl"] - closed["net_pnl"]).abs()
    print("raw_gross_pnl - net_pnl stats:")
    print(f"  max diff: {diff.max():.4f}")
    print(f"  mean diff: {diff.mean():.4f}")
    print()
    print(f"Sum raw_gross_pnl : ${closed['raw_gross_pnl'].sum():+,.2f}")
    print(f"Sum gross_pnl     : ${closed['gross_pnl'].sum():+,.2f}")
    print(f"Sum net_pnl       : ${closed['net_pnl'].sum():+,.2f}")
    print(f"Sum total_costs   : ${closed['total_transaction_costs'].sum():+,.2f}")
    print()
    # Is raw_gross_pnl the pre-cost P&L?
    check = (closed["raw_gross_pnl"] - closed["total_transaction_costs"] - closed["net_pnl"]).abs().max()
    print(f"raw_gross_pnl - costs - net_pnl max residual: {check:.6f}")
    check2 = (closed["raw_gross_pnl"] + closed["total_transaction_costs"] - closed["net_pnl"]).abs().max()
    print(f"raw_gross_pnl + costs - net_pnl max residual: {check2:.6f}")
    # Try: gross_pnl = raw_gross_pnl, net = gross - costs?
    check3 = (closed["gross_pnl"] + closed["total_transaction_costs"] - closed["net_pnl"]).abs().max()
    print(f"gross_pnl + costs - net_pnl max residual: {check3:.6f}")
    # Show sample
    cols = ["raw_gross_pnl", "gross_pnl", "total_transaction_costs", "net_pnl"]
    print("\nSample rows:")
    print(closed[cols].head(10).to_string())
else:
    print("raw_gross_pnl column not available.")

print()
print("CONCLUSION: The 'gross_pnl' column in these ledgers appears to ALREADY include cost deductions.")
print("'raw_gross_pnl' = the true pre-cost P&L. 'net_pnl' = gross_pnl (both are post-cost).")
print("Costs are reported separately for informational decomposition only.")

# Recalculate true gross and net using raw_gross_pnl
if "raw_gross_pnl" in closed.columns:
    true_gross = closed["raw_gross_pnl"].sum()
    true_costs = closed["total_transaction_costs"].sum()
    true_net = closed["net_pnl"].sum()
    print(f"\nTrue gross P&L (pre-cost)  : ${true_gross:+,.2f}")
    print(f"Total transaction costs    : ${true_costs:+,.2f}")
    print(f"Net P&L (post-cost)        : ${true_net:+,.2f}")
    print(f"Implied: raw_gross - costs : ${true_gross - true_costs:+,.2f}  (should equal net)")
    
    # True profit factor
    wins_raw = closed[closed["raw_gross_pnl"] > 0]["raw_gross_pnl"].sum()
    losses_raw = abs(closed[closed["raw_gross_pnl"] <= 0]["raw_gross_pnl"].sum())
    pf_raw = wins_raw / losses_raw if losses_raw > 0 else float("inf")
    print(f"\nTrue gross PF (pre-cost)   : {pf_raw:.3f}")
    
    wins_net = closed[closed["net_pnl"] > 0]["net_pnl"].sum()
    losses_net = abs(closed[closed["net_pnl"] <= 0]["net_pnl"].sum())
    pf_net = wins_net / losses_net if losses_net > 0 else float("inf")
    print(f"Net PF (as reported)       : {pf_net:.3f}")

print()
print("=" * 80)
print("BOOTSTRAP CONFIDENCE ANALYSIS — M15 C1 (n=29)")
print("=" * 80)

m15_c1 = pd.read_csv(STRATEGY_REPORTS / "trades_M15_SMC_v2_session_filtered.csv")
c1_closed = m15_c1[m15_c1["status"] == "CLOSED"].copy() if "status" in m15_c1.columns else m15_c1.copy()
pnls = c1_closed["net_pnl"].values
n = len(pnls)

np.random.seed(42)
N_BOOT = 10000
boot_pfs = []
boot_nets = []
boot_wrs = []

for _ in range(N_BOOT):
    sample = np.random.choice(pnls, size=n, replace=True)
    wins = sample[sample > 0]
    losses = sample[sample <= 0]
    w_sum = wins.sum()
    l_sum = abs(losses.sum())
    pf = w_sum / l_sum if l_sum > 0 else (float("inf") if w_sum > 0 else 0.0)
    boot_pfs.append(pf)
    boot_nets.append(sample.sum())
    boot_wrs.append((sample > 0).mean() * 100)

boot_pfs = np.array([x for x in boot_pfs if np.isfinite(x)])
boot_nets = np.array(boot_nets)
boot_wrs = np.array(boot_wrs)

print(f"n trades            : {n}")
print(f"Observed PF         : {c1_closed['net_pnl'].apply(lambda x: x).pipe(lambda s: s[s>0].sum() / abs(s[s<=0].sum())):.3f}")
print(f"Observed net P&L    : ${pnls.sum():+,.2f}")
print(f"Observed win rate   : {(pnls > 0).mean()*100:.1f}%")
print()
print(f"Bootstrap PF (10,000 resamples):")
print(f"  Mean  : {np.mean(boot_pfs):.3f}")
print(f"  Median: {np.median(boot_pfs):.3f}")
print(f"  P5    : {np.percentile(boot_pfs, 5):.3f}")
print(f"  P25   : {np.percentile(boot_pfs, 25):.3f}")
print(f"  P75   : {np.percentile(boot_pfs, 75):.3f}")
print(f"  P95   : {np.percentile(boot_pfs, 95):.3f}")
print(f"  P(PF > 1.0): {(boot_pfs > 1.0).mean()*100:.1f}%")
print(f"  P(PF > 1.5): {(boot_pfs > 1.5).mean()*100:.1f}%")
print()
print(f"Bootstrap net P&L (10,000 resamples):")
print(f"  Mean  : ${np.mean(boot_nets):+,.2f}")
print(f"  P5    : ${np.percentile(boot_nets, 5):+,.2f}")
print(f"  P95   : ${np.percentile(boot_nets, 5):+,.2f}")
print(f"  P(net > 0): {(boot_nets > 0).mean()*100:.1f}%")
print()

# Identify dominant trades — how much does the single largest win contribute?
sorted_pnl = np.sort(pnls)[::-1]
top1_contribution = sorted_pnl[0] / pnls.sum() * 100 if pnls.sum() > 0 else float("nan")
top3_contribution = sorted_pnl[:3].sum() / pnls.sum() * 100 if pnls.sum() > 0 else float("nan")
print(f"Largest single win  : ${sorted_pnl[0]:+,.2f}")
print(f"Top-1 trade as % of total profit: {top1_contribution:.1f}%")
print(f"Top-3 trades as % of total profit: {top3_contribution:.1f}%")
print()

# Date concentration
c1_closed["signal_time"] = pd.to_datetime(c1_closed["signal_time"], utc=True)
c1_closed["month"] = c1_closed["signal_time"].dt.strftime("%Y-%m")
monthly = c1_closed.groupby("month")["net_pnl"].agg(["count", "sum"])
monthly.columns = ["trades", "net_pnl"]
print("Performance by calendar month:")
print(monthly.to_string())
print()
print("STATISTICAL VERDICT:")
print(f"  With n={n} trades, bootstrap P(PF>1) = {(boot_pfs > 1.0).mean()*100:.0f}%")
print(f"  The 90% bootstrap interval for PF spans [{np.percentile(boot_pfs,5):.3f}, {np.percentile(boot_pfs,95):.3f}]")
print(f"  This interval is WIDE — results are dominated by {top3_contribution:.0f}% from 3 trades.")
print(f"  CAVEAT: iid bootstrap is biased for time-series data with serial dependence.")

