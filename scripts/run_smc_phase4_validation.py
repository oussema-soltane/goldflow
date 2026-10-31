"""GoldFlow Phase 4 — SMC v1 Strategy Validation Runner.

Performs a reproducible, three-way chronological evaluation of the frozen SMC v1
strategy on each configured timeframe. Signal detection and execution use the
same code as the Phase 3D backtest, with no rule changes.

Usage (from repository root):
  py -3.13 scripts/run_smc_phase4_validation.py
  py -3.13 scripts/run_smc_phase4_validation.py --timeframes H4 H1
  py -3.13 scripts/run_smc_phase4_validation.py --require-matched-execution-spec

Exit codes:
  0  Validation completed and reports written.
  2  Data-readiness or execution-spec gate blocked the run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backtesting.engine import BacktestConfig, run_event_backtest
from src.backtesting.split import ChronologicalSplit, SplitConfig
from src.research.data_readiness import audit_all_datasets, evaluate_research_readiness
from src.research.execution_spec_audit import audit_processed_execution_specs
from src.research.smc_research import load_and_verify_inputs
from src.smc.engine import SMCConfig, analyze_smc
from src.strategy.smc_setups import SMCSetupConfig, detect_smc_setups_with_funnel

TIMEFRAMES = ["H4", "H1", "M15", "M5"]
FROZEN_CONFIG_PATH = ROOT / "configs" / "smc_v1_frozen.json"

FATAL_SPEC_STATUSES = {
    "TICK_VALUE_MISMATCH", "CALC_MODE_UNSUPPORTED", "CALC_MODE_MISMATCH",
    "SYMBOL_MISMATCH", "BROKER_MISMATCH", "CROSS_DATASET_SPEC_MISMATCH",
}
MATCHED_SPEC_STATUS = "MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE"

# Frozen config schema version this code expects.
EXPECTED_FROZEN_SCHEMA = "smc_v1_frozen_strategy"

# Required frozen config sections and their required sub-fields.
_FROZEN_REQUIRED_FIELDS: dict[str, list[str]] = {
    "swing_identification": ["swing_window_k"],
    "sweep_identification": ["min_penetration_price_units", "max_sweep_to_choch_bars"],
    "liquidity_pool": ["equal_level_tolerance_price_units"],
    "order_block": ["lookback_bars", "zone_basis"],
    "retest_conditions": ["max_bars_choch_to_retest"],
    "stop_loss": ["stop_buffer_price_units"],
    "take_profit": ["fixed_rr_fallback"],
    "risk_management": ["risk_fraction", "initial_capital_usd"],
    "execution_costs": [
        "contract_size_oz", "fallback_spread_usd",
        "slippage_per_side_usd", "commission_per_lot_per_side_usd",
    ],
}


def _load_and_validate_frozen_config(path: Path) -> dict[str, Any]:
    """Load frozen config JSON and strictly validate schema.

    Raises RuntimeError for missing/unknown/bad-type fields so a report
    can never claim 'frozen SMC v1' while actually running defaults.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"Frozen config not found: {path}. "
            f"This file must exist before Phase 4 validation can run."
        )
    with open(path, encoding="utf-8") as _f:
        cfg = json.load(_f)

    schema = cfg.get("_schema")
    if schema != EXPECTED_FROZEN_SCHEMA:
        raise RuntimeError(
            f"Frozen config schema mismatch: expected {EXPECTED_FROZEN_SCHEMA!r}, "
            f"got {schema!r}. Update EXPECTED_FROZEN_SCHEMA or fix the config file."
        )

    rules = cfg.get("strategy_rules", {})
    if not rules:
        raise RuntimeError(
            "Frozen config is missing 'strategy_rules' section. "
            "Cannot proceed without validated strategy parameters."
        )

    missing: list[str] = []
    for section, fields in _FROZEN_REQUIRED_FIELDS.items():
        sec = rules.get(section)
        if sec is None:
            missing.append(f"strategy_rules.{section} (entire section missing)")
            continue
        for field in fields:
            if field not in sec:
                missing.append(f"strategy_rules.{section}.{field}")

    if missing:
        raise RuntimeError(
            f"Frozen config is missing required fields: {missing}. "
            "All required fields must be present before Phase 4 validation."
        )

    return cfg


def _frozen_config_sha256(path: Path) -> str:
    """Compute SHA-256 of the frozen config file bytes."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _frozen_to_smc_config(frozen_cfg: dict[str, Any]) -> "SMCConfig":
    """Map frozen config fields to an SMCConfig object.

    This is the ONLY place SMCConfig is instantiated for Phase 4.
    Values come exclusively from the frozen JSON, not Python defaults.
    """
    rules = frozen_cfg["strategy_rules"]
    swing_k = int(rules["swing_identification"]["swing_window_k"])
    tol = float(rules["liquidity_pool"]["equal_level_tolerance_price_units"])
    min_pen = float(rules["sweep_identification"]["min_penetration_price_units"])
    ob_lookback = int(rules["order_block"]["lookback_bars"])
    ob_basis = str(rules["order_block"]["zone_basis"])

    return SMCConfig(
        swing_window=swing_k,
        equal_level_tolerance=tol,
        min_sweep_penetration=min_pen,
        order_block_lookback=ob_lookback,
        order_block_zone_basis=ob_basis,
        track_order_block_lifecycle=True,
    )


def _frozen_to_setup_config(
    frozen_cfg: dict[str, Any],
) -> "SMCSetupConfig":
    """Map frozen config fields to an SMCSetupConfig object."""
    rules = frozen_cfg["strategy_rules"]
    max_sweep_to_choch = int(rules["sweep_identification"]["max_sweep_to_choch_bars"])
    max_choch_to_retest = int(rules["retest_conditions"]["max_bars_choch_to_retest"])
    stop_buf = float(rules["stop_loss"]["stop_buffer_price_units"])
    fixed_rr = float(rules["take_profit"]["fixed_rr_fallback"])

    return SMCSetupConfig(
        max_sweep_to_choch_bars=max_sweep_to_choch,
        max_bars_choch_to_retest=max_choch_to_retest,
        stop_buffer=stop_buf,
        fixed_rr=fixed_rr,
        use_opposing_liquidity_target=True,
    )


def _frozen_to_backtest_config(
    frozen_cfg: dict[str, Any],
    override: "Optional[BacktestConfig]" = None,
) -> "BacktestConfig":
    """Map execution cost fields from frozen config to a BacktestConfig.

    If override is provided (e.g. from CLI args), it takes precedence and a
    mismatch warning is emitted but execution is not blocked.
    """
    rules = frozen_cfg["strategy_rules"]
    costs = rules["execution_costs"]
    risk = rules["risk_management"]

    frozen_bc = BacktestConfig(
        initial_capital=float(risk["initial_capital_usd"]),
        risk_fraction=float(risk["risk_fraction"]),
        fallback_spread_usd=float(costs["fallback_spread_usd"]),
        slippage_per_side_usd=float(costs["slippage_per_side_usd"]),
        commission_per_lot_per_side=float(costs["commission_per_lot_per_side_usd"]),
    )
    if override is not None:
        mismatches: list[str] = []
        for field in ("initial_capital", "risk_fraction", "fallback_spread_usd",
                      "slippage_per_side_usd", "commission_per_lot_per_side"):
            fv = getattr(frozen_bc, field, None)
            ov = getattr(override, field, None)
            if fv is not None and ov is not None and abs(float(fv) - float(ov)) > 1e-9:
                mismatches.append(
                    f"  {field}: frozen={fv}, provided={ov}"
                )
        if mismatches:
            print(
                "[WARNING] BacktestConfig from CLI args differs from frozen config values:",
                file=sys.stderr,
            )
            for m in mismatches:
                print(m, file=sys.stderr)
            print(
                "  Using CLI-provided values. Report will note this discrepancy.",
                file=sys.stderr,
            )
        return override
    return frozen_bc


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _candidate_records(candidates: list[Any], timeframe: str) -> list[dict[str, Any]]:
    records = []
    for n, candidate in enumerate(candidates, start=1):
        record = candidate.to_dict()
        record["setup_id"] = f"SMC_{timeframe}_{n:04d}"
        record["timeframe"] = timeframe
        records.append(record)
    return records


def _run_segment(
    full_df: pd.DataFrame,
    segment_df: pd.DataFrame,
    seg_start_idx: int,
    seg_end_idx: int,
    segment_label: str,
    tf: str,
    config: BacktestConfig,
    smc_config: Optional[SMCConfig] = None,
    setup_config: Optional[SMCSetupConfig] = None,
) -> dict[str, Any]:
    """Run SMC detection+backtest on a single chronological segment.

    SMC analysis runs on the FULL dataset up through the end of the segment
    so that swing/structure context from earlier bars is always available.
    Only candidates whose signal_index falls within the segment's actual row range
    [seg_start_idx, seg_end_idx] are executed.

    This preserves the forward-bias-free principle: detection uses no
    information beyond what was available at each bar's close.

    Parameters
    ----------
    smc_config : SMCConfig, optional
        Must be instantiated from the frozen JSON via _frozen_to_smc_config()
        when running validation. Falls back to SMCConfig() if None.
    setup_config : SMCSetupConfig, optional
        Must be instantiated from the frozen JSON via _frozen_to_setup_config()
        when running validation. Falls back to SMCSetupConfig() if None.
    """
    if smc_config is None:
        smc_config = SMCConfig()
    if setup_config is None:
        setup_config = SMCSetupConfig()
    # Use the full bars up through end of segment for analysis context
    analysis_df = full_df.iloc[:seg_end_idx + 1].copy().reset_index(drop=True)
    analysis = analyze_smc(analysis_df, symbol="XAUUSD", timeframe=tf, config=smc_config)
    candidates, funnel = detect_smc_setups_with_funnel(analysis_df, analysis, setup_config)

    # Filter to candidates whose signal falls within this segment
    candidates_in_segment = [
        c for c in candidates
        if seg_start_idx <= c.signal_index <= seg_end_idx
    ]

    # Remap signal_index to segment-local indices for the backtest engine.
    # The segment_df is reset-indexed starting at 0, so we subtract seg_start_idx.
    local_candidates = []
    segment_reset = segment_df.copy().reset_index(drop=True)
    for c in candidates_in_segment:
        d = c.to_dict()
        d["signal_index"] = c.signal_index - seg_start_idx
        d["setup_id"] = d.get("setup_id", f"SMC_{tf}_seg_{c.signal_index}")
        d["timeframe"] = tf
        local_candidates.append(d)

    result = run_event_backtest(segment_reset, local_candidates, config, timeframe=tf)
    m = result.metrics
    return {
        "segment": segment_label,
        "timeframe": tf,
        "segment_start": segment_reset["time"].iloc[0].isoformat() if len(segment_reset) else None,
        "segment_end": segment_reset["time"].iloc[-1].isoformat() if len(segment_reset) else None,
        "n_rows": len(segment_reset),
        "candidates_from_full_context": len(candidates_in_segment),
        "candidates_simulated": len(local_candidates),
        "candidate_count": m["candidate_count"],
        "closed_trades": m["closed_trades"],
        "rule_exit_trades": m["rule_exit_trades"],
        "end_of_data_exits": m["end_of_data_exits"],
        "skipped_candidates": m["skipped_candidates"],
        "wins": m["wins"],
        "losses": m["losses"],
        "win_rate_pct": m["win_rate_pct"],
        "net_profit": m["net_profit"],
        "return_pct": m["return_pct"],
        "profit_factor": m["profit_factor"],
        "expectancy_per_rule_exit": m["expectancy_per_rule_exit"],
        "average_R_multiple": m["average_R_multiple"],
        "max_drawdown_cash": m["max_drawdown_cash"],
        "max_drawdown_pct": m["max_drawdown_pct"],
        "max_realized_drawdown_cash": m["max_realized_drawdown_cash"],
        "end_of_data_pnl": m["end_of_data_pnl"],
        "total_commission": m["total_commission"],
        "stop_gap_exits": m["stop_gap_exits"],
        "funnel": funnel,
        "equity_curve": result.equity_curve,
        "realized_equity_curve": result.realized_equity_curve,
        "trades": result.trades,
    }


def run_phase4_validation(
    data_dir: Path = ROOT / "data" / "processed",
    output_dir: Path = ROOT / "reports",
    *,
    timeframes: Optional[list[str]] = None,
    config: Optional[BacktestConfig] = None,
    split_config: Optional[SplitConfig] = None,
    require_matched_execution_spec: bool = False,
) -> dict[str, Any]:
    """Run the Phase 4 three-way chronological validation pipeline."""
    timeframes = [tf.upper() for tf in (timeframes or TIMEFRAMES)]
    unknown = sorted(set(timeframes) - set(TIMEFRAMES))
    if unknown:
        raise ValueError(f"Unsupported timeframe(s): {', '.join(unknown)}")
    config = config or BacktestConfig()
    split_config = split_config or SplitConfig()

    # --- Gate 1: Execution spec ---
    execution_spec_audit = audit_processed_execution_specs(data_dir, config=config)
    if execution_spec_audit["overall_status"] in FATAL_SPEC_STATUSES:
        raise RuntimeError(
            f"Execution specification gate blocked Phase 4 validation: "
            f"status={execution_spec_audit['overall_status']}"
        )
    if require_matched_execution_spec and execution_spec_audit["overall_status"] != MATCHED_SPEC_STATUS:
        raise RuntimeError(
            f"Execution specification gate blocked Phase 4 validation (strict mode): "
            f"status={execution_spec_audit['overall_status']}"
        )

    # --- Gate 2: Data readiness ---
    audit_result = audit_all_datasets(str(data_dir))
    readiness = evaluate_research_readiness(audit_result)
    if readiness["overall_status"] == "BLOCKED":
        blockers = "; ".join(readiness.get("blockers", []))
        raise RuntimeError(f"Research data gate is BLOCKED. Phase 4 not run. {blockers}")

    # --- Load datasets ---
    datasets = load_and_verify_inputs(data_dir, timeframes=timeframes)

    # --- Load frozen config ---
    frozen_config = _load_and_validate_frozen_config(FROZEN_CONFIG_PATH)
    frozen_sha = _frozen_config_sha256(FROZEN_CONFIG_PATH)
    smc_config = _frozen_to_smc_config(frozen_config)
    setup_config = _frozen_to_setup_config(frozen_config)
    config = _frozen_to_backtest_config(frozen_config, override=config)

    generated_at = datetime.now(timezone.utc).isoformat()
    per_timeframe: dict[str, Any] = {}
    all_trades: list[dict[str, Any]] = []

    for tf in timeframes:
        original_df, meta = datasets[tf]
        frame = original_df.copy().reset_index(drop=True)
        frame["time"] = pd.to_datetime(frame["time"], utc=True)

        # Compute input fingerprint
        csv_path = data_dir / f"XAUUSD_{tf}_clean.csv"
        fingerprint = _file_sha256(csv_path) if csv_path.exists() else "unavailable"

        # Create split
        split = ChronologicalSplit(frame, split_config)

        tf_result: dict[str, Any] = {
            "timeframe": tf,
            "total_rows": len(frame),
            "data_start": frame["time"].min().isoformat(),
            "data_end": frame["time"].max().isoformat(),
            "input_sha256": fingerprint,
            "source_verification_status": meta.get("source_verification_status"),
            "split_summary": split.summary(),
            "segments": {},
        }

        for seg_info in split.segments:
            seg_df = split.get_segment(seg_info.label)
            seg_result = _run_segment(
                frame,
                seg_df,
                seg_info.row_start,
                seg_info.row_end - 1,
                seg_info.label,
                tf,
                config,
                smc_config=smc_config,
                setup_config=setup_config,
            )
            # Tag trades with segment label
            for trade in seg_result["trades"]:
                trade["segment"] = seg_info.label
                trade["timeframe"] = tf
                all_trades.append(trade)

            tf_result["segments"][seg_info.label] = {
                k: v for k, v in seg_result.items() if k not in ("trades", "equity_curve", "realized_equity_curve")
            }
            tf_result["segments"][seg_info.label]["equity_curve"] = seg_result["equity_curve"]

        per_timeframe[tf] = tf_result

    # De-dup trades list
    seen_ids: set[str] = set()
    deduped_trades: list[dict[str, Any]] = []
    for t in all_trades:
        tid = f"{t.get('timeframe')}_{t.get('segment')}_{t.get('setup_id')}_{t.get('entry_time', '')}"
        if tid not in seen_ids:
            seen_ids.add(tid)
            deduped_trades.append(t)
    all_trades = deduped_trades

    payload: dict[str, Any] = {
        "report_title": "GoldFlow Phase 4 — SMC v1 Chronological Strategy Validation",
        "generated_at_utc": generated_at,
        "instrument": "XAUUSD",
        "timeframes": timeframes,
        "frozen_strategy_config_path": str(FROZEN_CONFIG_PATH.relative_to(ROOT)),
        "frozen_strategy_config_sha256": frozen_sha,
        "frozen_strategy_version": frozen_config.get("_strategy_name", "SMC v1"),
        "frozen_strategy_rules": frozen_config.get("strategy_rules", {}),
        "readiness_status": readiness["overall_status"],
        "execution_spec_audit_status": execution_spec_audit["overall_status"],
        "split_config": {
            "train_fraction": split_config.train_fraction,
            "validate_fraction": split_config.validate_fraction,
            "holdout_fraction": split_config.holdout_fraction,
        },
        "backtest_config": config.__dict__,
        "per_timeframe": per_timeframe,
        "evaluation_warnings": [
            "DATA PROVENANCE: Declared as MT5, not independently authenticated (UNVERIFIED_PROVENANCE).",
            "IN-SAMPLE RESULTS: Phase 3C/3D examined the full training segment. Not a fresh discovery.",
            "SAMPLE SIZE: Trade counts per segment are small. Statistical conclusions are unreliable.",
            "OOS CAVEAT: The validate/holdout segments were inspected in Phases 3C/3D via the full-history runs. Treat this as chronological stability testing, not genuinely unseen evaluation.",
            "NO OPTIMIZATION: Strategy parameters were NOT tuned to these segment results.",
            "COST ASSUMPTIONS: Spread/slippage use the same frozen cost scenario as Phase 3D. See robustness report for sensitivity.",
        ],
    }

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    payload["run_id"] = run_id

    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = output_dir / "smc_phase4_validation_metrics.json"
    trades_path = output_dir / "smc_phase4_validation_trades.csv"
    report_path = output_dir / "PHASE4_STRATEGY_VALIDATION.md"

    # Archive previous outputs if they exist rather than silently overwriting
    archive_dir = output_dir / "archive" / f"validation_pre_{run_id}"
    archived_any = False
    for p in (metrics_path, trades_path, report_path):
        if p.is_file():
            if not archived_any:
                archive_dir.mkdir(parents=True, exist_ok=True)
                archived_any = True
            shutil.copy2(p, archive_dir / p.name)

    payload["artifact_paths"] = {
        "metrics_json": str(metrics_path.relative_to(ROOT)),
        "trades_csv": str(trades_path.relative_to(ROOT)),
        "report_md": str(report_path.relative_to(ROOT)),
    }

    metrics_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(all_trades).to_csv(trades_path, index=False)
    report_text = _build_markdown_report(payload)
    report_path.write_text(report_text, encoding="utf-8")

    return payload


def _fmt(v: Any, d: int = 2) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:,.{d}f}"
    return str(v)


def _build_markdown_report(payload: dict[str, Any]) -> str:
    lines: list[str] = [
        "# GoldFlow Phase 4 — SMC v1 Chronological Strategy Validation",
        "",
        f"**Generated UTC:** {payload['generated_at_utc']}",
        f"**Strategy:** {payload['frozen_strategy_version']} (frozen in `configs/smc_v1_frozen.json`)",
        f"**Data readiness:** {payload['readiness_status']}",
        f"**Execution spec:** {payload['execution_spec_audit_status']}",
        "",
        "> **IMPORTANT LIMITATIONS:**",
        "> - Data provenance is **UNVERIFIED_PROVENANCE**: declared MT5, not independently authenticated.",
        "> - The validate/holdout segments were visible during Phases 3C/3D full-history analysis. This is chronological stability testing, not genuinely unseen OOS validation.",
        "> - Trade counts per segment are small. No statistical conclusions are supported.",
        "> - Strategy parameters were NOT optimized on any segment.",
        "> - Do not equate any positive backtest results with a repeatable live trading edge.",
        "",
    ]

    sc = payload.get("split_config", {})
    lines += [
        "## Chronological Split Configuration",
        "",
        f"| Segment | Fraction |",
        "|---|---|",
        f"| Training | {sc.get('train_fraction', 0)*100:.0f}% |",
        f"| Validation | {sc.get('validate_fraction', 0)*100:.0f}% |",
        f"| Holdout | {sc.get('holdout_fraction', 0)*100:.0f}% |",
        "",
        "The training segment overlaps with Phase 3C/3D inspection. The validation and holdout",
        "segments provide chronological stability diagnostics only.",
        "",
    ]

    for tf in payload.get("timeframes", []):
        tf_data = payload["per_timeframe"].get(tf, {})
        lines += [
            f"## {tf} Results",
            "",
            f"**Data range:** {tf_data.get('data_start', 'N/A')} to {tf_data.get('data_end', 'N/A')}",
            f"**Total rows:** {tf_data.get('total_rows', 'N/A')}",
            "",
            "| Segment | Rows | Start | End | Candidates | Rule Exits | EOD | Win Rate | Net P&L | Profit Factor | Max DD |",
            "|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for seg_label in ("train", "validate", "holdout"):
            seg = tf_data.get("segments", {}).get(seg_label, {})
            if not seg:
                lines.append(f"| {seg_label} | — | — | — | — | — | — | — | — | — | — |")
                continue
            wr = _fmt(seg.get("win_rate_pct")) + "%" if seg.get("win_rate_pct") is not None else "N/A"
            pf = _fmt(seg.get("profit_factor")) if seg.get("profit_factor") not in (None, "infinite") else str(seg.get("profit_factor"))
            lines.append(
                f"| {seg_label} | {seg.get('n_rows', 0)} "
                f"| {(seg.get('segment_start') or '')[:10]} "
                f"| {(seg.get('segment_end') or '')[:10]} "
                f"| {seg.get('candidate_count', 0)} "
                f"| {seg.get('rule_exit_trades', 0)} "
                f"| {seg.get('end_of_data_exits', 0)} "
                f"| {wr} "
                f"| ${_fmt(seg.get('net_profit', 0))} "
                f"| {pf} "
                f"| ${_fmt(seg.get('max_drawdown_cash', 0))} |"
            )

        # EOD note
        for seg_label in ("train", "validate", "holdout"):
            seg = tf_data.get("segments", {}).get(seg_label, {})
            eod_pnl = seg.get("end_of_data_pnl", 0) or 0
            if abs(eod_pnl) > 1.0:
                lines.append(
                    f"\n> **{seg_label} END_OF_DATA warning:** ${eod_pnl:.2f} from forced liquidation "
                    "at segment boundary. Excluded from win rate and profit factor but included in net P&L."
                )

        split_warn = tf_data.get("split_summary", {}).get("warnings", [])
        for w in split_warn:
            lines.append(f"\n> **Split warning ({tf}):** {w}")
        lines.append("")

    lines += [
        "## Method Notes",
        "",
        "- SMC detection runs on the full history up through each segment end to preserve swing/structure context.",
        "- Only candidates whose signal bar falls within the target segment are evaluated.",
        "- Signal bars, stop levels, and take-profit targets use the frozen SMC v1 rules (see `configs/smc_v1_frozen.json`).",
        "- Trade execution: next-bar-open, bid-side bars, conservative stop-first, no look-ahead.",
        "- END_OF_DATA exits excluded from win rate, profit factor, expectancy, and average R.",
        "- Drawdown: close-to-close mark-to-market; OHLC cannot reveal intrabar minima.",
        "- See `reports/smc_phase4_robustness_metrics.json` for cost sensitivity analysis.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="GoldFlow Phase 4 SMC v1 Chronological Validation")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--timeframes", nargs="+", choices=TIMEFRAMES, default=TIMEFRAMES)
    parser.add_argument("--train-fraction", type=float, default=0.60)
    parser.add_argument("--validate-fraction", type=float, default=0.20)
    parser.add_argument("--initial-capital", type=float, default=10_000.0)
    parser.add_argument("--risk-fraction", type=float, default=0.01)
    parser.add_argument("--fallback-spread-usd", type=float, default=0.20)
    parser.add_argument("--slippage-per-side-usd", type=float, default=0.05)
    parser.add_argument("--commission-per-lot-per-side", type=float, default=0.0)
    parser.add_argument(
        "--require-matched-execution-spec",
        action="store_true",
        help="Refuse to run unless MT5 specifications match config.",
    )
    args = parser.parse_args()

    config = BacktestConfig(
        initial_capital=args.initial_capital,
        risk_fraction=args.risk_fraction,
        fallback_spread_usd=args.fallback_spread_usd,
        slippage_per_side_usd=args.slippage_per_side_usd,
        commission_per_lot_per_side=args.commission_per_lot_per_side,
    )
    split_config = SplitConfig(
        train_fraction=args.train_fraction,
        validate_fraction=args.validate_fraction,
    )
    try:
        payload = run_phase4_validation(
            args.data_dir,
            args.output_dir,
            timeframes=args.timeframes,
            config=config,
            split_config=split_config,
            require_matched_execution_spec=args.require_matched_execution_spec,
        )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"PHASE 4 VALIDATION NOT RUN: {exc}", file=sys.stderr)
        return 2

    print(f"Readiness: {payload['readiness_status']} | Spec: {payload['execution_spec_audit_status']}")
    for tf in payload["timeframes"]:
        tf_data = payload["per_timeframe"][tf]
        print(f"\n{tf}  ({tf_data['total_rows']} rows, {tf_data['data_start'][:10]} to {tf_data['data_end'][:10]})")
        for seg_label in ("train", "validate", "holdout"):
            seg = tf_data["segments"].get(seg_label, {})
            if not seg:
                continue
            wr = f"{seg['win_rate_pct']:.1f}%" if seg.get("win_rate_pct") is not None else "N/A"
            print(
                f"  {seg_label:8s}: {seg['rule_exit_trades']:2d} rule exits "
                f"({seg['candidate_count']} cands) | "
                f"wr={wr} | net=${seg['net_profit']:.2f} | "
                f"PF={_fmt(seg['profit_factor'])} | maxDD=${seg['max_drawdown_cash']:.2f}"
            )
    print(f"\nReport: {payload['artifact_paths']['report_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
