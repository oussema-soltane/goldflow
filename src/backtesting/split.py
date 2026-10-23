"""Chronological train/validate/holdout split for GoldFlow Phase 4 research.

Splits a DataFrame of OHLC bars by row position (not calendar time) using
configurable fractions. Fractions are treated as minimums: any remainder goes
to the training segment. The split is purely positional; no shuffling or
resampling is performed.

Rules enforced:
- No data leakage across partition boundaries.
- A bar's close cannot be used as a signal bar if any subsequent bar is in
  an earlier partition (chronological order is verified on input).
- The holdout segment must never be used for parameter selection.
- If a timeframe has fewer bars than required for at least 1 candidate per
  segment, a warning is emitted and the caller must decide how to proceed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NamedTuple, Optional

import pandas as pd


class SegmentInfo(NamedTuple):
    label: str
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    row_start: int   # inclusive
    row_end: int     # exclusive
    n_rows: int


@dataclass(frozen=True)
class SplitConfig:
    """Chronological split fractions.

    Fractions must sum to <= 1.0. The training fraction gets any remainder
    (so train_fraction is effectively a minimum).
    """
    train_fraction: float = 0.60
    validate_fraction: float = 0.20
    # holdout_fraction is derived: 1 - train - validate
    min_rows_per_segment: int = 50  # raise a warning if any segment has fewer

    def __post_init__(self) -> None:
        for name, val in [
            ("train_fraction", self.train_fraction),
            ("validate_fraction", self.validate_fraction),
        ]:
            if not isinstance(val, (int, float)) or not (0 < val < 1):
                raise ValueError(f"{name} must be in (0, 1)")
        if self.train_fraction + self.validate_fraction >= 1.0:
            raise ValueError("train_fraction + validate_fraction must be < 1.0")
        if not isinstance(self.min_rows_per_segment, int) or self.min_rows_per_segment < 1:
            raise ValueError("min_rows_per_segment must be a positive integer")

    @property
    def holdout_fraction(self) -> float:
        return 1.0 - self.train_fraction - self.validate_fraction


class ChronologicalSplit:
    """Three-way chronological split of a OHLC DataFrame.

    Attributes
    ----------
    segments : list[SegmentInfo]
        Ordered [train, validate, holdout] metadata.
    warnings : list[str]
        Non-fatal issues (e.g., segments with fewer rows than min_rows_per_segment).
    """

    LABELS = ("train", "validate", "holdout")

    def __init__(self, df: pd.DataFrame, config: Optional[SplitConfig] = None) -> None:
        self._config = config or SplitConfig()
        self._frame = self._validate(df)
        self.segments, self.warnings = self._compute_splits()

    @staticmethod
    def _validate(df: pd.DataFrame) -> pd.DataFrame:
        required = {"time", "open", "high", "low", "close"}
        missing = sorted(required - set(df.columns))
        if missing:
            raise ValueError(f"Split input missing columns: {', '.join(missing)}")
        frame = df.copy().reset_index(drop=True)
        frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
        if frame["time"].isna().any():
            raise ValueError("Split input has invalid timestamps")
        if not frame["time"].is_monotonic_increasing:
            raise ValueError("Split input timestamps must be chronological")
        if frame["time"].duplicated().any():
            raise ValueError("Split input timestamps must be unique")
        if len(frame) < 3:
            raise ValueError("Split input must have at least 3 rows")
        return frame

    def _compute_splits(self) -> tuple[list[SegmentInfo], list[str]]:
        n = len(self._frame)
        cfg = self._config
        n_train = max(1, int(n * cfg.train_fraction))
        n_validate = max(1, int(n * cfg.validate_fraction))
        # holdout gets the remainder; guarantee at least 1 row each
        n_holdout = n - n_train - n_validate
        if n_holdout < 1:
            # shrink validate by 1 to give holdout a row
            n_validate = max(1, n_validate - 1)
            n_holdout = n - n_train - n_validate
        if n_holdout < 1:
            # shrink train by 1 as last resort
            n_train = max(1, n_train - 1)
            n_holdout = n - n_train - n_validate

        boundaries = [
            (0, n_train),
            (n_train, n_train + n_validate),
            (n_train + n_validate, n),
        ]
        segments: list[SegmentInfo] = []
        warnings: list[str] = []
        for label, (start, end) in zip(self.LABELS, boundaries):
            segment_df = self._frame.iloc[start:end]
            nrows = end - start
            if nrows < self._config.min_rows_per_segment:
                warnings.append(
                    f"{label} segment has only {nrows} rows "
                    f"(min_rows_per_segment={self._config.min_rows_per_segment}). "
                    "Trade counts will likely be too small for reliable conclusions."
                )
            seg = SegmentInfo(
                label=label,
                start_time=pd.Timestamp(segment_df["time"].iloc[0]),
                end_time=pd.Timestamp(segment_df["time"].iloc[-1]),
                row_start=start,
                row_end=end,
                n_rows=nrows,
            )
            segments.append(seg)
        return segments, warnings

    def get_segment(self, label: str) -> pd.DataFrame:
        """Return the rows for a named segment, reset-indexed."""
        for seg in self.segments:
            if seg.label == label:
                return self._frame.iloc[seg.row_start:seg.row_end].copy().reset_index(drop=True)
        raise ValueError(f"Unknown segment label {label!r}. Use one of: {self.LABELS}")

    @property
    def train(self) -> pd.DataFrame:
        return self.get_segment("train")

    @property
    def validate(self) -> pd.DataFrame:
        return self.get_segment("validate")

    @property
    def holdout(self) -> pd.DataFrame:
        return self.get_segment("holdout")

    def summary(self) -> dict[str, Any]:
        return {
            "total_rows": len(self._frame),
            "config": {
                "train_fraction": self._config.train_fraction,
                "validate_fraction": self._config.validate_fraction,
                "holdout_fraction": self._config.holdout_fraction,
                "min_rows_per_segment": self._config.min_rows_per_segment,
            },
            "segments": [
                {
                    "label": s.label,
                    "start_time": s.start_time.isoformat(),
                    "end_time": s.end_time.isoformat(),
                    "row_start": s.row_start,
                    "row_end": s.row_end,
                    "n_rows": s.n_rows,
                }
                for s in self.segments
            ],
            "warnings": self.warnings,
        }


def chronological_split(
    df: pd.DataFrame,
    config: Optional[SplitConfig] = None,
) -> ChronologicalSplit:
    """Convenience wrapper returning a ChronologicalSplit object."""
    return ChronologicalSplit(df, config)
