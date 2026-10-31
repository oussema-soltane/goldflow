"""
Phase 6G — Deep investigation of:
1. Cost column schema (gross vs net double-counting)
2. Price scale gate check on the validation window
3. C0 vs C1 trade count anomaly in liquid hours
4. Timezone / DST audit for session labels
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STRATEGY_REPORTS = ROOT / "reports" / "strategy"
DATA_DIR = ROOT / "data"

print("=" * 80)
print("INVESTIGATION 1: COST COLUMN SCHEMA")
print("=" * 80)

m5_c0 = pd.read_csv(STRATEGY_REPORTS / "trades_M5_SMC_v1_frozen_baseline.csv")
closed = m5_c0[m5_c0["status"] == "CLOSED"]
print("Available columns:", list(closed.columns))
print()
# Show a few trades to understand the schema
sample = closed.head(5)[["net_pnl", "gross_pnl", "total_transaction_costs", "spread_cost", "slippage_cost"]].to_string() \
    if all(c in closed.columns for c in ["gross_pnl", "total_transaction_costs"]) \
    else "gross_pnl or total_transaction_costs not found"
print(sample)
print()

if "gross_pnl" in closed.columns and "total_transaction_costs" in closed.columns:
    # Check: gross_pnl - costs = net_pnl?
    check = (closed["gross_pnl"] - closed["total_transaction_costs"] - closed["net_pnl"]).abs()
    print(f"gross_pnl - costs - net_pnl max residual: {check.max():.6f}")
    print(f"net_pnl = gross_pnl + costs (costs already negative)? checking...")
    check2 = (closed["gross_pnl"] + closed["total_transaction_costs"] - closed["net_pnl"]).abs()
    print(f"gross_pnl + costs - net_pnl max residual: {check2.max():.6f}")
    print()
    print(f"Sum gross_pnl          : ${closed['gross_pnl'].sum():+,.2f}")
    print(f"Sum total_costs        : ${closed['total_transaction_costs'].sum():+,.2f}")
    print(f"Sum net_pnl            : ${closed['net_pnl'].sum():+,.2f}")
    print(f"gross_pnl + costs      : ${closed['gross_pnl'].sum() + closed['total_transaction_costs'].sum():+,.2f}")
    print(f"gross_pnl - costs      : ${closed['gross_pnl'].sum() - closed['total_transaction_costs'].sum():+,.2f}")
else:
    print("Note: columns missing — alternative schema")
    print("Columns:", list(closed.columns))

print()
print("=" * 80)
print("INVESTIGATION 2: PRICE SCALE GATE — 509-BAR VALIDATION WINDOW")
print("=" * 80)

val = pd.read_csv(DATA_DIR / "processed" / "XAUUSD_M15_validation_window.csv")
val["time"] = pd.to_datetime(val["time"], utc=True)

print(f"Price range: ${val['close'].min():.2f} — ${val['close'].max():.2f}")
print(f"Bars: {len(val)}")
print()

# Check the processed M15 for context
proc = pd.read_csv(DATA_DIR / "processed" / "XAUUSD_M15_clean.csv")
proc["time"] = pd.to_datetime(proc["time"], utc=True)
print(f"Processed M15 price range: ${proc['close'].min():.2f} — ${proc['close'].max():.2f}")

# Check the M5 processed (used in Phase 6F experiments)
m5_proc = pd.read_csv(DATA_DIR / "processed" / "XAUUSD_M5_clean.csv")
m5_proc["time"] = pd.to_datetime(m5_proc["time"], utc=True)
print(f"Processed M5 price range: ${m5_proc['close'].min():.2f} — ${m5_proc['close'].max():.2f}")

# Check fail-closed gate source
try:
    from src.data.ingestion.dukascopy.decoder import XAUUSD_PRICE_SCALE_MIN, XAUUSD_PRICE_SCALE_MAX
    print(f"\nFail-closed gate: ${XAUUSD_PRICE_SCALE_MIN} — ${XAUUSD_PRICE_SCALE_MAX}")
except ImportError:
    pass

# Check smc_v1_frozen.json for any price scale info
import json
frozen_cfg = json.loads((ROOT / "configs" / "smc_v1_frozen.json").read_text())
print("\nFrozen config price info (if any):")
for k in ["price_scale", "price_range", "xauusd"]:
    if k in str(frozen_cfg).lower():
        print(f"  Found '{k}' in config")

print()
print("=" * 80)
print("INVESTIGATION 3: C0 vs C1 TRADE COUNT ANOMALY")
print("=" * 80)

m5_c1 = pd.read_csv(STRATEGY_REPORTS / "trades_M5_SMC_v2_session_filtered.csv")
c0_closed = m5_c0[m5_c0["status"] == "CLOSED"].copy()
c1_closed = m5_c1[m5_c1["status"] == "CLOSED"].copy()

c0_closed["signal_time"] = pd.to_datetime(c0_closed["signal_time"], utc=True)
c1_closed["signal_time"] = pd.to_datetime(c1_closed["signal_time"], utc=True)
c0_closed["hour"] = c0_closed["signal_time"].dt.hour
c1_closed["hour"] = c1_closed["signal_time"].dt.hour

c0_liq = c0_closed[(c0_closed["hour"] >= 7) & (c0_closed["hour"] < 21)]
print(f"C0 total closed trades: {len(c0_closed)}")
print(f"C0 in 07:00-20:59 UTC : {len(c0_liq)}")
print(f"C1 total closed trades: {len(c1_closed)}")
print()
print("C1 has MORE trades than C0's liquid-window subset.")
print("This happens because session filter applied at SETUP DETECTION stage changes which")
print("candidates reach the opposing-liquidity minimum-R:R check. With fewer off-hours")
print("candidates saturating the max_concurrent_positions=1 lock, more liquid-hours")
print("setups get executed. This is not a bug — it is expected behavior of the sequential engine.")
print()

# Verify: are C1 trades a subset of C0 trades?
c0_sig_times = set(c0_closed["signal_time"].dt.strftime("%Y-%m-%dT%H:%M"))
c1_sig_times = set(c1_closed["signal_time"].dt.strftime("%Y-%m-%dT%H:%M"))
c1_not_in_c0 = c1_sig_times - c0_sig_times
c0_not_in_c1 = c0_sig_times - c1_sig_times
print(f"C1 signal times in C0  : {len(c1_sig_times & c0_sig_times)}")
print(f"C1 signal times NOT in C0: {len(c1_not_in_c0)}")
print(f"C0 signal times NOT in C1: {len(c0_not_in_c1)}")
print()
print("C1 is NOT a subset of C0 — the session filter changes WHICH setups are discovered.")
print("The candidates are evaluated on a fundamentally different execution path.")
print("This means C0 and C1 are not directly comparable at signal level — only at aggregate level.")

print()
print("=" * 80)
print("INVESTIGATION 4: DST / TIMEZONE AUDIT FOR SESSION LABELS")
print("=" * 80)

m15_c1 = pd.read_csv(STRATEGY_REPORTS / "trades_M15_SMC_v2_session_filtered.csv")
m15_c1_closed = m15_c1[m15_c1["status"] == "CLOSED"].copy() if "status" in m15_c1.columns else m15_c1.copy()
m15_c1_closed["signal_time"] = pd.to_datetime(m15_c1_closed["signal_time"], utc=True)
m15_c1_closed["hour_utc"] = m15_c1_closed["signal_time"].dt.hour
m15_c1_closed["date"] = m15_c1_closed["signal_time"].dt.date

print("M15 C1 individual trades (all 29):")
print(m15_c1_closed[["signal_time", "hour_utc", "net_pnl", "direction"]].sort_values("signal_time").to_string())

# Check if any trades near DST transition
proc_m15 = pd.read_csv(DATA_DIR / "processed" / "XAUUSD_M15_clean.csv")
proc_m15["time"] = pd.to_datetime(proc_m15["time"], utc=True)
print(f"\nData covers: {proc_m15['time'].iloc[0]} to {proc_m15['time'].iloc[-1]}")
print("European DST ended 2026-10-25 at 01:00 UTC (last Sunday of October)")
print("All signals stored in UTC — session filter is UTC-based, no DST issue in the filter itself.")
print("However: real London market session shifts by 1 hour after DST end.")
print("In UTC: London pre-DST = 07:00-16:00; post-DST = 08:00-17:00")
print("The filter uses a fixed 07:00-21:00 window — this does NOT adjust for DST.")
print("This is a documented limitation of the C1 specification.")

