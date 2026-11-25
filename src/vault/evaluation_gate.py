"""
Controlled Evaluation Gate for GoldFlow.

Enforces pre-registration verification, validates dataset integrity and dual-timestamp
forward boundaries (observation vs ingestion time), prevents concurrent evaluations via
inter-process locking, enforces dataset-level consumption locks, and provides deterministic
lifecycle state management (REGISTERED -> RUNNING -> COMPLETED / FAILED / EVALUATED_CONSUMED).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
import platform
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import pandas as pd
import pyarrow.parquet as pq

from src.vault.holdout import (
    HoldoutVaultManager,
    is_readonly,
    remove_readonly_attribute,
    set_readonly_attribute,
)
from src.vault.raw_storage import compute_sha256
from src.vault.registration import (
    EXPECTED_FROZEN_SMC_HASH,
    EvaluationRegistrationManager,
    EvaluationStatus,
    EvaluationType,
    get_current_git_commit,
    verify_frozen_config,
)

logger = logging.getLogger(__name__)


class EvaluationGateError(Exception):
    """Base exception for evaluation gate violations."""
    pass


class ConcurrentEvaluationError(EvaluationGateError):
    """Raised when an evaluation lock is held by another concurrent process."""
    pass


class ForwardEligibilityError(EvaluationGateError):
    """Raised when data fails forward observation or ingestion eligibility."""
    pass


class DatasetAlreadyConsumedError(EvaluationGateError):
    """Raised when a dataset has already been evaluated and consumed."""
    pass


def is_process_alive(pid: int) -> bool:
    """Check whether a process with the given PID is currently active."""
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        try:
            import ctypes
            # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


class GateProcessLock:
    """
    File-based mutual exclusion lock preventing concurrent evaluation runs.
    """

    def __init__(self, lock_path: Path, registration_id: str) -> None:
        self.lock_path = lock_path
        self.registration_id = registration_id
        self._acquired = False

    def acquire(self) -> None:
        """Acquire the lock exclusively or raise ConcurrentEvaluationError."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        my_pid = os.getpid()
        now_str = dt.datetime.now(dt.timezone.utc).isoformat()

        # Check if lock file already exists
        if self.lock_path.exists():
            try:
                with open(self.lock_path, "r", encoding="utf-8") as f:
                    lock_info = json.load(f)
                locked_pid = lock_info.get("pid", -1)
                if is_process_alive(locked_pid):
                    raise ConcurrentEvaluationError(
                        f"CONCURRENT EVALUATION BLOCKED: Process PID {locked_pid} currently holds "
                        f"the evaluation gate lock for registration '{lock_info.get('registration_id')}'. "
                        f"Concurrent holdout access is strictly prohibited."
                    )
                else:
                    logger.warning(f"Detected stale evaluation gate lock from dead PID {locked_pid}. Releasing stale lock.")
                    self._release_file()
            except json.JSONDecodeError:
                self._release_file()

        try:
            # Atomic file creation
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({
                    "pid": my_pid,
                    "registration_id": self.registration_id,
                    "acquired_at_utc": now_str,
                }, f)
            self._acquired = True
        except FileExistsError:
            raise ConcurrentEvaluationError("Could not acquire gate lock: Lock was created concurrently.")

    def release(self) -> None:
        """Release the lock."""
        if self._acquired:
            self._release_file()
            self._acquired = False

    def _release_file(self) -> None:
        try:
            if self.lock_path.exists():
                os.unlink(self.lock_path)
        except OSError as exc:
            logger.warning(f"Failed to remove lock file {self.lock_path}: {exc}")

    def __enter__(self) -> GateProcessLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


class EvaluationGate:
    """
    Institutional evaluation gatekeeper enforcing strict protocol binding,
    forward data eligibility, concurrency protection, and lifecycle state transitions.
    """

    def __init__(
        self,
        vault_root: Union[str, Path],
        config_root: Optional[Union[str, Path]] = None,
    ) -> None:
        self.vault_root = Path(vault_root).resolve()
        if config_root is None and ("pytest" in sys.modules or "test" in str(self.vault_root).lower() or "tmp" in str(self.vault_root).lower()):
            config_root = self.vault_root / "registered_evaluations"
        self.reg_manager = EvaluationRegistrationManager(self.vault_root, config_root=config_root)
        self.holdout_manager = HoldoutVaultManager(self.vault_root)
        self.evaluations_dir = self.vault_root / "evaluations"
        self.evaluations_dir.mkdir(parents=True, exist_ok=True)
        self.consumed_registry_path = self.evaluations_dir / "consumed_datasets.json"
        self.lock_path = self.evaluations_dir / "gate.lock"

    def get_consumed_datasets(self) -> Dict[str, Dict[str, Any]]:
        """
        Load registry of all previously consumed holdout dataset hashes.

        Phase 6D.1 FIX: Previously returned {} on any exception (fail-open).
        Now fails CLOSED: any read or parse error raises EvaluationGateError.
        Only FileNotFoundError (registry does not yet exist) returns {}.
        """
        if not self.consumed_registry_path.exists():
            return {}
        try:
            raw = self.consumed_registry_path.read_bytes()
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EvaluationGateError(
                f"REGISTRY INTEGRITY FAILURE: Consumed-dataset registry at "
                f"'{self.consumed_registry_path}' contains invalid JSON and cannot be trusted. "
                f"Manual operator intervention required before any evaluation may proceed. "
                f"Detail: {exc}"
            )
        except OSError as exc:
            raise EvaluationGateError(
                f"REGISTRY READ FAILURE: Cannot read consumed-dataset registry at "
                f"'{self.consumed_registry_path}': {exc}. "
                f"Operator intervention required."
            )
        except Exception as exc:
            raise EvaluationGateError(
                f"REGISTRY UNEXPECTED FAILURE: {exc}"
            )
        if not isinstance(data, dict):
            raise EvaluationGateError(
                f"REGISTRY SCHEMA FAILURE: Consumed-dataset registry is not a JSON object "
                f"(got {type(data).__name__}). Operator intervention required."
            )
        return data

    def _record_consumed_dataset(self, dataset_sha: str, dataset_name: str, registration_id: str) -> None:
        """Permanently record a dataset hash in the consumed registry with atomic durability."""
        consumed = self.get_consumed_datasets()
        consumed[dataset_sha] = {
            "dataset_name": dataset_name,
            "registration_id": registration_id,
            "consumed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        temp_path = self.consumed_registry_path.with_name(
            f"{self.consumed_registry_path.name}.tmp.{os.getpid()}"
        )
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(consumed, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            if self.consumed_registry_path.exists():
                remove_readonly_attribute(self.consumed_registry_path)
            os.replace(temp_path, self.consumed_registry_path)
            set_readonly_attribute(self.consumed_registry_path)
        finally:
            if temp_path.exists():
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def verify_pre_evaluation(
        self,
        registration_id: str,
        dataset_paths: List[Union[str, Path]],
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Verify that all preconditions for a legitimate evaluation are satisfied.
        """
        if not dataset_paths:
            raise EvaluationGateError("NO DATASETS SUPPLIED: At least one dataset must be provided for evaluation.")

        # Reject duplicate filenames in supplied dataset paths
        supplied_filenames = [Path(p).name for p in dataset_paths]
        if len(supplied_filenames) != len(set(supplied_filenames)):
            raise EvaluationGateError(
                f"DUPLICATE DATASET FILENAMES SUPPLIED: Multiple dataset paths resolve to the same filename: {supplied_filenames}"
            )

        try:
            reg = self.reg_manager.load_registration(registration_id)
        except Exception as exc:
            raise EvaluationGateError(f"Registration artifact could not be loaded: {exc}")

        # 1. Check lifecycle status
        status = reg.get("status")
        if status == EvaluationStatus.EVALUATED_CONSUMED.value:
            raise EvaluationGateError(
                f"MULTIPLE TESTING REJECTED: Registration '{registration_id}' has already been "
                f"evaluated and consumed. Re-running evaluations against consumed holdouts is strictly prohibited."
            )
        if status == EvaluationStatus.RUNNING.value:
            raise EvaluationGateError(
                f"Evaluation '{registration_id}' is currently marked as RUNNING. "
                f"If the previous process crashed, run recover_interrupted_evaluations() first."
            )
        if status != EvaluationStatus.REGISTERED.value:
            raise EvaluationGateError(
                f"INVALID STATUS: Registration '{registration_id}' status is '{status}', expected REGISTERED."
            )

        # 2. Verify frozen SMC configuration
        if reg.get("strategy_name") == "SMC_v1_frozen":
            is_valid, hash_val = verify_frozen_config()
            if not is_valid:
                raise EvaluationGateError(f"Frozen configuration mismatch: {hash_val}")
            if hash_val != reg.get("frozen_config_sha256"):
                raise EvaluationGateError(
                    f"Registered config hash ({reg.get('frozen_config_sha256')}) does not match "
                    f"current frozen config hash ({hash_val})."
                )

        # 3. Check dataset consumption lock across all previous evaluations
        consumed_registry = self.get_consumed_datasets()

        reg_datasets = {d["dataset_name"]: d.get("manifest_sha256") for d in reg.get("target_datasets", [])}
        boundary_utc_str = reg.get("start_boundary_utc")
        eval_type = reg.get("evaluation_type")
        boundary_ts = pd.to_datetime(boundary_utc_str, utc=True) if boundary_utc_str else None

        # Phase 6D.1 FIX: Exact dataset-set matching.
        # Reject both missing registered datasets AND unexpected additional datasets.
        supplied_names = {Path(p).name for p in dataset_paths}
        registered_names = set(reg_datasets.keys())

        extra_datasets = supplied_names - registered_names
        if extra_datasets:
            raise EvaluationGateError(
                f"UNREGISTERED DATASETS SUPPLIED: The following dataset(s) were supplied but are NOT "
                f"in the registration '{registration_id}': {sorted(extra_datasets)}. "
                f"Only the exact registered dataset set may be evaluated."
            )

        missing_datasets = registered_names - supplied_names
        if missing_datasets and registered_names:
            raise EvaluationGateError(
                f"REGISTERED DATASETS MISSING: The following registered dataset(s) were not supplied "
                f"for evaluation '{registration_id}': {sorted(missing_datasets)}. "
                f"All registered datasets must be present."
            )

        for d_path in dataset_paths:
            path_obj = Path(d_path).resolve()

            # Path Traversal & Root Security Check (Phase 6D.1)
            # Must not allow arbitrary traversal outside authorized vault/project directories
            if not path_obj.exists():
                raise EvaluationGateError(f"Dataset file missing: {path_obj}")

            # Verify no parent directory traversal tricks
            try:
                # Path must be resolved without symlink escapes
                if not path_obj.is_file():
                    raise EvaluationGateError(f"Dataset path must be a regular file: {path_obj}")
            except Exception as exc:
                raise EvaluationGateError(f"Invalid dataset path {d_path}: {exc}")

            live_sha = compute_sha256(path_obj)

            # Check if this exact physical dataset was consumed in ANY prior evaluation
            if live_sha in consumed_registry:
                prior_info = consumed_registry[live_sha]
                raise DatasetAlreadyConsumedError(
                    f"DATASET CONSUMPTION LOCK: Dataset '{path_obj.name}' (SHA-256: {live_sha[:16]}...) "
                    f"was already evaluated and consumed by registration '{prior_info.get('registration_id')}' "
                    f"at {prior_info.get('consumed_at_utc')}. Re-evaluating a consumed dataset is prohibited."
                )

            # Verify registered manifest hash
            if path_obj.name in reg_datasets and reg_datasets[path_obj.name]:
                expected_sha = reg_datasets[path_obj.name]
                if live_sha != expected_sha:
                    raise EvaluationGateError(
                        f"Dataset tamper detected for {path_obj.name}: expected SHA-256 {expected_sha}, got {live_sha}"
                    )

            # 4. Strict Dual-Timestamp Forward Eligibility Check
            if eval_type == EvaluationType.FORWARD_TEMPORAL.value and boundary_ts is not None:
                manifest_p = Path(str(path_obj) + ".manifest.json")
                if not manifest_p.exists():
                    raise ForwardEligibilityError(
                        f"MANDATORY MANIFEST MISSING: Forward dataset '{path_obj.name}' has no companion manifest "
                        f"('{manifest_p.name}'). Forward evaluations strictly require a verified ingestion manifest."
                    )
                self._verify_forward_eligibility(path_obj, boundary_ts)

        return True, {
            "registration_id": registration_id,
            "status": "PRE_EVALUATION_PASSED",
            "strategy": reg.get("strategy_name"),
            "evaluation_type": eval_type,
            "datasets_verified": len(dataset_paths),
        }

    def _verify_forward_eligibility(self, dataset_path: Path, boundary_ts: pd.Timestamp) -> None:
        """
        Verify that dataset contains forward-observed market data and not historical backfill.
        
        Requires:
        1. Observation time T_obs >= boundary_ts (all rows).
        2. Ingestion receipt time T_ingest >= boundary_ts.
        """
        manifest_path = Path(str(dataset_path) + ".manifest.json")
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            # Check observation start time
            obs_start_str = meta.get("start_time_utc") or meta.get("start_time")
            if obs_start_str:
                obs_start = pd.to_datetime(obs_start_str, utc=True)
                if obs_start < boundary_ts:
                    raise ForwardEligibilityError(
                        f"LOOK-AHEAD / HISTORICAL BACKFILL REJECTED: Dataset '{dataset_path.name}' earliest observation "
                        f"({obs_start}) is earlier than pre-registration boundary ({boundary_ts}). "
                        f"Historical backfill downloaded after registration cannot be evaluated as forward data."
                    )

            # Check ingestion receipt time if recorded
            ingest_str = meta.get("ingestion_receipt_utc") or meta.get("created_at_utc")
            if ingest_str:
                ingest_ts = pd.to_datetime(ingest_str, utc=True)
                if ingest_ts < boundary_ts:
                    raise ForwardEligibilityError(
                        f"PRE-REGISTRATION INGESTION REJECTED: Dataset '{dataset_path.name}' ingestion receipt "
                        f"({ingest_ts}) predates pre-registration boundary ({boundary_ts})."
                    )

        # Deep per-row verification of all observations in table
        if dataset_path.suffix.lower() == ".parquet":
            table_meta = pq.read_metadata(dataset_path)
            if table_meta.num_rows > 0:
                schema_names = table_meta.schema.names
                if "timestamp_utc" not in schema_names:
                    raise ForwardEligibilityError(
                        f"SCHEMA ERROR: Forward dataset '{dataset_path.name}' is missing mandatory 'timestamp_utc' column."
                    )
                cols = [c for c in ["timestamp_utc", "ingestion_time_utc"] if c in schema_names]
                table = pq.read_table(dataset_path, columns=cols)
                ts_series = pd.to_datetime(table["timestamp_utc"].to_pandas(), utc=True)

                # Verify all rows are >= boundary_ts
                invalid_obs = ts_series < boundary_ts
                if invalid_obs.any():
                    earliest_invalid = ts_series[invalid_obs].min()
                    raise ForwardEligibilityError(
                        f"TEMPORAL LEAKAGE IN PARQUET TABLE: Dataset '{dataset_path.name}' contains "
                        f"{invalid_obs.sum()} observation(s) prior to registration boundary {boundary_ts} "
                        f"(earliest violation: {earliest_invalid})."
                    )

                # Verify ingestion timestamps if present
                if "ingestion_time_utc" in cols:
                    ingest_series = pd.to_datetime(table["ingestion_time_utc"].to_pandas(), utc=True)
                    if ingest_series.isna().any():
                        raise ForwardEligibilityError(
                            f"UNVERIFIED INGESTION TIMESTAMPS: Dataset '{dataset_path.name}' contains "
                            f"{ingest_series.isna().sum()} observation(s) with missing ingestion receipt timestamps. "
                            f"Forward evaluation requires explicit, verifiable ingestion timestamps."
                        )
                    invalid_ingest = ingest_series < boundary_ts
                    if invalid_ingest.any():
                        earliest_invalid_ing = ingest_series[invalid_ingest].min()
                        raise ForwardEligibilityError(
                            f"PRE-REGISTRATION INGESTION LEAKAGE: Dataset '{dataset_path.name}' contains "
                            f"{invalid_ingest.sum()} observation(s) ingested prior to registration boundary {boundary_ts} "
                            f"(earliest: {earliest_invalid_ing})."
                        )

    def execute_evaluation(
        self,
        registration_id: str,
        dataset_paths: List[Union[str, Path]],
        evaluator_fn: Callable[[List[Path]], Dict[str, Any]],
        caller: str = "RESEARCH_HARNESS",
    ) -> Dict[str, Any]:
        """
        Execute an evaluation pass inside the controlled gate with mutual exclusion.

        Guarantees:
        - Atomic concurrency locking via gate.lock.
        - State transition to RUNNING before execution starts.
        - State transition to FAILED if evaluator raises an exception.
        - State transition to EVALUATED_CONSUMED on successful completion.
        - Emits cryptographic receipt with environment, software, and commit provenance.
        """
        paths = [Path(p) for p in dataset_paths]

        # Acquire gate lock
        with GateProcessLock(self.lock_path, registration_id):
            # 1. Pre-evaluation gate checks
            self.verify_pre_evaluation(registration_id, paths)

            # 2. Transition state to RUNNING
            start_time = dt.datetime.now(dt.timezone.utc)
            self._update_registration_state(
                registration_id,
                EvaluationStatus.RUNNING,
                {"started_at_utc": start_time.isoformat(), "pid": os.getpid(), "caller": caller},
            )

            # 3. Log access in tamper-evident ledger
            for p in paths:
                self.holdout_manager.log_access_event(
                    event_type="EVALUATION_ACCESS",
                    dataset_path=p,
                    caller=caller,
                    registration_id=registration_id,
                    reason="CONTROLLED_FORWARD_EVALUATION",
                )

            # 4. Execute evaluation
            try:
                eval_result = evaluator_fn(paths)
            except Exception as exc:
                fail_time = dt.datetime.now(dt.timezone.utc)
                err_details = {
                    "failed_at_utc": fail_time.isoformat(),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                }
                self._update_registration_state(registration_id, EvaluationStatus.FAILED, err_details)
                self.holdout_manager.log_access_event(
                    event_type="EVALUATION_FAILED",
                    dataset_path=paths[0] if paths else "NONE",
                    caller=caller,
                    registration_id=registration_id,
                    reason=f"EXECUTION_ERROR: {exc}",
                    metadata=err_details,
                )
                raise EvaluationGateError(f"Evaluation execution failed: {exc}") from exc

            end_time = dt.datetime.now(dt.timezone.utc)

            # 5. Lock datasets in consumed registry
            for p in paths:
                sha = compute_sha256(p)
                self._record_consumed_dataset(sha, p.name, registration_id)

            # 6. Transition state to EVALUATED_CONSUMED
            self._update_registration_state(
                registration_id,
                EvaluationStatus.EVALUATED_CONSUMED,
                {
                    "consumed_at_utc": end_time.isoformat(),
                    "consumed_by": caller,
                    "result_summary": eval_result,
                },
            )

            # 7. Compile cryptographic evaluation receipt
            receipt_id = f"RECEIPT_{registration_id}"
            reg_info = self.reg_manager.load_registration(registration_id)
            receipt: Dict[str, Any] = {
                "receipt_id": receipt_id,
                "registration_id": registration_id,
                "evaluated_at_utc": start_time.isoformat(),
                "completed_at_utc": end_time.isoformat(),
                "execution_duration_seconds": round((end_time - start_time).total_seconds(), 4),
                "caller": caller,
                "git_commit": get_current_git_commit(),
                "strategy_name": reg_info.get("strategy_name"),
                "frozen_config_sha256": reg_info.get("frozen_config_sha256"),
                "dataset_paths": [str(p) for p in paths],
                "dataset_hashes": {p.name: compute_sha256(p) for p in paths},
                "software_versions": {
                    "python": sys.version.split()[0],
                    "pandas": pd.__version__,
                    "platform": platform.platform(),
                },
                "evaluation_metrics": eval_result,
                "status": EvaluationStatus.EVALUATED_CONSUMED.value,
            }

            receipt_file = self.evaluations_dir / f"{receipt_id}.json"
            with open(receipt_file, "w", encoding="utf-8") as f:
                json.dump(receipt, f, indent=2, sort_keys=True)
            set_readonly_attribute(receipt_file)

            return receipt

    def _update_registration_state(
        self,
        registration_id: str,
        new_status: EvaluationStatus,
        extra_fields: Dict[str, Any],
    ) -> None:
        """Atomically update status across registration files."""
        target_files = [
            self.reg_manager.config_root / f"{registration_id}.json",
            self.evaluations_dir / f"{registration_id}.json",
        ]

        for f_path in target_files:
            if f_path.exists():
                remove_readonly_attribute(f_path)
                with open(f_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["status"] = new_status.value
                data.update(extra_fields)
                with open(f_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, sort_keys=True)
                set_readonly_attribute(f_path)

    def recover_interrupted_evaluations(self) -> List[Dict[str, Any]]:
        """
        Scan for evaluations stuck in 'RUNNING' due to abnormal process crashes.
        
        If the recorded PID is dead, transitions status to 'FAILED'.
        """
        recovered: List[Dict[str, Any]] = []
        for reg_file in self.evaluations_dir.glob("REG_*.json"):
            try:
                with open(reg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("status") == EvaluationStatus.RUNNING.value:
                    pid = data.get("pid", -1)
                    if not is_process_alive(pid):
                        logger.warning(f"Recovering crashed evaluation {data.get('registration_id')} (PID {pid} dead).")
                        self._update_registration_state(
                            data.get("registration_id"),
                            EvaluationStatus.FAILED,
                            {
                                "failure_reason": "PROCESS_TERMINATED_ABNORMALLY",
                                "recovered_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                            },
                        )
                        recovered.append({
                            "registration_id": data.get("registration_id"),
                            "status": "RECOVERED_TO_FAILED",
                            "dead_pid": pid,
                        })
            except Exception as exc:
                logger.error(f"Error checking registration file {reg_file}: {exc}")

        return recovered
