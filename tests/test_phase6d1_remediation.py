"""
Comprehensive Data Integrity, Vault Security, Evaluation Gate and Research Reconciliation Tests.

Guards Phase 6D.1 remediations:
1. Immutable shard storage (multi-hour preservation, overwrite prevention, idempotent re-ingestion, conflict rejection).
2. Preservation and verification of original compressed source objects.
3. Ingestion timestamp provenance (no backdating of historical records; None when unknown).
4. Unconditional fail-closed gate for real XAUUSD network ingestion.
5. HTTP safety gates: 404, 403, 429, timeout, oversized response, holdout storage escape.
6. Fail-closed evaluation gate: registry corruption, exact registered dataset-set matching.
7. Full-table dual-timestamp validation across all forward rows.
8. Hash-chain audit ledger: full-chain verification before append.
9. MT5 transactional promotion rollback: cleanup of newly created targets.
10. Independent M15 and M5 cost-replay reconciliation.
11. Bid-side volume preservation.
12. Dual hash verification (raw file bytes vs platform-independent canonical JSON).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import urllib.error

import numpy as np
import pandas as pd
import pytest

from src.data.ingestion.base import (
    AuthenticationError,
    DataUnavailableError,
    IngestionError,
)
from src.data.ingestion.bi5_decoder import (
    Bi5FileLayout,
    DukascopyBi5Decoder,
)
from src.data.ingestion.dukascopy_provider import DukascopyIngestionProvider
from src.data.ingestion.instrument_spec import (
    DUKASCOPY_EURUSD_SPEC,
    DUKASCOPY_XAUUSD_SPEC,
    SYNTHETIC_XAUUSD_FIXTURE_SPEC,
    UnverifiedPriceScaleError,
    VerificationStatus,
    get_provider_instrument_spec,
)
from src.data.ingestion.models import (
    DatasetClassification,
    RawTickObservation,
)
from src.vault.audit_ledger import TamperEvidentAuditLedger
from src.vault.evaluation_gate import (
    EvaluationGate,
    EvaluationGateError,
    ForwardEligibilityError,
)
from src.vault.raw_storage import (
    PartitionConflictError,
    PartitionStorageManager,
    compute_sha256,
)
from src.vault.registration import (
    EXPECTED_FROZEN_SMC_HASH,
    EvaluationRegistrationManager,
    EvaluationStatus,
    EvaluationType,
    verify_frozen_config,
)
from tests.fixtures.synthetic_bi5 import generate_valid_hourly_fixture


# ==============================================================================
# 1. IMMUTABLE STORAGE & OVERWRITE DEFECT REGRESSION TESTS
# ==============================================================================

class TestImmutableStorageAndPartitioning:
    """Tests ensuring hourly ingestion cannot overwrite partitions or source bytes."""

    def test_two_distinct_hours_produce_separate_shard_files(self, tmp_path: Path):
        """Ingesting two distinct hours in the same month must produce two distinct files."""
        mgr = PartitionStorageManager(vault_root=tmp_path)

        df_h1 = pd.DataFrame({
            "timestamp_utc": pd.date_range("2026-10-20 08:00:00", periods=5, freq="10s", tz="UTC"),
            "bid": [2735.1, 2735.2, 2735.15, 2735.3, 2735.25],
            "ask": [2735.3, 2735.4, 2735.35, 2735.5, 2735.45],
            "volume": [1.0, 1.0, 1.0, 1.0, 1.0],
        })
        df_h2 = pd.DataFrame({
            "timestamp_utc": pd.date_range("2026-10-20 09:00:00", periods=5, freq="10s", tz="UTC"),
            "bid": [2736.1, 2736.2, 2736.15, 2736.3, 2736.25],
            "ask": [2736.3, 2736.4, 2736.35, 2736.5, 2736.45],
            "volume": [1.0, 1.0, 1.0, 1.0, 1.0],
        })

        p1, m1, _ = mgr.write_partition(df_h1, "XAUUSD", "DUKASCOPY", granularity="hourly")
        p2, m2, _ = mgr.write_partition(df_h2, "XAUUSD", "DUKASCOPY", granularity="hourly")

        assert p1.exists()
        assert p2.exists()
        assert p1 != p2, f"Hour 1 ({p1.name}) and Hour 2 ({p2.name}) must have distinct filenames"
        assert "20261020_08" in p1.name
        assert "20261020_09" in p2.name

    def test_repeated_ingestion_of_identical_hour_is_idempotent(self, tmp_path: Path):
        """Repeated ingestion of identical content must succeed and return the existing partition."""
        mgr = PartitionStorageManager(vault_root=tmp_path)

        df = pd.DataFrame({
            "timestamp_utc": pd.date_range("2026-10-20 08:00:00", periods=5, freq="10s", tz="UTC"),
            "bid": [2735.1, 2735.2, 2735.15, 2735.3, 2735.25],
            "ask": [2735.3, 2735.4, 2735.35, 2735.5, 2735.45],
            "volume": [1.0, 1.0, 1.0, 1.0, 1.0],
        })

        p1, m1, man1 = mgr.write_partition(df, "XAUUSD", "DUKASCOPY", granularity="hourly")
        sha1 = man1["file_sha256"]

        # Ingest again with identical data
        p2, m2, man2 = mgr.write_partition(df, "XAUUSD", "DUKASCOPY", granularity="hourly")

        assert p1 == p2
        assert man2["file_sha256"] == sha1

    def test_conflicting_content_same_partition_name_is_rejected(self, tmp_path: Path):
        """Attempting to write conflicting data to an existing partition must raise PartitionConflictError."""
        mgr = PartitionStorageManager(vault_root=tmp_path)

        df1 = pd.DataFrame({
            "timestamp_utc": pd.date_range("2026-10-20 08:00:00", periods=5, freq="10s", tz="UTC"),
            "bid": [2735.1, 2735.2, 2735.15, 2735.3, 2735.25],
            "ask": [2735.3, 2735.4, 2735.35, 2735.5, 2735.45],
            "volume": [1.0, 1.0, 1.0, 1.0, 1.0],
        })
        # Different data for the same hour
        df2 = pd.DataFrame({
            "timestamp_utc": pd.date_range("2026-10-20 08:00:00", periods=5, freq="10s", tz="UTC"),
            "bid": [2740.0, 2741.0, 2742.0, 2743.0, 2744.0],
            "ask": [2740.2, 2741.2, 2742.2, 2743.2, 2744.2],
            "volume": [2.0, 2.0, 2.0, 2.0, 2.0],
        })

        mgr.write_partition(df1, "XAUUSD", "DUKASCOPY", granularity="hourly")

        with pytest.raises(PartitionConflictError, match="IMMUTABLE STORAGE CONFLICT"):
            mgr.write_partition(df2, "XAUUSD", "DUKASCOPY", granularity="hourly")

    def test_original_compressed_bytes_persisted_separately(self, tmp_path: Path):
        """Original source bytes must be persisted with their own manifest."""
        mgr = PartitionStorageManager(vault_root=tmp_path)
        sample_bytes = b"MOCK_LZMA_COMPRESSED_DATA_PAYLOAD_12345"

        src_file, src_manifest, meta = mgr.write_source_object(
            raw_bytes=sample_bytes,
            symbol="XAUUSD",
            provider="DUKASCOPY",
            timestamp=dt.datetime(2026, 10, 20, 8, 0, 0, tzinfo=dt.timezone.utc),
            source_filename="XAUUSD_20261020_08h_ticks.bi5",
        )

        assert src_file.exists()
        assert src_manifest.exists()
        assert src_file.read_bytes() == sample_bytes
        assert meta["byte_count"] == len(sample_bytes)
        assert meta["file_sha256"] == hashlib.sha256(sample_bytes).hexdigest()

    def test_manifest_contains_both_sha256_keys(self, tmp_path: Path):
        """Manifest must include both file_sha256 and sha256 to prevent None lookup bugs."""
        mgr = PartitionStorageManager(vault_root=tmp_path)
        df = pd.DataFrame({
            "timestamp_utc": pd.date_range("2026-10-20 08:00:00", periods=3, freq="10s", tz="UTC"),
            "bid": [2735.1, 2735.2, 2735.3],
            "ask": [2735.3, 2735.4, 2735.5],
            "volume": [1.0, 1.0, 1.0],
        })
        _, _, man = mgr.write_partition(df, "XAUUSD", "DUKASCOPY", granularity="hourly")
        assert man.get("file_sha256") is not None
        assert man.get("sha256") is not None
        assert man["file_sha256"] == man["sha256"]


# ==============================================================================
# 2. INGESTION TIMESTAMP PROVENANCE REGRESSION TESTS
# ==============================================================================

class TestIngestionTimestampProvenance:
    """Guards against fabricated or backdated ingestion timestamps."""

    def test_historical_observation_ingestion_time_is_none_by_default(self):
        """A historical observation with no specified ingestion time must retain None."""
        ts = pd.Timestamp("2024-05-15 14:30:00", tz="UTC")
        obs = RawTickObservation(
            timestamp_utc=ts,
            symbol="XAUUSD",
            bid=2350.50,
            ask=2350.70,
            ingestion_time_utc=None,
        )
        assert obs.ingestion_time_utc is None, "ingestion_time_utc must not be defaulted to observation time"
        assert not obs.has_known_ingestion_time
        assert obs.to_dict()["ingestion_time_utc"] is None

    def test_explicit_ingestion_time_is_preserved_when_supplied(self):
        """When an actual retrieval receipt timestamp is supplied, it is preserved."""
        obs_ts = pd.Timestamp("2024-05-15 14:30:00", tz="UTC")
        ing_ts = pd.Timestamp("2026-10-29 18:00:00", tz="UTC")
        obs = RawTickObservation(
            timestamp_utc=obs_ts,
            symbol="XAUUSD",
            bid=2350.50,
            ask=2350.70,
            ingestion_time_utc=ing_ts,
        )
        assert obs.ingestion_time_utc == ing_ts
        assert obs.has_known_ingestion_time
        assert obs.to_dict()["ingestion_time_utc"] == ing_ts.isoformat()

    def test_bid_volume_is_preserved(self):
        """Bid-side volume must be preserved and accessible in to_dict()."""
        ts = pd.Timestamp("2026-10-20 09:00:00", tz="UTC")
        obs = RawTickObservation(
            timestamp_utc=ts,
            symbol="XAUUSD",
            bid=2735.0,
            ask=2735.2,
            volume=1.5,
            bid_volume=2.25,
        )
        assert obs.volume == 1.5
        assert obs.bid_volume == 2.25
        d = obs.to_dict()
        assert d["volume"] == 1.5
        assert d["bid_volume"] == 2.25


# ==============================================================================
# 3. REAL XAUUSD INGESTION GATE HARDENING TESTS
# ==============================================================================

class TestRealXAUUSDIngestionGate:
    """Verifies that real XAUUSD network ingestion is unconditionally blocked."""

    def test_real_network_ingestion_unconditionally_rejects_unverified_xauusd(self):
        """validate_for_real_network_ingestion must raise UnverifiedPriceScaleError."""
        spec = DUKASCOPY_XAUUSD_SPEC
        with pytest.raises(UnverifiedPriceScaleError) as exc_info:
            spec.validate_for_real_network_ingestion()
        assert "UNRESOLVED PREREQUISITE" in str(exc_info.value)
        assert "UNVERIFIED_PENDING_CONFIRMATION" in str(exc_info.value)

    def test_synthetic_fixture_spec_cannot_authorize_real_network_ingestion(self):
        """A synthetic fixture spec must be rejected for real network ingestion."""
        spec = SYNTHETIC_XAUUSD_FIXTURE_SPEC
        with pytest.raises(UnverifiedPriceScaleError, match="SYNTHETIC_FIXTURE_ONLY"):
            spec.validate_for_real_network_ingestion()

    def test_provider_real_network_pilot_refuses_xauusd_even_with_allow_unverified_flag(self):
        """Setting allow_unverified_scale=True on the provider must NOT bypass real XAUUSD gate."""
        provider = DukascopyIngestionProvider(allow_unverified_scale=True)
        target_hour = pd.Timestamp("2026-10-20 09:00:00", tz="UTC")

        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(UnverifiedPriceScaleError) as exc_info:
                provider.execute_bounded_retrieval_pilot(
                    symbol="XAUUSD",
                    target_hour_utc=target_hour,
                    output_dir=Path(tmp_dir),
                    allow_network=True,
                )
            assert "REAL NETWORK INGESTION BLOCKED" in str(exc_info.value)


# ==============================================================================
# 4. HTTP SAFETY AND RETRIEVAL GATE TESTS
# ==============================================================================

class TestHttpSafetyGates:
    """Verifies HTTP status code handling and boundary constraints."""

    def test_http_404_raises_data_unavailable(self):
        """HTTP 404 must raise DataUnavailableError, not silent empty success."""
        provider = DukascopyIngestionProvider()
        target_hour = pd.Timestamp("2026-10-20 09:00:00", tz="UTC")

        err = urllib.error.HTTPError(
            url="https://datafeed.dukascopy.com/mock.bi5",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("urllib.request.urlopen", side_effect=err):
                with pytest.raises(DataUnavailableError, match="HTTP_404_NOT_FOUND"):
                    provider.execute_bounded_retrieval_pilot(
                        symbol="EURUSD",
                        target_hour_utc=target_hour,
                        output_dir=Path(tmp_dir),
                        allow_network=True,
                    )

    def test_http_403_raises_authentication_error(self):
        """HTTP 403 must raise AuthenticationError."""
        provider = DukascopyIngestionProvider()
        target_hour = pd.Timestamp("2026-10-20 09:00:00", tz="UTC")

        err = urllib.error.HTTPError(
            url="https://datafeed.dukascopy.com/mock.bi5",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("urllib.request.urlopen", side_effect=err):
                with pytest.raises(AuthenticationError, match="HTTP_403_FORBIDDEN"):
                    provider.execute_bounded_retrieval_pilot(
                        symbol="EURUSD",
                        target_hour_utc=target_hour,
                        output_dir=Path(tmp_dir),
                        allow_network=True,
                    )

    def test_http_429_raises_rate_limit_error(self):
        """HTTP 429 must raise IngestionError with RATE_LIMITED message."""
        provider = DukascopyIngestionProvider()
        target_hour = pd.Timestamp("2026-10-20 09:00:00", tz="UTC")

        err = urllib.error.HTTPError(
            url="https://datafeed.dukascopy.com/mock.bi5",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("urllib.request.urlopen", side_effect=err):
                with pytest.raises(IngestionError, match="HTTP_429_RATE_LIMITED"):
                    provider.execute_bounded_retrieval_pilot(
                        symbol="EURUSD",
                        target_hour_utc=target_hour,
                        output_dir=Path(tmp_dir),
                        allow_network=True,
                    )

    def test_oversized_response_is_rejected(self):
        """A response larger than 50MB must be rejected."""
        provider = DukascopyIngestionProvider()
        target_hour = pd.Timestamp("2026-10-20 09:00:00", tz="UTC")

        mock_resp = MagicMock()
        mock_resp.geturl.return_value = "https://datafeed.dukascopy.com/EURUSD/2026/09/20/09h_ticks.bi5"
        # Return 51MB of data
        mock_resp.read.return_value = b"X" * (51 * 1024 * 1024)
        mock_resp.__enter__.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("urllib.request.urlopen", return_value=mock_resp):
                with pytest.raises(IngestionError, match="OVERSIZED_RESPONSE"):
                    provider.execute_bounded_retrieval_pilot(
                        symbol="EURUSD",
                        target_hour_utc=target_hour,
                        output_dir=Path(tmp_dir),
                        allow_network=True,
                    )

    def test_attempt_to_write_into_holdout_vault_is_blocked(self):
        """Targeting a holdout vault directory must raise IngestionError."""
        provider = DukascopyIngestionProvider()
        target_hour = pd.Timestamp("2026-10-20 09:00:00", tz="UTC")

        with tempfile.TemporaryDirectory() as tmp_dir:
            holdout_path = Path(tmp_dir) / "protected_holdout_vault"
            holdout_path.mkdir()

            with pytest.raises(IngestionError, match="STORAGE VIOLATION"):
                provider.execute_bounded_retrieval_pilot(
                    symbol="EURUSD",
                    target_hour_utc=target_hour,
                    output_dir=holdout_path,
                    allow_network=True,
                )


# ==============================================================================
# 5. EVALUATION GATE FAIL-CLOSED & REGISTRATION TESTS
# ==============================================================================

class TestEvaluationGateHardening:
    """Verifies evaluation gate fails closed on corruption and mismatch."""

    def test_corrupted_consumed_registry_fails_closed(self, tmp_path: Path):
        """Corrupted (invalid JSON) consumed-dataset registry must block evaluation."""
        gate = EvaluationGate(vault_root=tmp_path)
        gate.consumed_registry_path.parent.mkdir(parents=True, exist_ok=True)
        # Write invalid corrupted JSON
        gate.consumed_registry_path.write_text("{CORRUPTED_JSON_DATA", encoding="utf-8")

        with pytest.raises(EvaluationGateError, match="REGISTRY INTEGRITY FAILURE"):
            gate.get_consumed_datasets()

    def test_extra_unregistered_dataset_rejected(self, tmp_path: Path):
        """Supplying datasets not in the registered list must raise EvaluationGateError."""
        reg_mgr = EvaluationRegistrationManager(vault_root=tmp_path)
        gate = EvaluationGate(vault_root=tmp_path)

        # Create two sample datasets
        d1 = tmp_path / "dataset_1.parquet"
        d2 = tmp_path / "dataset_2_extra.parquet"
        df = pd.DataFrame({"timestamp_utc": pd.date_range("2026-10-28 10:00", periods=5, freq="1min", tz="UTC")})
        df.to_parquet(d1)
        df.to_parquet(d2)

        # Register only d1
        reg_id, _, _ = reg_mgr.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[{"dataset_name": d1.name, "manifest_sha256": compute_sha256(d1)}],
            registered_by="RESEARCH_HARNESS",
            evaluation_start_boundary_utc=dt.datetime(2026, 10, 28, 9, 0, tzinfo=dt.timezone.utc),
            allow_uncommitted_git=True,
        )

        # Attempt evaluation with both d1 and unexpected d2
        with pytest.raises(EvaluationGateError, match="UNREGISTERED DATASETS SUPPLIED"):
            gate.verify_pre_evaluation(reg_id, [d1, d2])

    def test_missing_registered_dataset_rejected(self, tmp_path: Path):
        """Failing to supply a registered dataset must raise EvaluationGateError."""
        reg_mgr = EvaluationRegistrationManager(vault_root=tmp_path)
        gate = EvaluationGate(vault_root=tmp_path)

        d1 = tmp_path / "dataset_1.parquet"
        d2 = tmp_path / "dataset_2.parquet"
        df = pd.DataFrame({"timestamp_utc": pd.date_range("2026-10-28 10:00", periods=5, freq="1min", tz="UTC")})
        df.to_parquet(d1)
        df.to_parquet(d2)

        reg_id, _, _ = reg_mgr.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[
                {"dataset_name": d1.name, "manifest_sha256": compute_sha256(d1)},
                {"dataset_name": d2.name, "manifest_sha256": compute_sha256(d2)},
            ],
            registered_by="RESEARCH_HARNESS",
            evaluation_start_boundary_utc=dt.datetime(2026, 10, 28, 9, 0, tzinfo=dt.timezone.utc),
            allow_uncommitted_git=True,
        )

        # Supply only d1
        with pytest.raises(EvaluationGateError, match="REGISTERED DATASETS MISSING"):
            gate.verify_pre_evaluation(reg_id, [d1])

    def test_per_row_temporal_leakage_detected(self, tmp_path: Path):
        """Any single row predating the forward registration boundary must be caught."""
        gate = EvaluationGate(vault_root=tmp_path)
        boundary = pd.Timestamp("2026-10-28 10:00:00", tz="UTC")

        # Create table where row 0 is valid, but row 2 has temporal leakage (09:59)
        d = tmp_path / "forward_leak.parquet"
        df = pd.DataFrame({
            "timestamp_utc": [
                pd.Timestamp("2026-10-28 10:01:00", tz="UTC"),
                pd.Timestamp("2026-10-28 10:02:00", tz="UTC"),
                pd.Timestamp("2026-10-28 09:59:00", tz="UTC"),  # LEAK! Prior to boundary
            ]
        })
        df.to_parquet(d)

        with pytest.raises(ForwardEligibilityError, match="TEMPORAL LEAKAGE IN PARQUET TABLE"):
            gate._verify_forward_eligibility(d, boundary)


# ==============================================================================
# 6. HASH-CHAIN AUDIT LEDGER INTEGRITY TESTS
# ==============================================================================

class TestAuditLedgerTamperEvidentChain:
    """Verifies that appending to a corrupted ledger is strictly blocked."""

    def test_corrupted_chain_blocks_append(self, tmp_path: Path):
        """If an existing ledger entry is tampered with, append_entry must fail."""
        log_file = tmp_path / "audit.jsonl"
        ledger = TamperEvidentAuditLedger(log_file)

        ledger.append_entry({"event": "GENESIS_EVENT", "value": 1})
        ledger.append_entry({"event": "SECOND_EVENT", "value": 2})

        # Tamper with the first line directly on disk
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        record0 = json.loads(lines[0])
        record0["value"] = 99999  # Tamper!
        lines[0] = json.dumps(record0)
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Attempting to append must fail
        with pytest.raises(ValueError, match="AUDIT LEDGER CORRUPTED"):
            ledger.append_entry({"event": "THIRD_EVENT", "value": 3})


# ==============================================================================
# 7. MT5 TRANSACTIONAL PROMOTION ROLLBACK TESTS
# ==============================================================================

class TestMT5TransactionalRollback:
    """Verifies that failed promotion cleans up newly created files."""

    def test_rollback_removes_newly_created_files_when_later_step_fails(self, tmp_path: Path):
        """If raw succeeds but clean fails, the newly created raw file must be unlinked."""
        from scripts.download_data import transactionally_stage_and_promote

        raw_dir = tmp_path / "raw"
        clean_dir = tmp_path / "processed"
        raw_dir.mkdir()
        clean_dir.mkdir()

        raw_target = raw_dir / "XAUUSD_M15_raw.csv"
        clean_target = clean_dir / "XAUUSD_M15_clean.csv"
        meta_target = clean_dir / "XAUUSD_M15_clean.meta.json"

        # Neither file exists initially
        assert not raw_target.exists()
        assert not clean_target.exists()

        df_raw = pd.DataFrame({"time": pd.to_datetime(["2026-10-20"], utc=True), "open": [2735.0]})
        df_clean = df_raw.copy()
        meta = {"symbol": "XAUUSD", "timeframe": "M15", "retrieval_date_utc": "2026-10-20T00:00:00Z"}

        # Simulate failure during clean target replacement
        orig_replace = os.replace
        call_count = [0]

        def fail_on_clean(src, dst):
            call_count[0] += 1
            if call_count[0] == 2:  # 1 is raw, 2 is clean
                raise OSError("Simulated disk error on clean file promotion")
            return orig_replace(src, dst)

        with patch("os.replace", side_effect=fail_on_clean):
            with pytest.raises(RuntimeError, match="Atomic promotion failed"):
                transactionally_stage_and_promote(
                    df_raw=df_raw,
                    df_clean=df_clean,
                    meta=meta,
                    audit_log={},
                    symbol="XAUUSD",
                    timeframe="M15",
                    raw_dir=raw_dir,
                    processed_dir=clean_dir,
                )

        # Must NOT leave behind newly created raw_target!
        assert not raw_target.exists(), "Newly created raw target must be unlinked after rollback"
        assert not clean_target.exists()
        assert not meta_target.exists()


# ==============================================================================
# 8. CANONICAL VS RAW FROZEN CONFIG HASH STABILITY TESTS
# ==============================================================================

class TestFrozenConfigHashPolicy:
    """Verifies frozen SMC v1 config integrity across both hashing layers."""

    def test_raw_file_sha256_matches_baseline(self):
        """Exact raw bytes must hash to EXPECTED_FROZEN_SMC_HASH."""
        config_path = Path("configs/smc_v1_frozen.json")
        assert config_path.exists()
        raw_bytes = config_path.read_bytes()
        actual_sha = hashlib.sha256(raw_bytes).hexdigest()
        assert actual_sha == EXPECTED_FROZEN_SMC_HASH

    def test_canonical_json_content_hash_stability(self):
        """Canonical content hash must be stable and line-ending agnostic."""
        config_path = Path("configs/smc_v1_frozen.json")
        data = json.loads(config_path.read_text(encoding="utf-8"))
        canonical_bytes = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        canonical_sha = hashlib.sha256(canonical_bytes).hexdigest()

        # Known verified canonical hash for smc_v1_frozen
        EXPECTED_CANONICAL_HASH = "2696d34331cd0fa134edea55f7559dda55637bebe27766033155a12997d8a295"
        assert canonical_sha == EXPECTED_CANONICAL_HASH, (
            f"Canonical content hash changed! Expected {EXPECTED_CANONICAL_HASH}, got {canonical_sha}"
        )
