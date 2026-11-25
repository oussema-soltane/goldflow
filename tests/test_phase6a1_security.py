"""
Unit & Integration Tests for GoldFlow Phase 6A.1:
Security Hardening, Holdout Protection, State Machine, and Audit Integrity.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from src.data.ingestion.bar_builder import synthesize_m1_bars
from src.data.ingestion.models import RawTickObservation
from src.data.ingestion.validator import (
    DEFAULT_FX_LIMITS,
    DEFAULT_GOLD_LIMITS,
    InstrumentPriceLimits,
    TickDataValidator,
    validate_and_canonicalize_ticks,
)
from src.vault.audit_ledger import TamperEvidentAuditLedger
from src.vault.evaluation_gate import (
    ConcurrentEvaluationError,
    DatasetAlreadyConsumedError,
    EvaluationGate,
    EvaluationGateError,
    ForwardEligibilityError,
    GateProcessLock,
)
from src.vault.holdout import (
    HoldoutVaultManager,
    check_ntfs_acl_protection,
    remove_readonly_attribute,
    set_readonly_attribute,
)
from src.vault.raw_storage import compute_sha256
from src.vault.registration import (
    EvaluationRegistrationManager,
    EvaluationStatus,
    EvaluationType,
)


class TestNTFSAccessControlAndAuditLedger:
    """Tests for NTFS ACL inspection and cryptographic hash-chained audit ledgers."""

    def test_ntfs_acl_inspection(self, tmp_path: Path) -> None:
        diag = check_ntfs_acl_protection(tmp_path)
        assert diag["target_path"] == str(tmp_path.resolve())
        assert "residual_risk_disclosure" in diag
        assert diag["security_boundary_status"] in ("ADVISORY_APPLICATION_CONTROL", "POSIX_FILE_PERMISSIONS")

    def test_tamper_evident_audit_ledger_chain_and_detection(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test_audit.jsonl"
        ledger = TamperEvidentAuditLedger(log_file)

        # Append valid entries
        e1 = ledger.append_entry({"event": "INITIALIZE", "user": "alice"})
        e2 = ledger.append_entry({"event": "DATASET_SEALED", "user": "bob"})
        e3 = ledger.append_entry({"event": "EVALUATION_COMPLETED", "user": "charlie"})

        assert e1["entry_index"] == 0
        assert e2["entry_index"] == 1
        assert e3["entry_index"] == 2
        assert e2["prev_entry_sha256"] == e1["entry_sha256"]
        assert e3["prev_entry_sha256"] == e2["entry_sha256"]

        # Verify intact chain
        is_valid, count, err = ledger.verify_chain()
        assert is_valid
        assert count == 3
        assert err is None

        # Tamper test 1: Modify a field in the second record
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        tampered_rec = json.loads(lines[1])
        tampered_rec["user"] = "mallory"
        lines[1] = json.dumps(tampered_rec) + "\n"

        with open(log_file, "w", encoding="utf-8") as f:
            f.writelines(lines)

        is_valid, bad_idx, err = ledger.verify_chain()
        assert not is_valid
        assert bad_idx == 1
        assert "Tamper detected" in err

        # Tamper test 2: Delete a line
        lines.pop(1)
        with open(log_file, "w", encoding="utf-8") as f:
            f.writelines(lines)

        is_valid, bad_idx, err = ledger.verify_chain()
        assert not is_valid
        assert bad_idx == 1
        assert "broken at position 1" in err


class TestEvaluationGateConcurrencyAndLifecycle:
    """Tests for inter-process locking, lifecycle states, and crash recovery."""

    def test_gate_process_lock_concurrency(self, tmp_path: Path) -> None:
        lock_file = tmp_path / "gate.lock"
        lock1 = GateProcessLock(lock_file, "REG_TEST_001")
        lock2 = GateProcessLock(lock_file, "REG_TEST_002")

        # Acquire lock1
        lock1.acquire()
        assert lock_file.exists()

        # Concurrent attempt with lock2 must raise ConcurrentEvaluationError
        with pytest.raises(ConcurrentEvaluationError, match="CONCURRENT EVALUATION BLOCKED"):
            lock2.acquire()

        # Release lock1
        lock1.release()
        assert not lock_file.exists()

        # Now lock2 can acquire cleanly
        lock2.acquire()
        assert lock_file.exists()
        lock2.release()

    def test_gate_stale_lock_recovery_from_dead_pid(self, tmp_path: Path) -> None:
        lock_file = tmp_path / "gate.lock"
        # Write a simulated stale lock with an impossible/dead PID
        with open(lock_file, "w", encoding="utf-8") as f:
            json.dump({"pid": 99999999, "registration_id": "REG_DEAD", "acquired_at_utc": "2026-01-01T00:00:00Z"}, f)

        lock = GateProcessLock(lock_file, "REG_NEW")
        # Acquiring must detect dead PID and successfully reclaim the lock
        lock.acquire()
        assert lock_file.exists()
        with open(lock_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["registration_id"] == "REG_NEW"
        lock.release()

    def test_evaluation_lifecycle_and_failure_transition(self, tmp_path: Path) -> None:
        vault_root = tmp_path / "vault"
        config_root = tmp_path / "configs"
        gate = EvaluationGate(vault_root=vault_root, config_root=config_root)

        # Create dummy dataset
        dataset_file = tmp_path / "sample.parquet"
        pd.DataFrame({"timestamp_utc": [pd.Timestamp("2026-11-01 12:00:00", tz="UTC")], "open": [2650.0]}).to_parquet(dataset_file)
        dataset_sha = compute_sha256(dataset_file)

        manifest_file = Path(str(dataset_file) + ".manifest.json")
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({
                "file_sha256": dataset_sha,
                "start_time_utc": "2026-11-01T12:00:00Z",
                "ingestion_receipt_utc": "2026-11-01T12:05:00Z",
            }, f)

        # Register forward evaluation
        reg_id, reg_path, _ = gate.reg_manager.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[{"dataset_name": dataset_file.name, "manifest_sha256": dataset_sha}],
            registered_by="TESTER",
            evaluation_start_boundary_utc=dt.datetime(2026, 11, 1, 0, 0, tzinfo=dt.timezone.utc),
        )

        # Failing evaluator function
        def faulty_evaluator(paths):
            raise RuntimeError("Engine calculation simulated panic.")

        # Execution must fail and transition registration to FAILED
        with pytest.raises(EvaluationGateError, match="Engine calculation simulated panic"):
            gate.execute_evaluation(reg_id, [dataset_file], faulty_evaluator)

        reg_data = gate.reg_manager.load_registration(reg_id)
        assert reg_data["status"] == EvaluationStatus.FAILED.value
        assert "RuntimeError" in reg_data["error_type"]
        assert "Engine calculation simulated panic" in reg_data["error_message"]

        # Cleanup readonly files
        remove_readonly_attribute(reg_path)
        remove_readonly_attribute(gate.evaluations_dir / f"{reg_id}.json")

    def test_interrupted_run_crash_recovery(self, tmp_path: Path) -> None:
        vault_root = tmp_path / "vault"
        config_root = tmp_path / "configs"
        gate = EvaluationGate(vault_root=vault_root, config_root=config_root)

        # Register an evaluation
        reg_id, reg_path, _ = gate.reg_manager.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.CROSS_PROVIDER,
            target_dataset_manifest_hashes=[],
            registered_by="TESTER",
        )

        # Simulate a crash: manually set state to RUNNING with a dead PID
        gate._update_registration_state(reg_id, EvaluationStatus.RUNNING, {"pid": 99999999, "started_at_utc": "2026-10-28T10:00:00Z"})

        # Run recovery
        recovered = gate.recover_interrupted_evaluations()
        assert len(recovered) == 1
        assert recovered[0]["registration_id"] == reg_id
        assert recovered[0]["status"] == "RECOVERED_TO_FAILED"

        # Verify state is now FAILED
        reg_info = gate.reg_manager.load_registration(reg_id)
        assert reg_info["status"] == EvaluationStatus.FAILED.value
        assert reg_info["failure_reason"] == "PROCESS_TERMINATED_ABNORMALLY"

        remove_readonly_attribute(reg_path)
        remove_readonly_attribute(gate.evaluations_dir / f"{reg_id}.json")

    def test_dataset_consumption_lock_prevents_reuse_by_other_strategy(self, tmp_path: Path) -> None:
        vault_root = tmp_path / "vault"
        config_root = tmp_path / "configs"
        gate = EvaluationGate(vault_root=vault_root, config_root=config_root)

        # Create dataset
        data_file = tmp_path / "dataset_shared.parquet"
        pd.DataFrame({"timestamp_utc": [pd.Timestamp("2026-11-01 10:00:00", tz="UTC")], "open": [2650.0]}).to_parquet(data_file)
        data_sha = compute_sha256(data_file)
        manifest_file = Path(str(data_file) + ".manifest.json")
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({"file_sha256": data_sha, "start_time_utc": "2026-11-01T10:00:00Z"}, f)

        # Strategy 1 evaluates and consumes the dataset
        reg_id1, reg_path1, _ = gate.reg_manager.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[{"dataset_name": data_file.name, "manifest_sha256": data_sha}],
            registered_by="STRATEGY_1",
            evaluation_start_boundary_utc=dt.datetime(2026, 11, 1, 0, 0, tzinfo=dt.timezone.utc),
        )

        receipt = gate.execute_evaluation(reg_id1, [data_file], lambda p: {"pnl": 100.0})
        assert receipt["status"] == EvaluationStatus.EVALUATED_CONSUMED.value

        # Strategy 2 registers on the same dataset
        reg_id2, reg_path2, _ = gate.reg_manager.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[{"dataset_name": data_file.name, "manifest_sha256": data_sha}],
            registered_by="STRATEGY_2",
            evaluation_start_boundary_utc=dt.datetime(2026, 11, 1, 0, 0, tzinfo=dt.timezone.utc),
        )

        # Evaluation by Strategy 2 MUST FAIL with DatasetAlreadyConsumedError
        with pytest.raises(DatasetAlreadyConsumedError, match="DATASET CONSUMPTION LOCK"):
            gate.execute_evaluation(reg_id2, [data_file], lambda p: {"pnl": 200.0})

        remove_readonly_attribute(reg_path1)
        remove_readonly_attribute(reg_path2)
        remove_readonly_attribute(gate.evaluations_dir / f"{reg_id1}.json")
        remove_readonly_attribute(gate.evaluations_dir / f"{reg_id2}.json")
        remove_readonly_attribute(gate.evaluations_dir / f"RECEIPT_{reg_id1}.json")
        remove_readonly_attribute(gate.consumed_registry_path)


class TestForwardDataEligibilityAndBackfillRejection:
    """Tests proving forward-data eligibility and rejecting historical backfill."""

    def test_historical_backfill_rejected(self, tmp_path: Path) -> None:
        vault_root = tmp_path / "vault"
        config_root = tmp_path / "configs"
        gate = EvaluationGate(vault_root=vault_root, config_root=config_root)

        # Registration boundary is 2026-11-01 00:00 UTC
        boundary = dt.datetime(2026, 11, 1, 0, 0, tzinfo=dt.timezone.utc)

        # Backfilled historical data: ingested at 2026-11-02, but observations from 2026-10-15
        backfill_file = tmp_path / "backfill.parquet"
        pd.DataFrame({
            "timestamp_utc": [pd.Timestamp("2026-10-15 10:00:00", tz="UTC")],
            "open": [2650.0],
        }).to_parquet(backfill_file)
        backfill_sha = compute_sha256(backfill_file)

        manifest_file = Path(str(backfill_file) + ".manifest.json")
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({
                "file_sha256": backfill_sha,
                "start_time_utc": "2026-10-15T10:00:00Z",
                "ingestion_receipt_utc": "2026-11-02T10:00:00Z", # Ingested after registration, but obs in past!
            }, f)

        reg_id, reg_path, _ = gate.reg_manager.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[{"dataset_name": backfill_file.name, "manifest_sha256": backfill_sha}],
            registered_by="RESEARCHER",
            evaluation_start_boundary_utc=boundary,
        )

        with pytest.raises(ForwardEligibilityError, match="HISTORICAL BACKFILL REJECTED"):
            gate.verify_pre_evaluation(reg_id, [backfill_file])

        remove_readonly_attribute(reg_path)
        remove_readonly_attribute(gate.evaluations_dir / f"{reg_id}.json")

    def test_observation_exactly_at_boundary_accepted(self, tmp_path: Path) -> None:
        vault_root = tmp_path / "vault"
        config_root = tmp_path / "configs"
        gate = EvaluationGate(vault_root=vault_root, config_root=config_root)

        boundary = dt.datetime(2026, 11, 1, 0, 0, tzinfo=dt.timezone.utc)
        exact_file = tmp_path / "exact_boundary.parquet"
        pd.DataFrame({
            "timestamp_utc": [pd.Timestamp("2026-11-01 00:00:00", tz="UTC")],
            "open": [2650.0],
        }).to_parquet(exact_file)
        sha = compute_sha256(exact_file)

        manifest_file = Path(str(exact_file) + ".manifest.json")
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({
                "file_sha256": sha,
                "start_time_utc": "2026-11-01T00:00:00Z",
                "ingestion_receipt_utc": "2026-11-01T00:01:00Z",
            }, f)

        reg_id, reg_path, _ = gate.reg_manager.register(
            strategy_name="SMC_v1_frozen",
            evaluation_type=EvaluationType.FORWARD_TEMPORAL,
            target_dataset_manifest_hashes=[{"dataset_name": exact_file.name, "manifest_sha256": sha}],
            registered_by="RESEARCHER",
            evaluation_start_boundary_utc=boundary,
        )

        # Exactly at boundary must pass verification
        is_valid, _ = gate.verify_pre_evaluation(reg_id, [exact_file])
        assert is_valid

        remove_readonly_attribute(reg_path)
        remove_readonly_attribute(gate.evaluations_dir / f"{reg_id}.json")


class TestInstrumentLimitsAndDeduplication:
    """Tests for configurable instrument profiles and sequence-aware deduplication."""

    def test_sequence_aware_deduplication(self) -> None:
        # Same timestamp, but distinct sequence IDs: legitimate fast market trades -> PRESERVE BOTH
        ticks = [
            RawTickObservation(pd.Timestamp("2026-10-28 10:00:00.100", tz="UTC"), "XAUUSD", bid=2650.0, ask=2650.2, volume=1.0, sequence_id=101),
            RawTickObservation(pd.Timestamp("2026-10-28 10:00:00.100", tz="UTC"), "XAUUSD", bid=2650.0, ask=2650.2, volume=1.0, sequence_id=102),
            # True duplicate: same sequence ID 102
            RawTickObservation(pd.Timestamp("2026-10-28 10:00:00.100", tz="UTC"), "XAUUSD", bid=2650.0, ask=2650.2, volume=1.0, sequence_id=102),
        ]

        cleaned_df, report = validate_and_canonicalize_ticks(ticks)
        assert len(cleaned_df) == 2
        assert report.duplicates_dropped == 1
        assert list(cleaned_df["sequence_id"]) == [101, 102]

    def test_configurable_instrument_limits(self) -> None:
        eur_validator = TickDataValidator(price_limits=DEFAULT_FX_LIMITS)

        # EURUSD quote: bid 1.0850, ask 1.0852
        valid_eur = [RawTickObservation(pd.Timestamp("2026-10-28 10:00:00", tz="UTC"), "EURUSD", bid=1.0850, ask=1.0852)]
        df_valid, rep_valid = eur_validator.validate_and_canonicalize(valid_eur)
        assert rep_valid.valid_count == 1

        # Gold price passed to EURUSD validator must fail price limits
        invalid_eur = [RawTickObservation(pd.Timestamp("2026-10-28 10:00:00", tz="UTC"), "EURUSD", bid=2650.0, ask=2650.2)]
        df_invalid, rep_invalid = eur_validator.validate_and_canonicalize(invalid_eur)
        assert rep_invalid.valid_count == 0
        assert rep_invalid.invalid_prices == 1


class TestM1BarBuilderTraceabilityAndBoundaries:
    """Tests for M1 bar boundary rules, empty gaps, and source sequence traceability."""

    def test_boundary_timestamp_intervals(self) -> None:
        ticks = [
            RawTickObservation(pd.Timestamp("2026-10-28 10:00:00.000", tz="UTC"), "XAUUSD", bid=2650.0, ask=2650.2, sequence_id=1),
            RawTickObservation(pd.Timestamp("2026-10-28 10:00:59.999", tz="UTC"), "XAUUSD", bid=2651.0, ask=2651.2, sequence_id=2),
            # Boundary tick at 10:01:00.000 MUST belong to 10:01:00 bar
            RawTickObservation(pd.Timestamp("2026-10-28 10:01:00.000", tz="UTC"), "XAUUSD", bid=2652.0, ask=2652.2, sequence_id=3),
        ]

        bars, _ = synthesize_m1_bars(ticks, price_source="bid")
        assert len(bars) == 2

        # Bar 1: 10:00:00
        assert bars[0].timestamp_utc == pd.Timestamp("2026-10-28 10:00:00", tz="UTC")
        assert bars[0].first_sequence_id == 1
        assert bars[0].last_sequence_id == 2
        assert bars[0].tick_count == 2
        assert bars[0].close == 2651.0

        # Bar 2: 10:01:00
        assert bars[1].timestamp_utc == pd.Timestamp("2026-10-28 10:01:00", tz="UTC")
        assert bars[1].first_sequence_id == 3
        assert bars[1].last_sequence_id == 3
        assert bars[1].tick_count == 1
        assert bars[1].open == 2652.0

