"""High-Impact USD Economic News Filter for systematic XAU/USD trading.

Economic events (NFP, CPI, PPI, FOMC, Core PCE, GDP) trigger substantial spread
widening, liquidity vacuum, and price slippage on gold. This module implements
a strict blackout window around high-impact announcements:
- 15 minutes before scheduled release (pre-event spread widening protection).
- 30 minutes after scheduled release (post-event volatility stabilization).

Fail-closed architecture: if the calendar file cannot be loaded or is empty,
news protection blocks trade entry rather than proceeding without verification.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd

from src.strategy.smc_mtf import _as_utc_timestamp
from src.strategy.smc_setups import SMCSetupCandidate


@dataclass(frozen=True)
class NewsFilterConfig:
    """Parameters for news blackout protection."""
    pre_news_minutes: int = 15
    post_news_minutes: int = 30
    require_coverage: bool = True  # Reject if entry timestamp is outside calendar range


class HighImpactNewsFilter:
    """Manages high-impact USD economic events and blocks trades during blackout windows."""

    def __init__(
        self,
        calendar_source: Optional[Union[str, Path, pd.DataFrame]] = None,
        config: Optional[NewsFilterConfig] = None,
    ) -> None:
        self.config = config or NewsFilterConfig()
        self.pre_buffer = pd.Timedelta(minutes=self.config.pre_news_minutes)
        self.post_buffer = pd.Timedelta(minutes=self.config.post_news_minutes)
        self.events: list[dict[str, Any]] = []
        self.event_timestamps_ns: list[int] = []
        self.calendar_start: Optional[pd.Timestamp] = None
        self.calendar_end: Optional[pd.Timestamp] = None
        self.is_loaded = False

        self._load_calendar(calendar_source)

    def _load_calendar(self, source: Optional[Union[str, Path, pd.DataFrame]]) -> None:
        if source is None:
            # Default to standard project calendar
            default_path = Path("data/news/usd_high_impact_news.csv")
            if default_path.exists():
                source = default_path
            else:
                self.is_loaded = False
                return

        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                self.is_loaded = False
                return
            df = pd.read_csv(path)
        elif isinstance(source, pd.DataFrame):
            df = source.copy()
        else:
            raise ValueError(f"Unsupported calendar source type: {type(source)}")

        if df.empty or "timestamp_utc" not in df.columns or "event_name" not in df.columns:
            self.is_loaded = False
            return

        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
        df = df.sort_values("timestamp_utc").reset_index(drop=True)

        for _, row in df.iterrows():
            ts = row["timestamp_utc"]
            self.events.append({
                "timestamp": ts,
                "event_name": str(row["event_name"]),
                "currency": str(row.get("currency", "USD")),
                "impact": str(row.get("impact_level", "HIGH")),
            })
            self.event_timestamps_ns.append(ts.value)

        if self.events:
            self.calendar_start = self.events[0]["timestamp"]
            self.calendar_end = self.events[-1]["timestamp"]
            self.is_loaded = True

    def evaluate_timestamp(
        self, dt: Any
    ) -> tuple[bool, Optional[str], Optional[str], Optional[float]]:
        """Check if timestamp falls within a high-impact news blackout window.

        Returns:
            (is_blocked, nearest_event_name, rejection_reason, minutes_relative_to_event)
            where minutes_relative_to_event is negative before event, positive after.
        """
        dt_utc = _as_utc_timestamp(dt, label="news evaluation timestamp")

        if not self.is_loaded or not self.events:
            return True, None, "news_calendar_unloaded_fail_closed", None

        # Check coverage
        if self.config.require_coverage:
            if dt_utc < self.calendar_start - pd.Timedelta(days=7) or dt_utc > self.calendar_end + pd.Timedelta(days=7):
                return True, None, "news_calendar_coverage_gap", None

        t_val = dt_utc.value
        # Binary search for closest events
        idx = bisect_right(self.event_timestamps_ns, t_val)
        candidate_indices = []
        if idx > 0:
            candidate_indices.append(idx - 1)
        if idx < len(self.events):
            candidate_indices.append(idx)
        if idx + 1 < len(self.events):
            candidate_indices.append(idx + 1)

        nearest_event = None
        min_abs_diff_mins = float("inf")
        nearest_rel_mins = 0.0

        for i in candidate_indices:
            ev = self.events[i]
            ev_time = ev["timestamp"]
            diff = (dt_utc - ev_time).total_seconds() / 60.0
            if abs(diff) < min_abs_diff_mins:
                min_abs_diff_mins = abs(diff)
                nearest_event = ev
                nearest_rel_mins = diff

            # Blackout window check: [ev_time - pre_buffer, ev_time + post_buffer]
            window_start = ev_time - self.pre_buffer
            window_end = ev_time + self.post_buffer
            if window_start <= dt_utc <= window_end:
                mins_str = f"{diff:+.1f}m"
                reason = f"news_blackout:{ev['event_name']}:{mins_str}"
                return True, ev["event_name"], reason, diff

        return False, nearest_event["event_name"] if nearest_event else None, None, nearest_rel_mins

    def filter_candidates(
        self,
        candidates: Sequence[SMCSetupCandidate],
        lower_timeframe: str = "M15",
    ) -> tuple[list[SMCSetupCandidate], dict[str, Any], list[dict[str, Any]]]:
        """Filter setup candidates against news blackout rules."""
        accepted: list[SMCSetupCandidate] = []
        audit_rows: list[dict[str, Any]] = []
        rejection_counter: Counter[str] = Counter()

        for ordinal, candidate in enumerate(candidates, start=1):
            entry_time = candidate.next_bar_time
            if entry_time is None:
                is_blocked = True
                ev_name = None
                reason = "no_next_bar"
                rel_mins = None
            else:
                is_blocked, ev_name, reason, rel_mins = self.evaluate_timestamp(entry_time)

            if not is_blocked:
                accepted.append(candidate)
            else:
                # Group blackout reasons by broad category for the summary counter
                summary_reason = reason.split(":")[0] if (reason and ":" in reason) else (reason or "news_blocked")
                rejection_counter[summary_reason] += 1

            audit_rows.append({
                "candidate_ordinal": ordinal,
                "lower_timeframe": lower_timeframe.upper(),
                "signal_index": int(candidate.signal_index),
                "signal_time": pd.Timestamp(candidate.signal_time).isoformat(),
                "entry_time": pd.Timestamp(entry_time).isoformat() if entry_time is not None else None,
                "nearest_event": ev_name,
                "minutes_to_event": round(rel_mins, 1) if rel_mins is not None else None,
                "accepted": not is_blocked,
                "rejection_reason": reason,
            })

        funnel = {
            "input_candidates": len(candidates),
            "accepted_candidates": len(accepted),
            "rejected_candidates": len(candidates) - len(accepted),
            "rejection_reasons": dict(sorted(rejection_counter.items())),
            "policy": f"Block entries within [-{self.config.pre_news_minutes}m, +{self.config.post_news_minutes}m] of high-impact releases.",
            "calendar_events_count": len(self.events),
            "calendar_span": f"{self.calendar_start} to {self.calendar_end}" if self.is_loaded else "unloaded",
        }
        return accepted, funnel, audit_rows

