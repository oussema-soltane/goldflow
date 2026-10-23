"""Run a frozen-rule chronological holdout and transaction-cost stress test.

This is a temporal holdout using the bundled historical sample, not an
independent untouched validation set: Phase 3C/3D research has already examined
these histories. Keep the SMC/entry rules fixed and use genuinely new data for
confirmatory evidence.

Examples:
  python scripts/run_smc_validation.py
  python scripts/run_smc_validation.py --train-fraction 0.70 --timeframes H4 H1 M15 M5
  python scripts/run_smc_validation.py --commission-per-lot-per-side 3.5
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backtesting.engine import BacktestConfig, run_event_backtest
from src.research.data_readiness import audit_all_datasets, evaluate_research_readiness
from src.research.execution_spec_audit import audit_processed_execution_specs
from src.research.smc_research import load_and_verify_inputs
from src.smc.engine import SMCConfig, analyze_smc
from src.strategy.smc_setups import SMCSetupConfig, detect_smc_setups_with_funnel

TIMEFRAMES = ["H4", "H1", "M15", "M5"]
COST_MULTIPLIERS = (1.0, 1.5, 2.0)


def chronological_split_index(n_rows: int, train_fraction: float = 0.70) -> int:
    """Return the first holdout row index for a deterministic chronological split."""
    if n_rows < 3:
        raise ValueError("At least 3 bars are required for a chronological holdout")
    if not 0.5 <= train_fraction < 1.0:
        raise ValueError("train_fraction must be in [0.5, 1.0)")
    index = int(math.floor(n_rows * train_fraction))
    return max(1, min(n_rows - 1, index))


def filter_candidates_from_index(candidates: Iterable[Any], split_index: int) -> list[Any]:
    """Keep only candidates signaled on or after the holdout boundary."""
    kept = []
    for candidate in candidates:
        raw = candidate.get("signal_index") if isinstance(candidate, Mapping) else getattr(candidate, "signal_index", None)
        if raw is None:
            raise ValueError("Every candidate must have signal_index for holdout filtering")
        try:
            signal_index = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid candidate signal_index: {raw!r}") from exc
        if signal_index >= split_index:
            kept.append(candidate)
    return kept


def _candidate_records(candidates: list[Any], timeframe: str) -> list[dict[str, Any]]:
    records = []
    for n, candidate in enumerate(candidates, start=1):
        record = candidate.to_dict() if hasattr(candidate, "to_dict") else dict(candidate)
        record["setup_id"] = f"OOS_SMC_{timeframe}_{n:04d}"
        record["timeframe"] = timeframe
        records.append(record)
    return records


def _spread_profile(frame: pd.DataFrame, point_size: float) -> dict[str, Any]:
    if "spread" not in frame.columns:
        return {"source_field_present": False, "positive_bar_count": 0, "zero_or_missing_count": len(frame), "median_usd_per_oz": None, "p90_usd_per_oz": None, "p99_usd_per_oz": None}
    points = pd.to_numeric(frame["spread"], errors="coerce")
    valid = points[np.isfinite(points) & (points > 0)] * point_size
    return {
        "source_field_present": True,
        "positive_bar_count": int(valid.shape[0]),
        "zero_or_missing_count": int(len(frame) - valid.shape[0]),
        "median_usd_per_oz": float(valid.median()) if not valid.empty else None,
        "p90_usd_per_oz": float(valid.quantile(0.90)) if not valid.empty else None,
        "p99_usd_per_oz": float(valid.quantile(0.99)) if not valid.empty else None,
    }


def _scaled_cost_inputs(
    frame: pd.DataFrame,
    base_config: BacktestConfig,
    multiplier: float,
) -> tuple[pd.DataFrame, BacktestConfig]:
    """Scale all variable execution costs consistently for sensitivity analysis."""
    scaled_frame = frame.copy()
    if "spread" in scaled_frame.columns:
        scaled_frame["spread"] = pd.to_numeric(scaled_frame["spread"], errors="coerce") * multiplier
    scaled_config = replace(
        base_config,
        fallback_spread_usd=base_config.fallback_spread_usd * multiplier,
        slippage_per_side_usd=base_config.slippage_per_side_usd * multiplier,
        commission_per_lot_per_side=base_config.commission_per_lot_per_side * multiplier,
    )
    return scaled_frame, scaled_config


def _scenario_metrics(metrics: Mapping[str, Any], multiplier: float) -> dict[str, Any]:
    keys = (
        "candidate_count", "closed_trades", "rule_exit_trades", "time_stop_exits", "end_of_data_exits",
        "end_of_data_pnl", "net_profit_from_rule_exits", "skipped_candidates",
        "skipped_by_reason", "wins", "losses", "win_rate_pct", "net_profit",
        "return_pct", "profit_factor", "expectancy_per_rule_exit", "average_R_multiple",
        "max_drawdown_cash", "max_drawdown_pct", "max_realized_drawdown_cash", "max_realized_drawdown_pct", "total_commission", "stop_gap_exits",
        "stop_first_collisions", "losses_beyond_risk_budget", "max_open_positions_observed",
    )
    result = {key: metrics.get(key) for key in keys}
    result["cost_multiplier"] = multiplier
    return result


def run_validation_pipeline(
    data_dir: Path = ROOT / "data" / "processed",
    output_dir: Path = ROOT / "reports",
    *,
    timeframes: Optional[list[str]] = None,
    train_fraction: float = 0.70,
    config: Optional[BacktestConfig] = None,
    require_matched_execution_spec: bool = False,
) -> dict[str, Any]:
    """Evaluate frozen SMC setup rules in the final chronological segment."""
    timeframes = [tf.upper() for tf in (timeframes or TIMEFRAMES)]
    unknown = sorted(set(timeframes) - set(TIMEFRAMES))
    if unknown:
        raise ValueError(f"Unsupported timeframe(s): {', '.join(unknown)}")
    if not timeframes:
        raise ValueError("At least one timeframe is required")
    # Validate the split before any disk I/O or expensive analysis.
    if not 0.5 <= train_fraction < 1.0:
        raise ValueError("train_fraction must be in [0.5, 1.0)")
    config = config or BacktestConfig()

    execution_spec_audit = audit_processed_execution_specs(data_dir, config=config)
    expected_spec_status = "MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE"
    if require_matched_execution_spec and execution_spec_audit["overall_status"] != expected_spec_status:
        raise RuntimeError(
            "Execution specification gate blocked holdout validation: "
            f"status={execution_spec_audit['overall_status']}. Capture the intended MT5 specs and rerun the audit."
        )

    audit = audit_all_datasets(str(data_dir))
    readiness = evaluate_research_readiness(audit)
    if readiness["overall_status"] == "BLOCKED":
        blockers = "; ".join(readiness.get("blockers", []))
        raise RuntimeError(f"Research data gate is BLOCKED. Validation not run. {blockers}")

    datasets = load_and_verify_inputs(data_dir, timeframes=timeframes)
    per_timeframe: dict[str, Any] = {}
    all_trades: list[dict[str, Any]] = []

    for tf in timeframes:
        source_frame, meta = datasets[tf]
        frame = source_frame.copy().reset_index(drop=True)
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        split_index = chronological_split_index(len(frame), train_fraction)
        holdout_start = pd.Timestamp(frame.iloc[split_index]["time"])
        holdout_end = pd.Timestamp(frame.iloc[-1]["time"])

        # Generate candidates with the existing documented detector. Its causal
        # confirmation timestamps are retained; only signals at/after the frozen
        # temporal boundary can enter this evaluation.
        analysis = analyze_smc(frame, symbol="XAUUSD", timeframe=tf, config=SMCConfig())
        all_candidates, funnel = detect_smc_setups_with_funnel(frame, analysis, SMCSetupConfig())
        test_candidates = filter_candidates_from_index(all_candidates, split_index)
        records = _candidate_records(test_candidates, tf)

        scenarios: dict[str, Any] = {}
        for multiplier in COST_MULTIPLIERS:
            scenario_frame, scenario_config = _scaled_cost_inputs(frame, config, multiplier)
            result = run_event_backtest(scenario_frame, records, scenario_config, timeframe=tf)
            scenario_key = f"{multiplier:.1f}x"
            scenario_metrics = _scenario_metrics(result.metrics, multiplier)
            scenarios[scenario_key] = scenario_metrics
            for trade in result.trades:
                all_trades.append({
                    **trade,
                    "validation_period": "chronological_holdout",
                    "holdout_start": holdout_start.isoformat(),
                    "holdout_end": holdout_end.isoformat(),
                    "cost_scenario": scenario_key,
                })

        # Summarize spread observations in the holdout period for transparency.
        holdout_frame = frame.iloc[split_index:].copy()
        profile = _spread_profile(holdout_frame, config.point_size)
        per_timeframe[tf] = {
            "rows_total": len(frame),
            "split_index": split_index,
            "train_fraction_requested": train_fraction,
            "training_rows_for_context": split_index,
            "holdout_rows": len(frame) - split_index,
            "training_start": frame.iloc[0]["time"].isoformat(),
            "training_end": frame.iloc[split_index - 1]["time"].isoformat(),
            "holdout_start": holdout_start.isoformat(),
            "holdout_end": holdout_end.isoformat(),
            "candidates_all_history": len(all_candidates),
            "candidates_before_holdout": len(all_candidates) - len(test_candidates),
            "holdout_candidates_detected": len(test_candidates),
            "candidate_funnel_full_history": funnel,
            "source_verification_status": meta.get("source_verification_status"),
            "source_declared": meta.get("source"),
            "spread_profile_holdout_usd_per_oz": profile,
            "cost_scenarios": scenarios,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "report_title": "GoldFlow Phase 3D — Frozen-Rule Chronological Holdout and Cost Stress Validation",
        "generated_at_utc": generated_at,
        "validation_design": {
            "type": "per-timeframe chronological holdout",
            "train_fraction": train_fraction,
            "holdout_fraction": 1.0 - train_fraction,
            "setup_rules_frozen": True,
            "no_parameter_optimization_performed": True,
            "cost_multipliers": list(COST_MULTIPLIERS),
            "limitation": "This is a temporal holdout within data already examined in Phase 3C/3D, so it is not a fully independent confirmatory out-of-sample test. Use unseen data collected after freezing the rules for that claim.",
        },
        "instrument": "XAUUSD",
        "timeframes": timeframes,
        "readiness_status": readiness["overall_status"],
        "readiness_blockers": readiness.get("blockers", []),
        "readiness_warnings": {tf: audit.get(tf, {}).get("warnings", []) for tf in timeframes},
        "execution_spec_audit_status": execution_spec_audit["overall_status"],
        "execution_spec_audit": execution_spec_audit,
        "provenance_caveat": "Bundled metadata declares MT5 API provenance and timestamp integrity, but broker data and symbol contract specifications are not independently authenticated by this pipeline.",
        "base_config": asdict(config),
        "cost_scenario_method": "Scale each observed bar spread point value, fallback spread, per-side slippage, and commission by the scenario multiplier; use identical holdout signal candidates across scenarios. Position size is recalculated with each scenario's execution costs.",
        "metrics_by_timeframe": per_timeframe,
    }
    json_path = output_dir / "smc_oos_validation_metrics.json"
    csv_path = output_dir / "smc_oos_validation_trades.csv"
    report_path = output_dir / "PHASE3D_SMC_HOLDOUT_VALIDATION.md"
    trades_df = pd.DataFrame(all_trades)
    payload["artifact_paths"] = {
        "metrics_json": str(json_path.relative_to(ROOT)) if json_path.is_relative_to(ROOT) else str(json_path.resolve()),
        "trades_csv": str(csv_path.relative_to(ROOT)) if csv_path.is_relative_to(ROOT) else str(csv_path.resolve()),
        "markdown_report": str(report_path.relative_to(ROOT)) if report_path.is_relative_to(ROOT) else str(report_path.resolve()),
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    trades_df.to_csv(csv_path, index=False)
    report_path.write_text(_markdown_report(payload), encoding="utf-8")
    return payload


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (float, int, np.floating, np.integer)):
        return f"{value:,.{digits}f}"
    return str(value)


def _markdown_report(payload: Mapping[str, Any]) -> str:
    lines = [
        "# GoldFlow Phase 3D — Frozen-Rule Chronological Holdout Validation",
        "",
        f"**Generated UTC:** {payload['generated_at_utc']}",
        f"**Readiness:** {payload['readiness_status']}",
        f"**Execution specification audit:** {payload.get('execution_spec_audit_status', 'NOT_RECORDED')}",
        "",
        "> **Critical limitation:** this is a chronological holdout inside historical data already inspected during Phase 3C/3D. It is useful for checking temporal stability and cost sensitivity, but it is not an untouched independent confirmation of profitability.",
        "",
    ]
    if payload.get("execution_spec_audit_status") != "MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE":
        lines += [
            "> **EXECUTION-SPECIFICATION WARNING:** Captured broker point/contract/volume/tick specifications are missing or mismatch this run's config. Cash P&L and sizing are assumption-based, not broker-equivalent.",
            "",
        ]
    lines += [
        "## Protocol",
        "",
        f"- The first {payload['validation_design']['train_fraction']:.0%} of each timeframe's bars supply structure/swing context; signals are eligible only in the final {payload['validation_design']['holdout_fraction']:.0%}.",
        "- SMC setup rules and thresholds are frozen; no parameters were optimized on the holdout.",
        "- Same holdout candidates are evaluated at 1.0x, 1.5x and 2.0x transaction costs. Observed spread points, fallback spread, slippage and commission scale together.",
        "- Metrics separate rule exits (including optional TIME_STOP exits) from END_OF_DATA liquidation; all end-of-data trades remain marked explicitly. This frozen-rule cost-only validator defaults to no time stop.",
        "- Each timeframe has its own date split; results are **not directly comparable across timeframes** because their history ranges differ.",
        "",
        "## Holdout windows and results",
        "",
        "| TF | Holdout start UTC | Holdout end UTC | Bars | Candidates | Spread median / p90 ($/oz) | Cost | Closed | Rule exits | Time stops | EOD exits | Skipped | Rule-exit P&L | End-data P&L | Net P&L | Win % | PF | Max DD (MTM) | Realized DD |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for tf in payload["timeframes"]:
        entry = payload["metrics_by_timeframe"][tf]
        spread = entry["spread_profile_holdout_usd_per_oz"]
        spread_text = f"{_fmt(spread['median_usd_per_oz'])} / {_fmt(spread['p90_usd_per_oz'])}"
        for scenario, metrics in entry["cost_scenarios"].items():
            win = "N/A" if metrics["win_rate_pct"] is None else f"{_fmt(metrics['win_rate_pct'])}%"
            pf = _fmt(metrics["profit_factor"])
            lines.append(
                f"| {tf} | {entry['holdout_start'][:10]} | {entry['holdout_end'][:10]} | {entry['holdout_rows']} | "
                f"{entry['holdout_candidates_detected']} | {spread_text} | {scenario} | {metrics['closed_trades']} | {metrics['rule_exit_trades']} | "
                f"{metrics.get('time_stop_exits', 0)} | {metrics['end_of_data_exits']} | {metrics['skipped_candidates']} | ${_fmt(metrics['net_profit_from_rule_exits'])} | ${_fmt(metrics['end_of_data_pnl'])} | "
                f"${_fmt(metrics['net_profit'])} | {win} | {pf} | ${_fmt(metrics['max_drawdown_cash'])} | ${_fmt(metrics['max_realized_drawdown_cash'])} |"
            )
    lines += [
        "",
        "## How to interpret this report",
        "",
        "- **Rule-exit P&L** is the sum of completed non-END_OF_DATA trades, net of modeled costs. It excludes positions forcibly marked at the final bar.",
        "- **Net P&L** includes END_OF_DATA liquidation. Do not interpret that figure without reading the separate end-data P&L column.",
        "- A small trade count is not enough evidence to infer a stable edge. Compare trade count, profit factor, expectancy, drawdown, and cost sensitivity together.",
        "- Max DD (MTM) uses close-to-close estimated liquidation values for open positions; realized DD ignores floating P&L and is included only as a diagnostic. Neither reconstructs worst intrabar equity from OHLC bars.",
        "- If results turn negative under 1.5x or 2.0x costs, the strategy is fragile to execution uncertainty under these assumptions.",
        "- Spread percentiles are based on the bar `spread` field converted using configured `point_size`; zero values use fallback spread at execution time. The source declares MT5 API provenance, but the broker contract/point specifications are not independently verified.",
        "- OHLC bars cannot reveal true intrabar event order; the engine applies stop-first when stop and target are both hit. This remains a model assumption, not tick-level reconstruction.",
        "- This report is not a walk-forward optimization, live-forward test, or genuine untouched out-of-sample validation.",
        "",
        "## Artifacts",
        "",
        f"- `{Path(payload['artifact_paths']['metrics_json']).name}` — full machine-readable validation results.",
        f"- `{Path(payload['artifact_paths']['trades_csv']).name}` — every closed/skipped trade for each cost scenario.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GoldFlow frozen-rule chronological holdout and cost stress validation")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--timeframes", nargs="+", choices=TIMEFRAMES, default=TIMEFRAMES)
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--initial-capital", type=float, default=10_000.0)
    parser.add_argument("--risk-fraction", type=float, default=0.01)
    parser.add_argument("--contract-size-oz", type=float, default=100.0)
    parser.add_argument("--point-size", type=float, default=0.01)
    parser.add_argument("--fallback-spread-usd", type=float, default=0.20)
    parser.add_argument("--slippage-per-side-usd", type=float, default=0.05)
    parser.add_argument("--commission-per-lot-per-side", type=float, default=0.0)
    parser.add_argument("--min-lot", type=float, default=0.01)
    parser.add_argument("--lot-step", type=float, default=0.01)
    parser.add_argument("--max-lots", type=float, default=100.0)
    parser.add_argument("--max-concurrent-positions", type=int, default=1)
    parser.add_argument("--require-matched-execution-spec", action="store_true")
    args = parser.parse_args()
    try:
        config = BacktestConfig(
            initial_capital=args.initial_capital,
            risk_fraction=args.risk_fraction,
            contract_size_oz=args.contract_size_oz,
            point_size=args.point_size,
            fallback_spread_usd=args.fallback_spread_usd,
            slippage_per_side_usd=args.slippage_per_side_usd,
            commission_per_lot_per_side=args.commission_per_lot_per_side,
            min_lot=args.min_lot,
            lot_step=args.lot_step,
            max_lots=args.max_lots,
            max_concurrent_positions=args.max_concurrent_positions,
        )
        payload = run_validation_pipeline(
            args.data_dir, args.output_dir,
            timeframes=args.timeframes, train_fraction=args.train_fraction, config=config,
            require_matched_execution_spec=args.require_matched_execution_spec,
        )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"VALIDATION NOT RUN: {exc}", file=sys.stderr)
        return 2
    print(
        f"Readiness: {payload['readiness_status']} | execution specs: {payload['execution_spec_audit_status']} | "
        f"split: {args.train_fraction:.0%}/{1-args.train_fraction:.0%}"
    )
    for tf in payload["timeframes"]:
        item = payload["metrics_by_timeframe"][tf]
        print(f"{tf}: holdout {item['holdout_start']} -> {item['holdout_end']} | {item['holdout_candidates_detected']} candidates")
        for scenario, metrics in item["cost_scenarios"].items():
            print(f"  {scenario}: rule P&L ${metrics['net_profit_from_rule_exits']:.2f} | EOD ${metrics['end_of_data_pnl']:.2f} | net ${metrics['net_profit']:.2f} | exits {metrics['rule_exit_trades']}")
    print(f"Report: {payload['artifact_paths']['markdown_report']}")
    print(f"Metrics: {payload['artifact_paths']['metrics_json']}")
    print(f"Trades: {payload['artifact_paths']['trades_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
