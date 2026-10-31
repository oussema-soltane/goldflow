"""Run the experimental Phase 3E H4/H1-confirmed SMC entry comparison.

The frozen SMC v1 rules are the baseline. The experimental variant applies a
strict causal filter to M15/M5 candidates and leaves all entry/exit and execution
rules unchanged. Results are full-history exploratory comparisons, not OOS proof.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_smc_phase4_validation import (
    FROZEN_CONFIG_PATH,
    _file_sha256,
    _frozen_to_backtest_config,
    _frozen_to_setup_config,
    _frozen_to_smc_config,
    _load_and_validate_frozen_config,
)
from src.backtesting.engine import BacktestConfig, run_event_backtest
from src.research.data_readiness import audit_all_datasets, evaluate_research_readiness
from src.research.execution_spec_audit import audit_processed_execution_specs
from src.research.smc_research import load_and_verify_inputs
from src.smc.engine import analyze_smc
from src.strategy.smc_mtf import LOWER_TIMEFRAMES, TIMEFRAME_DURATIONS, filter_candidates_by_mtf
from src.strategy.smc_setups import SMCSetupCandidate, detect_smc_setups_with_funnel

TIMEFRAMES = ("H4", "H1", "M15", "M5")
FATAL_SPEC_STATUSES = {
    "TICK_VALUE_MISMATCH", "CALC_MODE_UNSUPPORTED", "CALC_MODE_MISMATCH",
    "SYMBOL_MISMATCH", "BROKER_MISMATCH", "CROSS_DATASET_SPEC_MISMATCH",
}
EXPECTED_SPEC_STATUS = "MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE"


def _portable(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _portable_execution_audit_paths(audit: dict[str, Any]) -> dict[str, Any]:
    """Make project-local paths portable in the saved audit artifact."""
    cleaned = dict(audit)
    data_dir = cleaned.get("data_dir")
    if isinstance(data_dir, str):
        cleaned["data_dir"] = _portable(Path(data_dir))
    datasets = cleaned.get("datasets")
    if isinstance(datasets, list):
        cleaned_datasets = []
        for item in datasets:
            if not isinstance(item, dict):
                cleaned_datasets.append(item)
                continue
            dataset = dict(item)
            sidecar_path = dataset.get("sidecar_path")
            if isinstance(sidecar_path, str):
                dataset["sidecar_path"] = _portable(Path(sidecar_path))
            cleaned_datasets.append(dataset)
        cleaned["datasets"] = cleaned_datasets
    return cleaned


def _candidate_records(
    candidates: list[SMCSetupCandidate],
    timeframe: str,
    stable_ids: dict[int, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ordinal, candidate in enumerate(candidates, start=1):
        row = candidate.to_dict()
        row["setup_id"] = stable_ids.get(id(candidate), f"SMC_{timeframe}_{ordinal:04d}")
        row["timeframe"] = timeframe
        rows.append(row)
    return rows


def _metric_row(timeframe: str, variant: str, candidate_count: int, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "timeframe": timeframe,
        "variant": variant,
        "candidate_count": candidate_count,
        "closed_trades": metrics.get("closed_trades", 0),
        "rule_exit_trades": metrics.get("rule_exit_trades", 0),
        "end_of_data_exits": metrics.get("end_of_data_exits", 0),
        "skipped_candidates": metrics.get("skipped_candidates", 0),
        "win_rate_pct": metrics.get("win_rate_pct"),
        "net_profit": metrics.get("net_profit"),
        "return_pct": metrics.get("return_pct"),
        "profit_factor": metrics.get("profit_factor"),
        "max_drawdown_cash": metrics.get("max_drawdown_cash"),
        "max_realized_drawdown_cash": metrics.get("max_realized_drawdown_cash"),
        "average_R_multiple": metrics.get("average_R_multiple"),
        "expectancy_per_rule_exit": metrics.get("expectancy_per_rule_exit"),
    }


def run_smc_mtf_pipeline(
    data_dir: Path = ROOT / "data" / "processed",
    output_dir: Path = ROOT / "reports",
    *,
    timeframes: Optional[list[str]] = None,
    require_matched_execution_spec: bool = False,
) -> dict[str, Any]:
    """Compare frozen SMC v1 against its H4/H1-confirmed M15/M5 variant."""
    selected = [tf.upper() for tf in (timeframes or list(LOWER_TIMEFRAMES))]
    unknown = sorted(set(selected) - set(LOWER_TIMEFRAMES))
    if unknown:
        raise ValueError(f"Unsupported entry timeframe(s): {', '.join(unknown)}")
    if not selected:
        raise ValueError("At least one of M15 or M5 must be selected")

    frozen_cfg = _load_and_validate_frozen_config(FROZEN_CONFIG_PATH)
    frozen_sha256 = _file_sha256(FROZEN_CONFIG_PATH)
    smc_config = _frozen_to_smc_config(frozen_cfg)
    setup_config = _frozen_to_setup_config(frozen_cfg)
    backtest_config: BacktestConfig = _frozen_to_backtest_config(frozen_cfg)

    execution_spec_audit = audit_processed_execution_specs(data_dir, config=backtest_config)
    spec_status = execution_spec_audit.get("overall_status", "UNKNOWN")
    if spec_status in FATAL_SPEC_STATUSES:
        raise RuntimeError(
            "Execution specification audit blocked the experiment: "
            f"{spec_status}. Reconcile the MT5 symbol specs before running."
        )
    if require_matched_execution_spec and spec_status != EXPECTED_SPEC_STATUS:
        raise RuntimeError(
            "Strict execution-specification gate blocked the experiment: "
            f"{spec_status}; expected {EXPECTED_SPEC_STATUS}. Capture and audit specs from the intended MT5 terminal."
        )

    data_audit = audit_all_datasets(str(data_dir))
    readiness = evaluate_research_readiness(data_audit)
    if readiness.get("overall_status") == "BLOCKED":
        blockers = "; ".join(readiness.get("blockers", []))
        raise RuntimeError(f"Research readiness is BLOCKED; no backtest was run. {blockers}")

    required_tfs = list(dict.fromkeys(["H4", "H1", *selected]))
    datasets = load_and_verify_inputs(data_dir, timeframes=required_tfs)

    # Compute the last confirmed candle-close time for H4 and H1.
    # "confirmed at" = last bar's open timestamp + timeframe duration.
    # This is the hard boundary beyond which no new H4/H1 context can exist.
    from src.strategy.smc_mtf import TIMEFRAME_DURATIONS
    h4_frame = datasets["H4"][0].copy()
    h4_frame["time"] = pd.to_datetime(h4_frame["time"], utc=True)
    h4_data_end_time = h4_frame["time"].max() + TIMEFRAME_DURATIONS["H4"]

    h1_frame = datasets["H1"][0].copy()
    h1_frame["time"] = pd.to_datetime(h1_frame["time"], utc=True)
    h1_data_end_time = h1_frame["time"].max() + TIMEFRAME_DURATIONS["H1"]

    # The common valid evaluation end: the minimum of H4 and H1 confirmed close times.
    # Candidates and bars beyond this boundary use stale context — they are excluded.
    common_eval_end = min(h4_data_end_time, h1_data_end_time)

    # Higher-timeframe context analyses (H4, H1)
    analyses = {
        "H4": analyze_smc(h4_frame, symbol="XAUUSD", timeframe="H4", config=smc_config),
        "H1": analyze_smc(h1_frame, symbol="XAUUSD", timeframe="H1", config=smc_config),
    }

    all_trades: list[dict[str, Any]] = []
    all_curve_rows: list[dict[str, Any]] = []
    all_candidate_audit_rows: list[dict[str, Any]] = []
    per_timeframe: dict[str, Any] = {}
    comparison_rows: list[dict[str, Any]] = []

    for tf in selected:
        frame, meta = datasets[tf]
        frame = frame.copy().reset_index(drop=True)
        frame["time"] = pd.to_datetime(frame["time"], utc=True)

        # Trim the entry-timeframe frame to the valid higher-timeframe data boundary.
        # Both baseline and MTF-confirmed variants must run on the identical trimmed window
        # so their results are directly comparable and neither uses stale context.
        frame_valid = frame[frame["time"] <= common_eval_end].copy().reset_index(drop=True)
        eval_end_actual = frame_valid["time"].max() if len(frame_valid) > 0 else None

        # Analyze SMC on the trimmed valid frame so analysis.total_bars matches frame_valid
        analyses[tf] = analyze_smc(frame_valid, symbol="XAUUSD", timeframe=tf, config=smc_config)

        candidates, candidate_funnel = detect_smc_setups_with_funnel(
            frame_valid, analyses[tf], setup_config
        )
        stable_ids = {
            id(candidate): f"SMC_{tf}_{ordinal:04d}"
            for ordinal, candidate in enumerate(candidates, start=1)
        }
        records_baseline = _candidate_records(candidates, tf, stable_ids)
        filtered, filter_funnel, audit_rows = filter_candidates_by_mtf(
            candidates,
            lower_timeframe=tf,
            h4_analysis=analyses["H4"],
            h1_analysis=analyses["H1"],
            h4_data_end_time=h4_data_end_time,
            h1_data_end_time=h1_data_end_time,
        )
        records_filtered = _candidate_records(filtered, tf, stable_ids)
        for row in audit_rows:
            row["setup_id"] = stable_ids.get(
                id(candidates[row["candidate_ordinal"] - 1]),
                f"SMC_{tf}_{row['candidate_ordinal']:04d}",
            )
            row["analysis_key"] = f"{tf}|SMC_v1_H4_H1_confirmed"
            all_candidate_audit_rows.append(row)

        baseline_result = run_event_backtest(
            frame_valid, records_baseline, backtest_config, timeframe=tf
        )
        filtered_result = run_event_backtest(
            frame_valid, records_filtered, backtest_config, timeframe=tf
        )

        baseline_metric_row = _metric_row(tf, "SMC_v1_baseline", len(candidates), baseline_result.metrics)
        filtered_metric_row = _metric_row(tf, "SMC_v1_H4_H1_confirmed", len(filtered), filtered_result.metrics)
        comparison_rows.extend([baseline_metric_row, filtered_metric_row])

        for variant, result in (("SMC_v1_baseline", baseline_result), ("SMC_v1_H4_H1_confirmed", filtered_result)):
            for trade in result.trades:
                row = dict(trade)
                row["strategy_variant"] = variant
                row["analysis_key"] = f"{tf}|{variant}"
                all_trades.append(row)
            for point in result.equity_curve:
                row = dict(point)
                row["timeframe"] = tf
                row["strategy_variant"] = variant
                row["analysis_key"] = f"{tf}|{variant}"
                all_curve_rows.append(row)

        per_timeframe[tf] = {
            "data_rows_total": len(frame),
            "data_rows_valid_window": len(frame_valid),
            "data_start_time": frame["time"].min().isoformat(),
            "data_end_time": frame["time"].max().isoformat(),
            "valid_eval_end_time": eval_end_actual.isoformat() if eval_end_actual is not None else None,
            "h4_confirmed_end_time": h4_data_end_time.isoformat(),
            "h1_confirmed_end_time": h1_data_end_time.isoformat(),
            "common_eval_end_time": common_eval_end.isoformat(),
            "eval_window_note": (
                f"Both baseline and MTF-confirmed variants are evaluated on the identical "
                f"trimmed window (bars with time <= {common_eval_end.isoformat()}). "
                f"The entry frame had {len(frame)} total bars; {len(frame_valid)} bars "
                f"fall within the valid higher-timeframe data boundary."
            ),
            "source_declared": meta.get("source"),
            "source_verification_status": meta.get("source_verification_status"),
            "candidate_funnel": candidate_funnel,
            "mtf_filter_funnel": filter_funnel,
            "baseline": baseline_result.metrics,
            "mtf_confirmed": filtered_result.metrics,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = output_dir / "smc_mtf_metrics.json"
    trades_path = output_dir / "smc_mtf_trades.csv"
    curves_path = output_dir / "smc_mtf_equity_curves.csv"
    audit_path = output_dir / "smc_mtf_candidate_context_audit.csv"
    powerbi_summary_path = output_dir / "smc_mtf_powerbi_summary.csv"
    report_path = output_dir / "PHASE3E_SMC_MULTI_TIMEFRAME_EXPERIMENT.md"

    payload: dict[str, Any] = {
        "report_title": "GoldFlow Phase 3E — H4/H1-Confirmed SMC Entry Experiment",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "instrument": "XAUUSD",
        "strategy_baseline": "SMC v1 frozen rule set",
        "experimental_variant": "Require latest completed H4 and H1 structure trends to agree and match lower-timeframe candidate direction",
        "entry_timeframes": selected,
        "context_timeframes": ["H4", "H1"],
        "h4_confirmed_end_time": h4_data_end_time.isoformat(),
        "h1_confirmed_end_time": h1_data_end_time.isoformat(),
        "common_eval_end_time": common_eval_end.isoformat(),
        "data_boundary_enforcement": (
            "Both baseline and MTF-confirmed variants are evaluated on identical trimmed windows "
            f"(bars with time <= {common_eval_end.isoformat()}). H4 confirmed end: "
            f"{h4_data_end_time.isoformat()}. H1 confirmed end: {h1_data_end_time.isoformat()}. "
            "The StructureTrendTimeline.at() method returns None for any decision_time strictly "
            "after the h4_data_end_time / h1_data_end_time boundary, preventing stale-context "
            "carry-forward. All entry-frame bars beyond common_eval_end are excluded before "
            "candidate detection so neither variant can generate trades in the stale-context zone."
        ),
        "data_readiness_status": readiness.get("overall_status"),
        "data_readiness_warnings": readiness.get("warnings", []),
        "execution_spec_audit_status": spec_status,
        "execution_spec_audit": _portable_execution_audit_paths(execution_spec_audit),
        "frozen_config_path": _portable(FROZEN_CONFIG_PATH),
        "frozen_config_sha256": frozen_sha256,
        "smc_config": smc_config.__dict__,
        "setup_config": setup_config.__dict__,
        "backtest_config": backtest_config.__dict__,
        "per_timeframe": per_timeframe,
        "interpretation_limitations": [
            "This is an exploratory full-history comparison. The bundled records have already been examined during earlier phases; this is not an untouched out-of-sample result.",
            "Sidecars declare MT5 provenance but the broker/source history is not independently authenticated.",
            "Candidate count and observed win rate can fall sharply after higher-timeframe filtering; small samples do not support strong statistical conclusions.",
            "The context filter uses the latest structure-break state known at entry, not a full discretionary market-structure interpretation.",
            "OHLC event simulation cannot reconstruct tick-level intrabar path or guarantee future live execution.",
        ],
        "artifact_paths": {
            "metrics_json": _portable(metrics_path),
            "trades_csv": _portable(trades_path),
            "equity_curves_csv": _portable(curves_path),
            "candidate_context_audit_csv": _portable(audit_path),
            "powerbi_summary_csv": _portable(powerbi_summary_path),
            "markdown_report": _portable(report_path),
        },
    }
    metrics_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(all_trades).to_csv(trades_path, index=False)
    pd.DataFrame(all_curve_rows).to_csv(curves_path, index=False)
    pd.DataFrame(all_candidate_audit_rows).to_csv(audit_path, index=False)
    powerbi_summary = pd.DataFrame(comparison_rows).rename(columns={"variant": "strategy_variant"})
    powerbi_summary["analysis_key"] = (
        powerbi_summary["timeframe"].astype(str) + "|" + powerbi_summary["strategy_variant"].astype(str)
    )
    preferred_order = ["analysis_key", "timeframe", "strategy_variant"]
    powerbi_summary = powerbi_summary[preferred_order + [c for c in powerbi_summary.columns if c not in preferred_order]]
    powerbi_summary.to_csv(powerbi_summary_path, index=False)
    report_path.write_text(_markdown_report(payload, comparison_rows), encoding="utf-8")
    return payload


def _fmt(value: Any, suffix: str = "", digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (float, int)):
        return f"{value:,.{digits}f}{suffix}"
    return f"{value}{suffix}"


def _markdown_report(payload: dict[str, Any], comparison_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# GoldFlow Phase 3E — Multi-Timeframe SMC Experiment",
        "",
        f"**Generated UTC:** {payload['generated_at_utc']}",
        f"**Entry timeframes:** {', '.join(payload['entry_timeframes'])}",
        f"**Context:** H4 + H1 latest completed structure direction",
        f"**Frozen SMC v1 SHA-256:** `{payload['frozen_config_sha256']}`",
        f"**Data readiness:** `{payload['data_readiness_status']}`",
        f"**Execution-spec audit:** `{payload['execution_spec_audit_status']}`",
        "",
        "> This is an exploratory research comparison, not a live-trading claim or genuine untouched out-of-sample validation. Source provenance remains declared, not independently authenticated.",
        "",
        "## Comparison results",
        "",
        "| Timeframe | Variant | Candidates | Closed | Rule exits | Win rate* | Net P&L** | Return | Profit factor* | Max DD (MTM) | Avg R* |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in comparison_rows:
        lines.append(
            f"| {row['timeframe']} | {row['variant']} | {row['candidate_count']} | {row['closed_trades']} | {row['rule_exit_trades']} | "
            f"{_fmt(row['win_rate_pct'], '%')} | ${_fmt(row['net_profit'])} | {_fmt(row['return_pct'], '%')} | "
            f"{_fmt(row['profit_factor'])} | ${_fmt(row['max_drawdown_cash'])} | {_fmt(row['average_R_multiple'])} |"
        )
    lines += [
        "",
        "* Win rate, profit factor and average R exclude `END_OF_DATA` mark-outs as defined by the shared event-driven engine.",
        "** Net P&L includes end-of-data liquidation. Max DD is close-to-close mark-to-market and is not an intrabar maximum.",
        "",
        "## Filtering funnel",
        "",
    ]
    for tf in payload["entry_timeframes"]:
        info = payload["per_timeframe"][tf]
        funnel = info["mtf_filter_funnel"]
        lines += [
            f"### {tf}",
            f"- Original candidates: {funnel['input_candidates']}",
            f"- Accepted after H4/H1 alignment: {funnel['accepted_candidates']}",
            f"- Rejected: {funnel['rejected_candidates']}",
        ]
        for reason, count in funnel.get("rejection_reasons", {}).items():
            lines.append(f"- {reason}: {count}")
        lines.append("")
    lines += [
        "## Causal timing contract",
        "",
        "A structure-break event on H4/H1 is available only at its candle close, computed as the event candle's open timestamp plus the source timeframe duration. For a lower-timeframe candidate, context is sampled at its `next_bar_time` (the intended entry open). Events whose availability is later than that entry timestamp are excluded. A missing H4/H1 context, disagreement between H4 and H1, or mismatch with the candidate direction rejects the experimental entry.",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["interpretation_limitations"])
    lines += [
        "",
        "## Artifacts",
        "",
        f"- `{Path(payload['artifact_paths']['metrics_json']).name}` — compact machine-readable comparison and metrics.",
        f"- `{Path(payload['artifact_paths']['trades_csv']).name}` — both variants' trade ledgers, keyed by stable baseline setup ID.",
        f"- `{Path(payload['artifact_paths']['equity_curves_csv']).name}` — mark-to-market and realized equity curves, stored separately from JSON.",
        f"- `{Path(payload['artifact_paths']['candidate_context_audit_csv']).name}` — per-candidate H4/H1 direction and availability audit.",
        f"- `{Path(payload['artifact_paths']['powerbi_summary_csv']).name}` — flat comparison table suitable for Power BI Desktop import.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GoldFlow Phase 3E H4/H1-confirmed SMC experiment")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--timeframes", nargs="+", choices=list(LOWER_TIMEFRAMES), default=list(LOWER_TIMEFRAMES))
    parser.add_argument(
        "--require-matched-execution-spec",
        action="store_true",
        help="Require audited execution specs to match the frozen simulation assumptions before running.",
    )
    args = parser.parse_args()
    try:
        payload = run_smc_mtf_pipeline(
            args.data_dir,
            args.output_dir,
            timeframes=args.timeframes,
            require_matched_execution_spec=args.require_matched_execution_spec,
        )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"MULTI-TIMEFRAME EXPERIMENT NOT RUN: {exc}", file=sys.stderr)
        return 2

    print(
        f"Phase 3E complete | readiness={payload['data_readiness_status']} | "
        f"execution_specs={payload['execution_spec_audit_status']}"
    )
    for tf in payload["entry_timeframes"]:
        info = payload["per_timeframe"][tf]
        base = info["baseline"]
        mtf = info["mtf_confirmed"]
        print(
            f"{tf}: baseline {base['closed_trades']} closed, net ${base['net_profit']:.2f}; "
            f"H4/H1-confirmed {mtf['closed_trades']} closed, net ${mtf['net_profit']:.2f}; "
            f"accepted {info['mtf_filter_funnel']['accepted_candidates']}/{info['mtf_filter_funnel']['input_candidates']} candidates"
        )
    for key, value in payload["artifact_paths"].items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
