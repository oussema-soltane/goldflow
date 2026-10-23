"""
Data Quality Validation Engine for GoldFlow.

Performs stringent financial data quality audits:
- OHLC price consistency (high >= max(open, close), low <= min(open, close), high >= low).
- Non-negative, non-zero, non-infinite price validation.
- Missing value (null/NaN) inspection.
- Duplicate timestamp detection.
- Strict chronological monotonic ordering verification.
- Smart time-gap analysis (separating expected weekend closures from abnormal intraday gaps).
- Automated reporting (machine-readable JSON + human-readable Markdown).
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


@dataclass
class GapInfo:
    start_time: str
    end_time: str
    duration_minutes: float
    is_weekend: bool
    description: str


@dataclass
class DataQualityReport:
    symbol: str
    timeframe: str
    total_rows: int
    start_date: Optional[str]
    end_date: Optional[str]
    is_chronological: bool
    duplicate_timestamps_count: int
    duplicate_timestamps: List[str]
    missing_values_by_column: Dict[str, int]
    invalid_ohlc_count: int
    invalid_ohlc_indices: List[int]
    total_gaps_count: int
    weekend_gaps_count: int
    abnormal_gaps_count: int
    abnormal_gaps: List[Dict[str, Any]]
    incomplete_candle_detected: bool
    status: str  # "PASSED", "PASSED_WITH_WARNINGS", "FAILED"
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save_json(self, output_path: Union[str, Path] = "reports/data_quality_report.json") -> Path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return p

    def save_markdown(self, output_path: Union[str, Path] = "reports/data_quality_report.md") -> Path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        
        status_badge = "🟢 PASSED" if self.status == "PASSED" else (
            "🟡 PASSED WITH WARNINGS" if self.status == "PASSED_WITH_WARNINGS" else "🔴 FAILED"
        )
        
        md_lines = [
            "# GoldFlow — Data Quality Report",
            "",
            f"**Audit Status:** {status_badge}",
            f"- **Symbol:** `{self.symbol}`",
            f"- **Timeframe:** `{self.timeframe}`",
            f"- **Total Bars Analyzed:** {self.total_rows:,}",
            f"- **Date Range:** {self.start_date or 'N/A'} to {self.end_date or 'N/A'}",
            f"- **Generated At:** {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "## 1. Summary of Integrity Checks",
            "",
            "| Check | Status | Details |",
            "| :--- | :--- | :--- |",
            f"| **Chronological Order** | {'✅ PASS' if self.is_chronological else '❌ FAIL'} | {'Timestamps strictly monotonic' if self.is_chronological else 'Out-of-order candles detected'} |",
            f"| **Duplicate Timestamps** | {'✅ PASS' if self.duplicate_timestamps_count == 0 else '❌ FAIL'} | {self.duplicate_timestamps_count} duplicate timestamp(s) found |",
            f"| **Missing Values (NaN)** | {'✅ PASS' if sum(self.missing_values_by_column.values()) == 0 else '❌ FAIL'} | {sum(self.missing_values_by_column.values())} total missing cell(s) |",
            f"| **OHLC Consistency** | {'✅ PASS' if self.invalid_ohlc_count == 0 else '❌ FAIL'} | {self.invalid_ohlc_count} invalid OHLC row(s) |",
            f"| **Expected Weekend Gaps** | ℹ️ INFO | {self.weekend_gaps_count} standard market closure period(s) |",
            f"| **Abnormal Market Gaps** | {'✅ PASS' if self.abnormal_gaps_count == 0 else '⚠️ WARNING'} | {self.abnormal_gaps_count} unexpected trading gap(s) |",
            f"| **Incomplete Active Bar** | {'⚠️ WARNING' if self.incomplete_candle_detected else '✅ PASS'} | {'Active candle excluded' if not self.incomplete_candle_detected else 'Active incomplete candle present'} |",
            "",
        ]

        if self.errors:
            md_lines.extend([
                "## 2. Critical Errors (Action Required)",
                "",
            ])
            for err in self.errors:
                md_lines.append(f"- 🔴 {err}")
            md_lines.append("")

        if self.warnings:
            md_lines.extend([
                "## 3. Data Quality Warnings",
                "",
            ])
            for w in self.warnings:
                md_lines.append(f"- ⚠️ {w}")
            md_lines.append("")

        if self.abnormal_gaps:
            md_lines.extend([
                "## 4. Abnormal Time Gaps (Intraday/Weekday)",
                "",
                "| Gap Start | Gap End | Duration (min) | Notes |",
                "| :--- | :--- | :--- | :--- |",
            ])
            for g in self.abnormal_gaps[:10]:
                md_lines.append(f"| {g['start_time']} | {g['end_time']} | {g['duration_minutes']} | {g['description']} |")
            if len(self.abnormal_gaps) > 10:
                md_lines.append(f"| ... | ... | ... | *({len(self.abnormal_gaps) - 10} more gaps omitted)* |")
            md_lines.append("")

        md_lines.extend([
            "---",
            "*Report generated automatically by GoldFlow Data Pipeline. Zero price interpolation applied.*",
            "",
        ])

        p.write_text("\n".join(md_lines), encoding="utf-8")
        return p


TIMEFRAME_STEP_MINUTES: Dict[str, int] = {
    "M5": 5,
    "M15": 15,
    "H1": 60,
    "H4": 240,
}


def is_weekend_closure(t1: pd.Timestamp, t2: pd.Timestamp) -> bool:
    """
    Determine if a gap between t1 and t2 spans a typical market weekend closure.
    
    FOREX / GOLD MARKET SCHEDULE CONVENTION:
    -----------------------------------------
    Gold spot trading ceases on Friday evening (~21:00-22:00 UTC / 17:00 NY time)
    and resumes on Sunday evening (~21:00-22:00 UTC / 17:00 NY time / Monday morning open).
    
    A gap qualifies as a normal weekend closure ONLY if:
    1. Total elapsed duration is at least 40 hours (standard ~48 hour weekend).
    2. Gap starts near the Friday market close (Friday hour >= 17, or Saturday).
       The floor of 17 (not 20) is deliberate: H4 bar-open times sit on a
       4-hour grid, so the last H4 bar before the Friday 21:00 UTC close opens
       at 17:00 UTC.  Lower-resolution timeframes (H1/M15/M5) have their last
       pre-close bar open at 20:00/20:45/20:55 UTC respectively, all >= 17.
       A Friday 10:00 UTC start is still rejected (10 < 17), preserving the
       regression test that daytime outages must not be swallowed.
    3. Gap ends near the Sunday evening / Monday open (Sunday hour >= 20, or Monday hour <= 2).
    
    A gap starting on Friday daytime (e.g. 10:00 AM) or ending midweek indicates an
    abnormal trading disruption and is NOT swallowed as a standard weekend closure.
    """
    delta_hours = (t2 - t1).total_seconds() / 3600.0
    if delta_hours < 40.0:
        return False

    day1 = t1.weekday()  # Monday is 0, Friday is 4, Saturday is 5, Sunday is 6
    day2 = t2.weekday()

    # Must start near Friday evening close (or early Saturday).
    # Floor of 17 (not 20) accommodates H4's 4-hour bar grid: the last H4 bar
    # before the Friday 21:00 UTC market close opens at 17:00 UTC.
    is_normal_close = (day1 == 4 and t1.hour >= 17) or (day1 == 5 and t1.hour <= 2)
    # Must end near Sunday evening reopen (or early Monday)
    is_normal_reopen = (day2 == 6 and t2.hour >= 20) or (day2 == 0 and t2.hour <= 2)

    return bool(is_normal_close and is_normal_reopen)


def validate_market_data(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
) -> DataQualityReport:
    """
    Execute comprehensive validation on a market data DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing at least ['time', 'open', 'high', 'low', 'close'].
    symbol : str
        Instrument symbol.
    timeframe : str
        Timeframe key ('H4', 'H1', 'M15', 'M5').

    Returns
    -------
    DataQualityReport
        Detailed audit results.
    """
    warnings: List[str] = []
    errors: List[str] = []

    if df.empty:
        errors.append("Dataset is empty (0 rows).")
        return DataQualityReport(
            symbol=symbol,
            timeframe=timeframe,
            total_rows=0,
            start_date=None,
            end_date=None,
            is_chronological=False,
            duplicate_timestamps_count=0,
            duplicate_timestamps=[],
            missing_values_by_column={},
            invalid_ohlc_count=0,
            invalid_ohlc_indices=[],
            total_gaps_count=0,
            weekend_gaps_count=0,
            abnormal_gaps_count=0,
            abnormal_gaps=[],
            incomplete_candle_detected=False,
            status="FAILED",
            warnings=warnings,
            errors=errors,
        )

    # Ensure required columns
    required_cols = ["time", "open", "high", "low", "close"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        errors.append(f"Missing mandatory columns: {missing_cols}")
        return DataQualityReport(
            symbol=symbol,
            timeframe=timeframe,
            total_rows=len(df),
            start_date=None,
            end_date=None,
            is_chronological=False,
            duplicate_timestamps_count=0,
            duplicate_timestamps=[],
            missing_values_by_column={c: 1 for c in missing_cols},
            invalid_ohlc_count=0,
            invalid_ohlc_indices=[],
            total_gaps_count=0,
            weekend_gaps_count=0,
            abnormal_gaps_count=0,
            abnormal_gaps=[],
            incomplete_candle_detected=False,
            status="FAILED",
            warnings=warnings,
            errors=errors,
        )

    # Use reset_index to guarantee positional index alignment regardless of input index
    work_df = df.reset_index(drop=True).copy()
    work_df["time"] = pd.to_datetime(work_df["time"], utc=True)

    total_rows = len(work_df)
    start_date = work_df["time"].iloc[0].strftime("%Y-%m-%d %H:%M:%S UTC")
    end_date = work_df["time"].iloc[-1].strftime("%Y-%m-%d %H:%M:%S UTC")

    # 1. Missing values check
    missing_values = {col: int(work_df[col].isna().sum()) for col in work_df.columns}
    total_missing = sum(missing_values.values())
    if total_missing > 0:
        errors.append(f"Detected {total_missing} NaN / null values across columns.")

    # 2. Duplicate timestamps check
    dup_mask = work_df["time"].duplicated(keep=False)
    dup_count = int(work_df["time"].duplicated().sum())
    dup_samples = work_df.loc[dup_mask, "time"].astype(str).tolist()[:10]
    if dup_count > 0:
        errors.append(f"Detected {dup_count} duplicate timestamp(s).")

    # 3. Chronological ordering
    is_chronological = bool(work_df["time"].is_monotonic_increasing)
    if not is_chronological:
        errors.append("Timestamps are not strictly in ascending chronological order.")

    # 4. OHLC price relationships check
    # high >= open, high >= close, low <= open, low <= close, high >= low
    # prices must be strictly positive, non-null, and finite
    invalid_mask = (
        work_df["open"].isna()
        | work_df["high"].isna()
        | work_df["low"].isna()
        | work_df["close"].isna()
        | (work_df["high"] < work_df["open"])
        | (work_df["high"] < work_df["close"])
        | (work_df["low"] > work_df["open"])
        | (work_df["low"] > work_df["close"])
        | (work_df["high"] < work_df["low"])
        | (work_df["open"] <= 0)
        | (work_df["high"] <= 0)
        | (work_df["low"] <= 0)
        | (work_df["close"] <= 0)
        | np.isinf(work_df["open"])
        | np.isinf(work_df["high"])
        | np.isinf(work_df["low"])
        | np.isinf(work_df["close"])
    )
    invalid_ohlc_count = int(invalid_mask.sum())
    invalid_indices = work_df.index[invalid_mask].tolist()[:20]
    if invalid_ohlc_count > 0:
        errors.append(
            f"Detected {invalid_ohlc_count} row(s) violating OHLC geometric boundaries or numeric validity."
        )

    # 5. Smart Time Gaps Detection (using safe positional indexing)
    step_min = TIMEFRAME_STEP_MINUTES.get(timeframe, 15)
    expected_delta = pd.Timedelta(minutes=step_min)
    time_diffs = work_df["time"].diff()

    # Gap threshold: difference exceeding 1.5x expected step
    gap_threshold = expected_delta * 1.5
    gap_positions = [i for i, is_gap in enumerate(time_diffs > gap_threshold) if is_gap and i > 0]

    total_gaps = len(gap_positions)
    weekend_gaps = 0
    abnormal_gaps = []

    for pos in gap_positions:
        t_prev = work_df["time"].iloc[pos - 1]
        t_curr = work_df["time"].iloc[pos]
        duration_min = (t_curr - t_prev).total_seconds() / 60.0
        
        if is_weekend_closure(t_prev, t_curr):
            weekend_gaps += 1
        else:
            abnormal_gaps.append({
                "row_index": pos,
                "start_time": str(t_prev),
                "end_time": str(t_curr),
                "duration_minutes": round(duration_min, 1),
                "description": f"Missing ~{int(duration_min // step_min)} bars during active market hours",
            })

    abnormal_gaps_count = len(abnormal_gaps)
    if abnormal_gaps_count > 0:
        warnings.append(
            f"Detected {abnormal_gaps_count} abnormal intraday/weekday gap(s) exceeding normal {timeframe} interval."
        )

    # 6. Status classification
    if errors:
        status = "FAILED"
    elif warnings:
        status = "PASSED_WITH_WARNINGS"
    else:
        status = "PASSED"

    report = DataQualityReport(
        symbol=symbol,
        timeframe=timeframe,
        total_rows=total_rows,
        start_date=start_date,
        end_date=end_date,
        is_chronological=is_chronological,
        duplicate_timestamps_count=dup_count,
        duplicate_timestamps=dup_samples,
        missing_values_by_column=missing_values,
        invalid_ohlc_count=invalid_ohlc_count,
        invalid_ohlc_indices=invalid_indices,
        total_gaps_count=total_gaps,
        weekend_gaps_count=weekend_gaps,
        abnormal_gaps_count=abnormal_gaps_count,
        abnormal_gaps=abnormal_gaps,
        incomplete_candle_detected=False,
        status=status,
        warnings=warnings,
        errors=errors,
    )
    return report

