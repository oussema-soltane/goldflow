"""
GoldFlow Phase 3A — Research Protocol: Descriptive Event Statistics.

Computes reproducible, look-ahead-free descriptive statistics for ICT market
structure events on historical XAUUSD data.

No strategy entry or exit logic, no ML training, and no performance metrics
are computed here.  Results are strictly descriptive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from src.ict.models import (
    FairValueGap,
    LiquiditySweep,
    MarketStructureShift,
    OrderBlock,
    StructureBreak,
    SwingPoint,
)


# ─────────────────────────────────────────────────────────────────────────────
# Period split
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PeriodSplit:
    """
    Chronological train / validation / test split of a DataFrame.

    Split is strictly by time — no shuffling — so no future information leaks
    into the training window.
    """
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    train_end: pd.Timestamp
    val_end: pd.Timestamp

    @classmethod
    def from_ratios(
        cls,
        df: pd.DataFrame,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
    ) -> "PeriodSplit":
        """Split df by row count using purely chronological ordering."""
        if "time" not in df.columns:
            raise ValueError("DataFrame must contain a 'time' column.")
        if not (0.0 < train_ratio < 1.0):
            raise ValueError("train_ratio must be between 0 and 1 (exclusive).")
        if not (0.0 <= val_ratio < 1.0):
            raise ValueError("val_ratio must be between 0 and 1 (inclusive of 0, exclusive of 1).")
        if train_ratio + val_ratio >= 1.0:
            raise ValueError("train_ratio + val_ratio must be less than 1 so the test split is non-empty when enough rows exist.")
        df = df.sort_values("time").reset_index(drop=True)
        n = len(df)
        train_end_idx = int(n * train_ratio)
        val_end_idx = int(n * (train_ratio + val_ratio))
        train = df.iloc[:train_end_idx]
        val = df.iloc[train_end_idx:val_end_idx]
        test = df.iloc[val_end_idx:]
        return cls(
            train=train,
            validation=val,
            test=test,
            train_end=train["time"].iloc[-1] if len(train) > 0 else pd.NaT,
            val_end=val["time"].iloc[-1] if len(val) > 0 else pd.NaT,
        )

    def describe(self) -> Dict[str, Any]:
        return {
            "train_bars": len(self.train),
            "train_start": str(self.train["time"].iloc[0]) if len(self.train) > 0 else None,
            "train_end": str(self.train["time"].iloc[-1]) if len(self.train) > 0 else None,
            "val_bars": len(self.validation),
            "val_start": str(self.validation["time"].iloc[0]) if len(self.validation) > 0 else None,
            "val_end": str(self.validation["time"].iloc[-1]) if len(self.validation) > 0 else None,
            "test_bars": len(self.test),
            "test_start": str(self.test["time"].iloc[0]) if len(self.test) > 0 else None,
            "test_end": str(self.test["time"].iloc[-1]) if len(self.test) > 0 else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Price-horizon measurements (look-ahead FREE)
# ─────────────────────────────────────────────────────────────────────────────

def compute_rolling_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute True Range and rolling Average True Range without look-ahead.
    For each bar i, atr[i] incorporates information only up to and including bar i close.
    """
    if df.empty or len(df) == 0:
        return pd.Series(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    n = len(df)
    tr = np.zeros(n, dtype=float)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
    atr = pd.Series(tr, index=df.index).rolling(window=period, min_periods=period).mean()
    return atr


def measure_forward_excursion(
    df: pd.DataFrame,
    event_bar_index: int,
    horizon_bars: int,
    direction: str,
    reference_price: Optional[float] = None,
    start_bar_index: Optional[int] = None,
    baseline_atr: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Measure the maximum favorable excursion (MFE) and maximum adverse excursion
    (MAE) over the next ``horizon_bars`` candles **after** the event bar.

    Critically:
    - Uses only bars AFTER the event bar (index > event_bar_index) or from start_bar_index.
    - Does NOT use any data from the event bar itself as a look-ahead proxy.
    - 'direction' is either 'bullish' or 'bearish'; determines which is favorable.
    - If reference_price is None, uses close of event_bar_index.
    - If start_bar_index is None, start = event_bar_index + 1.

    Returns
    -------
    dict with keys:
      - mfe             : Maximum Favorable Excursion (positive float, reference = ref_price)
      - mae             : Maximum Adverse Excursion (positive float, i.e. worst-case move against)
      - final           : Close price at horizon end (or None if insufficient bars)
      - mfe_atr         : MFE normalized by baseline_atr (or None)
      - mae_atr         : MAE normalized by baseline_atr (or None)
      - final_diff      : Net price movement in favorable direction at horizon end
      - favorable_close : Boolean indicating if final_diff > 0
      - mfe_greater_mae : Boolean indicating if mfe > mae
      - bars_available  : how many forward bars were actually present
      - complete_horizon: whether all horizon_bars were available
      - censored        : whether measurement was truncated by dataset edge
    """
    if direction not in {"bullish", "bearish"}:
        raise ValueError("direction must be 'bullish' or 'bearish'.")
    if horizon_bars < 0:
        raise ValueError("horizon_bars must be non-negative.")
    if event_bar_index < 0 or event_bar_index >= len(df):
        raise IndexError("event_bar_index must refer to an existing row in df.")
    if horizon_bars == 0:
        return {
            "mfe": None,
            "mae": None,
            "final": None,
            "mfe_atr": None,
            "mae_atr": None,
            "final_diff": None,
            "favorable_close": None,
            "mfe_greater_mae": None,
            "bars_available": 0,
            "complete_horizon": True,
            "censored": False,
        }

    ref_price = float(df["close"].iloc[event_bar_index]) if reference_price is None else float(reference_price)
    start = (event_bar_index + 1) if start_bar_index is None else int(start_bar_index)
    end = min(start + horizon_bars, len(df))

    if start >= len(df) or start >= end:
        return {
            "mfe": None,
            "mae": None,
            "final": None,
            "mfe_atr": None,
            "mae_atr": None,
            "final_diff": None,
            "favorable_close": None,
            "mfe_greater_mae": None,
            "bars_available": 0,
            "complete_horizon": False,
            "censored": True,
        }

    forward = df.iloc[start:end]
    complete_horizon = len(forward) == horizon_bars

    highs = forward["high"].values
    lows = forward["low"].values

    if direction == "bullish":
        mfe = float(np.max(highs) - ref_price)
        mae = float(ref_price - np.min(lows))
        final_close = float(forward["close"].iloc[-1])
        final_diff = float(final_close - ref_price)
    else:  # bearish
        mfe = float(ref_price - np.min(lows))
        mae = float(np.max(highs) - ref_price)
        final_close = float(forward["close"].iloc[-1])
        final_diff = float(ref_price - final_close)

    mfe_val = max(0.0, mfe)
    mae_val = max(0.0, mae)
    mfe_atr = (mfe_val / baseline_atr) if (baseline_atr is not None and baseline_atr > 0) else None
    mae_atr = (mae_val / baseline_atr) if (baseline_atr is not None and baseline_atr > 0) else None

    return {
        "mfe": mfe_val,
        "mae": mae_val,
        "final": final_close,
        "mfe_atr": mfe_atr,
        "mae_atr": mae_atr,
        "final_diff": final_diff,
        "favorable_close": final_diff > 0,
        "mfe_greater_mae": mfe_val > mae_val,
        "bars_available": len(forward),
        "complete_horizon": complete_horizon,
        "censored": not complete_horizon,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Session classification
# ─────────────────────────────────────────────────────────────────────────────

def classify_session(ts: pd.Timestamp) -> str:
    """
    Classify a UTC timestamp into a Forex trading session.
    Sessions overlap; we classify by dominant session at event confirmation time.
    """
    h = ts.hour
    if 22 <= h or h < 8:
        return "Asia"
    if 8 <= h < 12:
        return "London"
    if 12 <= h < 17:
        return "NY_AM"
    return "NY_PM"


# ─────────────────────────────────────────────────────────────────────────────
# Descriptive report builder
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EventDescriptiveReport:
    """
    Collects descriptive statistics for one event type in one dataset/period.
    Not a strategy backtest.  No entry/exit, spread, or slippage assumptions.
    """
    event_type: str
    timeframe: str
    period: str                      # 'train', 'validation', 'test', or 'all'
    total_bars: int
    event_count: int
    event_rate_per_100_bars: float
    by_session: Dict[str, int] = field(default_factory=dict)
    mfe_stats: Dict[str, Optional[float]] = field(default_factory=dict)
    mae_stats: Dict[str, Optional[float]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timeframe": self.timeframe,
            "period": self.period,
            "total_bars": self.total_bars,
            "event_count": self.event_count,
            "event_rate_per_100_bars": round(self.event_rate_per_100_bars, 3),
            "by_session": self.by_session,
            "mfe_stats": self.mfe_stats,
            "mae_stats": self.mae_stats,
            "notes": self.notes,
        }


def build_structure_break_report(
    df: pd.DataFrame,
    structure_breaks: List[StructureBreak],
    timeframe: str,
    period: str,
    horizon_bars: int = 20,
) -> EventDescriptiveReport:
    """Build a descriptive report for BOS/CHoCH structure breaks."""
    total = len(df)
    notes = [
        "First break from neutral trend is labelled CHoCH by implementation convention.",
        "No trade entries or exits are assumed.",
        f"Forward excursion horizon: {horizon_bars} bars after event confirmation bar.",
        "MFE/MAE summary statistics include only events with the full requested forward horizon; edge-of-sample partial horizons are excluded.",
    ]

    mfe_list: List[float] = []
    mae_list: List[float] = []
    session_counts: Dict[str, int] = {}
    valid_event_count = 0

    for brk in structure_breaks:
        idx = brk.break_index
        if idx < 0 or idx >= total:
            continue
        valid_event_count += 1
        direction = "bullish" if brk.direction.value == "BULLISH" else "bearish"

        exc = measure_forward_excursion(df, idx, horizon_bars, direction)
        if exc["mfe"] is not None and exc["complete_horizon"]:
            mfe_list.append(exc["mfe"])
        if exc["mae"] is not None and exc["complete_horizon"]:
            mae_list.append(exc["mae"])

        ts = df["time"].iloc[idx]
        sess = classify_session(ts)
        session_counts[sess] = session_counts.get(sess, 0) + 1

    notes.append(f"Full-horizon MFE/MAE sample count: {len(mfe_list)} of {valid_event_count} valid events.")

    def _stats(vals: List[float]) -> Dict[str, Optional[float]]:
        if not vals:
            return {"mean": None, "median": None, "p25": None, "p75": None, "max": None}
        arr = np.array(vals)
        return {
            "mean": round(float(arr.mean()), 3),
            "median": round(float(np.median(arr)), 3),
            "p25": round(float(np.percentile(arr, 25)), 3),
            "p75": round(float(np.percentile(arr, 75)), 3),
            "max": round(float(arr.max()), 3),
        }

    rate = (len(structure_breaks) / total * 100) if total > 0 else 0.0
    return EventDescriptiveReport(
        event_type="StructureBreak (BOS+CHoCH)",
        timeframe=timeframe,
        period=period,
        total_bars=total,
        event_count=valid_event_count,
        event_rate_per_100_bars=rate,
        by_session=session_counts,
        mfe_stats=_stats(mfe_list),
        mae_stats=_stats(mae_list),
        notes=notes,
    )


def build_fvg_report(
    df: pd.DataFrame,
    fvgs: List[FairValueGap],
    timeframe: str,
    period: str,
    horizon_bars: int = 20,
) -> EventDescriptiveReport:
    """Build a descriptive report for Fair Value Gaps."""
    total = len(df)
    notes = [
        "FVG origin: 3-bar pattern; event known only at close of bar i+1 (third candle).",
        "Forward excursion uses close of bar i+1 as reference price.",
        "Mitigation status is retrospective; not used as entry signal here.",
        f"Forward excursion horizon: {horizon_bars} bars after creation_index.",
        "MFE/MAE summary statistics include only events with the full requested forward horizon; edge-of-sample partial horizons are excluded.",
    ]

    mfe_list: List[float] = []
    mae_list: List[float] = []
    session_counts: Dict[str, int] = {}
    mitigation_rates = {"partial": 0, "full": 0, "unmitigated": 0}
    valid_event_count = 0

    for fvg in fvgs:
        idx = fvg.creation_index
        if idx < 0 or idx >= total:
            continue
        valid_event_count += 1
        direction = fvg.gap_type.value.lower()  # 'bullish' or 'bearish'
        exc = measure_forward_excursion(df, idx, horizon_bars, direction)
        if exc["mfe"] is not None and exc["complete_horizon"]:
            mfe_list.append(exc["mfe"])
        if exc["mae"] is not None and exc["complete_horizon"]:
            mae_list.append(exc["mae"])

        ts = df["time"].iloc[idx]
        sess = classify_session(ts)
        session_counts[sess] = session_counts.get(sess, 0) + 1

        status = fvg.status.value.lower()
        if "fully" in status:
            mitigation_rates["full"] += 1
        elif "partial" in status or "encroachment" in status:
            mitigation_rates["partial"] += 1
        else:
            mitigation_rates["unmitigated"] += 1

    notes.append(f"Mitigation breakdown: {mitigation_rates}")
    notes.append(f"Full-horizon MFE/MAE sample count: {len(mfe_list)} of {valid_event_count} valid events.")

    def _stats(vals: List[float]) -> Dict[str, Optional[float]]:
        if not vals:
            return {"mean": None, "median": None, "p25": None, "p75": None, "max": None}
        arr = np.array(vals)
        return {
            "mean": round(float(arr.mean()), 3),
            "median": round(float(np.median(arr)), 3),
            "p25": round(float(np.percentile(arr, 25)), 3),
            "p75": round(float(np.percentile(arr, 75)), 3),
            "max": round(float(arr.max()), 3),
        }

    rate = (len(fvgs) / total * 100) if total > 0 else 0.0
    return EventDescriptiveReport(
        event_type="FairValueGap",
        timeframe=timeframe,
        period=period,
        total_bars=total,
        event_count=valid_event_count,
        event_rate_per_100_bars=rate,
        by_session=session_counts,
        mfe_stats=_stats(mfe_list),
        mae_stats=_stats(mae_list),
        notes=notes,
    )
