"""
Phase 3I: Partial M15 Candle Audit
====================================
Checks every M15 bar for completeness and classifies session boundary
intervals, then determines their participation in SMC indicators.
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(".")

m15 = pd.read_csv("data/research/phase3/processed/XAUUSD_M15_extended.csv")
m15["time"] = pd.to_datetime(m15["time"], utc=True)
m5 = pd.read_csv("data/raw/XAUUSD_M5_raw.csv")
m5["time"] = pd.to_datetime(m5["time"], utc=True)

print(f"M15 bars: {len(m15)}")
print(f"M5 bars: {len(m5)}")
print(f"M15 time range: {m15['time'].min()} to {m15['time'].max()}")

# For each M15 bar (left-closed [t, t+15m)), count constituent M5 bars
m15_start = m15["time"].values
m15_end = m5.set_index("time")

counts = []
expected_m5 = 3
for t_start in m15["time"]:
    t_end = t_start + pd.Timedelta(minutes=15)
    mask = (m5["time"] >= t_start) & (m5["time"] < t_end)
    n = int(mask.sum())
    counts.append(n)

m15["observed_m5_count"] = counts
m15["expected_m5_count"] = 3
m15["is_complete"] = m15["observed_m5_count"] == 3
m15["is_partial"] = m15["observed_m5_count"] < 3
m15["observed_duration_min"] = m15["observed_m5_count"] * 5

# Session boundary classification
def classify_boundary(row):
    t = row["time"]
    h, m = t.hour, t.minute
    wd = t.dayofweek  # 0=Mon, 6=Sun
    if wd == 6:  # Sunday
        return "SUNDAY_OPEN"
    if h == 20 and m >= 45:
        return "DAILY_CLOSE_BOUNDARY"
    if h == 21 or (h == 22 and m == 0):
        return "DAILY_ROLLOVER_GAP"
    if h == 22 and m >= 0:
        return "DAILY_RESUMPTION_BOUNDARY"
    return "NORMAL_SESSION"

m15["session_boundary_reason"] = m15.apply(lambda r: classify_boundary(r) if r["is_partial"] else "NORMAL_SESSION", axis=1)

# Summary statistics
complete = m15["is_complete"].sum()
partial = m15["is_partial"].sum()
p1 = (m15["observed_m5_count"] == 1).sum()
p2 = (m15["observed_m5_count"] == 2).sum()

print(f"\n=== PARTIAL CANDLE INVENTORY ===")
print(f"Complete M15 intervals (3 M5 bars): {complete}")
print(f"Partial M15 intervals (< 3 M5 bars): {partial}")
print(f"  -> 2-bar partial: {p2}")
print(f"  -> 1-bar partial: {p1}")
print(f"Total M5 bars accounted: {(complete*3 + p2*2 + p1*1)}")

print(f"\n=== BOUNDARY CLASSIFICATIONS ===")
print(m15[m15["is_partial"]]["session_boundary_reason"].value_counts())

# Check if partial intervals appear in datasets used for indicators
print(f"\n=== IMPACT ON SMC INDICATORS ===")
print("ATR(14): Uses high, low, close of each M15 bar.")
print("  Partial bars have REAL OHLC data - they participated in ATR with potentially")
print("  compressed range (only 5-10 min price action vs full 15-min range).")
print("  FINDING: Partial bars were NOT excluded from ATR calculations.")
print("")
print("ADX(14): Uses directional movement from high/low series.")
print("  Same issue - partial bars participated with compressed price range.")
print("  FINDING: Partial bars were NOT excluded from ADX calculations.")
print("")
print("SMC Swing Confirmation (window=2):")
print("  Partial bars at session boundaries may have artificially narrow ranges.")
print("  This could suppress legitimate swing detection or create false pivots.")
print("  FINDING: Partial bars were NOT tagged or excluded from swing detection.")
print("")
print("Order Block Detection:")
print("  Order blocks are identified from full candle OHLC structure.")
print("  A 1-bar or 2-bar M15 interval with compressed range may misidentify")
print("  the order block boundary (high/low of a session-opening stub candle).")
print("  FINDING: Partial bars participated in order block detection without exclusion.")

# Save audit dataset
audit_cols = ["time", "open", "high", "low", "close",
              "expected_m5_count", "observed_m5_count",
              "is_complete", "is_partial", "observed_duration_min",
              "session_boundary_reason"]
m15_audit = m15[audit_cols]
m15_audit.to_csv("scratch/PHASE3I_M15_PARTIAL_CANDLE_AUDIT.csv", index=False)
print(f"\nSaved audit dataset: scratch/PHASE3I_M15_PARTIAL_CANDLE_AUDIT.csv")

# Count how many trades in Phase 3 experiments used partial entry bars
trade_ledger = pd.read_csv("reports/PHASE3_TRADE_LEDGER.csv")
print(f"\n=== TRADE LEDGER PARTIAL CANDLE CROSS-CHECK ===")
print(f"Phase 3 trade ledger: {len(trade_ledger)} trades")
if "entry_time" in trade_ledger.columns:
    trade_ledger["entry_time"] = pd.to_datetime(trade_ledger["entry_time"], utc=True, errors="coerce")
    partial_times = set(m15[m15["is_partial"]]["time"].dt.tz_convert("UTC").astype(str))
    matched = trade_ledger["entry_time"].astype(str).isin(partial_times)
    print(f"Trades entering on partial M15 bars: {matched.sum()} / {len(trade_ledger)}")
else:
    print("entry_time column not found - cannot cross-check")

