"""
Phase 3I-C: Historical Metric Reconciliation
=============================================
Investigates:
1. EXP_K net P&L discrepancy: +$538.14 (old) vs +$538.31 (new).
2. Bootstrap changes between Phase 3H and scratch CSV.
3. Bootstrap implementation details: seeds, N_resamples, methodology.
"""
import pandas as pd
import numpy as np
from pathlib import Path
import hashlib

ROOT = Path(".")

# Load trade ledger
ledger = pd.read_csv("reports/PHASE3_TRADE_LEDGER.csv")
print(f"Trade ledger total rows: {len(ledger)}")
print(f"Columns: {list(ledger.columns)}")
print(f"Experiment IDs: {sorted(ledger['experiment_id'].unique())}")

# EXP_K specific
expk = ledger[ledger["experiment_id"] == "EXP_K_FULL"].copy()
print(f"\n=== EXP_K_FULL IN-SAMPLE TRADES ===")
print(f"Total rows: {len(expk)}")
print(f"Entry_reason counts: {expk.get('exit_reason', pd.Series()).value_counts().to_dict()}")

# Filter to completed trades (no END_OF_DATA, no open)
if "exit_reason" in expk.columns:
    completed = expk[~expk["exit_reason"].isin(["END_OF_DATA", "no_next_bar", "max_concurrent_positions"])].copy()
    skipped = expk[expk["exit_reason"].isin(["END_OF_DATA", "no_next_bar", "max_concurrent_positions"])]
    print(f"Completed trades: {len(completed)}")
    print(f"Skipped/End-of-data: {len(skipped)}")
else:
    completed = expk.copy()
    print(f"No exit_reason column - using all rows as completed")

if "net_pnl" in completed.columns:
    pnls = completed["net_pnl"].astype(float)
    gross_p = pnls[pnls > 0].sum()
    gross_l = abs(pnls[pnls < 0].sum())
    net = pnls.sum()
    wins = (pnls > 0).sum()
    pf = gross_p / gross_l if gross_l > 0 else 999.0
    wr = wins / len(pnls) * 100

    print(f"\n=== INDEPENDENTLY RECOMPUTED EXP_K IS METRICS ===")
    print(f"Trade Count (N):    {len(pnls)}")
    print(f"Winners:            {wins}")
    print(f"Win Rate:           {wr:.2f}%")
    print(f"Gross Profit:       ${gross_p:.2f}")
    print(f"Gross Loss:         ${gross_l:.2f}")
    print(f"Net P&L:            ${net:.2f}")
    print(f"Profit Factor:      {pf:.4f}")

    print(f"\n=== DISCREPANCY WITH PUBLISHED VALUES ===")
    published_old = 538.14
    published_new = 538.31
    print(f"Previously published (old):   ${published_old:.2f}")
    print(f"Phase 3H published (new):     ${published_new:.2f}")
    print(f"Independently computed:       ${net:.2f}")
    print(f"Difference (old vs new):      ${published_new - published_old:.2f}")
    print(f"Difference (computed vs new): ${net - published_new:.2f}")

# Check bootstrap implementations
print(f"\n=== BOOTSTRAP IMPLEMENTATION DETAILS ===")
print("--- scratch/audit_bootstrap_sensitivity.py ---")
print("  n_resamples: 10,000 per block length")
print("  block_lengths: [1, 3, 5, 10, 15, 20]")
print("  random seed: np.random.default_rng(42) SHARED across all block lengths")
print("  method: Stationary block bootstrap (geometric block lengths)")
print("  PF CI: percentile method [2.5%, 97.5%]")
print("  P(Net<=0): proportion of resamples with net_pnl <= 0")
print("  ISSUE: RNG state is advanced sequentially across block lengths.")
print("  This means block L=3 uses different RNG state than L=1,")
print("  making cross-block comparison non-trivially reproducible.")

# Check the BOOTSTRAP_CI_ANALYSIS.csv
bci_path = Path("reports/BOOTSTRAP_CI_ANALYSIS.csv")
if bci_path.exists():
    bci = pd.read_csv(bci_path)
    print(f"\n--- reports/BOOTSTRAP_CI_ANALYSIS.csv ---")
    print(bci.to_string())

# Check scratch bootstrap CSVs  
for fname in ["scratch/BOOTSTRAP_SENSITIVITY_EXP_H.csv", "scratch/BOOTSTRAP_SENSITIVITY_EXP_K.csv"]:
    p = Path(fname)
    if p.exists():
        df = pd.read_csv(p)
        print(f"\n--- {fname} ---")
        print(df.to_string(index=False))

# Hash the trade ledger for reference
ledger_hash = hashlib.sha256(Path("reports/PHASE3_TRADE_LEDGER.csv").read_bytes()).hexdigest()
print(f"\n=== TRADE LEDGER INTEGRITY ===")
print(f"PHASE3_TRADE_LEDGER.csv SHA-256: {ledger_hash}")
print(f"Total rows in ledger: {len(ledger)}")
print(f"Experiments: {sorted(ledger['experiment_id'].unique())}")

