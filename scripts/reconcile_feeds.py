#!/usr/bin/env python3
"""
Cross-Provider Market Data Feed Reconciliation Tool for GoldFlow.

Compares two local market data feeds (e.g. MT5 broker data vs. Dukascopy-derived bars)
across overlapping UTC time boundaries, quantifies price deviations, spread distributions,
missing intervals, and provides both machine-readable JSON and human-readable Markdown audits.

Operates strictly offline without external network requests.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("feed_reconciler")


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_dataset(file_path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Load a CSV or Parquet market dataset into a normalized DataFrame with UTC datetime index.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    sha256_hash = compute_file_sha256(file_path)

    if file_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(file_path)
    elif file_path.suffix.lower() in (".csv", ".txt"):
        df = pd.read_csv(file_path)
    else:
        raise ValueError(f"Unsupported file format '{file_path.suffix}'. Expected .parquet or .csv.")

    # Locate time column
    time_col = None
    for candidate in ["time", "timestamp", "timestamp_utc", "date", "datetime"]:
        if candidate in df.columns:
            time_col = candidate
            break

    if time_col is None:
        raise ValueError(f"No recognizable timestamp column found in {file_path.name}.")

    # Ensure UTC timezone awareness
    df["time_utc"] = pd.to_datetime(df[time_col], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)

    metadata = {
        "file_name": file_path.name,
        "file_path": str(file_path.resolve()),
        "sha256": sha256_hash,
        "row_count": len(df),
        "earliest_time": df["time_utc"].min().isoformat() if len(df) > 0 else None,
        "latest_time": df["time_utc"].max().isoformat() if len(df) > 0 else None,
        "columns": list(df.columns),
    }

    return df, metadata


def reconcile_market_feeds(
    primary_df: pd.DataFrame,
    primary_meta: Dict[str, Any],
    comparison_df: pd.DataFrame,
    comparison_meta: Dict[str, Any],
    tolerance_pts: float = 0.50,
) -> Dict[str, Any]:
    """
    Perform rigorous bar-by-bar and distribution reconciliation between two feeds.
    """
    p_name = primary_meta["file_name"]
    c_name = comparison_meta["file_name"]

    # 1. Check duplicate timestamps
    p_dups = int(primary_df["time_utc"].duplicated().sum())
    c_dups = int(comparison_df["time_utc"].duplicated().sum())

    # 2. Determine overlapping UTC boundary
    p_min = primary_df["time_utc"].min()
    p_max = primary_df["time_utc"].max()
    c_min = comparison_df["time_utc"].min()
    c_max = comparison_df["time_utc"].max()

    overlap_start = max(p_min, c_min)
    overlap_end = min(p_max, c_max)

    has_overlap = overlap_start <= overlap_end

    if not has_overlap:
        return {
            "status": "NO_TEMPORAL_OVERLAP",
            "primary": primary_meta,
            "comparison": comparison_meta,
            "primary_range": [p_min.isoformat(), p_max.isoformat()],
            "comparison_range": [c_min.isoformat(), c_max.isoformat()],
            "error_message": "The two datasets do not share any common temporal window.",
        }

    # Filter to overlap window
    p_overlap = primary_df[(primary_df["time_utc"] >= overlap_start) & (primary_df["time_utc"] <= overlap_end)].copy()
    c_overlap = comparison_df[(comparison_df["time_utc"] >= overlap_start) & (comparison_df["time_utc"] <= overlap_end)].copy()

    # Drop duplicates if any for index alignment
    p_overlap = p_overlap.drop_duplicates(subset=["time_utc"]).set_index("time_utc")
    c_overlap = c_overlap.drop_duplicates(subset=["time_utc"]).set_index("time_utc")

    # Common index
    common_index = p_overlap.index.intersection(c_overlap.index)
    p_only_index = p_overlap.index.difference(c_overlap.index)
    c_only_index = c_overlap.index.difference(p_overlap.index)

    p_aligned = p_overlap.loc[common_index]
    c_aligned = c_overlap.loc[common_index]

    num_aligned = len(common_index)

    # 3. Price Field Alignment (Check available OHLC columns)
    ohlc_cols = ["open", "high", "low", "close"]
    p_has_ohlc = all(col in p_aligned.columns for col in ohlc_cols)
    c_has_ohlc = all(col in c_aligned.columns for col in ohlc_cols)

    diff_stats: Dict[str, Any] = {}
    if p_has_ohlc and c_has_ohlc and num_aligned > 0:
        for col in ohlc_cols:
            delta = c_aligned[col] - p_aligned[col]
            abs_delta = delta.abs()
            diff_stats[col] = {
                "mean_diff": round(float(delta.mean()), 4),
                "std_diff": round(float(delta.std()), 4) if len(delta) > 1 else 0.0,
                "mae": round(float(abs_delta.mean()), 4),
                "rmse": round(float(np.sqrt((delta**2).mean())), 4),
                "max_diff": round(float(abs_delta.max()), 4),
                "p50_diff": round(float(abs_delta.median()), 4),
                "p95_diff": round(float(abs_delta.quantile(0.95)), 4),
                "exceeding_tolerance_count": int((abs_delta > tolerance_pts).sum()),
                "exceeding_tolerance_pct": round(float((abs_delta > tolerance_pts).mean() * 100.0), 2),
            }

    # 4. Spread Distribution Comparison
    spread_stats: Dict[str, Any] = {}
    for label, df_curr in [("primary", p_overlap), ("comparison", c_overlap)]:
        sp_col = None
        for candidate in ["spread", "spread_mean", "spread_typical"]:
            if candidate in df_curr.columns:
                sp_col = candidate
                break
        if sp_col is not None:
            sp_series = df_curr[sp_col]
            spread_stats[label] = {
                "field_name": sp_col,
                "mean": round(float(sp_series.mean()), 4),
                "median": round(float(sp_series.median()), 4),
                "min": round(float(sp_series.min()), 4),
                "max": round(float(sp_series.max()), 4),
                "p95": round(float(sp_series.quantile(0.95)), 4),
            }

    reconciliation_result = {
        "status": "RECONCILIATION_COMPLETED",
        "primary": primary_meta,
        "comparison": comparison_meta,
        "overlap_window": {
            "start_utc": overlap_start.isoformat(),
            "end_utc": overlap_end.isoformat(),
            "duration_hours": round(float((overlap_end - overlap_start).total_seconds() / 3600.0), 2),
        },
        "coverage": {
            "primary_overlap_rows": len(p_overlap),
            "comparison_overlap_rows": len(c_overlap),
            "aligned_bars": num_aligned,
            "primary_only_bars": len(p_only_index),
            "comparison_only_bars": len(c_only_index),
            "primary_duplicate_timestamps": p_dups,
            "comparison_duplicate_timestamps": c_dups,
        },
        "price_deviations": diff_stats,
        "spread_comparison": spread_stats,
        "tolerance_pts": tolerance_pts,
        "methodology_disclaimer": (
            "HISTORICAL CROSS-PROVIDER FEED RECONCILIATION: This audit compares historical pricing "
            "structures across two feeds to evaluate broker markup, spread widening, and liquidity differences. "
            "It does NOT constitute forward temporal validation and must not be used as evidence of strategy profitability."
        ),
    }

    return reconciliation_result


def generate_markdown_report(result: Dict[str, Any]) -> str:
    """Generate structured markdown report from reconciliation result."""
    p_meta = result.get("primary", {})
    c_meta = result.get("comparison", {})
    status = result.get("status")

    lines = [
        "# GoldFlow Historical Cross-Provider Feed Reconciliation Report",
        "",
        "**Author:** Senior Quantitative Research Engineer",
        f"**Date:** {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**Audit Status:** {status}",
        "",
        "---",
        "",
        "## 1. Input Datasets & Manifest Hashes",
        "",
        "| Attribute | Primary Dataset (MT5 / Reference) | Comparison Dataset (Dukascopy / Feed) |",
        "| :--- | :--- | :--- |",
        f"| **File Name** | `{p_meta.get('file_name')}` | `{c_meta.get('file_name')}` |",
        f"| **SHA-256 Digest** | `{p_meta.get('sha256')}` | `{c_meta.get('sha256')}` |",
        f"| **Total Rows** | {p_meta.get('row_count'):,} | {c_meta.get('row_count'):,} |",
        f"| **Time Range** | {p_meta.get('earliest_time')} $\\to$ {p_meta.get('latest_time')} | {c_meta.get('earliest_time')} $\\to$ {c_meta.get('latest_time')} |",
        "",
        "---",
        "",
    ]

    if status != "RECONCILIATION_COMPLETED":
        lines.extend([
            f"### Temporal Overlap Notice: {status}",
            f"{result.get('error_message', 'No temporal overlap found.')}",
            "",
        ])
        return "\n".join(lines)

    cov = result["coverage"]
    window = result["overlap_window"]

    lines.extend([
        "## 2. Temporal Overlap & Alignment Summary",
        "",
        f"- **Overlapping UTC Window:** `{window['start_utc']}` $\\to$ `{window['end_utc']}` ({window['duration_hours']} hours)",
        f"- **Aligned Common Bars:** {cov['aligned_bars']:,}",
        f"- **Primary Exclusive Bars (Missing in Comparison):** {cov['primary_only_bars']:,}",
        f"- **Comparison Exclusive Bars (Missing in Primary):** {cov['comparison_only_bars']:,}",
        f"- **Duplicate Timestamps:** Primary: {cov['primary_duplicate_timestamps']}, Comparison: {cov['comparison_duplicate_timestamps']}",
        "",
        "---",
        "",
        "## 3. Price Deviation & OHLC Variance",
        "",
        "| Field | Mean Diff | MAE | RMSE | Max Diff | P50 (Median) | P95 Diff | Exceeding Tol. (%) |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])

    for col, stats in result.get("price_deviations", {}).items():
        lines.append(
            f"| **{col.upper()}** | {stats['mean_diff']:+.4f} | {stats['mae']:.4f} | {stats['rmse']:.4f} | "
            f"{stats['max_diff']:.4f} | {stats['p50_diff']:.4f} | {stats['p95_diff']:.4f} | "
            f"{stats['exceeding_tolerance_pct']:.2f}% |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 4. Spread Distribution Comparison",
        "",
        "| Feed | Field | Mean Spread | Median Spread | Min Spread | Max Spread | P95 Spread |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])

    for label, sp in result.get("spread_comparison", {}).items():
        lines.append(
            f"| **{label.capitalize()}** | `{sp['field_name']}` | {sp['mean']:.4f} | {sp['median']:.4f} | "
            f"{sp['min']:.4f} | {sp['max']:.4f} | {sp['p95']:.4f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 5. Architectural Reconciliation & Disclaimers",
        "",
        result.get("methodology_disclaimer", ""),
        "",
        "- **Pricing Mechanism Variance:** Retail MT5 broker feeds incorporate proprietary broker spread markups (typically 15–30¢ on XAUUSD) and synthetic filtering. Institutional ECN feeds (such as Dukascopy SWFX) reflect raw matching-engine top-of-book quotes with tighter baseline spreads but microsecond volatility.",
        "- **Session Rollover Differences:** Gaps during daily bank maintenance (21:00–22:00 UTC) frequently exhibit different tick frequencies across venues.",
    ])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="GoldFlow Cross-Provider Market Data Feed Reconciliation")
    parser.add_argument("--primary-file", required=True, help="Path to primary dataset (e.g. MT5 CSV/Parquet)")
    parser.add_argument("--comparison-file", required=True, help="Path to comparison dataset (e.g. Dukascopy Parquet)")
    parser.add_argument("--output-json", default=None, help="Output path for machine-readable JSON metrics")
    parser.add_argument("--output-md", default=None, help="Output path for human-readable Markdown report")
    parser.add_argument("--tolerance-pts", type=float, default=0.50, help="Tolerance threshold in price points")

    args = parser.parse_args()

    try:
        p_df, p_meta = load_dataset(Path(args.primary_file))
        c_df, c_meta = load_dataset(Path(args.comparison_file))

        result = reconcile_market_feeds(
            primary_df=p_df,
            primary_meta=p_meta,
            comparison_df=c_df,
            comparison_meta=c_meta,
            tolerance_pts=args.tolerance_pts,
        )

        md_report = generate_markdown_report(result)

        if args.output_json:
            out_json = Path(args.output_json)
            out_json.parent.mkdir(parents=True, exist_ok=True)
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            logger.info(f"Machine-readable metrics saved to {out_json}")

        if args.output_md:
            out_md = Path(args.output_md)
            out_md.parent.mkdir(parents=True, exist_ok=True)
            with open(out_md, "w", encoding="utf-8") as f:
                f.write(md_report)
            logger.info(f"Markdown report saved to {out_md}")

        print(md_report)
        return 0
    except Exception as exc:
        logger.error(f"Reconciliation failed: {exc}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

