"""Run GoldFlow Phase 3D Pure-SMC event-driven backtesting.

Examples (from the repository root):
  python scripts/run_smc_backtest.py
  python scripts/run_smc_backtest.py --mode common-window
  python scripts/run_smc_backtest.py --risk-fraction 0.005 --max-concurrent-positions 1

The script refuses datasets that fail the project's research-readiness gates.
READY_WITH_WARNINGS data can run, but those warnings are included in the report.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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


def _common_window(datasets: dict[str, tuple[pd.DataFrame, dict[str, Any]]], timeframes: list[str]) -> tuple[pd.Timestamp, pd.Timestamp]:
    starts = [pd.to_datetime(datasets[tf][0]["time"], utc=True).min() for tf in timeframes]
    ends = [pd.to_datetime(datasets[tf][0]["time"], utc=True).max() for tf in timeframes]
    start, end = max(starts), min(ends)
    if start >= end:
        raise ValueError("Selected timeframes do not have a non-empty common date window")
    return pd.Timestamp(start), pd.Timestamp(end)


def _candidate_records(candidates: list[Any], timeframe: str) -> list[dict[str, Any]]:
    records = []
    for n, candidate in enumerate(candidates, start=1):
        record = candidate.to_dict()
        record["setup_id"] = f"SMC_{timeframe}_{n:04d}"
        record["timeframe"] = timeframe
        records.append(record)
    return records


def run_backtest_pipeline(
    data_dir: Path = ROOT / "data" / "processed",
    output_dir: Path = ROOT / "reports",
    *,
    timeframes: Optional[list[str]] = None,
    mode: str = "full-history",
    config: Optional[BacktestConfig] = None,
    require_matched_execution_spec: bool = False,
) -> dict[str, Any]:
    """Run selected timeframes and write auditable Phase 3D artifacts."""
    timeframes = [tf.upper() for tf in (timeframes or TIMEFRAMES)]
    unknown = sorted(set(timeframes) - set(TIMEFRAMES))
    if unknown:
        raise ValueError(f"Unsupported timeframe(s): {', '.join(unknown)}")
    if not timeframes:
        raise ValueError("At least one timeframe is required")
    if mode not in {"full-history", "common-window"}:
        raise ValueError("mode must be 'full-history' or 'common-window'")
    config = config or BacktestConfig()

    # Audit broker-specific execution assumptions separately from OHLC readiness.
    # Exploratory runs remain possible by default, but the result artifacts always
    # disclose whether point/contract/volume/tick values matched captured MT5 specs.
    execution_spec_audit = audit_processed_execution_specs(data_dir, config=config)
    expected_spec_status = "MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE"
    fatal_spec_statuses = {
        "TICK_VALUE_MISMATCH", "CALC_MODE_UNSUPPORTED", "CALC_MODE_MISMATCH",
        "SYMBOL_MISMATCH", "BROKER_MISMATCH", "CROSS_DATASET_SPEC_MISMATCH",
    }
    if execution_spec_audit["overall_status"] in fatal_spec_statuses:
        raise RuntimeError(
            "Execution specification gate blocked the backtest due to spec mismatch: "
            f"status={execution_spec_audit['overall_status']}. Capture specifications from the intended MT5 "
            "terminal using scripts/capture_mt5_execution_specs.py, then rerun scripts/audit_execution_specs.py. "
            "A matching specification still does not authenticate historical data provenance."
        )
    if require_matched_execution_spec and execution_spec_audit["overall_status"] != expected_spec_status:
        raise RuntimeError(
            "Execution specification gate blocked the backtest: "
            f"status={execution_spec_audit['overall_status']}. Capture specifications from the intended MT5 "
            "terminal using scripts/capture_mt5_execution_specs.py, then rerun scripts/audit_execution_specs.py. "
            "A matching specification still does not authenticate historical data provenance."
        )

    audit = audit_all_datasets(str(data_dir))
    readiness = evaluate_research_readiness(audit)
    if readiness["overall_status"] == "BLOCKED":
        blockers = "; ".join(readiness.get("blockers", []))
        raise RuntimeError(f"Research data gate is BLOCKED. Backtest not run. {blockers}")

    datasets = load_and_verify_inputs(data_dir, timeframes=timeframes)
    if mode == "common-window":
        common_start, common_end = _common_window(datasets, timeframes)
    else:
        common_start = common_end = None

    all_trades: list[dict[str, Any]] = []
    per_timeframe: dict[str, Any] = {}
    all_funnels: dict[str, Any] = {}

    for tf in timeframes:
        original_df, meta = datasets[tf]
        frame = original_df.copy().reset_index(drop=True)
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        if mode == "common-window":
            # Preserve earlier bars for swing/structure context but never execute
            # beyond the common end. Signals before the common start are omitted.
            frame = frame.loc[frame["time"] <= common_end].copy().reset_index(drop=True)
        if frame.empty:
            raise ValueError(f"No {tf} bars remain after applying the selected date window")

        analysis = analyze_smc(frame, symbol="XAUUSD", timeframe=tf, config=SMCConfig())
        candidates, funnel = detect_smc_setups_with_funnel(frame, analysis, SMCSetupConfig())
        candidates_before_window = len(candidates)
        if mode == "common-window":
            candidates = [c for c in candidates if pd.Timestamp(c.signal_time) >= common_start]
        records = _candidate_records(candidates, tf)
        result = run_event_backtest(frame, records, config, timeframe=tf)
        all_trades.extend(result.trades)
        per_timeframe[tf] = {
            **result.metrics,
            "rows_used_for_simulation": len(frame),
            "start_time": frame["time"].min().isoformat(),
            "end_time": frame["time"].max().isoformat(),
            "source_verification_status": meta.get("source_verification_status"),
            "source_declared": meta.get("source"),
            "candidate_funnel": funnel,
            "candidates_before_window_filter": candidates_before_window,
            "candidates_simulated": len(records),
            "equity_curve": result.equity_curve,
            "realized_equity_curve": result.realized_equity_curve,
        }
        all_funnels[tf] = funnel

    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "report_title": "GoldFlow Phase 3D — Pure-SMC Event-Driven Backtest",
        "generated_at_utc": generated_at,
        "mode": mode,
        "instrument": "XAUUSD",
        "timeframes": timeframes,
        "common_window": {"start": common_start.isoformat(), "end": common_end.isoformat()} if common_start is not None else None,
        "readiness_status": readiness["overall_status"],
        "readiness_blockers": readiness.get("blockers", []),
        "readiness_warnings": {tf: audit.get(tf, {}).get("warnings", []) for tf in timeframes},
        "execution_spec_audit_status": execution_spec_audit["overall_status"],
        "execution_spec_audit": execution_spec_audit,
        "source_provenance_caveat": "MT5 API is declared in the bundled sidecars; this script does not independently authenticate the broker or certify future executable fills.",
        "execution_assumptions": {
            "ohlc_quote_convention": "Input OHLC treated as bid-side prices",
            "entry": "next bar open; long fills at ask (bid open + bar spread) and short fills at bid; adverse slippage applied",
            "spread": "MT5 bar spread points multiplied by configurable point_size when positive; otherwise fixed fallback USD spread",
            "slippage": "Adverse price slippage per side; stops and end-of-data exits slippage-adjusted; take-profit limit fill assumes no exit slippage after touch",
            "intrabar_collision": "If a candle touches both stop and target, stop is filled first",
            "gap_handling": "A gap through stop fills at the worse opening executable quote plus slippage",
            "sizing": "Fixed fractional equity risk with executable stop distance including stop slippage and round-trip commission estimate; lot sizes rounded down to lot_step",
            "concurrency": "Concurrent positions are capped independently within each timeframe run; a slot is not reused based on unknown intrabar exit order",
            "end_of_data": "Remaining positions are closed at the last close with spread/slippage assumptions and marked END_OF_DATA",
            "time_stop": f"Optional maximum holding cap of {config.max_holding_bars} bars; entry bar counts as bar 1. Stop/target logic has priority, otherwise exits occur at the completed bar close with adverse slippage and quote-side spread treatment.",
            "common_window_method": "In common-window mode, earlier history is retained as warm-up/context; only signal bars at or after common_start are eligible, and execution stops at common_end. This can differ from Phase 3C counts produced by re-running detection on a window-only slice.",
        },
        "config": config.__dict__,
        "metrics_by_timeframe": per_timeframe,
    }
    suffix = "common_window" if mode == "common-window" else "full_history"
    metrics_path = output_dir / f"smc_backtest_metrics_{suffix}.json"
    trades_path = output_dir / f"smc_backtest_trades_{suffix}.csv"
    report_path = output_dir / f"PHASE3D_SMC_EVENT_BACKTEST_{suffix.upper()}.md"
    # Keep canonical paths for UI consumers while preserving both comparison runs.
    canonical_metrics_path = output_dir / "smc_backtest_metrics.json"
    canonical_trades_path = output_dir / "smc_backtest_trades.csv"
    canonical_report_path = output_dir / "PHASE3D_SMC_EVENT_BACKTEST.md"
    def portable(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(ROOT.resolve()))
        except ValueError:
            return str(path.resolve())

    payload["artifact_paths"] = {
        "metrics_json": portable(metrics_path),
        "trades_csv": portable(trades_path),
        "markdown_report": portable(report_path),
        "latest_metrics_json": portable(canonical_metrics_path),
        "latest_trades_csv": portable(canonical_trades_path),
        "latest_markdown_report": portable(canonical_report_path),
    }
    metrics_text = json.dumps(payload, indent=2, default=str)
    trades_df = pd.DataFrame(all_trades)
    report_text = _markdown_report(payload, trades_df)
    metrics_path.write_text(metrics_text, encoding="utf-8")
    trades_df.to_csv(trades_path, index=False)
    report_path.write_text(report_text, encoding="utf-8")
    canonical_metrics_path.write_text(metrics_text, encoding="utf-8")
    trades_df.to_csv(canonical_trades_path, index=False)
    canonical_report_path.write_text(report_text, encoding="utf-8")
    return payload


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (float, int)):
        return f"{value:,.{digits}f}"
    return str(value)


def _markdown_report(payload: dict[str, Any], trades: pd.DataFrame) -> str:
    lines = [
        "# GoldFlow Phase 3D — Pure-SMC Event-Driven Backtest",
        "",
        f"**Generated UTC:** {payload['generated_at_utc']}",
        f"**Mode:** {payload['mode']}",
        f"**Data readiness:** {payload['readiness_status']}",
        f"**Execution specification audit:** {payload.get('execution_spec_audit_status', 'NOT_RECORDED')}",
        "",
        "> **Interpretation warning:** This is a model-based historical simulation, not a live/broker execution record or a claim of future profitability. The sidecars declare MT5 API provenance, but this project does not independently authenticate the broker data or contract specification.",
        "",
    ]
    if payload.get("execution_spec_audit_status") != "MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE":
        lines += [
            "> **EXECUTION-SPECIFICATION WARNING:** Point size, contract size, volume limits and/or tick specifications are missing or do not match this run's configuration. Treat cash P&L, position sizing and risk estimates as assumption-based, not broker-equivalent. Run `scripts/capture_mt5_execution_specs.py` with the intended MT5 terminal and then rerun the audit. A matched specification still does not authenticate the historical feed.",
            "",
        ]
    reconciled = payload.get("execution_spec_audit", {}).get("reconciled_discrepancies", [])
    if reconciled:
        lines += [
            "> **TICK-VALUE RECONCILIATION NOTICE:** The execution specification audit reconciled a broker property discrepancy (`symbol_info.trade_tick_value = 0.1` vs linear contract formula expected 1.00 USD/tick) using live MT5 `order_calc_profit` inquiries. Profit calculations use the empirically authoritative linear formula `(exit - entry) * contract_size * lots`.",
            "",
        ]
    lines += ["## Execution assumptions", ""]
    for key, value in payload["execution_assumptions"].items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
    lines += [
        "", "## Results by timeframe", "",
        "| Timeframe | Candidates | Rule exits | Time stops | End-of-data | Skipped | Win rate* | Net P&L** | Return** | Profit factor* | Max DD** | Avg R* |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for tf in payload["timeframes"]:
        m = payload["metrics_by_timeframe"][tf]
        win_rate = "N/A" if m["win_rate_pct"] is None else f"{_fmt(m['win_rate_pct'])}%"
        lines.append(
            f"| {tf} | {m['candidate_count']} | {m['rule_exit_trades']} | {m.get('time_stop_exits', 0)} | {m['end_of_data_exits']} | {m['skipped_candidates']} | "
            f"{win_rate} | ${_fmt(m['net_profit'])} | {_fmt(m['return_pct'])}% | "
            f"{_fmt(m['profit_factor'])} | ${_fmt(m['max_drawdown_cash'])} ({_fmt(m['max_drawdown_pct'])}%) | {_fmt(m['average_R_multiple'])} |"
        )
    lines += [
        "",
        "* Win rate and profit factor exclude END_OF_DATA exits, which are sample-boundary marks rather than stop/target outcomes.",
        "** Net P&L and return include END_OF_DATA liquidation P&L. Inspect `end_of_data_pnl` before interpreting these metrics. Max drawdown is close-to-close mark-to-market; `max_realized_drawdown_cash` is also present in the JSON for comparison.",
        "",
        "## Candidate exclusions",
        "",
    ]
    for tf in payload["timeframes"]:
        m = payload["metrics_by_timeframe"][tf]
        lines.append(f"### {tf}")
        reasons = m.get("skipped_by_reason", {})
        if reasons:
            lines.extend([f"- {reason}: {count}" for reason, count in reasons.items()])
        else:
            lines.append("- No candidates skipped by the execution layer.")
        lines.append("")
    lines += [
        "## Method notes and limitations",
        "",
        "- Signals are produced by the documented Pure-SMC setup detector; entries use the next candle open rather than the signal close or order-block edge.",
        "- Stop/target references come from the setup candidate. Candidates with levels invalid relative to the cost-adjusted fill are rejected and logged.",
        "- The simulator uses OHLC bars, not tick data. Stop-first is a conservative rule for bars that touch both stop and target; it cannot reconstruct the true intrabar path.",
        "- Position sizing assumes the configured contract size and price-value relationship. Verify contract size, point size, lot step, and commissions against the broker symbol specification before interpreting cash P&L as broker-equivalent.",
        "- An END_OF_DATA exit is a forced liquidation at the sample boundary; it is not a stop/target result. Net P&L and return include it; win rate, profit factor, expectancy and average R exclude it. TIME_STOP exits are included among rule exits and counted separately.",
        "- Optional `max_holding_bars` time stops use the completed bar close after checking stop/target exits. The entry bar counts as bar 1; the same number of bars represents different elapsed time across timeframes.",
        "- Maximum drawdown uses a close-to-close mark-to-market equity path that estimates open-position liquidation at the executable close quote with modeled slippage and round-turn commission. A realized-only drawdown metric is available separately. OHLC cannot reconstruct intrabar equity minima.",
        "- Stop gaps can exceed the planned risk budget. The trade log records such cases; fixed-fractional sizing does not guarantee a maximum loss under gaps.",
        "- Timeframes may cover different historical ranges in full-history mode. Do not treat those as a controlled cross-timeframe comparison. Use `--mode common-window` for a shared date window. Common-window mode retains pre-window bars as warm-up/context and filters executed signals to the shared dates; counts may differ from Phase 3C's window-only re-detection at the boundary.",
        "- This is not a walk-forward or out-of-sample validation. The candidate rules and parameters have been examined on these data; reserve a later untouched period for validation before drawing strategy conclusions.",
        "- ICT remains a separate event engine and is not benchmarked here because the repository handoff says no complete ICT entry/exit strategy is specified.",
        "",
        "## Artifacts",
        "",
        f"- `{Path(payload['artifact_paths']['metrics_json']).name}` — assumptions, readiness state, metrics, and equity curves.",
        f"- `{Path(payload['artifact_paths']['trades_csv']).name}` — closed trades and skipped candidates with traceable setup IDs.",
        f"- `{Path(payload['artifact_paths']['markdown_report']).name}` — human-readable summary.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GoldFlow Phase 3D SMC event-driven backtest")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--timeframes", nargs="+", choices=TIMEFRAMES, default=TIMEFRAMES)
    parser.add_argument("--mode", choices=["full-history", "common-window"], default="full-history")
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
    parser.add_argument("--max-holding-bars", type=int, default=None, help="Optional time stop in bars, counting the entry bar as bar 1")
    parser.add_argument(
        "--require-matched-execution-spec",
        action="store_true",
        help="Refuse to run unless captured MT5 point/contract/volume/tick specifications match this config.",
    )
    args = parser.parse_args()
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
        max_holding_bars=args.max_holding_bars,
    )
    try:
        payload = run_backtest_pipeline(
            args.data_dir,
            args.output_dir,
            timeframes=args.timeframes,
            mode=args.mode,
            config=config,
            require_matched_execution_spec=args.require_matched_execution_spec,
        )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"BACKTEST NOT RUN: {exc}", file=sys.stderr)
        return 2
    print(
        f"Mode: {payload['mode']} | Data readiness: {payload['readiness_status']} | "
        f"Execution specs: {payload['execution_spec_audit_status']}"
    )
    for tf in payload["timeframes"]:
        m = payload["metrics_by_timeframe"][tf]
        print(f"{tf}: {m['closed_trades']} closed / {m['candidate_count']} candidates | net ${m['net_profit']:.2f} | return {m['return_pct']:.2f}% | max DD ${m['max_drawdown_cash']:.2f}")
    print(f"Report: {payload['artifact_paths']['markdown_report']}")
    print(f"Metrics: {payload['artifact_paths']['metrics_json']}")
    print(f"Trades: {payload['artifact_paths']['trades_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
