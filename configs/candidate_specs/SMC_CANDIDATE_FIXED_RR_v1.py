"""
Task 6: Define the 2R/3R Fixed Target SMC Candidate Experiment specification.
This file documents the candidate strategy configuration, comparison methodology,
and evaluation criteria before any experimental run is performed.
"""

CANDIDATE_SPEC = {
    "spec_version": "1.0",
    "created_utc": "2026-11-04T11:00:00Z",
    "experiment_id": "SMC_CANDIDATE_FIXED_RR_v1",
    "experiment_name": "Fixed 2R/3R Target with Partial Exit — SMC Candidate",
    "baseline_id": "SMC_BASELINE_LIQUIDITY_POOLS",
    "baseline_description": (
        "Sweep → CHoCH → Order Block Retest strategy using the nearest unmitigated "
        "opposing liquidity pool as the take-profit target. Zero partial exits. "
        "Backtest baseline results (zero commission): H4 +$448.73 PF 1.540, "
        "H1 -$339.41 PF 0.917, M15 -$239.12 PF 0.922, M5 -$4,955.63 PF 0.873."
    ),

    # --- CANDIDATE STRATEGY RULES ---
    "candidate_strategy": {
        "entry_rule": "Identical to baseline: Sweep → confirmed CHoCH → retest of origin OB zone on the following bar open.",
        "stop_loss_rule": "Identical to baseline: invalidation of the entry OB (close beyond the far boundary).",
        "take_profit_rule": (
            "CHANGED from baseline: "
            "Replace opposing liquidity pool target with a fixed multiple of the initial risk. "
            "Target 1 (partial exit): 2R (200% of initial risk distance). Exit 50% of position. "
            "Target 2 (remaining position): 3R (300% of initial risk distance). Exit remaining 50%. "
            "If a liquidity pool is encountered BEFORE 2R, it is noted but does NOT override the fixed target."
        ),
        "time_stop_rule": "Identical to baseline: None (no time-based exit, unless max_holding_bars is configured).",
        "concurrency_rule": "Identical to baseline: max_concurrent_positions=1 per timeframe.",
        "position_sizing_rule": "Identical to baseline: fixed fractional 1% equity risk per trade.",
    },

    # --- RATIONALE ---
    "rationale": [
        "The baseline strategy's core weakness (from quantitative forensic analysis): "
        "distant unmitigated opposing liquidity pools are frequently NOT reached before "
        "trailing price structure reverses and hits the stop loss. The result is an "
        "asymmetric outcome skew — winners are small (truncated by far TP) and losers "
        "consume 1R. This degraded PF<1 in H1, M15, M5.",
        "Fixed 2R/3R targets reduce dependency on pool location, forcing earlier partial "
        "exit at a mechanically reachable level while allowing a runner for trending conditions.",
        "The partial exit at 2R locks in profit and reduces the financial impact of stop-loss "
        "hits on the remaining position, improving the expectancy distribution.",
        "ADR-006 formally proposed this change. This experiment provides the quantitative test.",
    ],

    # --- IMPLEMENTATION PLAN ---
    "implementation": {
        "primary_change": "Add partial_exit_at_r and remaining_exit_at_r parameters to BacktestConfig.",
        "secondary_change": "Add partial exit logic to run_event_backtest: at 2R, reduce position to 50%; at 3R, close remainder.",
        "files_to_modify": ["src/backtesting/engine.py"],
        "files_NOT_to_modify": ["src/smc/engine.py", "src/strategy/smc_setups.py"],
        "new_test_file": "tests/test_candidate_fixed_rr.py",
        "note": "SMC detection engine and signal generation are NOT modified. Only the exit logic changes.",
    },

    # --- DATA PERIODS ---
    "data_periods": {
        "development_period": {
            "H4": "2023-07-27 to 2025-06-30 (approx first 60% of H4 dataset)",
            "H1": "2025-01-31 to 2025-11-30 (approx first 60% of H1 dataset)",
            "M15": "2026-08-04 to 2026-09-15 (approx first 60% of M15 dataset)",
            "M5": "2025-01-31 to 2025-11-30 (approx first 60% of M5 dataset)",
        },
        "validation_period": {
            "H4": "2025-07-01 to 2026-10-20 (remaining 40%)",
            "H1": "2025-12-01 to 2026-10-20 (remaining 40%)",
            "M15": "2026-09-16 to 2026-10-22 (remaining 40%)",
            "M5": "2025-12-01 to 2026-10-20 (remaining 40%)",
        },
        "holdout_status": "LOCKED. The validation period is NOT used for parameter optimization. "
                          "It is used ONLY for a single confirmatory evaluation after development.",
    },

    # --- COMPARISON METHODOLOGY ---
    "comparison_methodology": {
        "execution_assumptions": "Identical to baseline: same spread, slippage, commission (0.0), "
                                 "contract size, point size, lot step.",
        "data_used": "Identical processed datasets from data/processed/.",
        "signal_source": "Identical SMC setup candidates (identical scan via detect_smc_setups_with_funnel).",
        "mode": "full-history (same as baseline for reproducibility).",
        "metrics_to_compare": [
            "net_profit_usd", "profit_factor", "win_rate_pct",
            "max_drawdown_cash", "max_drawdown_pct", "expectancy_per_rule_exit",
            "average_R_multiple", "total_transaction_costs", "closed_trades",
        ],
    },

    # --- EVALUATION CRITERIA ---
    "evaluation_criteria": {
        "threshold_for_promotion": [
            "Profit Factor >= 1.10 on development period (H1 and/or M15).",
            "Max drawdown <= 20% on development period.",
            "No statistically significant improvement on H4 baseline (must not degrade H4).",
            "Validation period result directionally consistent with development period result.",
        ],
        "threshold_for_rejection": [
            "Profit Factor <= 0.90 on development period.",
            "Max drawdown > 25% on development period.",
            "Development and validation periods have contradictory directional results (overfit signal).",
        ],
        "interpretation_caveat": (
            "A favorable backtest result, including promotion above threshold, does NOT constitute "
            "proof of future profitability. It constitutes evidence that the candidate performed "
            "better than the baseline on the available synthetic-provenance historical data. "
            "The strategy requires out-of-sample live paper trading before any capital deployment."
        ),
    },

    # --- STATUS ---
    "status": "DEFINED — not yet executed. Run experiments only after this spec is committed and reviewed.",
}

if __name__ == "__main__":
    import json
    from pathlib import Path
    out = Path("configs/candidate_specs/SMC_CANDIDATE_FIXED_RR_v1.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(CANDIDATE_SPEC, indent=2), encoding="utf-8")
    print(f"Candidate spec written to: {out}")
    print(json.dumps(CANDIDATE_SPEC, indent=2))

