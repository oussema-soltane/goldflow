"""
Phase 6G Stage A — Re-verify Phase 6F results from source trade ledgers.
Reads the actual CSV trade ledgers produced by run_candidate_experiments.py
and recalculates all reported metrics independently.
Flags any discrepancy between stored JSON and recalculated values.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STRATEGY_REPORTS = ROOT / "reports" / "strategy"

# Phase 6F claimed figures for cross-check
CLAIMED = {
    "M5_SMC_v1_frozen_baseline":   {"closed_trades": 842, "net_pnl": -4955.63, "profit_factor": 0.878},
    "M5_SMC_v2_session_filtered":  {"closed_trades": 539, "net_pnl": -2365.82, "profit_factor": 0.928},
    "M5_SMC_v2_target_rationalized": {"closed_trades": 1188, "net_pnl": -6543.10, "profit_factor": 0.881},
    "M5_SMC_v2_composite_liquid":  {"closed_trades": 779, "net_pnl": -3507.86, "profit_factor": 0.921},
    "M5_SMC_v2_ny_session":        {"closed_trades": 415, "net_pnl": -3623.11, "profit_factor": 0.849},
    "M5_SMC_v2_mtf_aligned":       {"closed_trades": 262, "net_pnl": -2412.35, "profit_factor": 0.848},
    "M15_SMC_v1_frozen_baseline":  {"closed_trades": 40,  "net_pnl": -239.12,  "profit_factor": 0.913},
    "M15_SMC_v2_session_filtered": {"closed_trades": 29,  "net_pnl": 479.31,   "profit_factor": 1.257},
    "M15_SMC_v2_target_rationalized": {"closed_trades": 59, "net_pnl": 282.81, "profit_factor": 1.082},
    "M15_SMC_v2_composite_liquid": {"closed_trades": 35,  "net_pnl": -267.27,  "profit_factor": 0.876},
    "M15_SMC_v2_ny_session":       {"closed_trades": 21,  "net_pnl": -567.22,  "profit_factor": 0.604},
    "M15_SMC_v2_mtf_aligned":      {"closed_trades": 6,   "net_pnl": -515.58,  "profit_factor": 0.000},
}


def recalc_from_ledger(csv_path: Path) -> dict:
    """Independently recalculate metrics from a trade-ledger CSV."""
    if not csv_path.exists():
        return {"error": f"File not found: {csv_path}"}
    df = pd.read_csv(csv_path)
    closed = df[df["status"] == "CLOSED"] if "status" in df.columns else df
    n = len(closed)
    if n == 0:
        return {"closed_trades": 0, "net_pnl": 0.0, "profit_factor": 0.0}

    net_pnl = float(closed["net_pnl"].sum())
    wins = closed[closed["net_pnl"] > 0]
    losses = closed[closed["net_pnl"] <= 0]
    gross_wins = float(wins["net_pnl"].sum()) if not wins.empty else 0.0
    gross_losses = abs(float(losses["net_pnl"].sum())) if not losses.empty else 0.0
    pf = gross_wins / gross_losses if gross_losses > 0 else (float("inf") if gross_wins > 0 else 0.0)
    wr = len(wins) / n * 100 if n > 0 else 0.0
    avg_win = float(wins["net_pnl"].mean()) if not wins.empty else 0.0
    avg_loss = abs(float(losses["net_pnl"].mean())) if not losses.empty else 0.0
    costs = float(closed["total_transaction_costs"].sum()) if "total_transaction_costs" in closed.columns else None

    # Max drawdown via equity curve
    equity = closed["net_pnl"].cumsum() + 10000.0
    peak = equity.cummax()
    dd = peak - equity
    max_dd = float(dd.max())

    return {
        "closed_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(wr, 2),
        "net_pnl": round(net_pnl, 2),
        "gross_wins": round(gross_wins, 2),
        "gross_losses": round(gross_losses, 2),
        "profit_factor": round(pf, 3) if np.isfinite(pf) else pf,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "total_costs": round(costs, 2) if costs is not None else None,
        "max_drawdown_cash": round(max_dd, 2),
        "expectancy": round(net_pnl / n, 2),
    }


print("=" * 90)
print("PHASE 6G — STAGE A: PHASE 6F RESULT VERIFICATION")
print("=" * 90)

discrepancies = []
results_6g_a = {}

for key, claimed in CLAIMED.items():
    tf, *name_parts = key.split("_", 1)
    cand_name = name_parts[0] if name_parts else key
    csv_file = STRATEGY_REPORTS / f"trades_{key}.csv"
    actual = recalc_from_ledger(csv_file)
    results_6g_a[key] = {"claimed": claimed, "recalculated": actual}

    print(f"\n{key}")
    if "error" in actual:
        print(f"  ERROR: {actual['error']}")
        discrepancies.append({"key": key, "issue": actual["error"]})
        continue

    for metric in ("closed_trades", "net_pnl", "profit_factor"):
        c_val = claimed[metric]
        a_val = actual.get(metric)
        if a_val is None:
            match = "N/A"
        elif isinstance(c_val, int):
            match = "OK" if c_val == a_val else f"MISMATCH (claimed={c_val}, actual={a_val})"
        else:
            match = "OK" if abs(c_val - a_val) < 0.01 else f"MISMATCH (claimed={c_val}, actual={a_val})"
        print(f"  {metric:25s}: claimed={c_val}, recalc={a_val}  {match}")
        if "MISMATCH" in str(match):
            discrepancies.append({"key": key, "metric": metric, "claimed": c_val, "actual": a_val})

    # Extra detail for key candidates
    if "M15_SMC_v2_session" in key:
        print(f"  [DETAIL] wins={actual['wins']}, losses={actual['losses']}, WR={actual['win_rate_pct']}%")
        print(f"  [DETAIL] avg_win=${actual['avg_win']}, avg_loss=${actual['avg_loss']}")
        print(f"  [DETAIL] total_costs=${actual['total_costs']}, max_dd=${actual['max_drawdown_cash']}")
        print(f"  [DETAIL] expectancy/trade=${actual['expectancy']}")

print("\n" + "=" * 90)
if discrepancies:
    print(f"DISCREPANCIES FOUND: {len(discrepancies)}")
    for d in discrepancies:
        print(f"  {d}")
else:
    print("ALL REPORTED FIGURES VERIFIED — no discrepancies found.")

# Save result
out_path = STRATEGY_REPORTS / "phase6g_stage_a_verification.json"
with open(out_path, "w") as f:
    json.dump({"discrepancies": discrepancies, "detail": results_6g_a}, f, indent=2, default=str)
print(f"\nSaved: {out_path.name}")
