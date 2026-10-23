"""Run frozen-SMC position-lifecycle sensitivity tests with optional time stops.

Examples:
  python scripts/run_smc_lifecycle_stress.py
  python scripts/run_smc_lifecycle_stress.py --timeframes M15 M5 --hours 4 12 24 48

Holding horizons are converted to bars using nominal timeframe duration. Actual
wall-clock duration can be longer around market closures and data gaps. This is
sensitivity analysis, not parameter optimization or a profitability claim.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_smc_backtest import TIMEFRAMES, _candidate_records
from src.backtesting.engine import BacktestConfig, run_event_backtest
from src.research.data_readiness import audit_all_datasets, evaluate_research_readiness
from src.research.execution_spec_audit import audit_processed_execution_specs
from src.research.smc_research import load_and_verify_inputs
from src.smc.engine import SMCConfig, analyze_smc
from src.strategy.smc_setups import SMCSetupConfig, detect_smc_setups_with_funnel

BAR_HOURS = {"H4": 4.0, "H1": 1.0, "M15": 0.25, "M5": 5.0 / 60.0}
DEFAULT_HORIZONS_HOURS = [4, 8, 24, 48]
METRIC_KEYS = [
    "candidate_count", "closed_trades", "rule_exit_trades", "time_stop_exits",
    "end_of_data_exits", "end_of_data_pnl", "net_profit_from_rule_exits",
    "skipped_candidates", "skipped_by_reason", "wins", "losses", "breakeven",
    "win_rate_pct", "profit_factor", "expectancy_per_rule_exit", "average_R_multiple",
    "initial_capital", "final_equity", "net_profit", "return_pct",
    "max_drawdown_cash", "max_drawdown_pct", "max_realized_drawdown_cash",
    "max_realized_drawdown_pct", "losses_beyond_risk_budget", "mean_bars_held_rule_exits",
    "max_concurrent_positions_configured", "max_open_positions_observed",
]


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (float, int)):
        return f"{value:,.{digits}f}"
    return str(value)


def _candidate_funnel_summary(funnel: Mapping[str, Any]) -> dict[str, Any]:
    """Keep funnel output readable and JSON-safe while retaining core counts."""
    important = (
        "total_bars_evaluated", "total_structure_breaks", "choch_breaks_evaluated",
        "choch_with_preceding_sweep", "identifiable_order_blocks", "retest_evaluated",
        "retest_rejection_confirmed", "valid_risk_reward", "final_setup_candidates",
    )
    result = {}
    for key in important:
        if key in funnel:
            result[key] = funnel[key]
    # Funnel implementations may use slightly different names; retain scalars only.
    for key, value in funnel.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            result.setdefault(key, value)
    return result


def run_lifecycle_stress(
    data_dir: Path = ROOT / "data" / "processed",
    output_dir: Path = ROOT / "reports",
    *,
    timeframes: list[str] | None = None,
    horizons_hours: list[float] | None = None,
    config: BacktestConfig | None = None,
    require_matched_execution_spec: bool = False,
) -> dict[str, Any]:
    timeframes = [str(tf).upper() for tf in (timeframes or TIMEFRAMES)]
    unknown = sorted(set(timeframes) - set(TIMEFRAMES))
    if unknown or not timeframes:
        raise ValueError(f"Unsupported or empty timeframe selection: {unknown or timeframes}")
    horizons_hours = list(horizons_hours or DEFAULT_HORIZONS_HOURS)
    if any((not math.isfinite(float(h)) or float(h) <= 0) for h in horizons_hours):
        raise ValueError("All time-stop horizons must be positive finite hour values")
    horizons_hours = sorted({float(h) for h in horizons_hours})
    base_config = config or BacktestConfig()

    execution_spec_audit = audit_processed_execution_specs(data_dir, config=base_config)
    expected_spec_status = "MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE"
    if require_matched_execution_spec and execution_spec_audit["overall_status"] != expected_spec_status:
        raise RuntimeError(
            "Execution specification gate blocked lifecycle stress: "
            f"status={execution_spec_audit['overall_status']}. Capture the intended MT5 specs and rerun the audit."
        )

    audit = audit_all_datasets(str(data_dir))
    readiness = evaluate_research_readiness(audit)
    if readiness["overall_status"] == "BLOCKED":
        blockers = "; ".join(readiness.get("blockers", []))
        raise RuntimeError(f"Research data gate is BLOCKED. Lifecycle analysis not run. {blockers}")

    datasets = load_and_verify_inputs(data_dir, timeframes=timeframes)
    per_timeframe: dict[str, Any] = {}
    all_trades: list[dict[str, Any]] = []

    for tf in timeframes:
        frame, meta = datasets[tf]
        frame = frame.copy().reset_index(drop=True)
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        analysis = analyze_smc(frame, symbol="XAUUSD", timeframe=tf, config=SMCConfig())
        candidates, funnel = detect_smc_setups_with_funnel(frame, analysis, SMCSetupConfig())
        records = _candidate_records(candidates, tf)
        scenarios: dict[str, Any] = {}
        scenario_specs: list[tuple[str, float | None, int | None]] = [("no_time_stop", None, None)]
        for hours in horizons_hours:
            # Nominal timeframe-bar equivalent. It counts active chart bars and
            # therefore is not a strict wall-clock deadline across market gaps.
            bars = max(1, int(math.ceil(hours / BAR_HOURS[tf])))
            scenario_specs.append((f"max_{hours:g}h_nominal", hours, bars))

        for scenario, hours, max_bars in scenario_specs:
            scenario_config = replace(base_config, max_holding_bars=max_bars)
            result = run_event_backtest(frame, records, scenario_config, timeframe=tf)
            metrics = {key: result.metrics.get(key) for key in METRIC_KEYS}
            metrics.update({
                "scenario": scenario,
                "nominal_holding_hours": hours,
                "max_holding_bars": max_bars,
                "bar_duration_hours_nominal": BAR_HOURS[tf],
            })
            scenarios[scenario] = metrics
            for trade in result.trades:
                all_trades.append({
                    **trade,
                    "lifecycle_scenario": scenario,
                    "nominal_holding_hours": hours,
                    "max_holding_bars_configured": max_bars,
                    "data_start": frame["time"].min().isoformat(),
                    "data_end": frame["time"].max().isoformat(),
                })

        per_timeframe[tf] = {
            "rows": len(frame),
            "start_time": frame["time"].min().isoformat(),
            "end_time": frame["time"].max().isoformat(),
            "candidates_detected": len(records),
            "candidate_funnel": _candidate_funnel_summary(funnel),
            "source_verification_status": meta.get("source_verification_status"),
            "source_declared": meta.get("source"),
            "nominal_bar_hours": BAR_HOURS[tf],
            "scenarios": scenarios,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat()
    payload = {
        "report_title": "GoldFlow Phase 3D.2 — Position Lifecycle and Time-Stop Sensitivity",
        "generated_at_utc": generated,
        "readiness_status": readiness["overall_status"],
        "readiness_blockers": readiness.get("blockers", []),
        "readiness_warnings": {tf: audit.get(tf, {}).get("warnings", []) for tf in timeframes},
        "execution_spec_audit_status": execution_spec_audit["overall_status"],
        "execution_spec_audit": execution_spec_audit,
        "instrument": "XAUUSD",
        "timeframes": timeframes,
        "methodology": {
            "setup_rules_frozen": True,
            "entry_rules_changed": False,
            "parameter_optimization_performed": False,
            "execution_model": "Same event-driven engine and costs in every scenario; only max_holding_bars changes.",
            "time_stop": "Stop/target/gap logic is evaluated first. If no stop/target exit occurs and the configured bar cap is reached, exit at the current completed bar close with adverse slippage and quote-side spread treatment.",
            "bar_count_semantics": "The entry bar counts as held bar 1. Nominal hours convert to bars by timeframe; actual elapsed wall-clock time can be longer due to market closures, holidays, and missing bars.",
            "concurrency": "Each scenario independently reruns the same candidate list; time stops can free concurrency slots for later candidates.",
            "limitation": "The bundled history was already examined in earlier research phases. This is lifecycle sensitivity analysis, not independent out-of-sample validation or evidence of profitability.",
        },
        "base_config": asdict(base_config),
        "metrics_by_timeframe": per_timeframe,
    }
    metrics_path = output_dir / "smc_lifecycle_stress_metrics.json"
    trades_path = output_dir / "smc_lifecycle_stress_trades.csv"
    report_path = output_dir / "PHASE3D_SMC_POSITION_LIFECYCLE_STRESS.md"
    trade_df = pd.DataFrame(all_trades)
    payload["artifact_paths"] = {
        "metrics_json": str(metrics_path.relative_to(ROOT)) if metrics_path.is_relative_to(ROOT) else str(metrics_path.resolve()),
        "trades_csv": str(trades_path.relative_to(ROOT)) if trades_path.is_relative_to(ROOT) else str(trades_path.resolve()),
        "markdown_report": str(report_path.relative_to(ROOT)) if report_path.is_relative_to(ROOT) else str(report_path.resolve()),
    }
    metrics_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    trade_df.to_csv(trades_path, index=False)
    report_path.write_text(_markdown_report(payload), encoding="utf-8")
    return payload


def _markdown_report(payload: Mapping[str, Any]) -> str:
    lines = [
        "# GoldFlow Phase 3D.2 — Position Lifecycle and Time-Stop Sensitivity",
        "",
        f"**Generated UTC:** {payload['generated_at_utc']}",
        f"**Data readiness:** {payload['readiness_status']}",
        f"**Execution specification audit:** {payload.get('execution_spec_audit_status', 'NOT_RECORDED')}",
        "",
        "> This is a frozen-entry-rule execution sensitivity study. It is not a strategy optimization and does not establish profitability.",
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
        "- Entry, target, stop, spread, slippage, commission, sizing, and collision rules are unchanged across scenarios.",
        "- The no-time-stop baseline is compared against nominal 4h, 8h, 24h, and 48h holding caps by default.",
        "- Stop/target/gap exits have priority; otherwise the time stop closes at the completed bar close when the bar cap is reached.",
        "- The entry bar counts as bar 1. Nominal hours are converted to timeframe bars; actual wall-clock duration may be longer across closures and data gaps.",
        "- Time stops can free concurrency slots, so both accepted entries and skipped candidates may change between scenarios.",
        "- This same bundled history was reviewed earlier; treat this as a diagnostic, not genuine unseen out-of-sample confirmation.",
        "",
        "## Results",
        "",
        "| TF | Scenario | Max bars | Candidates | Closed | Rule exits | Time stops | EOD exits | Skipped | Rule-exit P&L | EOD P&L | Net P&L | Max DD MTM | Mean held bars |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for tf in payload["timeframes"]:
        for scenario, m in payload["metrics_by_timeframe"][tf]["scenarios"].items():
            lines.append(
                f"| {tf} | {scenario} | {m['max_holding_bars'] if m['max_holding_bars'] is not None else '—'} | "
                f"{_fmt(m['candidate_count'], 0)} | {_fmt(m['closed_trades'], 0)} | {_fmt(m['rule_exit_trades'], 0)} | "
                f"{_fmt(m['time_stop_exits'], 0)} | {_fmt(m['end_of_data_exits'], 0)} | {_fmt(m['skipped_candidates'], 0)} | "
                f"${_fmt(m['net_profit_from_rule_exits'])} | ${_fmt(m['end_of_data_pnl'])} | ${_fmt(m['net_profit'])} | "
                f"${_fmt(m['max_drawdown_cash'])} | {_fmt(m['mean_bars_held_rule_exits'])} |"
            )
    lines += [
        "",
        "## Interpretation safeguards",
        "",
        "- P&L still includes explicitly labeled END_OF_DATA liquidations; compare rule-exit P&L and EOD P&L separately.",
        "- Drawdown is close-to-close mark-to-market, not intrabar tick-level drawdown.",
        "- A time stop changes trade management and concurrency, not merely a report filter. Do not choose the best-looking horizon on this same sample and report it as validated.",
        "- Confirm broker symbol contract size, point size, spread interpretation, commission, and slippage before treating simulated cash metrics as broker-equivalent.",
        "- MT5 provenance in sidecars is declared, not independently authenticated.",
        "",
        "## Artifacts",
        "",
        f"- `{Path(payload['artifact_paths']['metrics_json']).name}` — scenario metrics.",
        f"- `{Path(payload['artifact_paths']['trades_csv']).name}` — full scenario-level trade and skip log.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GoldFlow position lifecycle and time-stop sensitivity")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--timeframes", nargs="+", choices=TIMEFRAMES, default=TIMEFRAMES)
    parser.add_argument("--hours", nargs="+", type=float, default=DEFAULT_HORIZONS_HOURS, help="Nominal holding horizons in hours; converted to timeframe bars")
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
        payload = run_lifecycle_stress(
            args.data_dir, args.output_dir, timeframes=args.timeframes,
            horizons_hours=args.hours, config=config,
            require_matched_execution_spec=args.require_matched_execution_spec,
        )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"LIFECYCLE STRESS NOT RUN: {exc}", file=sys.stderr)
        return 2
    print(f"Readiness: {payload['readiness_status']} | execution specs: {payload['execution_spec_audit_status']}")
    for tf in payload["timeframes"]:
        print(f"{tf}:")
        for scenario, m in payload["metrics_by_timeframe"][tf]["scenarios"].items():
            print(f"  {scenario}: rule P&L ${m['net_profit_from_rule_exits']:.2f} | EOD ${m['end_of_data_pnl']:.2f} | net ${m['net_profit']:.2f} | max DD ${m['max_drawdown_cash']:.2f} | skipped {m['skipped_candidates']}")
    print(f"Report: {payload['artifact_paths']['markdown_report']}")
    print(f"Metrics: {payload['artifact_paths']['metrics_json']}")
    print(f"Trades: {payload['artifact_paths']['trades_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
