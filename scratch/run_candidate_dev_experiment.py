import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

from src.backtesting.engine import BacktestConfig, run_event_backtest
from src.smc.engine import SMCConfig, analyze_smc
from src.strategy.smc_setups import SMCSetupConfig, detect_smc_setups_with_funnel

ROOT = Path(".")
data_dir = ROOT / "data" / "processed"
reports_dir = ROOT / "reports" / "strategy"
reports_dir.mkdir(parents=True, exist_ok=True)

timeframes = ["H4", "H1", "M15", "M5"]

def _candidate_records(candidates, timeframe):
    records = []
    for n, candidate in enumerate(candidates, start=1):
        record = candidate.to_dict()
        record["setup_id"] = f"SMC_{timeframe}_{n:04d}"
        record["timeframe"] = timeframe
        records.append(record)
    return records

results = {
    "experiment_id": "SMC_CANDIDATE_FIXED_RR_v1",
    "experiment_name": "Fixed 2R/3R Target with Partial Exit vs Baseline (Development Split 60%)",
    "split_ratio": 0.60,
    "validation_holdout_locked": True,
    "timeframes": {},
}

cfg_baseline = BacktestConfig(
    initial_capital=10000.0,
    risk_fraction=0.01,
    fallback_spread_usd=0.20,
    slippage_per_side_usd=0.05,
    commission_per_lot_per_side=0.0,
    partial_exit_at_r=0.0,
    remaining_exit_at_r=0.0,
)

cfg_candidate = BacktestConfig(
    initial_capital=10000.0,
    risk_fraction=0.01,
    fallback_spread_usd=0.20,
    slippage_per_side_usd=0.05,
    commission_per_lot_per_side=0.0,
    partial_exit_at_r=2.0,
    remaining_exit_at_r=3.0,
)

for tf in timeframes:
    csv_path = data_dir / f"XAUUSD_{tf}_clean.csv"
    df = pd.read_csv(csv_path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    n_total = len(df)
    n_dev = int(n_total * 0.6)
    dev_df = df.iloc[:n_dev].copy().reset_index(drop=True)
    val_df = df.iloc[n_dev:].copy().reset_index(drop=True)
    
    print(f"\nProcessing {tf} (Total: {n_total}, Dev: {n_dev} bars, Val: {len(val_df)} bars)...")
    analysis = analyze_smc(dev_df, symbol="XAUUSD", timeframe=tf, config=SMCConfig())
    candidates, funnel = detect_smc_setups_with_funnel(dev_df, analysis, SMCSetupConfig())
    records = _candidate_records(candidates, tf)
    
    res_base = run_event_backtest(dev_df, records, cfg_baseline, timeframe=tf)
    res_cand = run_event_backtest(dev_df, records, cfg_candidate, timeframe=tf)
    
    def extract_metrics(m):
        return {
            "candidate_count": m.get("candidate_count", 0),
            "closed_trades": m.get("closed_trades", 0),
            "rule_exit_trades": m.get("rule_exit_trades", 0),
            "end_of_data_exits": m.get("end_of_data_exits", 0),
            "win_rate_pct": m.get("win_rate_pct"),
            "net_profit": round(m.get("net_profit", 0.0), 2),
            "return_pct": round(m.get("return_pct", 0.0), 2),
            "profit_factor": round(m.get("profit_factor", 0.0), 3) if m.get("profit_factor") is not None else None,
            "max_drawdown_cash": round(m.get("max_drawdown_cash", 0.0), 2),
            "max_drawdown_pct": round(m.get("max_drawdown_pct", 0.0), 2),
            "average_R_multiple": round(m.get("average_R_multiple", 0.0), 3) if m.get("average_R_multiple") is not None else None,
            "expectancy_per_rule_exit": round(m.get("expectancy_per_rule_exit", 0.0), 2) if m.get("expectancy_per_rule_exit") is not None else None,
        }

    m_base = extract_metrics(res_base.metrics)
    m_cand = extract_metrics(res_cand.metrics)
    
    delta_net = round(m_cand["net_profit"] - m_base["net_profit"], 2)
    delta_pf = round((m_cand["profit_factor"] or 0.0) - (m_base["profit_factor"] or 0.0), 3)
    
    print(f"  Baseline : Net={m_base['net_profit']}, PF={m_base['profit_factor']}, WR={m_base['win_rate_pct']}%, Trades={m_base['closed_trades']}")
    print(f"  Candidate: Net={m_cand['net_profit']}, PF={m_cand['profit_factor']}, WR={m_cand['win_rate_pct']}%, Trades={m_cand['closed_trades']}")
    print(f"  Delta    : Net Delta=${delta_net:+,.2f}, PF Delta={delta_pf:+.3f}")
    
    results["timeframes"][tf] = {
        "dev_period": {
            "start": dev_df["time"].iloc[0].isoformat(),
            "end": dev_df["time"].iloc[-1].isoformat(),
            "bars": n_dev,
        },
        "val_period_locked": {
            "start": val_df["time"].iloc[0].isoformat(),
            "end": val_df["time"].iloc[-1].isoformat(),
            "bars": len(val_df),
            "status": "LOCKED_HOLDOUT",
        },
        "baseline": m_base,
        "candidate": m_cand,
        "delta": {
            "net_profit_delta_usd": delta_net,
            "profit_factor_delta": delta_pf,
        }
    }

out_file = reports_dir / "candidate_fixed_rr_dev_results.json"
out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"\nWrote results to {out_file}")
