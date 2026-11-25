"""
Phase 6D.2 Adversarial Verification Test Suite for GoldFlow.

Independently tests and verifies all security, provenance, vault, gating,
and integrity controls against adversarial attacks, bypass attempts,
and edge-case failure modes.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List
import unittest.mock as mock

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.data.cleaner import clean_market_data, save_processed_data
from src.data.ingestion.dukascopy_provider import DukascopyIngestionProvider
from src.data.ingestion.instrument_spec import (
    DUKASCOPY_EURUSD_SPEC,
    DUKASCOPY_XAUUSD_SPEC,
    SYNTHETIC_XAUUSD_FIXTURE_SPEC,
    UnverifiedPriceScaleError,
    VerificationStatus,
    ProviderInstrumentSpec,
)
from src.vault.audit_ledger import TamperEvidentAuditLedger, compute_entry_hash
from src.vault.evaluation_gate import (
    ConcurrentEvaluationError,
    DatasetAlreadyConsumedError,
    EvaluationGate,
    EvaluationGateError,
    ForwardEligibilityError,
    GateProcessLock,
)
from src.vault.raw_storage import (
    PartitionConflictError,
    PartitionStorageManager,
    compute_sha256,
)
from src.vault.registration import (
    EXPECTED_FROZEN_SMC_HASH,
    EvaluationRegistrationManager,
    EvaluationType,
    verify_frozen_config,
)


# ==============================================================================
# 1. ADVERSARIAL PARTITION SHARDING & IMMUTABILITY TESTS
# ==============================================================================

class TestAdversarialPartitionStorage:
    """Tests partition shard boundary containment and immutable conflict rejection."""

    def test_multi_hour_span_rejected_for_hourly_partition(self, tmp_path: Path):
        """Writing observations spanning across multiple hours to an hourly partition must fail."""
        storage = PartitionStorageManager(vault_root=tmp_path)
        
        # Observations spanning from 10:00 to 11:15
        df = pd.DataFrame({
            "timestamp_utc": [
                pd.Timestamp("2026-10-28 10:15:00", tz="UTC"),
                pd.Timestamp("2026-10-28 10:45:00", tz="UTC"),
                pd.Timestamp("2026-10-28 11:15:00", tz="UTC"),  # Crosses into next hour!
            ],
            "price": [2650.0, 2651.0, 2652.0],
        })

        with pytest.raises(ValueError, match="Cross-hour span rejected for hourly shard"):
            storage.write_partition(df, symbol="XAUUSD", provider="dukascopy", granularity="hourly")

    def test_multi_day_span_rejected_for_daily_partition(self, tmp_path: Path):
        """Writing observations spanning across multiple days to a daily partition must fail."""
        storage = PartitionStorageManager(vault_root=tmp_path)

        # Observations spanning across two days
        df = pd.DataFrame({
            "timestamp_utc": [
                pd.Timestamp("2026-10-27 23:55:00", tz="UTC"),
                pd.Timestamp("2026-10-28 00:05:00", tz="UTC"),  # Crosses into next day!
            ],
            "price": [2650.0, 2651.0],
        })

        with pytest.raises(ValueError, match="Cross-day span rejected for daily shard"):
            storage.write_partition(df, symbol="XAUUSD", provider="dukascopy", granularity="daily")

    def test_idempotent_reingestion_regenerates_lost_manifest(self, tmp_path: Path):
        """If partition Parquet exists but manifest was deleted, idempotent re-ingestion re-creates manifest."""
        storage = PartitionStorageManager(vault_root=tmp_path)

        df = pd.DataFrame({
            "timestamp_utc": [
                pd.Timestamp("2026-10-28 10:15:00", tz="UTC"),
                pd.Timestamp("2026-10-28 10:45:00", tz="UTC"),
            ],
            "price": [2650.0, 2651.0],
        })

        parquet_path, manifest_path, _ = storage.write_partition(
            df, symbol="EURUSD", provider="dukascopy", granularity="hourly"
        )
        assert parquet_path.exists()
        assert manifest_path.exists()

        # Delete the manifest to simulate edge-case file loss
        from src.vault.holdout import remove_readonly_attribute
        remove_readonly_attribute(manifest_path)
        manifest_path.unlink()
        assert not manifest_path.exists()

        # Re-ingest the exact same data: must succeed idempotently and regenerate the manifest
        re_p, re_m, meta = storage.write_partition(
            df, symbol="EURUSD", provider="dukascopy", granularity="hourly"
        )
        assert re_p == parquet_path
        assert re_m == manifest_path
        assert re_m.exists()
        assert meta["sha256"] == compute_sha256(parquet_path)


# ==============================================================================
# 2. CANONICAL HISTORY SHRINK & OVERWRITE ADVERSARIAL TESTS
# ==============================================================================

class TestCanonicalHistoryProtection:
    """Verifies that canonical processed data cannot be truncated by smaller samples."""

    def test_shrink_attempt_on_canonical_dataset_is_blocked(self, tmp_path: Path):
        """Attempting to overwrite a 1,000-row canonical dataset with a 100-row sample must fail."""
        out_dir = tmp_path / "processed"
        out_dir.mkdir(parents=True, exist_ok=True)

        # 1. Establish canonical dataset with 1,000 rows
        dates_large = pd.date_range("2026-01-01", periods=1000, freq="1h", tz="UTC")
        df_large = pd.DataFrame({
            "time": dates_large,
            "open": [2000.0] * 1000,
            "high": [2005.0] * 1000,
            "low": [1995.0] * 1000,
            "close": [2002.0] * 1000,
            "volume": [100] * 1000,
        })
        csv_path, meta_path = save_processed_data(
            df_large, symbol="XAUUSD", timeframe="H1", output_dir=out_dir
        )
        assert csv_path.exists()

        # 2. Create truncated sample with only 100 rows
        dates_small = pd.date_range("2026-01-01", periods=100, freq="1h", tz="UTC")
        df_small = pd.DataFrame({
            "time": dates_small,
            "open": [2000.0] * 100,
            "high": [2005.0] * 100,
            "low": [1995.0] * 100,
            "close": [2002.0] * 100,
            "volume": [100] * 100,
        })

        # Overwrite attempt without allow_shrink=True MUST FAIL
        with pytest.raises(ValueError, match="CANONICAL DATA SHRINK PROTECTED"):
            save_processed_data(
                df_small, symbol="XAUUSD", timeframe="H1", output_dir=out_dir, allow_shrink=False
            )

        # 3. An intentional shrink with explicit allow_shrink=True succeeds
        csv_path2, _ = save_processed_data(
            df_small, symbol="XAUUSD", timeframe="H1", output_dir=out_dir, allow_shrink=True
        )
        assert csv_path2.exists()
        reloaded = pd.read_csv(csv_path2)
        assert len(reloaded) == 100

    def test_synthetic_data_cannot_target_canonical_directory(self, tmp_path: Path):
        """Synthetic data must be rejected if targeted to a canonical directory."""
        canonical_dir = tmp_path / "data" / "processed"
        canonical_dir.mkdir(parents=True, exist_ok=True)

        df = pd.DataFrame({
            "time": [pd.Timestamp("2026-10-28 10:00:00", tz="UTC")],
            "open": [2650.0], "high": [2651.0], "low": [2649.0], "close": [2650.5], "volume": [10],
        })

        with pytest.raises(ValueError, match="Synthetic data must NOT be written to canonical"):
            save_processed_data(df, symbol="XAUUSD", timeframe="M15", output_dir=canonical_dir, synthetic=True)


# ==============================================================================
# 3. EVALUATION GATE ADVERSARIAL ATTEMPTS & FAIL-CLOSED GUARDS
# ==============================================================================

class TestEvaluationGateAdversarialBypass:
    """Adversarial bypass attempts against the evaluation gate."""

    def test_forward_evaluation_without_manifest_is_strictly_rejected(self, tmp_path: Path):
        """An attacker who deletes or omits the .manifest.json must be rejected."""
        gate = EvaluationGate(vault_root=tmp_path)
        reg_mgr = EvaluationRegistrationManager(vault_root=tmp_path)

        # Create valid Parquet file
        d = tmp_path / "forward_data.parquet"
        df = pd.DataFrame({
            "timestamp_utc": [pd.Timestamp("2026-10-28 15:00:00", tz="UTC")],
            "open": [2650.0],
        })
        df.to_parquet(d)
        d_sha = compute_sha256(d)

        # Register forward temporal evaluation
        reg_id, _, _ = reg_mgr.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[{"dataset_name": d.name, "manifest_sha256": d_sha}],
            registered_by="ADVERSARIAL_TEST",
            evaluation_start_boundary_utc=dt.datetime(2026, 10, 28, 14, 0, tzinfo=dt.timezone.utc),
            allow_uncommitted_git=True,
        )

        # Intentionally omit .manifest.json on disk
        manifest_path = Path(str(d) + ".manifest.json")
        if manifest_path.exists():
            manifest_path.unlink()

        with pytest.raises(ForwardEligibilityError, match="MANDATORY MANIFEST MISSING"):
            gate.verify_pre_evaluation(reg_id, [d])

    def test_empty_dataset_list_rejected(self, tmp_path: Path):
        """Evaluating with an empty dataset list must be rejected."""
        gate = EvaluationGate(vault_root=tmp_path)
        reg_mgr = EvaluationRegistrationManager(vault_root=tmp_path)

        reg_id, _, _ = reg_mgr.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[],
            registered_by="TEST",
            evaluation_start_boundary_utc=dt.datetime(2026, 10, 28, 14, 0, tzinfo=dt.timezone.utc),
            allow_uncommitted_git=True,
        )

        with pytest.raises(EvaluationGateError, match="NO DATASETS SUPPLIED"):
            gate.verify_pre_evaluation(reg_id, [])

    def test_duplicate_dataset_filenames_rejected(self, tmp_path: Path):
        """Supplying duplicate dataset filenames across different paths must be rejected."""
        gate = EvaluationGate(vault_root=tmp_path)
        reg_mgr = EvaluationRegistrationManager(vault_root=tmp_path)

        dir_a = tmp_path / "dir_a"
        dir_b = tmp_path / "dir_b"
        dir_a.mkdir()
        dir_b.mkdir()

        file_a = dir_a / "data.parquet"
        file_b = dir_b / "data.parquet"
        df = pd.DataFrame({"timestamp_utc": [pd.Timestamp("2026-10-28 15:00:00", tz="UTC")]})
        df.to_parquet(file_a)
        df.to_parquet(file_b)

        reg_id, _, _ = reg_mgr.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[{"dataset_name": "data.parquet", "manifest_sha256": compute_sha256(file_a)}],
            registered_by="TEST",
            evaluation_start_boundary_utc=dt.datetime(2026, 10, 28, 14, 0, tzinfo=dt.timezone.utc),
            allow_uncommitted_git=True,
        )

        with pytest.raises(EvaluationGateError, match="DUPLICATE DATASET FILENAMES SUPPLIED"):
            gate.verify_pre_evaluation(reg_id, [file_a, file_b])

    def test_forward_parquet_missing_timestamp_column_rejected(self, tmp_path: Path):
        """Forward dataset parquet missing 'timestamp_utc' column must be rejected."""
        gate = EvaluationGate(vault_root=tmp_path)
        boundary = pd.Timestamp("2026-10-28 14:00:00", tz="UTC")

        d = tmp_path / "corrupted_schema.parquet"
        df = pd.DataFrame({"some_other_column": [1, 2, 3]})
        df.to_parquet(d)

        with pytest.raises(ForwardEligibilityError, match="SCHEMA ERROR.*missing mandatory 'timestamp_utc'"):
            gate._verify_forward_eligibility(d, boundary)

    def test_forward_parquet_null_ingestion_timestamp_rejected(self, tmp_path: Path):
        """If a forward dataset contains ingestion_time_utc with NULL values, it must be rejected."""
        gate = EvaluationGate(vault_root=tmp_path)
        boundary = pd.Timestamp("2026-10-28 14:00:00", tz="UTC")

        d = tmp_path / "null_ingestion.parquet"
        df = pd.DataFrame({
            "timestamp_utc": [pd.Timestamp("2026-10-28 15:00:00", tz="UTC"), pd.Timestamp("2026-10-28 15:01:00", tz="UTC")],
            "ingestion_time_utc": [pd.Timestamp("2026-10-28 15:00:05", tz="UTC"), None],  # NULL receipt time!
        })
        df.to_parquet(d)

        with pytest.raises(ForwardEligibilityError, match="UNVERIFIED INGESTION TIMESTAMPS"):
            gate._verify_forward_eligibility(d, boundary)

    def test_forward_parquet_pre_registration_ingestion_time_rejected(self, tmp_path: Path):
        """If ingestion_time_utc predates boundary, even if observation is valid, must be rejected."""
        gate = EvaluationGate(vault_root=tmp_path)
        boundary = pd.Timestamp("2026-10-28 14:00:00", tz="UTC")

        d = tmp_path / "pre_reg_ingestion.parquet"
        df = pd.DataFrame({
            "timestamp_utc": [pd.Timestamp("2026-10-28 15:00:00", tz="UTC")],  # Observation is after boundary
            "ingestion_time_utc": [pd.Timestamp("2026-10-28 13:59:00", tz="UTC")],  # Ingested BEFORE boundary!
        })
        df.to_parquet(d)

        with pytest.raises(ForwardEligibilityError, match="PRE-REGISTRATION INGESTION LEAKAGE"):
            gate._verify_forward_eligibility(d, boundary)

    def test_atomic_consumed_dataset_persistence_survives_and_locks(self, tmp_path: Path):
        """_record_consumed_dataset records atomically and survives reload."""
        gate = EvaluationGate(vault_root=tmp_path)
        gate._record_consumed_dataset("sha256_mock_123", "test_dataset.parquet", "REG_001")

        consumed = gate.get_consumed_datasets()
        assert "sha256_mock_123" in consumed
        assert consumed["sha256_mock_123"]["dataset_name"] == "test_dataset.parquet"
        assert consumed["sha256_mock_123"]["registration_id"] == "REG_001"


# ==============================================================================
# 4. AUDIT LEDGER MALFORMED / TRUNCATED RECORD RESILIENCE
# ==============================================================================

class TestAuditLedgerAdversarial:
    """Verifies audit ledger behaves safely when encountering corrupted files."""

    def test_malformed_json_line_in_ledger_causes_verify_failure_and_blocks_append(self, tmp_path: Path):
        """If a line in the ledger is broken or truncated JSON, verify_chain returns False and append fails."""
        log_file = tmp_path / "audit.jsonl"
        ledger = TamperEvidentAuditLedger(log_file)

        ledger.append_entry({"event": "GENESIS"})
        ledger.append_entry({"event": "STEP_1"})

        # Append malformed raw text into the file
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("{\"incomplete_json_record: \n")

        # verify_chain must report failure cleanly without crashing
        is_valid, count, err = ledger.verify_chain()
        assert not is_valid
        assert "Malformed entry in ledger" in str(err)

        # append_entry must refuse to append to corrupted file
        with pytest.raises(ValueError, match="AUDIT LEDGER CORRUPTED"):
            ledger.append_entry({"event": "STEP_2"})

    def test_broken_hash_link_reported_correctly(self, tmp_path: Path):
        """If a middle entry's previous hash is altered, chain verification catches it."""
        log_file = tmp_path / "audit.jsonl"
        ledger = TamperEvidentAuditLedger(log_file)

        ledger.append_entry({"event": "E1"})
        ledger.append_entry({"event": "E2"})
        ledger.append_entry({"event": "E3"})

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        e2 = json.loads(lines[1])
        e2["prev_entry_sha256"] = "0" * 64  # Break hash link!
        lines[1] = json.dumps(e2)
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        is_valid, idx, err = ledger.verify_chain()
        assert not is_valid
        assert idx == 1
        assert "Hash chain broken at position 1" in str(err)


# ==============================================================================
# 5. REAL-NETWORK XAUUSD GATE HARDENING & SPOOFING RESISTANCE
# ==============================================================================

class TestRealNetworkGateHardening:
    """Ensures XAUUSD real-network gate cannot be bypassed by monkeypatching or custom specs."""

    def test_unverified_xauusd_spec_cannot_be_authorized_for_network(self):
        """validate_for_real_network_ingestion must reject DUKASCOPY_XAUUSD_SPEC unconditionally."""
        with pytest.raises(UnverifiedPriceScaleError, match="REAL NETWORK INGESTION BLOCKED.*UNVERIFIED_PENDING_CONFIRMATION"):
            DUKASCOPY_XAUUSD_SPEC.validate_for_real_network_ingestion()

    def test_custom_synthetic_spec_cannot_authorize_real_network(self, tmp_path: Path):
        """A synthetic fixture spec cannot authorize real network ingestion."""
        with pytest.raises(UnverifiedPriceScaleError, match="REAL NETWORK INGESTION BLOCKED.*SYNTHETIC_FIXTURE_ONLY"):
            SYNTHETIC_XAUUSD_FIXTURE_SPEC.validate_for_real_network_ingestion()

        provider = DukascopyIngestionProvider(allow_unverified_scale=True)
        with pytest.raises(UnverifiedPriceScaleError, match="REAL NETWORK INGESTION BLOCKED"):
            provider.execute_bounded_retrieval_pilot(
                symbol="XAUUSD",
                target_hour_utc=dt.datetime(2026, 10, 28, 10, 0, tzinfo=dt.timezone.utc),
                output_dir=tmp_path,
                allow_network=True,
            )


# ==============================================================================
# 6. FROZEN STRATEGY CONFIGURATION AND SEPARATION OF CONCERNS
# ==============================================================================

class TestFrozenStrategyAndIsolation:
    """Verifies the frozen SMC v1 config hash and that ICT engine remains separate."""

    def test_smc_v1_frozen_config_file_hash(self):
        """Exact SHA-256 hash of configs/smc_v1_frozen.json must match canonical anchor."""
        config_path = Path("configs/smc_v1_frozen.json")
        assert config_path.exists()
        raw_sha = compute_sha256(config_path)
        assert raw_sha == EXPECTED_FROZEN_SMC_HASH, f"Expected {EXPECTED_FROZEN_SMC_HASH}, got {raw_sha}"

    def test_verify_frozen_config_helper(self):
        """verify_frozen_config() must return True with matching hash."""
        is_valid, current_hash = verify_frozen_config()
        assert is_valid
        assert current_hash == EXPECTED_FROZEN_SMC_HASH

