"""
Unit & Integration Tests for GoldFlow Phase 6A Vault Storage, Holdout Isolation & Evaluation Gate.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.ingestion.mock_provider import MockDataIngestionProvider
from src.data.ingestion.validator import validate_and_canonicalize_ticks
from src.vault.evaluation_gate import EvaluationGate, EvaluationGateError
from src.vault.holdout import (
    HoldoutVaultManager,
    is_readonly,
    remove_readonly_attribute,
    set_readonly_attribute,
)
from src.vault.raw_storage import (
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


class TestPartitionStorageManager:
    """Test Parquet partition management, manifests, and checkpoints."""

    def test_partition_write_and_verification(self, tmp_path: Path) -> None:
        manager = PartitionStorageManager(vault_root=tmp_path)

        provider = MockDataIngestionProvider(seed=42)
        start = dt.datetime(2026, 10, 28, 10, 0, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 10, 28, 10, 2, 0, tzinfo=dt.timezone.utc)
        raw_ticks, _ = provider.fetch_historical_ticks("XAUUSD", start, end)
        cleaned_df, _ = validate_and_canonicalize_ticks(raw_ticks)

        # Write partition
        parquet_path, manifest_path, manifest = manager.write_partition(
            df=cleaned_df,
            symbol="XAUUSD",
            provider="MOCK_ECN",
            granularity="monthly",
        )

        assert parquet_path.exists()
        assert manifest_path.exists()
        assert manifest["row_count"] == len(cleaned_df)
        assert manifest["symbol"] == "XAUUSD"
        assert manifest["provider"] == "MOCK_ECN"

        # Verify integrity
        is_valid, diagnostics = manager.verify_partition(parquet_path)
        assert is_valid
        assert diagnostics["status"] == "VALID"
        assert diagnostics["row_count"] == len(cleaned_df)

        # Check append-only ingestion ledger
        assert manager.history_log_path.exists()
        with open(manager.history_log_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f]
        assert len(lines) == 1
        assert lines[0]["event"] == "PARTITION_COMMITTED"
        assert lines[0]["partition_sha256"] == manifest["file_sha256"]

        # Check checkpoint
        checkpoint = manager.get_checkpoint("XAUUSD")
        assert checkpoint is not None
        assert checkpoint["symbol"] == "XAUUSD"
        assert checkpoint["last_partition_file"] == parquet_path.name

        # Read back DataFrame
        read_df = manager.read_partition(parquet_path)
        assert len(read_df) == len(cleaned_df)
        assert "timestamp_utc" in read_df.columns

    def test_tamper_detection(self, tmp_path: Path) -> None:
        manager = PartitionStorageManager(vault_root=tmp_path)
        provider = MockDataIngestionProvider(seed=42)
        start = dt.datetime(2026, 10, 28, 10, 0, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 10, 28, 10, 1, 0, tzinfo=dt.timezone.utc)
        raw_ticks, _ = provider.fetch_historical_ticks("XAUUSD", start, end)
        cleaned_df, _ = validate_and_canonicalize_ticks(raw_ticks)

        parquet_path, manifest_path, _ = manager.write_partition(
            df=cleaned_df,
            symbol="XAUUSD",
            provider="MOCK_ECN",
        )

        # Tamper with the parquet file by appending bytes
        with open(parquet_path, "ab") as f:
            f.write(b"CORRUPTION_BYTES")

        is_valid, diag = manager.verify_partition(parquet_path)
        assert not is_valid
        assert "SHA-256 hash mismatch" in diag["error"]


class TestHoldoutVaultManager:
    """Test physical vault segregation, read-only locking, and access logging."""

    def test_dataset_sealing_and_readonly(self, tmp_path: Path) -> None:
        vault_root = tmp_path / "test_vault"
        manager = HoldoutVaultManager(vault_root=vault_root)

        # Create dummy source data
        source_file = tmp_path / "forward_sample.csv"
        source_file.write_text("timestamp,symbol,bid,ask\n2026-10-28T12:00:00Z,XAUUSD,2650.0,2650.3\n", encoding="utf-8")

        # Seal in holdout
        sealed_path, manifest_path, manifest = manager.seal_dataset(
            source_path=source_file,
            symbol="XAUUSD",
            dataset_name="XAUUSD_MOCK_202610.csv",
            caller="RESEARCHER_TEST",
            reason="BENCHMARK_SEALING",
        )

        assert sealed_path.exists()
        assert manifest_path.exists()
        assert is_readonly(sealed_path)
        assert is_readonly(manifest_path)

        # Verify holdout integrity
        is_valid, diag = manager.verify_holdout_integrity(sealed_path)
        assert is_valid
        assert diag["status"] == "VERIFIED"

        # Check access audit log
        assert manager.access_log_path.exists()
        with open(manager.access_log_path, "r", encoding="utf-8") as f:
            logs = [json.loads(line) for line in f]
        assert len(logs) == 1
        assert logs[0]["event_type"] == "DATASET_SEALED"
        assert logs[0]["caller"] == "RESEARCHER_TEST"

        # Cleanup: remove readonly before teardown
        remove_readonly_attribute(sealed_path)
        remove_readonly_attribute(manifest_path)


class TestEvaluationRegistrationAndGate:
    """Test evaluation pre-registration, protocol locking, and single-pass gating."""

    def test_registration_and_single_pass_gate(self, tmp_path: Path) -> None:
        vault_root = tmp_path / "vault"
        config_root = tmp_path / "configs"

        gate = EvaluationGate(vault_root=vault_root, config_root=config_root)

        # Create dummy sealed dataset
        dummy_data = tmp_path / "eval_data.parquet"
        dummy_df = pd.DataFrame({
            "timestamp_utc": [pd.Timestamp("2026-10-28 15:00:00", tz="UTC")],
            "open": [2650.0],
            "high": [2652.0],
            "low": [2649.0],
            "close": [2651.0],
            "tick_volume": [50],
        })
        dummy_df.to_parquet(dummy_data)
        dataset_sha = compute_sha256(dummy_data)

        # Manifest
        manifest_path = Path(str(dummy_data) + ".manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({
                "dataset_name": dummy_data.name,
                "file_sha256": dataset_sha,
                "start_time_utc": "2026-10-28T15:00:00Z",
                "end_time_utc": "2026-10-28T15:01:00Z",
            }, f)

        # Pre-register evaluation with boundary at 14:00 UTC
        boundary_time = dt.datetime(2026, 10, 28, 14, 0, 0, tzinfo=dt.timezone.utc)
        reg_id, reg_path, reg_data = gate.reg_manager.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[{"dataset_name": dummy_data.name, "manifest_sha256": dataset_sha}],
            registered_by="AUDITOR_TEST",
            evaluation_start_boundary_utc=boundary_time,
            notes="Phase 6A Gate Test",
        )

        assert reg_id.startswith("REG_FORWARD_TEMPORAL_")
        assert reg_data["status"] == "REGISTERED"
        assert reg_data["frozen_config_sha256"] == EXPECTED_FROZEN_SMC_HASH

        # Mock evaluation function
        def mock_evaluator(paths: list[Path]) -> dict:
            return {"net_pnl": 125.50, "total_trades": 4, "win_rate": 0.75}

        # First evaluation pass: must succeed
        receipt = gate.execute_evaluation(
            registration_id=reg_id,
            dataset_paths=[dummy_data],
            evaluator_fn=mock_evaluator,
            caller="TEST_HARNESS",
        )

        assert receipt["status"] == "EVALUATED_CONSUMED"
        assert receipt["evaluation_metrics"]["net_pnl"] == 125.50

        # Registration must now be consumed
        updated_reg = gate.reg_manager.load_registration(reg_id)
        assert updated_reg["status"] == "EVALUATED_CONSUMED"

        # Second evaluation pass: MUST FAIL to prevent data snooping / multiple testing
        with pytest.raises(EvaluationGateError, match="MULTIPLE TESTING REJECTED"):
            gate.execute_evaluation(
                registration_id=reg_id,
                dataset_paths=[dummy_data],
                evaluator_fn=mock_evaluator,
            )

        # Cleanup readonly files
        remove_readonly_attribute(reg_path)
        remove_readonly_attribute(gate.evaluations_dir / f"{reg_id}.json")
        remove_readonly_attribute(gate.evaluations_dir / f"RECEIPT_{reg_id}.json")

    def test_temporal_boundary_violation_detection(self, tmp_path: Path) -> None:
        vault_root = tmp_path / "vault"
        config_root = tmp_path / "configs"
        gate = EvaluationGate(vault_root=vault_root, config_root=config_root)

        # Create dataset with data from 10:00 UTC
        leaked_data = tmp_path / "leaked_data.parquet"
        leaked_df = pd.DataFrame({
            "timestamp_utc": [pd.Timestamp("2026-10-28 10:00:00", tz="UTC")],
            "open": [2650.0],
        })
        leaked_df.to_parquet(leaked_data)
        manifest_path = Path(str(leaked_data) + ".manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({
                "start_time_utc": "2026-10-28T10:00:00Z",
                "file_sha256": compute_sha256(leaked_data),
            }, f)

        # Register forward evaluation starting at 12:00 UTC (later than dataset)
        reg_id, reg_path, _ = gate.reg_manager.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[{"dataset_name": leaked_data.name, "manifest_sha256": compute_sha256(leaked_data)}],
            registered_by="AUDITOR_TEST",
            evaluation_start_boundary_utc=dt.datetime(2026, 10, 28, 12, 0, 0, tzinfo=dt.timezone.utc),
        )

        # Evaluation must fail due to look-ahead / temporal boundary violation
        with pytest.raises(EvaluationGateError, match="LOOK-AHEAD / HISTORICAL BACKFILL REJECTED"):
            gate.verify_pre_evaluation(reg_id, [leaked_data])

        # Cleanup
        remove_readonly_attribute(reg_path)
        remove_readonly_attribute(gate.evaluations_dir / f"{reg_id}.json")

