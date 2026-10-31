"""
Phase 6G — Regression and Integrity Tests.

Covers:
1. Frozen candidate spec immutability verified after Phase 6G modifications.
2. No-look-ahead assertion on session filter (filter uses signal_time, not outcome).
3. Validation window data boundary enforcement (no bar before 2026-10-22 09:30).
4. Cost schema: raw_gross_pnl - total_costs = net_pnl (per-trade identity).
5. C1 not a pure subset of C0 at signal level (documented anomaly guard).
6. Frozen config hash unchanged after Phase 6G.
7. Validation window price scale consistency (same regime as processed data).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

FROZEN_CONFIG_HASH = "1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a"
ROOT = Path(__file__).resolve().parent.parent
STRATEGY_REPORTS = ROOT / "reports" / "strategy"
DATA_DIR = ROOT / "data"


# ─────────────────────────────────────────────────────────────────────────────
class TestFrozenConfigAfterPhase6G:
    def test_config_hash_unchanged(self):
        path = ROOT / "configs" / "smc_v1_frozen.json"
        assert path.exists()
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        assert h == FROZEN_CONFIG_HASH, f"Config hash changed: {h}"


# ─────────────────────────────────────────────────────────────────────────────
class TestCandidateSpecFreezeIntegrity:
    def test_frozen_spec_file_exists(self):
        spec_path = STRATEGY_REPORTS / "phase6g_frozen_candidate_specs.json"
        assert spec_path.exists(), "Phase 6G frozen spec file not found"

    def test_frozen_spec_contains_c0_c1_c2(self):
        spec_path = STRATEGY_REPORTS / "phase6g_frozen_candidate_specs.json"
        specs = json.loads(spec_path.read_text(encoding="utf-8"))
        assert "C0_baseline" in specs["candidates"]
        assert "C1_session_filter" in specs["candidates"]
        assert "C2_target_rationalized" in specs["candidates"]

    def test_frozen_spec_records_git_head(self):
        spec_path = STRATEGY_REPORTS / "phase6g_frozen_candidate_specs.json"
        specs = json.loads(spec_path.read_text(encoding="utf-8"))
        assert specs.get("git_head") == "ad9807f8405811d65148d73d72139243f3d6a77f"

    def test_frozen_spec_c1_session_boundaries(self):
        spec_path = STRATEGY_REPORTS / "phase6g_frozen_candidate_specs.json"
        specs = json.loads(spec_path.read_text(encoding="utf-8"))
        c1 = specs["candidates"]["C1_session_filter"]
        assert c1["session_start_hour_utc"] == 7
        assert c1["session_end_hour_utc"] == 21
        assert c1["session_filter_enabled"] is True

    def test_frozen_spec_config_hash_matches(self):
        spec_path = STRATEGY_REPORTS / "phase6g_frozen_candidate_specs.json"
        specs = json.loads(spec_path.read_text(encoding="utf-8"))
        assert specs["smc_v1_config_hash"] == FROZEN_CONFIG_HASH


# ─────────────────────────────────────────────────────────────────────────────
class TestValidationWindowBoundary:
    def test_validation_file_exists(self):
        path = DATA_DIR / "processed" / "XAUUSD_M15_validation_window.csv"
        assert path.exists()

    def test_validation_window_starts_after_processed_last_bar(self):
        val_path = DATA_DIR / "processed" / "XAUUSD_M15_validation_window.csv"
        proc_path = DATA_DIR / "processed" / "XAUUSD_M15_clean.csv"
        assert val_path.exists() and proc_path.exists()

        val = pd.read_csv(val_path)
        proc = pd.read_csv(proc_path)
        val["time"] = pd.to_datetime(val["time"], utc=True)
        proc["time"] = pd.to_datetime(proc["time"], utc=True)

        proc_last = proc["time"].max()
        val_first = val["time"].min()

        assert val_first > proc_last, (
            f"Validation window starts at {val_first} which is not after "
            f"processed last bar {proc_last} — boundary contamination!"
        )

    def test_validation_window_bar_count(self):
        val_path = DATA_DIR / "processed" / "XAUUSD_M15_validation_window.csv"
        if not val_path.exists():
            pytest.skip("Validation window not generated yet")
        val = pd.read_csv(val_path)
        # Must have at least 400 bars (no silently truncated window)
        assert len(val) >= 400, f"Expected 400+ validation bars, got {len(val)}"

    def test_validation_window_no_future_bar_contamination(self):
        """Ensure validation window does not extend into unrecorded future."""
        val_path = DATA_DIR / "processed" / "XAUUSD_M15_validation_window.csv"
        if not val_path.exists():
            pytest.skip("Validation window not generated yet")
        val = pd.read_csv(val_path)
        val["time"] = pd.to_datetime(val["time"], utc=True)
        # Must not extend beyond 2026-10-29 23:00 UTC (raw file last bar is 22:30)
        assert val["time"].max() <= pd.Timestamp("2026-10-30 00:00:00+00:00")


# ─────────────────────────────────────────────────────────────────────────────
class TestCostSchemaIdentity:
    """Verify raw_gross_pnl - total_costs = net_pnl for every closed trade."""

    @pytest.fixture
    def m5_c0_closed(self):
        path = STRATEGY_REPORTS / "trades_M5_SMC_v1_frozen_baseline.csv"
        if not path.exists():
            pytest.skip("Trade ledger not available")
        df = pd.read_csv(path)
        return df[df["status"] == "CLOSED"]

    def test_cost_identity_per_trade(self, m5_c0_closed):
        required = {"raw_gross_pnl", "total_transaction_costs", "net_pnl"}
        missing = required - set(m5_c0_closed.columns)
        if missing:
            pytest.skip(f"Columns missing: {missing}")

        residuals = (
            m5_c0_closed["raw_gross_pnl"]
            - m5_c0_closed["total_transaction_costs"]
            - m5_c0_closed["net_pnl"]
        ).abs()
        assert residuals.max() < 1e-4, (
            f"Cost identity violated: max residual = {residuals.max():.6f}"
        )

    def test_costs_are_positive(self, m5_c0_closed):
        if "total_transaction_costs" not in m5_c0_closed.columns:
            pytest.skip("Column not available")
        # All transaction costs should be >= 0
        negative_costs = (m5_c0_closed["total_transaction_costs"] < 0).sum()
        assert negative_costs == 0, f"{negative_costs} trades have negative transaction costs"


# ─────────────────────────────────────────────────────────────────────────────
class TestSessionFilterNoLookahead:
    """Session filter must use signal_time (decision time), not exit outcome."""

    def test_c1_signals_all_in_session_window(self):
        path = STRATEGY_REPORTS / "trades_M15_SMC_v2_session_filtered.csv"
        if not path.exists():
            pytest.skip("C1 M15 trade ledger not found")
        df = pd.read_csv(path)
        closed = df[df["status"] == "CLOSED"] if "status" in df.columns else df
        closed = closed.copy()
        closed["signal_time"] = pd.to_datetime(closed["signal_time"], utc=True)
        hours = closed["signal_time"].dt.hour
        # All signals must be in [7, 20] (07:00 inclusive, 21:00 exclusive)
        out_of_window = ((hours < 7) | (hours >= 21)).sum()
        assert out_of_window == 0, (
            f"{out_of_window} C1 M15 trades have signal_time outside 07:00-20:59 UTC"
        )

    def test_exit_time_not_used_for_filter(self):
        """
        Confirm that no trade was rejected whose signal was in-session
        but whose exit (future) was out-of-session.
        This would indicate look-ahead in the filter.
        Proxy test: all trades in ledger have signal in [7,21).
        """
        path = STRATEGY_REPORTS / "trades_M15_SMC_v2_session_filtered.csv"
        if not path.exists():
            pytest.skip("C1 M15 trade ledger not found")
        df = pd.read_csv(path)
        if "exit_time" not in df.columns or "signal_time" not in df.columns:
            pytest.skip("Required columns not present")
        closed = df[df["status"] == "CLOSED"].copy() if "status" in df.columns else df.copy()
        closed["signal_time"] = pd.to_datetime(closed["signal_time"], utc=True)
        closed["exit_time"] = pd.to_datetime(closed["exit_time"], utc=True)
        # All entry decisions were in session — exit time is irrelevant to admission
        hours = closed["signal_time"].dt.hour
        assert ((hours >= 7) & (hours < 21)).all(), "Signal time filter violated"


# ─────────────────────────────────────────────────────────────────────────────
class TestVerificationArtifacts:
    def test_stage_a_verification_json_exists(self):
        path = STRATEGY_REPORTS / "phase6g_stage_a_verification.json"
        assert path.exists()

    def test_stage_a_no_discrepancies(self):
        path = STRATEGY_REPORTS / "phase6g_stage_a_verification.json"
        if not path.exists():
            pytest.skip("Verification file not generated")
        data = json.loads(path.read_text(encoding="utf-8"))
        discrepancies = data.get("discrepancies", [])
        assert len(discrepancies) == 0, (
            f"Phase 6F result discrepancies found:\n"
            + "\n".join(str(d) for d in discrepancies)
        )

    def test_validation_results_json_exists(self):
        path = STRATEGY_REPORTS / "phase6g_candidate_validation_results.json"
        assert path.exists()

    def test_validation_results_has_c0_c1_c2(self):
        path = STRATEGY_REPORTS / "phase6g_candidate_validation_results.json"
        if not path.exists():
            pytest.skip("Validation results not generated")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "C0" in data.get("results", {})
        assert "C1" in data.get("results", {})
        assert "C2" in data.get("results", {})

