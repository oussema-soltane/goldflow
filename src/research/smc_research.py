"""
GoldFlow Phase 3C — SMC Descriptive Research Protocol on Verified MT5 Data.

Implements rigorous, look-ahead-free descriptive measurements for Pure-SMC
events (swings, BOS, CHoCH, liquidity pools, sweeps, order blocks) and the
primary SMC reversal setup hypothesis (Sweep -> CHoCH -> OB Retest/Rejection).

Operates strictly on verified, non-synthetic MT5 datasets with verified
timestamp integrity and integer epoch provenance.

No execution logic, no order placement, no ML training, and no backtest
profitability claims are made here. Results are purely descriptive.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.data.cleaner import compute_file_sha256
from src.data.loader import load_local_data
from src.research.data_readiness import (
    DEFAULT_MINIMUM_BARS,
    audit_dataset,
    evaluate_research_readiness,
    load_meta,
)
from src.research.event_statistics import classify_session, compute_rolling_atr, measure_forward_excursion
from src.smc.engine import SMCConfig, analyze_smc
from src.smc.models import (
    SMCAnalysisResult,
    SMCDirection,
    SMCLiquidityType,
    SMCOrderBlockStatus,
    SMCStructureType,
    SMCSwingType,
)
from src.strategy.smc_setups import (
    SMCSetupCandidate,
    SMCSetupConfig,
    detect_smc_setups_with_funnel,
)


TIMEFRAMES = ["H4", "H1", "M15", "M5"]

DEFAULT_HORIZONS: Dict[str, List[int]] = {
    "M5": [6, 12, 24, 48],    # 30m, 1h, 2h, 4h
    "M15": [4, 8, 16, 32],   # 1h, 2h, 4h, 8h
    "H1": [4, 8, 16, 24],    # 4h, 8h, 16h, 24h
    "H4": [6, 12, 18, 30],   # 24h, 48h, 72h, 120h (1 week)
}

HORIZON_LABELS: Dict[str, Dict[int, str]] = {
    "M5": {6: "30m (6b)", 12: "1h (12b)", 24: "2h (24b)", 48: "4h (48b)"},
    "M15": {4: "1h (4b)", 8: "2h (8b)", 16: "4h (16b)", 32: "8h (32b)"},
    "H1": {4: "4h (4b)", 8: "8h (8b)", 16: "16h (16b)", 24: "24h (24b)"},
    "H4": {6: "24h (6b)", 12: "48h (12b)", 18: "72h (18b)", 30: "120h (30b)"},
}


@dataclass(frozen=True)
class ResearchProtocolConfig:
    smc_config: SMCConfig = field(default_factory=SMCConfig)
    setup_config: SMCSetupConfig = field(default_factory=SMCSetupConfig)
    horizons: Dict[str, List[int]] = field(default_factory=lambda: DEFAULT_HORIZONS)
    atr_period: int = 14


def load_and_verify_inputs(
    data_dir: Path,
    timeframes: List[str] = TIMEFRAMES,
    minimum_bars: Optional[Dict[str, int]] = None,
) -> Dict[str, Tuple[pd.DataFrame, Dict[str, Any]]]:
    """
    Load and verify all target MT5 datasets and their sidecars against the authoritative research readiness gate.
    Rejects synthetic, unverified, incomplete, or corrupted datasets immediately.
    """
    datasets: Dict[str, Tuple[pd.DataFrame, Dict[str, Any]]] = {}
    audited_reports: Dict[str, Dict[str, Any]] = {}

    for tf in timeframes:
        csv_path = data_dir / f"XAUUSD_{tf}_clean.csv"
        meta_path = data_dir / f"XAUUSD_{tf}_clean.meta.json"

        if not csv_path.exists():
            raise FileNotFoundError(f"Missing required dataset: {csv_path}")
        if not meta_path.exists():
            raise FileNotFoundError(f"Missing required metadata sidecar: {meta_path}")

        meta = load_meta(meta_path)
        if not meta:
            raise ValueError(f"Failed to load or parse metadata from {meta_path}")

        # Provenance enforcement
        if meta.get("is_synthetic") is not False:
            raise ValueError(f"Dataset {csv_path.name} is synthetic or lacks is_synthetic=False flag.")

        source = str(meta.get("source", "")).strip().lower()
        if not source or ("metatrader 5 api" not in source and source not in {"mt5", "metatrader5"}):
            raise ValueError(f"Dataset {csv_path.name} lacks verified MT5 source provenance (got: {meta.get('source')!r}).")

        if meta.get("timestamp_integrity_status") != "verified":
            raise ValueError(f"Dataset {csv_path.name} timestamp integrity status is not 'verified' (got: {meta.get('timestamp_integrity_status')!r}).")

        if meta.get("timestamp_mode_verified") is not True:
            raise ValueError(f"Dataset {csv_path.name} timestamp mode is not verified (timestamp_mode_verified={meta.get('timestamp_mode_verified')}).")

        timestamp_mode = meta.get("timestamp_mode")
        if timestamp_mode != "server_wall_clock":
            raise ValueError(f"Dataset {csv_path.name} mode is {timestamp_mode!r}, expected 'server_wall_clock'.")

        server_tz = meta.get("server_timezone")
        if server_tz != "Europe/Athens":
            raise ValueError(f"Dataset {csv_path.name} timezone is {server_tz!r}, expected 'Europe/Athens'.")

        if not meta.get("raw_timestamp_epoch_preserved"):
            raise ValueError(f"Dataset {csv_path.name} did not preserve raw MT5 epoch values.")

        # Incomplete active bar exclusion
        if meta.get("incomplete_bar_excluded") is False:
            raise ValueError(f"Dataset {csv_path.name} contains forming active candle (incomplete_bar_excluded is False).")

        df = load_local_data(csv_path)
        if df.empty:
            raise ValueError(f"Dataset {csv_path.name} is empty.")

        # Actual CSV row count matches metadata
        meta_row_count = meta.get("processed_row_count")
        if meta_row_count is not None and len(df) != int(meta_row_count):
            raise ValueError(f"Dataset {csv_path.name} row count {len(df)} does not match metadata processed_row_count {meta_row_count}.")

        # Minimum required bars
        min_bars = (minimum_bars or {}).get(tf, 100)
        if len(df) < min_bars:
            raise ValueError(f"Dataset {csv_path.name} has only {len(df)} rows; insufficient history (minimum required: {min_bars}).")

        # Dataframe integrity
        if "time" not in df.columns:
            raise ValueError(f"Dataset {csv_path.name} missing 'time' column.")
        if not hasattr(df["time"].dtype, "tz") or df["time"].dtype.tz is None:
            raise ValueError(f"Dataset {csv_path.name} timestamps are not UTC-aware.")
        if not df["time"].is_monotonic_increasing:
            raise ValueError(f"Dataset {csv_path.name} timestamps are not monotonically increasing.")
        if df["time"].duplicated().any():
            raise ValueError(f"Dataset {csv_path.name} contains duplicate timestamps.")

        # Future candle check relative to recorded retrieval time
        retrieval_value = meta.get("retrieval_date_utc")
        if retrieval_value:
            try:
                retrieval_ts = pd.Timestamp(retrieval_value)
                if retrieval_ts.tzinfo is None:
                    retrieval_ts = retrieval_ts.tz_localize("UTC")
                else:
                    retrieval_ts = retrieval_ts.tz_convert("UTC")
                future_count = int((df["time"] > retrieval_ts + pd.Timedelta(minutes=5)).sum())
                if future_count > 0:
                    raise ValueError(f"Dataset {csv_path.name} contains {future_count} future candle(s) relative to recorded retrieval time.")
            except (ValueError, TypeError) as exc:
                if "future candle" in str(exc):
                    raise

        # OHLC geometry validation
        ohlc_cols = ["open", "high", "low", "close"]
        for c in ohlc_cols:
            if c not in df.columns:
                raise ValueError(f"Dataset {csv_path.name} missing OHLC column {c!r}.")

        numeric_ohlc = df[ohlc_cols].apply(pd.to_numeric, errors="coerce")
        if not np.isfinite(numeric_ohlc.to_numpy(dtype=float)).all():
            raise ValueError(f"Dataset {csv_path.name} contains non-finite price values.")
        if (numeric_ohlc <= 0).any().any():
            raise ValueError(f"Dataset {csv_path.name} contains zero or negative prices.")
        bad_geometry = (
            (numeric_ohlc["high"] < numeric_ohlc["low"])
            | (numeric_ohlc["high"] < numeric_ohlc["open"])
            | (numeric_ohlc["high"] < numeric_ohlc["close"])
            | (numeric_ohlc["low"] > numeric_ohlc["open"])
            | (numeric_ohlc["low"] > numeric_ohlc["close"])
        )
        if bad_geometry.any():
            raise ValueError(f"Dataset {csv_path.name} contains {int(bad_geometry.sum())} OHLC boundary violations.")

        # Recorded hash check
        raw_source_name = meta.get("raw_source_file")
        raw_hash = meta.get("raw_file_sha256")
        if raw_source_name and raw_hash:
            raw_candidates = [
                data_dir.parent / "raw" / raw_source_name,
                data_dir / raw_source_name,
            ]
            raw_file = next((p for p in raw_candidates if p.is_file()), None)
            if raw_file:
                computed_hash = compute_file_sha256(raw_file)
                if computed_hash != raw_hash:
                    raise ValueError(f"Dataset {csv_path.name} raw file SHA256 mismatch: recorded {raw_hash[:12]} vs actual {computed_hash[:12]}.")

        # Run shared readiness audit for this dataset
        audit_rep = audit_dataset(df, meta, tf)
        audited_reports[tf] = audit_rep

        datasets[tf] = (df, meta)

    # 2. Authoritative cross-dataset readiness evaluation
    req_bars = {tf: (minimum_bars or {}).get(tf, 100) for tf in timeframes}
    readiness = evaluate_research_readiness(
        audited_reports, minimum_bars=req_bars, required_timeframes=timeframes
    )
    if readiness.get("overall_status") == "BLOCKED":
        blockers = []
        for tf, res in readiness.get("dataset_results", {}).items():
            for b in res.get("blockers", []):
                blockers.append(f"{tf}: {b}")
        if not blockers:
            blockers = readiness.get("blockers", ["Readiness gate blocked."])
        raise ValueError(f"Research readiness evaluation rejected dataset: {'; '.join(blockers)}")

    return datasets


def extract_events_dataframe(
    analysis: SMCAnalysisResult,
    df: pd.DataFrame,
    timeframe: str,
) -> pd.DataFrame:
    """
    Serialize all SMC events into a single traceable DataFrame with explicit
    source timestamps, confirmation timestamps, prices, and event IDs.
    """
    records: List[Dict[str, Any]] = []

    # 1. Swings
    for i, s in enumerate(analysis.swings):
        records.append({
            "event_id": f"SWING_{timeframe}_{i+1:04d}",
            "timeframe": timeframe,
            "event_type": "SWING",
            "subtype": s.swing_type.value,
            "direction": "BULLISH" if s.swing_type == SMCSwingType.SWING_LOW else "BEARISH",
            "source_index": s.index,
            "source_time": s.time.isoformat(),
            "confirmation_index": s.confirmed_index,
            "confirmation_time": s.confirmed_time.isoformat(),
            "price": s.price,
            "classification": s.classification,
            "session": classify_session(s.confirmed_time),
            "reference_id": None,
            "details": f"Strict fractal pivot ({s.classification}) confirmed at bar {s.confirmed_index}",
        })

    # 2. Structure Breaks
    for i, b in enumerate(analysis.structure_breaks):
        records.append({
            "event_id": f"BREAK_{timeframe}_{i+1:04d}",
            "timeframe": timeframe,
            "event_type": "STRUCTURE_BREAK",
            "subtype": b.break_type.value,
            "direction": b.direction.value,
            "source_index": b.break_index,
            "source_time": b.break_time.isoformat(),
            "confirmation_index": b.break_index,
            "confirmation_time": b.break_time.isoformat(),
            "price": b.break_price,
            "classification": f"{b.prior_trend.value}->{b.resulting_trend.value}",
            "session": classify_session(b.break_time),
            "reference_id": f"SWING_{timeframe}_{b.broken_swing.index+1:04d}",
            "details": f"Broke swing at {b.broken_swing.price:.2f} ({b.broken_swing.time.isoformat()})",
        })

    # 3. Liquidity Pools
    for i, p in enumerate(analysis.liquidity_pools):
        records.append({
            "event_id": f"POOL_{timeframe}_{i+1:04d}",
            "timeframe": timeframe,
            "event_type": "LIQUIDITY_POOL",
            "subtype": p.liquidity_type.value,
            "direction": "BEARISH" if p.liquidity_type == SMCLiquidityType.BUY_SIDE else "BULLISH",
            "source_index": p.second_swing_index,
            "source_time": p.second_swing_time.isoformat(),
            "confirmation_index": p.created_index,
            "confirmation_time": p.created_time.isoformat(),
            "price": p.level,
            "classification": f"tol={p.tolerance}",
            "session": classify_session(p.created_time),
            "reference_id": f"SWING_{timeframe}_{p.first_swing_index+1:04d}",
            "details": f"Paired swings {p.first_swing_index} & {p.second_swing_index} within {p.tolerance:.2f}",
        })

    # 4. Liquidity Sweeps
    for i, sw in enumerate(analysis.liquidity_sweeps):
        records.append({
            "event_id": f"SWEEP_{timeframe}_{i+1:04d}",
            "timeframe": timeframe,
            "event_type": "LIQUIDITY_SWEEP",
            "subtype": sw.liquidity_type.value,
            "direction": "BULLISH" if sw.liquidity_type == SMCLiquidityType.SELL_SIDE else "BEARISH",
            "source_index": sw.sweep_index,
            "source_time": sw.sweep_time.isoformat(),
            "confirmation_index": sw.sweep_index,
            "confirmation_time": sw.sweep_time.isoformat(),
            "price": sw.sweep_price,
            "classification": f"penetration={sw.penetration:.2f}",
            "session": classify_session(sw.sweep_time),
            "reference_id": f"POOL_{timeframe}_{sw.liquidity_pool.created_index+1:04d}",
            "details": f"Wick to {sw.sweep_price:.2f}, closed at {sw.close_price:.2f} through level {sw.liquidity_pool.level:.2f}",
        })

    # 5. Order Blocks
    for i, ob in enumerate(analysis.order_blocks):
        records.append({
            "event_id": f"OB_{timeframe}_{i+1:04d}",
            "timeframe": timeframe,
            "event_type": "ORDER_BLOCK",
            "subtype": ob.confirming_break_type.value,
            "direction": ob.direction.value,
            "source_index": ob.origin_index,
            "source_time": ob.origin_time.isoformat(),
            "confirmation_index": ob.created_index,
            "confirmation_time": ob.created_time.isoformat(),
            "price": (ob.high + ob.low) / 2.0,
            "classification": ob.status.value,
            "session": classify_session(ob.created_time),
            "reference_id": f"BREAK_{timeframe}_{ob.created_index+1:04d}",
            "details": f"Range [{ob.low:.2f}, {ob.high:.2f}] confirmed at break {ob.created_index}, status={ob.status.value}",
        })

    return pd.DataFrame(records)


def compute_event_distribution(
    events_df: pd.DataFrame,
    df: pd.DataFrame,
    timeframe: str,
) -> Dict[str, Any]:
    """Calculate summary statistics and breakdowns for all detected SMC events."""
    if events_df.empty:
        return {"total_events": 0, "by_type": {}, "by_session": {}, "by_month": {}}

    events_df["dt"] = pd.to_datetime(events_df["confirmation_time"], utc=True)
    events_df["year_month"] = events_df["dt"].dt.strftime("%Y-%m")

    by_type: Dict[str, Any] = {}
    for etype in events_df["event_type"].unique():
        sub = events_df[events_df["event_type"] == etype]
        by_type[etype] = {
            "count": len(sub),
            "rate_per_100_bars": round(len(sub) / len(df) * 100, 2),
            "bullish": int((sub["direction"] == "BULLISH").sum()),
            "bearish": int((sub["direction"] == "BEARISH").sum()),
            "by_session": sub["session"].value_counts().to_dict(),
        }

    return {
        "timeframe": timeframe,
        "total_bars": len(df),
        "total_events": len(events_df),
        "by_type": by_type,
        "by_session": events_df["session"].value_counts().to_dict(),
        "by_month": events_df["year_month"].value_counts().sort_index().to_dict(),
    }


def evaluate_setups_and_excursions(
    df: pd.DataFrame,
    analysis: SMCAnalysisResult,
    timeframe: str,
    config: ResearchProtocolConfig,
) -> Tuple[List[SMCSetupCandidate], pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Run setup hypothesis detection with complete funnel accounting, assign
    traceable IDs, and compute look-ahead-free forward excursions for each
    candidate across the documented horizons.
    """
    setups, funnel = detect_smc_setups_with_funnel(df, analysis, config.setup_config)
    horizons = config.horizons.get(timeframe, DEFAULT_HORIZONS.get(timeframe, [6, 12, 24, 48]))
    atr_series = compute_rolling_atr(df, period=config.atr_period)

    setup_records: List[Dict[str, Any]] = []
    excursion_records: List[Dict[str, Any]] = []

    for idx, s in enumerate(setups):
        setup_id = f"SETUP_{timeframe}_{idx+1:04d}"
        sig_idx = s.signal_index
        sig_time = s.signal_time

        # Decision point is the signal candle close
        decision_time = sig_time
        # Baseline ATR computed up to the signal candle close (zero look-ahead)
        base_atr = float(atr_series.iloc[sig_idx]) if (sig_idx < len(atr_series) and not pd.isna(atr_series.iloc[sig_idx])) else None

        # Next bar open is the research proxy for forward excursion
        next_open = s.next_bar_open
        next_time = s.next_bar_time
        session = classify_session(sig_time)

        setup_records.append({
            "setup_id": setup_id,
            "timeframe": timeframe,
            "direction": s.direction.value,
            "signal_index": sig_idx,
            "signal_time": sig_time.isoformat(),
            "decision_time": decision_time.isoformat(),
            "signal_close_price": s.entry_reference_price,
            "next_bar_open": next_open,
            "next_bar_time": next_time.isoformat() if next_time else None,
            "stop_loss_reference": s.stop_loss_reference,
            "take_profit_reference": s.take_profit_reference,
            "risk_distance": s.risk_distance,
            "reward_risk_ratio": s.reward_risk_ratio,
            "target_source": s.target_source,
            "sweep_index": s.sweep_index,
            "sweep_time": s.sweep_time.isoformat(),
            "choch_index": s.choch_index,
            "choch_time": s.choch_time.isoformat(),
            "ob_origin_index": s.order_block_origin_index,
            "ob_created_index": s.order_block_created_index,
            "ob_created_time": s.order_block_created_time.isoformat(),
            "baseline_atr": base_atr,
            "session": session,
        })

        if next_open is None:
            # Signal was confirmed on the final dataset bar; no forward measurement possible
            continue

        start_bar = sig_idx + 1
        for h in horizons:
            exc = measure_forward_excursion(
                df=df,
                event_bar_index=sig_idx,
                horizon_bars=h,
                direction="bullish" if s.direction == SMCDirection.BULLISH else "bearish",
                reference_price=next_open,
                start_bar_index=start_bar,
                baseline_atr=base_atr,
            )

            # Elapsed time calculation
            if exc["bars_available"] > 0:
                end_idx = min(start_bar + h, len(df)) - 1
                fwd_start_ts = df["time"].iloc[start_bar]
                fwd_end_ts = df["time"].iloc[end_idx]
                elapsed_hrs = round((fwd_end_ts - fwd_start_ts).total_seconds() / 3600.0, 2)
            else:
                elapsed_hrs = 0.0

            horizon_label = HORIZON_LABELS.get(timeframe, {}).get(h, f"{h}b")

            excursion_records.append({
                "setup_id": setup_id,
                "timeframe": timeframe,
                "direction": s.direction.value,
                "horizon_bars": h,
                "horizon_label": horizon_label,
                "reference_entry_price": next_open,
                "baseline_atr": base_atr,
                "mfe": exc["mfe"],
                "mae": exc["mae"],
                "mfe_atr": exc["mfe_atr"],
                "mae_atr": exc["mae_atr"],
                "final_diff": exc["final_diff"],
                "favorable_close": exc["favorable_close"],
                "mfe_greater_mae": exc["mfe_greater_mae"],
                "bars_available": exc["bars_available"],
                "complete_horizon": exc["complete_horizon"],
                "censored": exc["censored"],
                "elapsed_hours": elapsed_hrs,
                "session": session,
            })

    setups_df = pd.DataFrame(setup_records)
    excursions_df = pd.DataFrame(excursion_records)

    # Descriptive excursion statistics per horizon
    stats_by_horizon: Dict[str, Any] = {}
    for h in horizons:
        h_label = HORIZON_LABELS.get(timeframe, {}).get(h, f"{h}b")
        sub = excursions_df[excursions_df["horizon_bars"] == h] if not excursions_df.empty else pd.DataFrame()
        if sub.empty:
            continue

        completed = sub[sub["complete_horizon"] == True]
        censored = sub[sub["censored"] == True]

        def _dist(series: pd.Series) -> Dict[str, Optional[float]]:
            valid = series.dropna().to_numpy(dtype=float)
            if len(valid) == 0:
                return {"mean": None, "median": None, "std": None, "p25": None, "p75": None, "min": None, "max": None}
            return {
                "mean": round(float(np.mean(valid)), 3),
                "median": round(float(np.median(valid)), 3),
                "std": round(float(np.std(valid, ddof=1)) if len(valid) > 1 else 0.0, 3),
                "p25": round(float(np.percentile(valid, 25)), 3),
                "p75": round(float(np.percentile(valid, 75)), 3),
                "min": round(float(np.min(valid)), 3),
                "max": round(float(np.max(valid)), 3),
            }

        mfe_dist = _dist(completed["mfe"])
        mae_dist = _dist(completed["mae"])
        mfe_atr_dist = _dist(completed["mfe_atr"])
        mae_atr_dist = _dist(completed["mae_atr"])

        fav_rate = round(float(completed["favorable_close"].mean() * 100), 1) if len(completed) > 0 else None
        dom_rate = round(float(completed["mfe_greater_mae"].mean() * 100), 1) if len(completed) > 0 else None

        stats_by_horizon[str(h)] = {
            "horizon_bars": h,
            "horizon_label": h_label,
            "total_candidates": len(sub),
            "completed_observations": len(completed),
            "censored_observations": len(censored),
            "mfe_price": mfe_dist,
            "mae_price": mae_dist,
            "mfe_atr": mfe_atr_dist,
            "mae_atr": mae_atr_dist,
            "favorable_close_pct": fav_rate,
            "mfe_greater_mae_pct": dom_rate,
        }

    return setups, setups_df, excursions_df, {
        "timeframe": timeframe,
        "funnel": funnel,
        "total_setups": len(setups),
        "bullish_count": int(sum(s.direction == SMCDirection.BULLISH for s in setups)),
        "bearish_count": int(sum(s.direction == SMCDirection.BEARISH for s in setups)),
        "by_session": setups_df["session"].value_counts().to_dict() if not setups_df.empty else {},
        "target_sources": setups_df["target_source"].value_counts().to_dict() if not setups_df.empty else {},
        "horizons_stats": stats_by_horizon,
    }


def compute_common_window_study(
    datasets: Dict[str, Tuple[pd.DataFrame, Dict[str, Any]]],
    config: ResearchProtocolConfig,
) -> Dict[str, Any]:
    """
    Isolate the overlapping date window common to all 4 timeframes and compare
    event counts and setup frequencies on identical market history.
    """
    # Overlapping start is the latest start_time among all 4 timeframes
    # Overlapping end is the earliest end_time among all 4 timeframes
    start_times = [pd.to_datetime(meta["start_time"], utc=True) for _, meta in datasets.values()]
    end_times = [pd.to_datetime(meta["end_time"], utc=True) for _, meta in datasets.values()]

    common_start = max(start_times)
    common_end = min(end_times)

    common_results: Dict[str, Any] = {
        "common_start_utc": common_start.isoformat(),
        "common_end_utc": common_end.isoformat(),
        "timeframes": {},
    }

    for tf, (df, _) in datasets.items():
        sub_df = df[(df["time"] >= common_start) & (df["time"] <= common_end)].reset_index(drop=True)
        if sub_df.empty:
            continue

        analysis = analyze_smc(sub_df, symbol="XAUUSD", timeframe=tf, config=config.smc_config)
        setups, funnel = detect_smc_setups_with_funnel(sub_df, analysis, config.setup_config)

        common_results["timeframes"][tf] = {
            "bars_in_window": len(sub_df),
            "swings": len(analysis.swings),
            "bos": analysis.bos_count,
            "choch": analysis.choch_count,
            "liquidity_pools": len(analysis.liquidity_pools),
            "liquidity_sweeps": len(analysis.liquidity_sweeps),
            "order_blocks": len(analysis.order_blocks),
            "setups": len(setups),
            "bullish_setups": int(sum(s.direction == SMCDirection.BULLISH for s in setups)),
            "bearish_setups": int(sum(s.direction == SMCDirection.BEARISH for s in setups)),
            "funnel": funnel,
        }

    return common_results


def run_full_phase3c_research(
    data_dir: Path,
    output_dir: Path,
    config: Optional[ResearchProtocolConfig] = None,
) -> Dict[str, Any]:
    """
    Master pipeline: ingest verified datasets, extract events, evaluate setup
    candidates, compute forward excursions, execute common-window sub-study,
    and save all deliverables.
    """
    config = config or ResearchProtocolConfig()
    output_dir.mkdir(parents=True, exist_ok=True)

    datasets = load_and_verify_inputs(data_dir)

    all_events_dfs: List[pd.DataFrame] = []
    all_setups_dfs: List[pd.DataFrame] = []
    all_excursions_dfs: List[pd.DataFrame] = []

    timeframe_event_distributions: Dict[str, Any] = {}
    timeframe_setup_results: Dict[str, Any] = {}

    for tf in TIMEFRAMES:
        df, meta = datasets[tf]
        analysis = analyze_smc(df, symbol="XAUUSD", timeframe=tf, config=config.smc_config)

        # 1. Events DataFrame & Distribution
        ev_df = extract_events_dataframe(analysis, df, tf)
        ev_dist = compute_event_distribution(ev_df, df, tf)
        timeframe_event_distributions[tf] = ev_dist
        all_events_dfs.append(ev_df)

        # Export individual timeframe events CSV
        ev_csv = output_dir / f"smc_events_{tf}.csv"
        ev_df.to_csv(ev_csv, index=False)

        # 2. Setups & Excursions
        setups, setups_df, exc_df, setup_res = evaluate_setups_and_excursions(df, analysis, tf, config)
        timeframe_setup_results[tf] = setup_res
        all_setups_dfs.append(setups_df)
        all_excursions_dfs.append(exc_df)

        # Export individual timeframe setups CSV
        setups_csv = output_dir / f"smc_setups_{tf}.csv"
        setups_df.to_csv(setups_csv, index=False)

    # Unified CSV outputs
    unified_setups_df = pd.concat(all_setups_dfs, ignore_index=True) if all_setups_dfs else pd.DataFrame()
    unified_setups_csv = output_dir / "smc_setups_all.csv"
    unified_setups_df.to_csv(unified_setups_csv, index=False)

    unified_excursions_df = pd.concat(all_excursions_dfs, ignore_index=True) if all_excursions_dfs else pd.DataFrame()
    unified_excursions_csv = output_dir / "smc_excursions.csv"
    unified_excursions_df.to_csv(unified_excursions_csv, index=False)

    # 3. Common Window Comparison
    common_window_study = compute_common_window_study(datasets, config)

    # Compile structured summary
    report_dict: Dict[str, Any] = {
        "title": "GoldFlow Phase 3C — Pure-SMC Descriptive Research Study",
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "input_metadata": {
            tf: {
                "file": f"XAUUSD_{tf}_clean.csv",
                "rows": len(datasets[tf][0]),
                "start_utc": datasets[tf][1].get("start_time"),
                "end_utc": datasets[tf][1].get("end_time"),
                "broker_server": datasets[tf][1].get("broker_server"),
                "timestamp_mode": datasets[tf][1].get("timestamp_mode"),
                "server_timezone": datasets[tf][1].get("server_timezone"),
            }
            for tf in TIMEFRAMES
        },
        "event_distributions": timeframe_event_distributions,
        "setup_results": timeframe_setup_results,
        "common_window_study": common_window_study,
        "protocol_config": {
            "atr_period": config.atr_period,
            "max_sweep_to_choch_bars": config.setup_config.max_sweep_to_choch_bars,
            "max_bars_choch_to_retest": config.setup_config.max_bars_choch_to_retest,
            "stop_buffer": config.setup_config.stop_buffer,
            "fixed_rr": config.setup_config.fixed_rr,
            "minimum_reward_risk": config.setup_config.minimum_reward_risk,
            "use_opposing_liquidity_target": config.setup_config.use_opposing_liquidity_target,
            "require_premium_discount": config.setup_config.require_premium_discount,
            "horizons": config.horizons,
        },
    }

    # Save JSON report
    json_path = output_dir / "smc_descriptive_research.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)

    return report_dict
