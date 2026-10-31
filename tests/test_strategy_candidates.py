"""
Tests for Experimental SMC Strategy Candidates (Phase 6 Research).

Verifies:
1. Frozen SMC v1 configuration integrity remains intact and unaltered.
2. Research candidate specifications are immutable frozen dataclasses.
3. Session filtering causally rejects off-hours signals, admits London/NY signals.
4. Target rationalization enforces fixed 2.0R without opposing-swing dependency.
5. All candidate names and versions are unique.
6. Candidates do not mutate frozen config at runtime.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from src.smc.models import SMCDirection
from src.strategy.smc_setups import SMCSetupCandidate, SMCSetupConfig
from src.strategy.smc_research_candidates import (
    CANDIDATE_BASELINE_V1,
    CANDIDATE_SESSION_FILTERED,
    CANDIDATE_TARGET_RATIONALIZED,
    CANDIDATE_COMPOSITE_LIQUID,
    CANDIDATE_NY_SESSION,
    CANDIDATE_MTF_ALIGNED,
    ResearchCandidateSpec,
    filter_candidates_by_session,
)

FROZEN_CONFIG_HASH = "1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_candidate(signal_hour: int, direction: SMCDirection = SMCDirection.BULLISH) -> SMCSetupCandidate:
    """Construct a minimal SMCSetupCandidate at the given UTC hour on 2026-03-02."""
    ts = pd.Timestamp(f"2026-03-02 {signal_hour:02d}:15:00+00:00")
    if direction == SMCDirection.BULLISH:
        entry, sl, tp = 2000.0, 1995.0, 2010.0
    else:
        entry, sl, tp = 2010.0, 2015.0, 2000.0
    return SMCSetupCandidate(
        direction=direction,
        sweep_index=1,
        sweep_time=ts - pd.Timedelta(minutes=10),
        choch_index=2,
        choch_time=ts - pd.Timedelta(minutes=5),
        order_block_origin_index=0,
        order_block_created_index=1,
        order_block_created_time=ts - pd.Timedelta(minutes=5),
        signal_index=3,
        signal_time=ts,
        entry_reference_price=entry,
        stop_loss_reference=sl,
        take_profit_reference=tp,
        target_source="opposing_liquidity",
        risk_distance=abs(entry - sl),
        reward_risk_ratio=2.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFrozenConfigIntegrity:
    def test_config_file_exists(self):
        config_path = Path("configs/smc_v1_frozen.json")
        assert config_path.exists(), "configs/smc_v1_frozen.json must exist"

    def test_config_hash_unchanged(self):
        config_path = Path("configs/smc_v1_frozen.json")
        content = config_path.read_bytes()
        observed = hashlib.sha256(content).hexdigest()
        assert observed == FROZEN_CONFIG_HASH, (
            f"Frozen config hash MISMATCH!\n"
            f"  Expected : {FROZEN_CONFIG_HASH}\n"
            f"  Observed : {observed}"
        )


class TestCandidateSpecImmutability:
    def test_baseline_is_frozen(self):
        with pytest.raises((AttributeError, TypeError)):
            CANDIDATE_BASELINE_V1.session_filter_enabled = True  # type: ignore

    def test_composite_is_frozen(self):
        with pytest.raises((AttributeError, TypeError)):
            CANDIDATE_COMPOSITE_LIQUID.name = "tampered"  # type: ignore

    def test_setup_config_is_frozen(self):
        with pytest.raises((AttributeError, TypeError)):
            CANDIDATE_BASELINE_V1.setup_config.fixed_rr = 9.9  # type: ignore

    def test_all_specs_are_resonable(self):
        specs = [
            CANDIDATE_BASELINE_V1,
            CANDIDATE_SESSION_FILTERED,
            CANDIDATE_TARGET_RATIONALIZED,
            CANDIDATE_COMPOSITE_LIQUID,
            CANDIDATE_NY_SESSION,
            CANDIDATE_MTF_ALIGNED,
        ]
        for spec in specs:
            assert isinstance(spec, ResearchCandidateSpec)
            assert spec.name
            assert spec.version


class TestSessionFilter:
    """Verifies session filter accurately applies UTC hour boundaries."""

    CANDIDATES = [
        _make_candidate(1),   # 01:00 UTC — Asian (should be REJECTED by 07-21 filter)
        _make_candidate(8),   # 08:00 UTC — London (should be ACCEPTED)
        _make_candidate(14),  # 14:00 UTC — NY Overlap (should be ACCEPTED)
        _make_candidate(18),  # 18:00 UTC — NY Afternoon (should be ACCEPTED)
        _make_candidate(21),  # 21:00 UTC — Rollover/close (should be REJECTED, end is exclusive)
        _make_candidate(22),  # 22:00 UTC — After NY (should be REJECTED)
    ]

    def test_liquid_session_filter_07_21(self):
        """Hours 07:00-20:59 pass; 01:00, 21:00, 22:00 are rejected."""
        filtered = filter_candidates_by_session(self.CANDIDATES, start_hour=7, end_hour=21)
        accepted_hours = sorted(pd.Timestamp(c.signal_time).hour for c in filtered)
        assert accepted_hours == [8, 14, 18], f"Unexpected hours: {accepted_hours}"

    def test_01_utc_rejected(self):
        """Asian session 01:00 is strictly rejected."""
        filtered = filter_candidates_by_session([_make_candidate(1)], start_hour=7, end_hour=21)
        assert filtered == []

    def test_22_utc_rejected(self):
        """Post-NY 22:00 is strictly rejected."""
        filtered = filter_candidates_by_session([_make_candidate(22)], start_hour=7, end_hour=21)
        assert filtered == []

    def test_14_utc_accepted(self):
        """NY overlap 14:00 is accepted."""
        filtered = filter_candidates_by_session([_make_candidate(14)], start_hour=7, end_hour=21)
        assert len(filtered) == 1

    def test_ny_session_filter_13_21(self):
        """NY-only 13:00-20:59 filter admits 14:00 and 18:00, rejects others."""
        filtered = filter_candidates_by_session(self.CANDIDATES, start_hour=13, end_hour=21)
        accepted_hours = sorted(pd.Timestamp(c.signal_time).hour for c in filtered)
        assert accepted_hours == [14, 18], f"Unexpected NY hours: {accepted_hours}"

    def test_empty_list_returns_empty(self):
        filtered = filter_candidates_by_session([], start_hour=7, end_hour=21)
        assert filtered == []


class TestTargetRationalization:
    def test_baseline_uses_opposing_liquidity(self):
        assert CANDIDATE_BASELINE_V1.setup_config.use_opposing_liquidity_target is True

    def test_rationalized_uses_fixed_rr(self):
        cfg = CANDIDATE_TARGET_RATIONALIZED.setup_config
        assert cfg.use_opposing_liquidity_target is False
        assert cfg.fixed_rr == 2.0

    def test_composite_liquid_uses_fixed_rr(self):
        cfg = CANDIDATE_COMPOSITE_LIQUID.setup_config
        assert cfg.use_opposing_liquidity_target is False
        assert cfg.fixed_rr == 2.0

    def test_ny_session_uses_fixed_rr(self):
        cfg = CANDIDATE_NY_SESSION.setup_config
        assert cfg.use_opposing_liquidity_target is False
        assert cfg.fixed_rr == 2.0


class TestCandidateSuiteCompleteness:
    SUITE = [
        CANDIDATE_BASELINE_V1,
        CANDIDATE_SESSION_FILTERED,
        CANDIDATE_TARGET_RATIONALIZED,
        CANDIDATE_COMPOSITE_LIQUID,
        CANDIDATE_NY_SESSION,
        CANDIDATE_MTF_ALIGNED,
    ]

    def test_unique_names(self):
        names = [c.name for c in self.SUITE]
        assert len(names) == len(set(names)), f"Duplicate candidate names: {names}"

    def test_unique_versions(self):
        versions = [c.version for c in self.SUITE]
        assert len(versions) == len(set(versions)), f"Duplicate versions: {versions}"

    def test_six_candidates_registered(self):
        assert len(self.SUITE) == 6

    def test_baseline_version_is_1_0_0(self):
        assert CANDIDATE_BASELINE_V1.version == "1.0.0"

    def test_mtf_aligned_requires_htf_confirmation(self):
        assert CANDIDATE_MTF_ALIGNED.require_htf_confirmation is True

    def test_baseline_no_htf_confirmation(self):
        assert CANDIDATE_BASELINE_V1.require_htf_confirmation is False

    def test_session_filtered_window(self):
        assert CANDIDATE_SESSION_FILTERED.allowed_session_start_hour == 7
        assert CANDIDATE_SESSION_FILTERED.allowed_session_end_hour == 21

    def test_ny_session_window(self):
        assert CANDIDATE_NY_SESSION.allowed_session_start_hour == 13
        assert CANDIDATE_NY_SESSION.allowed_session_end_hour == 21
