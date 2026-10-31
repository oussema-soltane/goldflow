"""
Market Data Observation Validation & Canonicalization for GoldFlow.

Enforces strict UTC timestamp canonicalization, detects crossed quotes,
filters out-of-bounds prices with configurable instrument specifications,
eliminates true duplicates without dropping valid microsecond collisions,
and preserves original raw observations with complete audit traceability.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from src.data.ingestion.models import RawTickObservation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstrumentPriceLimits:
    """Configurable price and spread validation thresholds per instrument."""
    symbol: str
    min_price: float
    max_price: float
    max_spread: float
    min_spread: float = 0.0


DEFAULT_GOLD_LIMITS = InstrumentPriceLimits(
    symbol="XAUUSD",
    min_price=500.0,
    max_price=10000.0,
    max_spread=50.0,
    min_spread=0.0,
)

DEFAULT_FX_LIMITS = InstrumentPriceLimits(
    symbol="EURUSD",
    min_price=0.5,
    max_price=3.0,
    max_spread=0.01,
    min_spread=0.0,
)


@dataclass
class ValidationAuditReport:
    """Detailed summary of data cleaning and validation outcomes."""
    total_input: int = 0
    valid_count: int = 0
    dropped_count: int = 0
    crossed_quotes: int = 0
    out_of_order: int = 0
    duplicates_dropped: int = 0
    invalid_prices: int = 0
    invalid_spreads: int = 0
    raw_archive_path: Optional[str] = None
    raw_archive_sha256: Optional[str] = None
    rejections: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_input": self.total_input,
            "valid_count": self.valid_count,
            "dropped_count": self.dropped_count,
            "crossed_quotes": self.crossed_quotes,
            "out_of_order": self.out_of_order,
            "duplicates_dropped": self.duplicates_dropped,
            "invalid_prices": self.invalid_prices,
            "invalid_spreads": self.invalid_spreads,
            "raw_archive_path": self.raw_archive_path,
            "raw_archive_sha256": self.raw_archive_sha256,
            "rejections_logged": len(self.rejections),
        }


class TickDataValidator:
    """
    Validates, canonicalizes, and filters raw market tick observations.
    
    Supports instrument-specific limit profiles and sequence-aware deduplication.
    """

    def __init__(
        self,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        max_spread: Optional[float] = None,
        min_spread: Optional[float] = None,
        price_limits: Optional[InstrumentPriceLimits] = None,
        drop_crossed_quotes: bool = True,
        drop_duplicates: bool = True,
        max_rejection_logs: int = 500,
        raw_archive_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        if price_limits is not None:
            self.limits = price_limits
        else:
            self.limits = InstrumentPriceLimits(
                symbol="CUSTOM",
                min_price=min_price if min_price is not None else DEFAULT_GOLD_LIMITS.min_price,
                max_price=max_price if max_price is not None else DEFAULT_GOLD_LIMITS.max_price,
                max_spread=max_spread if max_spread is not None else DEFAULT_GOLD_LIMITS.max_spread,
                min_spread=min_spread if min_spread is not None else DEFAULT_GOLD_LIMITS.min_spread,
            )

        self.drop_crossed_quotes = drop_crossed_quotes
        self.drop_duplicates = drop_duplicates
        self.max_rejection_logs = max_rejection_logs
        self.raw_archive_dir = Path(raw_archive_dir) if raw_archive_dir else None

    @property
    def min_price(self) -> float:
        return self.limits.min_price

    @property
    def max_price(self) -> float:
        return self.limits.max_price

    @property
    def max_spread(self) -> float:
        return self.limits.max_spread

    @property
    def min_spread(self) -> float:
        return self.limits.min_spread

    def validate_and_canonicalize(
        self,
        observations: Union[List[RawTickObservation], pd.DataFrame],
    ) -> Tuple[pd.DataFrame, ValidationAuditReport]:
        """
        Validate and canonicalize a list of RawTickObservation objects or a DataFrame.
        """
        report = ValidationAuditReport()

        if isinstance(observations, list):
            if not observations:
                empty_df = pd.DataFrame(
                    columns=[
                        "timestamp_utc", "observation_time_utc", "ingestion_time_utc",
                        "symbol", "bid", "ask", "spread", "mid", "volume", "sequence_id", "provider"
                    ]
                )
                empty_df["timestamp_utc"] = pd.to_datetime(empty_df["timestamp_utc"], utc=True)
                return empty_df, report

            report.total_input = len(observations)
            records = [{
                "timestamp_utc": obs.timestamp_utc,
                "observation_time_utc": obs.observation_time_utc or obs.timestamp_utc,
                "ingestion_time_utc": obs.ingestion_time_utc or obs.timestamp_utc,
                "provider_sequence_ts": obs.provider_sequence_ts,
                "symbol": obs.symbol,
                "bid": obs.bid,
                "ask": obs.ask,
                "spread": obs.spread,
                "mid": obs.mid,
                "volume": obs.volume,
                "sequence_id": obs.sequence_id,
                "provider": obs.provider,
                "flags": obs.flags,
            } for obs in observations]
            df = pd.DataFrame(records)
        elif isinstance(observations, pd.DataFrame):
            if observations.empty:
                empty_df = pd.DataFrame(
                    columns=[
                        "timestamp_utc", "observation_time_utc", "ingestion_time_utc",
                        "symbol", "bid", "ask", "spread", "mid", "volume", "sequence_id", "provider"
                    ]
                )
                empty_df["timestamp_utc"] = pd.to_datetime(empty_df["timestamp_utc"], utc=True)
                return empty_df, report

            report.total_input = len(observations)
            df = observations.copy()
        else:
            raise TypeError(f"Unsupported observations type: {type(observations)}")

        # 0. Raw Observation Archival before cleaning if configured
        if self.raw_archive_dir:
            self.raw_archive_dir.mkdir(parents=True, exist_ok=True)
            archive_file = self.raw_archive_dir / f"raw_capture_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.jsonl"
            with open(archive_file, "w", encoding="utf-8") as f:
                for r in df.to_dict(orient="records"):
                    f.write(json.dumps(r, default=str) + "\n")
            report.raw_archive_path = str(archive_file)
            hasher = hashlib.sha256()
            with open(archive_file, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            report.raw_archive_sha256 = hasher.hexdigest()

        # 1. Standardize timestamp column name and type
        time_col = "timestamp_utc" if "timestamp_utc" in df.columns else ("time" if "time" in df.columns else None)
        if time_col is None:
            raise ValueError("Input data must contain 'timestamp_utc' or 'time' column.")

        df["timestamp_utc"] = pd.to_datetime(df[time_col], utc=True, format="ISO8601")
        if time_col != "timestamp_utc":
            df.drop(columns=[time_col], inplace=True, errors="ignore")

        if "observation_time_utc" not in df.columns:
            df["observation_time_utc"] = df["timestamp_utc"]
        else:
            df["observation_time_utc"] = pd.to_datetime(df["observation_time_utc"], utc=True, format="ISO8601")

        if "ingestion_time_utc" not in df.columns:
            df["ingestion_time_utc"] = df["observation_time_utc"]
        else:
            df["ingestion_time_utc"] = pd.to_datetime(df["ingestion_time_utc"], utc=True, format="ISO8601")

        # Ensure required columns exist
        for col, default_val in [
            ("symbol", self.limits.symbol),
            ("bid", np.nan),
            ("ask", np.nan),
            ("volume", 1.0),
            ("sequence_id", None),
            ("provider", "UNKNOWN"),
        ]:
            if col not in df.columns:
                df[col] = default_val

        # 2. Check for out-of-order timestamps
        if not df["timestamp_utc"].is_monotonic_increasing:
            diffs = df["timestamp_utc"].diff()
            inversions = (diffs < pd.Timedelta(0)).sum()
            report.out_of_order = int(inversions)
            # Re-sort chronologically, maintaining stable order on sequence_id
            sort_cols = ["timestamp_utc"]
            if df["sequence_id"].notna().any():
                sort_cols.append("sequence_id")
            df = df.sort_values(sort_cols).reset_index(drop=True)

        valid_mask = pd.Series(True, index=df.index)

        # 3. Detect duplicate rows (Sequence-Aware)
        # In fast market data feeds, multiple quotes/trades can legitimately arrive in the same millisecond.
        # Distinct sequence IDs indicate valid independent market events, not duplicates.
        if self.drop_duplicates:
            has_seq = df["sequence_id"].notna() & (df["sequence_id"] > 0)
            if has_seq.all():
                # All rows have explicit sequence IDs: duplicates must match sequence_id as well
                dup_cols = ["timestamp_utc", "bid", "ask", "volume", "sequence_id"]
                dup_mask = df.duplicated(subset=dup_cols, keep="first")
            elif has_seq.any():
                # Mixed: if sequence_id differs, it is NOT a duplicate
                dup_cols_with_seq = ["timestamp_utc", "bid", "ask", "volume", "sequence_id"]
                dup_cols_no_seq = ["timestamp_utc", "bid", "ask", "volume"]
                dup_mask = (df.duplicated(subset=dup_cols_with_seq, keep="first") & has_seq) | (
                    df.duplicated(subset=dup_cols_no_seq, keep="first") & (~has_seq)
                )
            else:
                dup_cols = ["timestamp_utc", "bid", "ask", "volume"]
                dup_mask = df.duplicated(subset=dup_cols, keep="first")

            report.duplicates_dropped = int(dup_mask.sum())
            if report.duplicates_dropped > 0:
                for idx in df[dup_mask].index[:self.max_rejection_logs]:
                    report.rejections.append({
                        "index": int(idx),
                        "timestamp": df.at[idx, "timestamp_utc"].isoformat(),
                        "reason": "duplicate_tick",
                        "bid": df.at[idx, "bid"],
                        "ask": df.at[idx, "ask"],
                        "sequence_id": df.at[idx, "sequence_id"],
                    })
                valid_mask = valid_mask & (~dup_mask)

        # 4. Check price positivity and bounds
        price_invalid_mask = (
            df["bid"].isna()
            | df["ask"].isna()
            | (df["bid"] <= self.min_price)
            | (df["bid"] >= self.max_price)
            | (df["ask"] <= self.min_price)
            | (df["ask"] >= self.max_price)
        )
        report.invalid_prices = int(price_invalid_mask.sum())
        if report.invalid_prices > 0:
            for idx in df[price_invalid_mask].index[:self.max_rejection_logs]:
                if len(report.rejections) < self.max_rejection_logs:
                    report.rejections.append({
                        "index": int(idx),
                        "timestamp": df.at[idx, "timestamp_utc"].isoformat(),
                        "reason": "price_out_of_bounds",
                        "bid": df.at[idx, "bid"],
                        "ask": df.at[idx, "ask"],
                    })
            valid_mask = valid_mask & (~price_invalid_mask)

        # 5. Check crossed quotes (bid > ask)
        crossed_mask = df["bid"] > df["ask"]
        report.crossed_quotes = int(crossed_mask.sum())
        if report.crossed_quotes > 0 and self.drop_crossed_quotes:
            for idx in df[crossed_mask].index[:self.max_rejection_logs]:
                if len(report.rejections) < self.max_rejection_logs:
                    report.rejections.append({
                        "index": int(idx),
                        "timestamp": df.at[idx, "timestamp_utc"].isoformat(),
                        "reason": "crossed_quote",
                        "bid": df.at[idx, "bid"],
                        "ask": df.at[idx, "ask"],
                    })
            valid_mask = valid_mask & (~crossed_mask)

        # 6. Check spread bounds
        spread_calc = df["ask"] - df["bid"]
        spread_invalid_mask = (spread_calc < self.min_spread) | (spread_calc > self.max_spread)
        spread_invalid_mask = spread_invalid_mask & (~crossed_mask)
        report.invalid_spreads = int(spread_invalid_mask.sum())
        if report.invalid_spreads > 0:
            for idx in df[spread_invalid_mask].index[:self.max_rejection_logs]:
                if len(report.rejections) < self.max_rejection_logs:
                    report.rejections.append({
                        "index": int(idx),
                        "timestamp": df.at[idx, "timestamp_utc"].isoformat(),
                        "reason": "spread_out_of_bounds",
                        "spread": float(spread_calc.at[idx]),
                    })
            valid_mask = valid_mask & (~spread_invalid_mask)

        # Filter valid rows
        cleaned_df = df[valid_mask].copy().reset_index(drop=True)
        report.valid_count = len(cleaned_df)
        report.dropped_count = report.total_input - report.valid_count

        # Compute canonical columns
        cleaned_df["spread"] = (cleaned_df["ask"] - cleaned_df["bid"]).round(5)
        cleaned_df["mid"] = ((cleaned_df["ask"] + cleaned_df["bid"]) / 2.0).round(5)
        cleaned_df["volume"] = cleaned_df["volume"].fillna(1.0).astype(float)

        canonical_cols = [
            "timestamp_utc", "observation_time_utc", "ingestion_time_utc",
            "symbol", "bid", "ask", "spread", "mid", "volume", "sequence_id", "provider"
        ]
        extra_cols = [c for c in cleaned_df.columns if c not in canonical_cols]
        cleaned_df = cleaned_df[canonical_cols + extra_cols]

        return cleaned_df, report


def validate_and_canonicalize_ticks(
    observations: Union[List[RawTickObservation], pd.DataFrame],
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    max_spread: Optional[float] = None,
    price_limits: Optional[InstrumentPriceLimits] = None,
    drop_crossed_quotes: bool = True,
    drop_duplicates: bool = True,
    raw_archive_dir: Optional[Union[str, Path]] = None,
) -> Tuple[pd.DataFrame, ValidationAuditReport]:
    """
    Convenience function to run validation and canonicalization on market ticks.
    """
    validator = TickDataValidator(
        min_price=min_price,
        max_price=max_price,
        max_spread=max_spread,
        price_limits=price_limits,
        drop_crossed_quotes=drop_crossed_quotes,
        drop_duplicates=drop_duplicates,
        raw_archive_dir=raw_archive_dir,
    )
    return validator.validate_and_canonicalize(observations)
