"""Higher-Timeframe (D1 and H4) directional bias engine for systematic XAU/USD trading.

Enforces strict causal order flow: lower-timeframe trades (M15, M5) are ONLY
permitted in the direction of confirmed higher-timeframe market structure.
A candidate setup is accepted ONLY when Daily (D1) and 4-Hour (H4) structures
are both confirmed and aligned. If either context is missing, neutral, or in
conflict, the engine defaults to NEUTRAL / NO TRADE (fail-closed architecture).

All timestamps are UTC-aware. D1 and H4 candles become available strictly upon
confirmed candle close; forming bars are never accessed.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.smc.engine import analyze_smc, SMCConfig
from src.smc.models import SMCAnalysisResult, SMCDirection
from src.strategy.smc_mtf import StructureTrendSnapshot, StructureTrendTimeline, _as_utc_timestamp
from src.strategy.smc_setups import SMCSetupCandidate


@dataclass(frozen=True)
class HTFBiasResult:
    """Result of higher-timeframe directional bias evaluation at a decision timestamp."""

    decision_time: pd.Timestamp
    bias: SMCDirection
    d1_direction: Optional[SMCDirection]
    d1_available_at: Optional[pd.Timestamp]
    h4_direction: Optional[SMCDirection]
    h4_available_at: Optional[pd.Timestamp]
    is_aligned: bool
    rejection_reason: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_time": self.decision_time.isoformat(),
            "bias": self.bias.value,
            "d1_direction": self.d1_direction.value if self.d1_direction else None,
            "d1_available_at": self.d1_available_at.isoformat() if self.d1_available_at else None,
            "h4_direction": self.h4_direction.value if self.h4_direction else None,
            "h4_available_at": self.h4_available_at.isoformat() if self.h4_available_at else None,
            "is_aligned": self.is_aligned,
            "rejection_reason": self.rejection_reason,
        }


def aggregate_daily_bars(
    df: pd.DataFrame,
    *,
    source_timeframe: str = "H4",
    drop_incomplete_trailing_day: bool = True,
) -> pd.DataFrame:
    """Causally aggregate intraday bars (H4 or H1) into completed Daily (D1) bars.

    Calendar day boundaries are defined strictly in UTC (00:00:00 to 23:59:59).
    The daily bar timestamp represents the start of the day (00:00:00 UTC).
    If ``drop_incomplete_trailing_day`` is True and the latest intraday timestamp
    does not reach the end of the final calendar day, that incomplete trailing day
    is discarded to prevent lookahead or partial-bar bias.
    """
    if df.empty:
        raise ValueError("Cannot aggregate empty DataFrame to daily bars")

    required_cols = {"time", "open", "high", "low", "close"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame missing required columns for daily aggregation: {missing}")

    work = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(work["time"]):
        work["time"] = pd.to_datetime(work["time"], utc=True)
    elif work["time"].dt.tz is None:
        raise ValueError("time column must be timezone-aware (UTC)")
    else:
        work["time"] = work["time"].dt.tz_convert("UTC")

    work = work.sort_values("time").reset_index(drop=True)
    work["date"] = work["time"].dt.floor("1D")

    agg_spec: dict[str, Any] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "tick_volume" in work.columns:
        agg_spec["tick_volume"] = "sum"
    elif "volume" in work.columns:
        agg_spec["volume"] = "sum"

    if "spread" in work.columns:
        agg_spec["spread"] = "mean"
    if "real_volume" in work.columns:
        agg_spec["real_volume"] = "sum"

    daily = work.groupby("date", as_index=False).agg(agg_spec).rename(columns={"date": "time"})

    if drop_incomplete_trailing_day and len(daily) > 0:
        last_day_start = daily["time"].iloc[-1]
        next_day_start = last_day_start + pd.Timedelta(days=1)
        # Check if the source data spans near the end of that day.
        # For H4, the final bar of the day opens at 20:00:00 and closes at 24:00 (next day 00:00).
        max_source_time = work["time"].max()
        # If the last bar open is before 20:00 (for H4) or before 23:00 (for H1), the day is incomplete.
        min_expected = next_day_start - pd.Timedelta(hours=4 if source_timeframe.upper() == "H4" else 1)
        if max_source_time < min_expected:
            daily = daily.iloc[:-1].reset_index(drop=True)

    return daily


class HTFDirectionalBiasEngine:
    """Manages D1 and H4 structure timelines to provide causal directional bias."""

    def __init__(
        self,
        h4_df: pd.DataFrame,
        d1_df: Optional[pd.DataFrame] = None,
        *,
        h4_config: Optional[SMCConfig] = None,
        d1_config: Optional[SMCConfig] = None,
    ) -> None:
        self.h4_df = h4_df.copy()
        if not pd.api.types.is_datetime64_any_dtype(self.h4_df["time"]):
            self.h4_df["time"] = pd.to_datetime(self.h4_df["time"], utc=True)
        else:
            self.h4_df["time"] = self.h4_df["time"].dt.tz_convert("UTC")
        self.h4_df = self.h4_df.sort_values("time").reset_index(drop=True)

        if d1_df is not None:
            self.d1_df = d1_df.copy()
            if not pd.api.types.is_datetime64_any_dtype(self.d1_df["time"]):
                self.d1_df["time"] = pd.to_datetime(self.d1_df["time"], utc=True)
            else:
                self.d1_df["time"] = self.d1_df["time"].dt.tz_convert("UTC")
            self.d1_df = self.d1_df.sort_values("time").reset_index(drop=True)
        else:
            self.d1_df = aggregate_daily_bars(self.h4_df, source_timeframe="H4")

        self.h4_config = h4_config or SMCConfig(swing_window=3)
        self.d1_config = d1_config or SMCConfig(swing_window=3)

        # Run deterministic SMC analysis
        self.h4_analysis = analyze_smc(self.h4_df, symbol="XAUUSD", timeframe="H4", config=self.h4_config)
        self.d1_analysis = analyze_smc(self.d1_df, symbol="XAUUSD", timeframe="D1", config=self.d1_config)

        # Establish strict data boundaries (last bar open + duration)
        self.h4_data_end_time = self.h4_df["time"].max() + pd.Timedelta(hours=4)
        self.d1_data_end_time = self.d1_df["time"].max() + pd.Timedelta(days=1)

        # Build causal timelines
        self.h4_timeline = StructureTrendTimeline.from_analysis(
            self.h4_analysis, "H4", data_end_time=self.h4_data_end_time
        )
        self.d1_timeline = StructureTrendTimeline.from_analysis(
            self.d1_analysis, "D1", data_end_time=self.d1_data_end_time
        )

    def evaluate_bias(self, decision_time: Any) -> HTFBiasResult:
        """Evaluate HTF bias at decision timestamp T.

        Only completed bars whose close_time <= T are knowable.
        Returns BULLISH if D1 == BULLISH and H4 == BULLISH.
        Returns BEARISH if D1 == BEARISH and H4 == BEARISH.
        Returns NEUTRAL with specific rejection reason otherwise (fail-closed).
        """
        decision_timestamp = _as_utc_timestamp(decision_time, label="decision_time")

        if decision_timestamp > self.h4_data_end_time:
            return HTFBiasResult(
                decision_time=decision_timestamp,
                bias=SMCDirection.NEUTRAL,
                d1_direction=None,
                d1_available_at=None,
                h4_direction=None,
                h4_available_at=None,
                is_aligned=False,
                rejection_reason="beyond_h4_data_boundary",
            )

        if decision_timestamp > self.d1_data_end_time:
            return HTFBiasResult(
                decision_time=decision_timestamp,
                bias=SMCDirection.NEUTRAL,
                d1_direction=None,
                d1_available_at=None,
                h4_direction=None,
                h4_available_at=None,
                is_aligned=False,
                rejection_reason="beyond_d1_data_boundary",
            )

        d1_snap = self.d1_timeline.at(decision_timestamp)
        h4_snap = self.h4_timeline.at(decision_timestamp)

        if d1_snap is None:
            return HTFBiasResult(
                decision_time=decision_timestamp,
                bias=SMCDirection.NEUTRAL,
                d1_direction=None,
                d1_available_at=None,
                h4_direction=h4_snap.direction if h4_snap else None,
                h4_available_at=h4_snap.available_at if h4_snap else None,
                is_aligned=False,
                rejection_reason="missing_d1_context",
            )

        if h4_snap is None:
            return HTFBiasResult(
                decision_time=decision_timestamp,
                bias=SMCDirection.NEUTRAL,
                d1_direction=d1_snap.direction,
                d1_available_at=d1_snap.available_at,
                h4_direction=None,
                h4_available_at=None,
                is_aligned=False,
                rejection_reason="missing_h4_context",
            )

        if d1_snap.direction == SMCDirection.NEUTRAL:
            return HTFBiasResult(
                decision_time=decision_timestamp,
                bias=SMCDirection.NEUTRAL,
                d1_direction=d1_snap.direction,
                d1_available_at=d1_snap.available_at,
                h4_direction=h4_snap.direction,
                h4_available_at=h4_snap.available_at,
                is_aligned=False,
                rejection_reason="d1_trend_neutral",
            )

        if h4_snap.direction == SMCDirection.NEUTRAL:
            return HTFBiasResult(
                decision_time=decision_timestamp,
                bias=SMCDirection.NEUTRAL,
                d1_direction=d1_snap.direction,
                d1_available_at=d1_snap.available_at,
                h4_direction=h4_snap.direction,
                h4_available_at=h4_snap.available_at,
                is_aligned=False,
                rejection_reason="h4_trend_neutral",
            )

        if d1_snap.direction != h4_snap.direction:
            return HTFBiasResult(
                decision_time=decision_timestamp,
                bias=SMCDirection.NEUTRAL,
                d1_direction=d1_snap.direction,
                d1_available_at=d1_snap.available_at,
                h4_direction=h4_snap.direction,
                h4_available_at=h4_snap.available_at,
                is_aligned=False,
                rejection_reason="htf_direction_conflict",
            )

        # Both agree and are either BULLISH or BEARISH
        return HTFBiasResult(
            decision_time=decision_timestamp,
            bias=d1_snap.direction,
            d1_direction=d1_snap.direction,
            d1_available_at=d1_snap.available_at,
            h4_direction=h4_snap.direction,
            h4_available_at=h4_snap.available_at,
            is_aligned=True,
            rejection_reason=None,
        )

    def filter_candidates(
        self,
        candidates: Sequence[SMCSetupCandidate],
        lower_timeframe: str,
    ) -> tuple[list[SMCSetupCandidate], dict[str, Any], list[dict[str, Any]]]:
        """Filter setup candidates against HTF directional bias.

        Only candidates whose direction strictly matches the confirmed HTF bias
        at next_bar_time are accepted.
        """
        accepted: list[SMCSetupCandidate] = []
        audit_rows: list[dict[str, Any]] = []
        rejection_counter: Counter[str] = Counter()

        for ordinal, candidate in enumerate(candidates, start=1):
            entry_time = candidate.next_bar_time
            if entry_time is None:
                reason = "no_next_bar"
                bias_res: Optional[HTFBiasResult] = None
            else:
                bias_res = self.evaluate_bias(entry_time)
                if not bias_res.is_aligned:
                    reason = bias_res.rejection_reason or "htf_not_aligned"
                elif candidate.direction != bias_res.bias:
                    reason = "candidate_direction_mismatch"
                else:
                    reason = "accepted"
                    accepted.append(candidate)

            if reason != "accepted":
                rejection_counter[reason] += 1

            audit_rows.append({
                "candidate_ordinal": ordinal,
                "lower_timeframe": lower_timeframe.upper(),
                "signal_index": int(candidate.signal_index),
                "signal_time": pd.Timestamp(candidate.signal_time).isoformat(),
                "entry_time": pd.Timestamp(entry_time).isoformat() if entry_time is not None else None,
                "candidate_direction": candidate.direction.value,
                "htf_bias": bias_res.bias.value if bias_res else None,
                "d1_direction": bias_res.d1_direction.value if (bias_res and bias_res.d1_direction) else None,
                "d1_available_at": bias_res.d1_available_at.isoformat() if (bias_res and bias_res.d1_available_at) else None,
                "h4_direction": bias_res.h4_direction.value if (bias_res and bias_res.h4_direction) else None,
                "h4_available_at": bias_res.h4_available_at.isoformat() if (bias_res and bias_res.h4_available_at) else None,
                "accepted": reason == "accepted",
                "rejection_reason": None if reason == "accepted" else reason,
            })

        funnel = {
            "input_candidates": len(candidates),
            "accepted_candidates": len(accepted),
            "rejected_candidates": len(candidates) - len(accepted),
            "rejection_reasons": dict(sorted(rejection_counter.items())),
            "policy": "Candidate direction must align with both D1 and H4 completed structure breaks.",
            "data_boundary_h4": self.h4_data_end_time.isoformat(),
            "data_boundary_d1": self.d1_data_end_time.isoformat(),
        }
        return accepted, funnel, audit_rows

