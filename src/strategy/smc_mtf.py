"""Causal multi-timeframe context filtering for experimental SMC research.

This is a separate Phase 3E experiment. It does not modify the frozen SMC v1
setup rules. H4 and H1 context are derived only from structure-break events whose
source candles have completed by the lower-timeframe entry timestamp.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.smc.models import SMCAnalysisResult, SMCDirection
from src.strategy.smc_setups import SMCSetupCandidate

TIMEFRAME_DURATIONS: Dict[str, pd.Timedelta] = {
    "M5": pd.Timedelta(minutes=5),
    "M15": pd.Timedelta(minutes=15),
    "H1": pd.Timedelta(hours=1),
    "H4": pd.Timedelta(hours=4),
    "D1": pd.Timedelta(days=1),
}
LOWER_TIMEFRAMES = ("M15", "M5")


def _as_utc_timestamp(value: Any, *, label: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware; naive timestamps are not accepted")
    return timestamp.tz_convert("UTC")


@dataclass(frozen=True)
class StructureTrendSnapshot:
    """The latest known directional structure state at a decision timestamp."""

    timeframe: str
    direction: SMCDirection
    available_at: pd.Timestamp
    break_time: pd.Timestamp
    break_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "direction": self.direction.value,
            "available_at": self.available_at.isoformat(),
            "break_time": self.break_time.isoformat(),
            "break_index": self.break_index,
        }


@dataclass(frozen=True)
class StructureTrendTimeline:
    """Chronological structure states with explicit candle-close availability.

    The optional ``data_end_time`` field records the last confirmed candle
    close for this timeframe's dataset.  When set, calls to ``at()`` with a
    ``decision_time`` strictly after ``data_end_time`` return ``None``
    rather than silently carrying forward the last known snapshot.  This
    enforces the requirement that the strategy must not use higher-timeframe
    context beyond the point where that dataset ends.
    """

    timeframe: str
    available_at_ns: Tuple[int, ...]
    snapshots: Tuple[StructureTrendSnapshot, ...]
    data_end_time: Optional[pd.Timestamp] = None

    @classmethod
    def from_analysis(
        cls,
        analysis: SMCAnalysisResult,
        timeframe: str,
        *,
        data_end_time: Optional[pd.Timestamp] = None,
    ) -> "StructureTrendTimeline":
        tf = timeframe.upper()
        if tf not in TIMEFRAME_DURATIONS:
            raise ValueError(f"Unsupported timeframe for trend context: {timeframe!r}")
        duration = TIMEFRAME_DURATIONS[tf]
        completed: list[tuple[int, StructureTrendSnapshot]] = []
        for ordinal, event in enumerate(analysis.structure_breaks):
            break_time = _as_utc_timestamp(event.break_time, label=f"{tf} structure-break time")
            available_at = break_time + duration
            snapshot = StructureTrendSnapshot(
                timeframe=tf,
                direction=event.resulting_trend,
                available_at=available_at,
                break_time=break_time,
                break_index=int(event.break_index),
            )
            # The original event ordinal is the stable tie-break if timestamps match.
            completed.append((ordinal, snapshot))
        completed.sort(key=lambda pair: (pair[1].available_at.value, pair[0]))
        snapshots = tuple(snapshot for _, snapshot in completed)
        return cls(
            timeframe=tf,
            available_at_ns=tuple(snapshot.available_at.value for snapshot in snapshots),
            snapshots=snapshots,
            data_end_time=data_end_time,
        )

    def at(self, decision_time: Any) -> Optional[StructureTrendSnapshot]:
        """Return the latest snapshot known at ``decision_time``; never use a forming bar.

        Returns ``None`` when:
        - No snapshot is available before ``decision_time`` (normal causal gap).
        - ``decision_time`` is strictly after ``self.data_end_time`` (dataset
          boundary enforcement).  This prevents the strategy from silently
          carrying forward stale higher-timeframe context after the dataset ends.
        """
        decision = _as_utc_timestamp(decision_time, label="decision_time")
        # Hard boundary: decision is beyond the end of the confirmed dataset.
        if self.data_end_time is not None and decision > self.data_end_time:
            return None
        position = bisect_right(self.available_at_ns, decision.value) - 1
        if position < 0:
            return None
        return self.snapshots[position]


def filter_candidates_by_mtf(
    candidates: Sequence[SMCSetupCandidate],
    *,
    lower_timeframe: str,
    h4_analysis: SMCAnalysisResult,
    h1_analysis: SMCAnalysisResult,
    h4_data_end_time: Optional[pd.Timestamp] = None,
    h1_data_end_time: Optional[pd.Timestamp] = None,
) -> tuple[list[SMCSetupCandidate], dict[str, Any], list[dict[str, Any]]]:
    """Keep only candidates aligned with the last completed H4 and H1 structure.

    The candidate's next-bar-open timestamp is the decision/entry timestamp. A
    candidate is accepted only when both higher-timeframe contexts are available,
    agree with each other, and match the candidate's direction. Missing next bars
    are rejected from the filtered variant because no executable entry exists.

    ``h4_data_end_time`` and ``h1_data_end_time`` are the confirmed end times of
    the H4 and H1 datasets (i.e. last bar open + timeframe duration).  Any
    candidate whose entry time falls strictly after either boundary is rejected
    with ``"missing_h4_context"`` or ``"missing_h1_context"`` because no new
    higher-timeframe information can be confirmed after that point.  Passing
    ``None`` (the default) disables the hard boundary check for that timeframe
    and preserves backward-compatible behaviour — but this allows stale-context
    carry-forward and should only be omitted in unit tests.
    """
    lower_tf = lower_timeframe.upper()
    if lower_tf not in LOWER_TIMEFRAMES:
        raise ValueError(f"Multi-timeframe entry timeframe must be one of {LOWER_TIMEFRAMES}")

    h4_timeline = StructureTrendTimeline.from_analysis(h4_analysis, "H4", data_end_time=h4_data_end_time)
    h1_timeline = StructureTrendTimeline.from_analysis(h1_analysis, "H1", data_end_time=h1_data_end_time)
    accepted: list[SMCSetupCandidate] = []
    audit_rows: list[dict[str, Any]] = []
    rejection_counter: Counter[str] = Counter()

    for ordinal, candidate in enumerate(candidates, start=1):
        entry_time = candidate.next_bar_time
        h4_snapshot: Optional[StructureTrendSnapshot] = None
        h1_snapshot: Optional[StructureTrendSnapshot] = None
        reason = "accepted"
        if entry_time is None:
            reason = "no_next_bar"
        else:
            entry_timestamp = _as_utc_timestamp(entry_time, label="candidate next_bar_time")
            h4_snapshot = h4_timeline.at(entry_timestamp)
            h1_snapshot = h1_timeline.at(entry_timestamp)
            if h4_snapshot is None or h4_snapshot.direction == SMCDirection.NEUTRAL:
                reason = "missing_h4_context"
            elif h1_snapshot is None or h1_snapshot.direction == SMCDirection.NEUTRAL:
                reason = "missing_h1_context"
            elif h4_snapshot.direction != h1_snapshot.direction:
                reason = "higher_timeframe_conflict"
            elif candidate.direction != h4_snapshot.direction:
                reason = "candidate_direction_mismatch"
            else:
                accepted.append(candidate)

        if reason != "accepted":
            rejection_counter[reason] += 1
        audit_rows.append({
            "candidate_ordinal": ordinal,
            "lower_timeframe": lower_tf,
            "signal_index": int(candidate.signal_index),
            "signal_time": pd.Timestamp(candidate.signal_time).isoformat(),
            "entry_time": pd.Timestamp(entry_time).isoformat() if entry_time is not None else None,
            "candidate_direction": candidate.direction.value,
            "h4_direction": h4_snapshot.direction.value if h4_snapshot else None,
            "h4_context_available_at": h4_snapshot.available_at.isoformat() if h4_snapshot else None,
            "h1_direction": h1_snapshot.direction.value if h1_snapshot else None,
            "h1_context_available_at": h1_snapshot.available_at.isoformat() if h1_snapshot else None,
            "accepted": reason == "accepted",
            "rejection_reason": None if reason == "accepted" else reason,
        })

    funnel = {
        "input_candidates": len(candidates),
        "accepted_candidates": len(accepted),
        "rejected_candidates": len(candidates) - len(accepted),
        "rejection_reasons": dict(sorted(rejection_counter.items())),
        "policy": "Latest completed H4 and H1 structure directions must agree with each other and the setup direction.",
        "availability_rule": "Higher-timeframe structure breaks become available at source candle open time plus the source timeframe duration; availability must be <= lower-timeframe next-bar entry time.",
        "data_boundary_h4": h4_data_end_time.isoformat() if h4_data_end_time is not None else "not_enforced",
        "data_boundary_h1": h1_data_end_time.isoformat() if h1_data_end_time is not None else "not_enforced",
        "data_boundary_note": (
            "Candidates with entry times strictly after h4_data_end_time or h1_data_end_time are "
            "rejected because no new confirmed higher-timeframe context is available after those "
            "boundaries. This prevents stale-context carry-forward beyond the dataset end."
            if (h4_data_end_time is not None or h1_data_end_time is not None)
            else "No hard data boundary enforced; stale-context carry-forward is permitted."
        ),
    }
    return accepted, funnel, audit_rows
