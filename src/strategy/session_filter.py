"""Session Liquidity Filter for systematic XAU/USD trading.

Institutional gold liquidity clusters during the London and New York sessions.
Trading during the Asian session (00:00 - 07:00 UTC) and the post-NY dead zone
(after 17:00 UTC) is characterized by low volume, false breakouts, and high
friction relative to volatility.

This module provides deterministic session validation with full support for:
1. Local financial exchange timezones (Europe/London and America/New_York) with
   automatic DST adjustment (BST/GMT and EDT/EST).
2. Explicit UTC operational time windows.
3. Fail-closed rejection of out-of-session entries with clear diagnostic reasons.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import zoneinfo

import pandas as pd

from src.strategy.smc_mtf import _as_utc_timestamp
from src.strategy.smc_setups import SMCSetupCandidate


@dataclass(frozen=True)
class SessionWindow:
    """Defines an intraday session window."""
    name: str
    timezone: str  # e.g. "UTC", "Europe/London", "America/New_York"
    start_time: time
    end_time: time

    def contains(self, dt_utc: pd.Timestamp) -> bool:
        """Check if UTC timestamp falls within this session window."""
        tz = zoneinfo.ZoneInfo(self.timezone)
        dt_local = dt_utc.astimezone(tz)
        t = dt_local.time()
        if self.start_time <= self.end_time:
            return self.start_time <= t <= self.end_time
        # Wraps midnight
        return t >= self.start_time or t <= self.end_time


@dataclass(frozen=True)
class SessionFilterConfig:
    """Configuration for session liquidity filtering."""
    allow_london: bool = True
    allow_new_york: bool = True
    allow_asian: bool = False

    # London local window: 07:00 to 11:00 London time (covers Frankfurt open 07:00 and London open 08:00 to morning peak)
    london_start: time = time(7, 0)
    london_end: time = time(11, 0)

    # New York local window: 08:00 to 12:00 NY time (covers US pre-market 08:00, US cash open 09:30, to lunch 12:00)
    # Corresponding to ~12:30/13:00 to 16:30/17:00 UTC depending on DST
    ny_start: time = time(8, 0)
    ny_end: time = time(12, 0)

    # Timezones
    london_tz: str = "Europe/London"
    ny_tz: str = "America/New_York"


class SessionLiquidityFilter:
    """Evaluates candidate setup entries against high-liquidity session windows."""

    def __init__(self, config: Optional[SessionFilterConfig] = None) -> None:
        self.config = config or SessionFilterConfig()
        self.windows: list[SessionWindow] = []

        if self.config.allow_london:
            self.windows.append(
                SessionWindow(
                    name="LONDON",
                    timezone=self.config.london_tz,
                    start_time=self.config.london_start,
                    end_time=self.config.london_end,
                )
            )

        if self.config.allow_new_york:
            self.windows.append(
                SessionWindow(
                    name="NEW_YORK",
                    timezone=self.config.ny_tz,
                    start_time=self.config.ny_start,
                    end_time=self.config.ny_end,
                )
            )

    def evaluate_timestamp(self, dt: Any) -> tuple[bool, Optional[str], Optional[str]]:
        """Evaluate whether a timestamp falls within an eligible session.

        Returns:
            (is_eligible, matched_session_name, rejection_reason)
        """
        dt_utc = _as_utc_timestamp(dt, label="session evaluation timestamp")

        # Check weekend: Saturday (5) and Sunday (6)
        if dt_utc.weekday() >= 5:
            return False, None, "weekend_market_closed"

        matched_sessions: list[str] = []
        for win in self.windows:
            if win.contains(dt_utc):
                matched_sessions.append(win.name)

        if matched_sessions:
            session_str = "+".join(matched_sessions)
            return True, session_str, None

        # Determine diagnostic rejection reason
        hour_utc = dt_utc.hour
        if 0 <= hour_utc < 7:
            reason = "asian_session_excluded"
        elif 11 <= hour_utc < 12:
            reason = "london_lunch_lull"
        elif hour_utc >= 17:
            reason = "post_ny_dead_zone"
        else:
            reason = "session_out_of_bounds"

        return False, None, reason

    def filter_candidates(
        self,
        candidates: Sequence[SMCSetupCandidate],
        lower_timeframe: str = "M15",
    ) -> tuple[list[SMCSetupCandidate], dict[str, Any], list[dict[str, Any]]]:
        """Filter setup candidates against session liquidity rules."""
        accepted: list[SMCSetupCandidate] = []
        audit_rows: list[dict[str, Any]] = []
        rejection_counter: Counter[str] = Counter()

        for ordinal, candidate in enumerate(candidates, start=1):
            entry_time = candidate.next_bar_time
            if entry_time is None:
                is_eligible = False
                matched_session = None
                reason = "no_next_bar"
            else:
                is_eligible, matched_session, reason = self.evaluate_timestamp(entry_time)

            if is_eligible:
                accepted.append(candidate)
            else:
                rejection_counter[reason or "unspecified_session_rejection"] += 1

            audit_rows.append({
                "candidate_ordinal": ordinal,
                "lower_timeframe": lower_timeframe.upper(),
                "signal_index": int(candidate.signal_index),
                "signal_time": pd.Timestamp(candidate.signal_time).isoformat(),
                "entry_time": pd.Timestamp(entry_time).isoformat() if entry_time is not None else None,
                "entry_weekday": pd.Timestamp(entry_time).day_name() if entry_time is not None else None,
                "entry_hour_utc": pd.Timestamp(entry_time).hour if entry_time is not None else None,
                "matched_session": matched_session,
                "accepted": is_eligible,
                "rejection_reason": reason,
            })

        funnel = {
            "input_candidates": len(candidates),
            "accepted_candidates": len(accepted),
            "rejected_candidates": len(candidates) - len(accepted),
            "rejection_reasons": dict(sorted(rejection_counter.items())),
            "policy": "Entries permitted strictly during configured London and New York session windows.",
            "london_window": f"{self.config.london_start.strftime('%H:%M')}-{self.config.london_end.strftime('%H:%M')} ({self.config.london_tz})",
            "new_york_window": f"{self.config.ny_start.strftime('%H:%M')}-{self.config.ny_end.strftime('%H:%M')} ({self.config.ny_tz})",
        }
        return accepted, funnel, audit_rows

