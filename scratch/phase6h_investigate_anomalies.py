"""
Phase 6H Investigation of Numerical Anomalies:
1. Anomaly A: Why C0, C1, C2 all reported max_drawdown_cash = $177.48
2. Anomaly B: Cost sensitivity (1x: -$83.12, 2x: -$85.47, 3x: -$76.63)
3. Anomaly C: Recalculate all metrics and compare realized vs MTM drawdown.
"""
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
STRATEGY_REPORTS = ROOT / "reports" / "strategy"

# 1. Inspect trade files
files = {
    "C0": list(STRATEGY_REPORTS.glob("phase6g_validation_trades_C0_*.csv"))[0],
    "C1": list(STRATEGY_REPORTS.glob("phase6g_validation_trades_C1_*.csv"))[0],
    "C2": list(STRATEGY_REPORTS.glob("phase6g_validation_trades_C2_*.csv"))[0],
}

print("=" * 80)
print("ANOMALY A: DRAWDOWN RECONSTRUCTION")
print("=" * 80)

for name, path in files.items():
    df = pd.read_csv(path)
    closed = df[df["status"] == "CLOSED"].copy()
    print(f"\n--- {name}: {path.name} ({len(closed)} closed trades) ---")
    cols = ["setup_id", "entry_time", "exit_time", "direction", "lots", "risk_budget_cash", "net_pnl", "exit_reason"]
    print(closed[[c for c in cols if c in closed.columns]].to_string())

    # Realized equity curve from trades
    realized_equity = [10000.0]
    for pnl in closed["net_pnl"]:
        realized_equity.append(realized_equity[-1] + pnl)
    
    # Realized drawdown
    peak = 10000.0
    realized_dd = 0.0
    for eq in realized_equity:
        peak = max(peak, eq)
        realized_dd = max(realized_dd, peak - eq)
    print(f"Reconstructed Realized DD: ${realized_dd:.2f}")

# Now let's run the actual backtest on the validation data and inspect the MTM equity curve!
import sys
sys.path.insert(0, str(ROOT))
from src.data.loader import load_local_data
from src.backtesting.engine import BacktestConfig, run_event_backtest
from src.strategy.smc_research_candidates import (
    CANDIDATE_BASELINE_V1,
    CANDIDATE_SESSION_FILTERED,
    CANDIDATE_TARGET_RATIONALIZED,
    run_candidate_simulation,
)

val_df = load_local_data(str(ROOT / "data" / "processed" / "XAUUSD_M15_validation_window.csv"))
config = BacktestConfig(
    initial_capital=10000.0,
    risk_fraction=0.01,
    fallback_spread_usd=0.20,
    slippage_per_side_usd=0.05,
    commission_per_lot_per_side=0.0,
)

print("\n" + "=" * 80)
print("DETAILED SIMULATION RUN FOR C0, C1, C2")
print("=" * 80)

for name, spec in [("C0", CANDIDATE_BASELINE_V1), ("C1", CANDIDATE_SESSION_FILTERED), ("C2", CANDIDATE_TARGET_RATIONALIZED)]:
    res = run_candidate_simulation(frame=val_df, spec=spec, timeframe="M15", config=config)
    print(f"\n{name} ({spec.name}):")
    print(f"  Closed trades: {res['closed_trades']}")
    print(f"  Net PnL: ${res['net_pnl']:.2f}")
    print(f"  Reported max_drawdown_cash (MTM): ${res['max_drawdown_cash']:.2f}")
    
    # Let's inspect the equity curve in res['equity_curve']
    eq_curve = res["equity_curve"]
    mtm_eq = [p["equity"] for p in eq_curve]
    real_eq = [p["realized_equity"] for p in eq_curve]
    
    # Calculate MTM peak-to-trough
    peak = 10000.0
    max_mtm_dd = 0.0
    worst_point = None
    for p in eq_curve:
        eq = p["equity"]
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_mtm_dd:
            max_mtm_dd = dd
            worst_point = (p["time"], peak, eq, dd, p["open_positions"], p["unrealized_pnl"])
    
    print(f"  Calculated MTM Max DD: ${max_mtm_dd:.2f}")
    print(f"  Worst MTM Point: {worst_point}")
    
    # Calculate Realized peak-to-trough from curve
    peak_r = 10000.0
    max_real_dd = 0.0
    for p in eq_curve:
        eq = p["realized_equity"]
        peak_r = max(peak_r, eq)
        max_real_dd = max(max_real_dd, peak_r - eq)
    print(f"  Calculated Realized Max DD from curve: ${max_real_dd:.2f}")

print("\n" + "=" * 80)
print("ANOMALY B: COST SENSITIVITY DEEP DIVE")
print("=" * 80)
# Run C1 with 1x, 2x, 3x costs and print trade-by-trade comparison
for mult in [1.0, 2.0, 3.0]:
    cfg = BacktestConfig(
        initial_capital=10000.0,
        risk_fraction=0.01,
        fallback_spread_usd=0.20 * mult,
        slippage_per_side_usd=0.05 * mult,
        commission_per_lot_per_side=0.0,
    )
    res = run_candidate_simulation(frame=val_df, spec=CANDIDATE_SESSION_FILTERED, timeframe="M15", config=cfg)
    trades = [t for t in res["trades"] if t.get("status") == "CLOSED"]
    print(f"\n--- Cost Multiplier {mult}x (Spread=${0.20*mult:.2f}, Slip=${0.05*mult:.2f}) ---")
    print(f"Total Net PnL: ${res['net_pnl']:.2f}, Total Costs: ${res['transaction_costs']:.2f}")
    df_t = pd.DataFrame(trades)[["setup_id", "entry_time", "entry_price", "exit_price", "lots", "risk_budget_cash", "raw_gross_pnl", "total_transaction_costs", "net_pnl", "exit_reason"]]
    print(df_t.to_string())
