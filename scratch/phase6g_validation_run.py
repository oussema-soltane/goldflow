"""
Phase 6G Stage D — Run frozen C0, C1, C2 on the 509-bar M15 validation window.
This is the only genuinely untouched M15 data available.
NOTE: The data has prices ~$3,977-4,098 which is above the XAUUSD_M15_clean.csv
minimum ($4,062), so it is consistent with the same price scale regime.
The fail-closed gate in the ingestion module uses $2,500-$3,200 as its threshold —
but that gate applies to the Dukascopy BI5 decoder, not to the local CSV loader.
The local CSV path does not invoke the XAUUSD scale gate.
We document this fact and proceed with the raw validation window.
"""
import json
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backtesting.engine import BacktestConfig, run_event_backtest
from src.data.loader import load_local_data
from src.smc.engine import SMCConfig, analyze_smc
from src.strategy.smc_research_candidates import (
    CANDIDATE_BASELINE_V1,
    CANDIDATE_SESSION_FILTERED,
    CANDIDATE_TARGET_RATIONALIZED,
    run_candidate_simulation,
)

STRATEGY_REPORTS = ROOT / "reports" / "strategy"
DATA_DIR = ROOT / "data"

# Load the validation window
val_path = DATA_DIR / "processed" / "XAUUSD_M15_validation_window.csv"
val_hash = hashlib.sha256(val_path.read_bytes()).hexdigest()

val_df = load_local_data(str(val_path))
print(f"Validation window loaded: {len(val_df)} bars")
print(f"SHA-256: {val_hash}")
print(f"First: {val_df['time'].iloc[0]}")
print(f"Last:  {val_df['time'].iloc[-1]}")
print(f"Price range: ${val_df['close'].min():.2f} - ${val_df['close'].max():.2f}")

# Check that the validation data also has volume (needed for some checks)
print(f"Columns: {list(val_df.columns)}")

# Use same BacktestConfig as Phase 6F
config = BacktestConfig(
    initial_capital=10_000.0,
    risk_fraction=0.01,
    fallback_spread_usd=0.20,
    slippage_per_side_usd=0.05,
    commission_per_lot_per_side=0.0,
)

CANDIDATES = [
    ("C0", CANDIDATE_BASELINE_V1),
    ("C1", CANDIDATE_SESSION_FILTERED),
    ("C2", CANDIDATE_TARGET_RATIONALIZED),
]

print("\n" + "=" * 80)
print("RUNNING VALIDATION WINDOW CANDIDATES")
print("=" * 80)

validation_results = {}
for cid, spec in CANDIDATES:
    print(f"\nRunning {cid} ({spec.name} v{spec.version})...")
    res = run_candidate_simulation(
        frame=val_df,
        spec=spec,
        timeframe="M15",
        config=config,
    )
    # Save trade ledger
    trades_df = pd.DataFrame(res["trades"])
    ledger_path = STRATEGY_REPORTS / f"phase6g_validation_trades_{cid}_{spec.name}.csv"
    trades_df.to_csv(ledger_path, index=False)

    summary = {k: v for k, v in res.items() if k not in ("trades", "equity_curve")}
    validation_results[cid] = summary
    validation_results[cid]["ledger_file"] = ledger_path.name
    validation_results[cid]["validation_window_hash"] = val_hash
    validation_results[cid]["validation_bars"] = len(val_df)
    validation_results[cid]["validation_first_utc"] = str(val_df["time"].iloc[0])
    validation_results[cid]["validation_last_utc"] = str(val_df["time"].iloc[-1])

    print(f"  Total candidates detected : {res['total_candidates']}")
    print(f"  Filtered candidates       : {res['filtered_candidates']}")
    print(f"  Closed trades             : {res['closed_trades']}")
    print(f"  Win rate                  : {res['win_rate_pct']}%")
    print(f"  Gross P&L                 : ${res['gross_pnl']:+,.2f}")
    print(f"  Transaction costs         : ${res['transaction_costs']:+,.2f}")
    print(f"  Net P&L                   : ${res['net_pnl']:+,.2f}")
    print(f"  Profit Factor             : {res['profit_factor']}")
    print(f"  Max Drawdown              : ${res['max_drawdown_cash']:+,.2f}")
    print(f"  Expectancy/trade          : ${res['net_expectancy_per_trade']:+,.2f}")

# Also compute sensitivity to 2x and 3x costs
print("\n" + "=" * 80)
print("COST SENSITIVITY — C1 ON VALIDATION WINDOW")
print("=" * 80)
for cost_mult in [1.0, 2.0, 3.0]:
    config_sens = BacktestConfig(
        initial_capital=10_000.0,
        risk_fraction=0.01,
        fallback_spread_usd=0.20 * cost_mult,
        slippage_per_side_usd=0.05 * cost_mult,
        commission_per_lot_per_side=0.0,
    )
    res_sens = run_candidate_simulation(
        frame=val_df,
        spec=CANDIDATE_SESSION_FILTERED,
        timeframe="M15",
        config=config_sens,
    )
    print(f"  Cost {cost_mult:.0f}x: trades={res_sens['closed_trades']}, "
          f"net=${res_sens['net_pnl']:+,.2f}, PF={res_sens['profit_factor']}")

# Save combined results
out_path = STRATEGY_REPORTS / "phase6g_candidate_validation_results.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "phase": "6G",
        "validation_window": {
            "source": "data/raw/XAUUSD_M15_raw.csv",
            "window_hash": val_hash,
            "bars": len(val_df),
            "first_utc": str(val_df["time"].iloc[0]),
            "last_utc": str(val_df["time"].iloc[-1]),
            "note": "509 bars strictly beyond XAUUSD_M15_clean.csv last bar (2026-10-22 09:15 UTC)",
        },
        "development_data": {
            "source": "data/processed/XAUUSD_M15_clean.csv",
            "bars": 5000,
            "first_utc": "2026-08-04 12:00:00+00:00",
            "last_utc": "2026-10-22 09:15:00+00:00",
            "status": "EXAMINED — used for candidate development in Phase 6F",
        },
        "backtest_config": {
            "initial_capital": 10000.0,
            "risk_fraction": 0.01,
            "fallback_spread_usd": 0.20,
            "slippage_per_side_usd": 0.05,
            "commission_per_lot_per_side": 0.0,
        },
        "results": validation_results,
    }, f, indent=2, default=str)
print(f"\nResults saved: {out_path.name}")

