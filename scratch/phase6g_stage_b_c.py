"""
Phase 6G Stage B+C — Freeze candidate specs, session audit, M5 cost reconciliation.
Also prepares the 509-bar M15 validation window from raw data.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STRATEGY_REPORTS = ROOT / "reports" / "strategy"
DATA_DIR = ROOT / "data"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: Freeze candidate specs as immutable records
# ─────────────────────────────────────────────────────────────────────────────
frozen_specs = {
    "freeze_timestamp_utc": "2026-10-30T12:00:00Z",
    "git_head": "ad9807f8405811d65148d73d72139243f3d6a77f",
    "smc_v1_config_hash": "1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a",
    "candidates": {
        "C0_baseline": {
            "name": "SMC_v1_frozen_baseline",
            "version": "1.0.0",
            "session_filter_enabled": False,
            "session_start_hour_utc": None,
            "session_end_hour_utc": None,
            "use_opposing_liquidity_target": True,
            "fixed_rr": 2.0,
            "minimum_reward_risk": 1.0,
            "require_htf_confirmation": False,
        },
        "C1_session_filter": {
            "name": "SMC_v2_session_filtered",
            "version": "2.0.0-alpha.1",
            "session_filter_enabled": True,
            "session_start_hour_utc": 7,
            "session_end_hour_utc": 21,
            "filter_note": "Inclusive of 07:00, exclusive of 21:00. Signal time (bar close) determines session. UTC-only — no DST conversion.",
            "use_opposing_liquidity_target": True,
            "fixed_rr": 2.0,
            "minimum_reward_risk": 1.0,
            "require_htf_confirmation": False,
        },
        "C2_target_rationalized": {
            "name": "SMC_v2_target_rationalized",
            "version": "2.0.0-alpha.2",
            "session_filter_enabled": False,
            "session_start_hour_utc": None,
            "session_end_hour_utc": None,
            "use_opposing_liquidity_target": False,
            "fixed_rr": 2.0,
            "minimum_reward_risk": 1.0,
            "require_htf_confirmation": False,
        },
    },
    "backtest_config": {
        "initial_capital_usd": 10000.0,
        "risk_fraction": 0.01,
        "fallback_spread_usd": 0.20,
        "slippage_per_side_usd": 0.05,
        "commission_per_lot_per_side": 0.0,
        "contract_size_oz": 100.0,
        "cost_per_roundtrip_usd": 0.60,
        "position_sizing": "fraction_of_equity * risk_distance_adjusted",
    },
}

freeze_path = STRATEGY_REPORTS / "phase6g_frozen_candidate_specs.json"
with open(freeze_path, "w") as f:
    json.dump(frozen_specs, f, indent=2)
print(f"Frozen specs written: {freeze_path.name}")
freeze_hash = hashlib.sha256(freeze_path.read_bytes()).hexdigest()
print(f"Freeze file hash: {freeze_hash}")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: Session audit — M5 C0 vs C1 deep reconciliation
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("SECTION 2: M5 SESSION AUDIT — C0 vs C1 at trade level")
print("=" * 80)

m5_c0 = pd.read_csv(STRATEGY_REPORTS / "trades_M5_SMC_v1_frozen_baseline.csv")
m5_c1 = pd.read_csv(STRATEGY_REPORTS / "trades_M5_SMC_v2_session_filtered.csv")

for label, df in [("C0 (all hours)", m5_c0), ("C1 (07-21 filter)", m5_c1)]:
    closed = df[df["status"] == "CLOSED"].copy()
    closed["signal_time"] = pd.to_datetime(closed["signal_time"], utc=True, errors="coerce")
    closed["hour"] = closed["signal_time"].dt.hour

    # Session buckets
    def session_of(h):
        if 0 <= h < 7:   return "Asian(00-07)"
        if 7 <= h < 13:  return "London(07-13)"
        if 13 <= h < 17: return "NY_Overlap(13-17)"
        if 17 <= h < 21: return "NY_Afternoon(17-21)"
        return "Rollover(21-24)"

    closed["session"] = closed["hour"].map(session_of)
    breakdown = closed.groupby("session").agg(
        trades=("net_pnl", "count"),
        net_pnl=("net_pnl", "sum"),
        wins=("net_pnl", lambda x: (x > 0).sum()),
    ).assign(
        win_rate=lambda x: (x["wins"] / x["trades"] * 100).round(1),
        pf=lambda x: x.apply(lambda r: None, axis=1)
    )

    # Compute PF per session
    for sess in breakdown.index:
        g = closed[closed["session"] == sess]["net_pnl"]
        w = g[g > 0].sum()
        l = abs(g[g <= 0].sum())
        breakdown.loc[sess, "profit_factor"] = round(w / l, 3) if l > 0 else float("inf")

    breakdown = breakdown.drop(columns=["pf"])
    total_net = closed["net_pnl"].sum()

    print(f"\n{label} — total net: ${total_net:+,.2f} ({len(closed)} trades)")
    print(breakdown[["trades", "net_pnl", "win_rate", "profit_factor"]].to_string())

# Check: do C0 trades with hour 7-20 equal C1?
c0_closed = m5_c0[m5_c0["status"] == "CLOSED"].copy()
c0_closed["signal_time"] = pd.to_datetime(c0_closed["signal_time"], utc=True, errors="coerce")
c0_closed["hour"] = c0_closed["signal_time"].dt.hour
c0_liquid = c0_closed[(c0_closed["hour"] >= 7) & (c0_closed["hour"] < 21)]
c1_closed = m5_c1[m5_c1["status"] == "CLOSED"]

print(f"\nC0 trades in 07:00-20:59 window : {len(c0_liquid)}")
print(f"C1 closed trades               : {len(c1_closed)}")
print(f"C0 liquid net P&L              : ${c0_liquid['net_pnl'].sum():+,.2f}")
print(f"C1 net P&L                     : ${c1_closed['net_pnl'].sum():+,.2f}")
note = "NOTE: C1 may have fewer trades than C0 filtered subset — opposing_liquidity filter interacts with session gate at setup detection stage."
print(note)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: M5 cost reconciliation
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("SECTION 3: M5 COST RECONCILIATION")
print("=" * 80)

c0 = m5_c0[m5_c0["status"] == "CLOSED"]
if "total_transaction_costs" in c0.columns:
    total_costs = c0["total_transaction_costs"].sum()
    spread_costs = c0["spread_cost"].sum() if "spread_cost" in c0.columns else None
    slippage_costs = c0["slippage_cost"].sum() if "slippage_cost" in c0.columns else None
    gross_pnl = c0["gross_pnl"].sum() if "gross_pnl" in c0.columns else None
    net_pnl = c0["net_pnl"].sum()
    print(f"Total transaction costs : ${total_costs:,.2f}")
    print(f"  Spread costs          : ${spread_costs:,.2f}" if spread_costs else "  Spread: N/A")
    print(f"  Slippage costs        : ${slippage_costs:,.2f}" if slippage_costs else "  Slippage: N/A")
    print(f"Gross P&L               : ${gross_pnl:+,.2f}" if gross_pnl else "Gross: N/A")
    print(f"Net P&L                 : ${net_pnl:+,.2f}")
    if gross_pnl is not None:
        print(f"Implied cost drag       : ${gross_pnl - net_pnl:,.2f} (vs claimed ~$3,032)")
else:
    print("total_transaction_costs column not found — inspecting columns:")
    print(list(c0.columns))

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: Prepare 509-bar M15 validation window
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("SECTION 4: M15 RAW VALIDATION WINDOW PREPARATION")
print("=" * 80)

raw_m15 = pd.read_csv(DATA_DIR / "raw" / "XAUUSD_M15_raw.csv")
raw_m15["time"] = pd.to_datetime(raw_m15["time"], utc=True, errors="coerce")
raw_m15 = raw_m15.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)

# Boundary: processed M15 last bar
proc_m15_last = pd.Timestamp("2026-10-22 09:15:00+00:00")

# Eligible: strictly after last processed bar
validation_raw = raw_m15[raw_m15["time"] > proc_m15_last].copy()
print(f"Raw M15 total bars                  : {len(raw_m15)}")
print(f"Processed M15 last bar (UTC)        : {proc_m15_last}")
print(f"Validation window bars              : {len(validation_raw)}")
print(f"Validation first (UTC)              : {validation_raw['time'].iloc[0]}")
print(f"Validation last (UTC)               : {validation_raw['time'].iloc[-1]}")
print(f"Validation span days                : {(validation_raw['time'].iloc[-1] - validation_raw['time'].iloc[0]).days}")

# Check OHLC completeness
required_cols = ["time", "open", "high", "low", "close"]
missing_cols = [c for c in required_cols if c not in validation_raw.columns]
print(f"Missing required columns            : {missing_cols if missing_cols else 'None'}")

# Check price scale
print(f"Close price range                   : ${validation_raw['close'].min():.2f} — ${validation_raw['close'].max():.2f}")
print(f"Plausible XAUUSD scale (2500-3200)  : {2400 <= validation_raw['close'].min() <= 3500 and 2400 <= validation_raw['close'].max() <= 3500}")

# Check for gaps
diffs = validation_raw["time"].diff().dropna()
mode_gap = diffs.mode().iloc[0]
real_gaps = diffs[diffs > mode_gap * 2]
print(f"Intra-window gaps (>30min)          : {len(real_gaps)}")

# Check volume if available
if "volume" in validation_raw.columns:
    zero_vol = (validation_raw["volume"] == 0).sum()
    print(f"Zero-volume bars                    : {zero_vol}")

# Save the validation window (DO NOT overwrite canonical processed data)
val_path = DATA_DIR / "processed" / "XAUUSD_M15_validation_window.csv"
validation_raw.to_csv(val_path, index=False)
val_hash = hashlib.sha256(val_path.read_bytes()).hexdigest()
print(f"\nValidation window saved to          : {val_path.name}")
print(f"SHA-256                             : {val_hash}")
print(f"\nNOTE: This file is SEPARATE from XAUUSD_M15_clean.csv (canonical processed data)")
print(f"The 509-bar window has NOT been cleaned via the canonical cleaner pipeline.")
print(f"It must be treated as RAW DATA requiring validation before backtest use.")

