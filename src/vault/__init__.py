"""
Independent Vault & Controlled Evaluation System for GoldFlow.

Provides immutable raw data partitions, cryptographic manifest verification,
physical holdout segregation, pre-registration protocols, and execution gates.
"""

from src.vault.audit_ledger import TamperEvidentAuditLedger, compute_entry_hash
from src.vault.evaluation_gate import (
    ConcurrentEvaluationError,
    DatasetAlreadyConsumedError,
    EvaluationGate,
    EvaluationGateError,
    ForwardEligibilityError,
    GateProcessLock,
)
from src.vault.holdout import (
    DEFAULT_VAULT_ENV_VAR,
    HoldoutVaultManager,
    check_ntfs_acl_protection,
    generate_ntfs_hardening_script,
    get_default_vault_root,
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
    FROZEN_SMC_CONFIG_PATH,
    EvaluationRegistrationManager,
    EvaluationStatus,
    EvaluationType,
    get_current_git_commit,
    verify_frozen_config,
)

__all__ = [
    "ConcurrentEvaluationError",
    "DEFAULT_VAULT_ENV_VAR",
    "DatasetAlreadyConsumedError",
    "EXPECTED_FROZEN_SMC_HASH",
    "EvaluationGate",
    "EvaluationGateError",
    "EvaluationRegistrationManager",
    "EvaluationStatus",
    "EvaluationType",
    "FROZEN_SMC_CONFIG_PATH",
    "ForwardEligibilityError",
    "GateProcessLock",
    "HoldoutVaultManager",
    "PartitionStorageManager",
    "TamperEvidentAuditLedger",
    "check_ntfs_acl_protection",
    "compute_entry_hash",
    "compute_sha256",
    "generate_ntfs_hardening_script",
    "get_current_git_commit",
    "get_default_vault_root",
    "is_readonly",
    "remove_readonly_attribute",
    "set_readonly_attribute",
    "verify_frozen_config",
]
