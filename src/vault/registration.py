"""
Evaluation Registration & Protocol Binding for GoldFlow.

Enforces pre-registration of evaluation parameters, frozen strategy configuration hashes,
git commit identities, and temporal boundaries prior to holdout evaluation.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from src.vault.holdout import is_readonly, set_readonly_attribute
from src.vault.raw_storage import compute_sha256

logger = logging.getLogger(__name__)

FROZEN_SMC_CONFIG_PATH = Path("configs/smc_v1_frozen.json")
EXPECTED_FROZEN_SMC_HASH = "1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a"


class EvaluationType(str, Enum):
    FORWARD_TEMPORAL = "FORWARD_TEMPORAL"
    CROSS_PROVIDER = "CROSS_PROVIDER"


class EvaluationStatus(str, Enum):
    REGISTERED = "REGISTERED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    EVALUATED_CONSUMED = "EVALUATED_CONSUMED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


def get_current_git_commit(repo_dir: Optional[Path] = None) -> str:
    """Retrieve the current HEAD git commit hash."""
    try:
        cmd = ["git", "rev-parse", "HEAD"]
        result = subprocess.run(
            cmd,
            cwd=str(repo_dir) if repo_dir else None,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception as exc:
        logger.warning(f"Unable to retrieve git commit: {exc}")
        return "UNKNOWN_COMMIT"


def verify_frozen_config(config_path: Path = FROZEN_SMC_CONFIG_PATH) -> Tuple[bool, str]:
    """Verify that the frozen SMC v1 config matches the expected SHA-256 digest."""
    if not config_path.exists():
        return False, f"Config file not found at {config_path}"
    live_hash = compute_sha256(config_path)
    if live_hash != EXPECTED_FROZEN_SMC_HASH:
        return False, f"Config hash mismatch: expected {EXPECTED_FROZEN_SMC_HASH}, got {live_hash}"
    return True, live_hash


class EvaluationRegistrationManager:
    """
    Manages registration artifacts to prevent multiple testing, post-hoc tweaking,
    and temporal look-ahead bias.
    """

    def __init__(self, vault_root: Union[str, Path], config_root: Optional[Union[str, Path]] = None) -> None:
        self.vault_root = Path(vault_root)
        self.evaluations_dir = self.vault_root / "evaluations"
        self.evaluations_dir.mkdir(parents=True, exist_ok=True)

        if config_root is not None:
            self.config_root = Path(config_root)
        elif "pytest" in sys.modules or "test" in str(self.vault_root).lower() or "tmp" in str(self.vault_root).lower():
            self.config_root = self.vault_root / "registered_evaluations"
        else:
            self.config_root = Path("configs/registered_evaluations")
        self.config_root.mkdir(parents=True, exist_ok=True)

    def register(
        self,
        strategy_name: str,
        evaluation_type: EvaluationType,
        target_dataset_manifest_hashes: List[Dict[str, str]],
        registered_by: str,
        evaluation_start_boundary_utc: Optional[dt.datetime] = None,
        notes: str = "",
        allow_uncommitted_git: bool = False,
    ) -> Tuple[str, Path, Dict[str, Any]]:
        """
        Create an immutable pre-registration artifact.

        Parameters
        ----------
        strategy_name : str
            Name of strategy (e.g. 'SMC_v1_frozen').
        evaluation_type : EvaluationType
            FORWARD_TEMPORAL or CROSS_PROVIDER.
        target_dataset_manifest_hashes : List[Dict[str, str]]
            List of target datasets and their expected SHA-256 hashes.
        registered_by : str
            Operator or protocol identifier.
        evaluation_start_boundary_utc : dt.datetime, optional
            Boundary time T_registration. If FORWARD_TEMPORAL, all evaluated
            observations must have timestamp >= this boundary.
        notes : str
            Auditing rationales or description.
        allow_uncommitted_git : bool
            Whether to allow registering when git status is uncommitted (testing only).

        Returns
        -------
        Tuple[str, Path, Dict[str, Any]]
            registration_id, registration file path, and registration dict.
        """
        # 1. Verify frozen config integrity
        if strategy_name == "SMC_v1_frozen":
            is_valid, hash_val = verify_frozen_config()
            if not is_valid:
                raise ValueError(f"Cannot register evaluation: Frozen config check failed: {hash_val}")
            frozen_config_hash = hash_val
        else:
            frozen_config_hash = "NON_FROZEN_CUSTOM"

        # 2. Get git commit
        git_commit = get_current_git_commit()

        # 3. Establish timestamp boundary
        registration_now = dt.datetime.now(dt.timezone.utc)
        if evaluation_start_boundary_utc is None:
            boundary_time = registration_now
        else:
            boundary_time = (
                evaluation_start_boundary_utc
                if evaluation_start_boundary_utc.tzinfo
                else evaluation_start_boundary_utc.replace(tzinfo=dt.timezone.utc)
            )

        registration_id = f"REG_{evaluation_type.value}_{uuid.uuid4().hex[:12].upper()}"

        record: Dict[str, Any] = {
            "registration_id": registration_id,
            "protocol_version": "1.0",
            "strategy_name": strategy_name,
            "frozen_config_sha256": frozen_config_hash,
            "git_commit": git_commit,
            "registered_by": registered_by,
            "registered_at_utc": registration_now.isoformat(),
            "evaluation_type": evaluation_type.value,
            "start_boundary_utc": boundary_time.isoformat(),
            "target_datasets": target_dataset_manifest_hashes,
            "status": EvaluationStatus.REGISTERED.value,
            "notes": notes,
        }

        # Write to configs/registered_evaluations
        reg_file = self.config_root / f"{registration_id}.json"
        with open(reg_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, sort_keys=True)

        # Mirror to vault/evaluations
        vault_mirror = self.evaluations_dir / f"{registration_id}.json"
        with open(vault_mirror, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, sort_keys=True)

        # Lock registration artifacts
        set_readonly_attribute(reg_file)
        set_readonly_attribute(vault_mirror)

        return registration_id, reg_file, record

    def load_registration(self, registration_id_or_path: Union[str, Path]) -> Dict[str, Any]:
        """Load and return registration details."""
        p = Path(registration_id_or_path)
        if not p.exists():
            # Try searching in config_root
            p = self.config_root / f"{registration_id_or_path}.json"
            if not p.exists():
                p = self.evaluations_dir / f"{registration_id_or_path}.json"
                if not p.exists():
                    raise FileNotFoundError(f"Registration artifact not found: {registration_id_or_path}")

        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

