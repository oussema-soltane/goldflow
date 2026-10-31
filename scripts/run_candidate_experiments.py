"""
GoldFlow — Run Experimental SMC Candidate Simulations (Phase 6 Research).

Executes research candidates across canonical datasets (M5 and M15) under strict causal
isolation and realistic execution costs ($0.30 fixed spread + $0.10 slippage).
Saves results to reports/strategy/candidate_experiments_results.json.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.backtesting.engine import BacktestConfig
from src.data.loader import load_local_data
from src.strategy.smc_research_candidates import (
    CANDIDATE_BASELINE_V1,
    CANDIDATE_SESSION_FILTERED,
    CANDIDATE_TARGET_RATIONALIZED,
    CANDIDATE_COMPOSITE_LIQUID,
    CANDIDATE_NY_SESSION,
    CANDIDATE_MTF_ALIGNED,
    ResearchCandidateSpec,
    run_candidate_simulation,
)


def main() -> None:
    print("=" * 80)
    print("GOLDFLOW — SMC RESEARCH CANDIDATE EXPERIMENTS")
    print("=" * 80)

    # 1. Load canonical data
    data_dir = PROJECT_ROOT / "data" / "processed"
    m5_path = data_dir / "XAUUSD_M5_clean.csv"
    m15_path = data_dir / "XAUUSD_M15_clean.csv"
    h1_path = data_dir / "XAUUSD_H1_clean.csv"
    h4_path = data_dir / "XAUUSD_H4_clean.csv"

    print(f"Loading canonical datasets from {data_dir}...")
    m5_df = load_local_data(str(m5_path))
    m15_df = load_local_data(str(m15_path))
    h1_df = load_local_data(str(h1_path))
    h4_df = load_local_data(str(h4_path))
    print(f"Loaded M5 ({len(m5_df)} bars), M15 ({len(m15_df)} bars), H1 ({len(h1_df)} bars), H4 ({len(h4_df)} bars)")

    candidates: list[ResearchCandidateSpec] = [
        CANDIDATE_BASELINE_V1,
        CANDIDATE_SESSION_FILTERED,
        CANDIDATE_TARGET_RATIONALIZED,
        CANDIDATE_COMPOSITE_LIQUID,
        CANDIDATE_NY_SESSION,
        CANDIDATE_MTF_ALIGNED,
    ]

    out_dir = PROJECT_ROOT / "reports" / "strategy"
    out_dir.mkdir(parents=True, exist_ok=True)

    results_summary: list[dict] = []
    config = BacktestConfig(
        initial_capital=10_000.0,
        risk_fraction=0.01,
        fallback_spread_usd=0.20,
        slippage_per_side_usd=0.05,
        commission_per_lot_per_side=0.0,
    )

    # Test M5
    print("\n--- RUNNING M5 CANDIDATE SUITE ---")
    for cand in candidates:
        print(f"Simulating M5: {cand.name} ({cand.version})...")
        res = run_candidate_simulation(
            frame=m5_df,
            spec=cand,
            timeframe="M5",
            config=config,
            h4_df=h4_df,
            h1_df=h1_df,
        )
        
        # Save individual trades
        trades_df = pd.DataFrame(res["trades"])
        trade_file = out_dir / f"trades_M5_{cand.name}.csv"
        trades_df.to_csv(trade_file, index=False)
        
        # Save summary item (without bulky trades / equity arrays)
        summary_item = {k: v for k, v in res.items() if k not in ("trades", "equity_curve")}
        summary_item["trades_file"] = str(trade_file.relative_to(PROJECT_ROOT))
        results_summary.append(summary_item)
        print(f"  Closed Trades: {res['closed_trades']} | Win Rate: {res['win_rate_pct']}% | Net P&L: ${res['net_pnl']:+,.2f} | PF: {res['profit_factor']} | Max DD: ${res['max_drawdown_cash']:,.2f}")

    # Test M15
    print("\n--- RUNNING M15 CANDIDATE SUITE ---")
    for cand in candidates:
        print(f"Simulating M15: {cand.name} ({cand.version})...")
        res = run_candidate_simulation(
            frame=m15_df,
            spec=cand,
            timeframe="M15",
            config=config,
            h4_df=h4_df,
            h1_df=h1_df,
        )
        
        # Save individual trades
        trades_df = pd.DataFrame(res["trades"])
        trade_file = out_dir / f"trades_M15_{cand.name}.csv"
        trades_df.to_csv(trade_file, index=False)
        
        # Save summary item
        summary_item = {k: v for k, v in res.items() if k not in ("trades", "equity_curve")}
        summary_item["trades_file"] = str(trade_file.relative_to(PROJECT_ROOT))
        results_summary.append(summary_item)
        print(f"  Closed Trades: {res['closed_trades']} | Win Rate: {res['win_rate_pct']}% | Net P&L: ${res['net_pnl']:+,.2f} | PF: {res['profit_factor']} | Max DD: ${res['max_drawdown_cash']:,.2f}")

    # Write combined summary JSON
    results_json = out_dir / "candidate_experiments_results.json"
    with open(results_json, "w", encoding="utf-8") as f:
        json.dump(results_summary, f, indent=2)
    print(f"\nAll candidate simulation results saved to {results_json}")

    # Print markdown comparison table
    print("\n" + "=" * 100)
    print(f"{'Timeframe':<10} | {'Candidate Name':<28} | {'Trades':<7} | {'WinRate':<8} | {'Net P&L ($)':<14} | {'PF':<7} | {'Max DD ($)':<12} | {'Expectancy'}")
    print("-" * 100)
    for r in results_summary:
        pf_str = f"{r['profit_factor']:.3f}" if r['profit_factor'] is not None else "N/A"
        print(f"{r['timeframe']:<10} | {r['candidate_name']:<28} | {r['closed_trades']:<7} | {r['win_rate_pct']:<7.1f}% | {r['net_pnl']:>+14.2f} | {pf_str:<7} | {r['max_drawdown_cash']:>12.2f} | {r['net_expectancy_per_trade']:>+8.2f}")
    print("=" * 100)


if __name__ == "__main__":
    main()
