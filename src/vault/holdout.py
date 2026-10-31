"""
Holdout Vault Isolation, Access Control & Threat Modeling for GoldFlow.

Establishes physical directory segregation between development and sealed holdout data,
implements Windows read-only file attributes, logs all access events to a tamper-evident
hash-chained audit ledger, and provides institutional threat modeling for single-user
and multi-user environments.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from src.vault.audit_ledger import TamperEvidentAuditLedger
from src.vault.raw_storage import compute_sha256

logger = logging.getLogger(__name__)

DEFAULT_VAULT_ENV_VAR = "GOLDFLOW_VAULT_STORAGE_PATH"


def get_default_vault_root() -> Path:
    """Resolve vault root path from environment variable or default fallback."""
    env_path = os.environ.get(DEFAULT_VAULT_ENV_VAR)
    if env_path:
        return Path(env_path).resolve()
    return Path("goldflow_vault").resolve()


def set_readonly_attribute(path: Union[str, Path]) -> None:
    """
    Set file or directory to read-only on Windows / POSIX.
    
    NOTE ON SECURITY BOUNDARY:
    Setting the read-only attribute is an ADVISORY protection mechanism to prevent
    accidental modification by development code. It DOES NOT constitute an OS security
    boundary against an administrator or a process running under the same user account.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Path does not exist: {p}")

    current_mode = os.stat(p).st_mode
    os.chmod(p, current_mode & ~stat.S_IWRITE)

    if sys.platform.startswith("win"):
        try:
            subprocess.run(["attrib", "+r", str(p)], check=False, capture_output=True)
        except Exception as exc:
            logger.debug(f"attrib +r failed for {p}: {exc}")


def remove_readonly_attribute(path: Union[str, Path]) -> None:
    """
    Remove read-only attribute to permit deliberate programmatic updates or cleanup.
    """
    p = Path(path)
    if not p.exists():
        return
    current_mode = os.stat(p).st_mode
    os.chmod(p, current_mode | stat.S_IWRITE)
    if sys.platform.startswith("win"):
        try:
            subprocess.run(["attrib", "-r", str(p)], check=False, capture_output=True)
        except Exception:
            pass


def is_readonly(path: Union[str, Path]) -> bool:
    """Check if file is read-only."""
    p = Path(path)
    if not p.exists():
        return False
    return not (os.stat(p).st_mode & stat.S_IWRITE)


def check_ntfs_acl_protection(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Inspect the NTFS Access Control List (ACL) on Windows or stat permissions on POSIX.
    
    Returns an objective diagnostic dictionary identifying whether true multi-user
    access separation exists, or whether the process is operating in a single-user
    workstation environment where administrative privilege limits apply.
    """
    target = Path(path).resolve()
    if not target.exists():
        return {"status": "ERROR", "message": f"Target path does not exist: {target}"}

    residual_risk = (
        "In a single-user Windows environment, any process running under the user or administrator "
        "context possesses the technical authority to override read-only attributes (attrib -r) and "
        "modify NTFS ACLs. GoldFlow relies on cryptographic SHA-256 manifests, hash-chained audit ledgers, "
        "and git pre-registration commitments rather than OS hardware isolation."
    )

    if sys.platform.startswith("win"):
        try:
            # Query NTFS ACL via icacls, handling Windows OEM / non-UTF8 encodings safely
            cmd = ["icacls", str(target)]
            res = subprocess.run(cmd, capture_output=True, check=False)
            raw_output = ""
            if res.stdout:
                try:
                    raw_output = res.stdout.decode("cp850", errors="replace").strip()
                except Exception:
                    raw_output = res.stdout.decode("utf-8", errors="replace").strip()

            lines = [l.strip() for l in raw_output.splitlines() if l.strip()]
            has_full_control = any("(F)" in line or "(OI)(CI)F" in line for line in lines)

            username = os.environ.get("USERNAME", "UNKNOWN")
            is_admin = False
            try:
                import ctypes
                is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
            except Exception:
                pass

            return {
                "platform": "windows_ntfs",
                "target_path": str(target),
                "current_user": username,
                "is_process_admin": is_admin,
                "raw_acl_summary": lines[:5],
                "has_full_control": has_full_control,
                "advisory_readonly": is_readonly(target),
                "environment_model": "SINGLE_USER_WORKSTATION" if is_admin or has_full_control else "RESTRICTED_SERVICE",
                "security_boundary_status": "ADVISORY_APPLICATION_CONTROL",
                "residual_risk_disclosure": residual_risk,
            }
        except Exception as exc:
            return {
                "platform": "windows_ntfs",
                "target_path": str(target),
                "error": str(exc),
                "security_boundary_status": "INSPECTION_FAILED",
                "residual_risk_disclosure": residual_risk,
            }
    else:
        mode = os.stat(target).st_mode
        return {
            "platform": "posix",
            "target_path": str(target),
            "octal_mode": oct(mode),
            "advisory_readonly": is_readonly(target),
            "environment_model": "POSIX_SINGLE_USER",
            "security_boundary_status": "POSIX_FILE_PERMISSIONS",
        }


def generate_ntfs_hardening_script(vault_root: Path) -> str:
    """
    Generate the institutional PowerShell script for locking holdout storage
    across dedicated Windows service accounts.
    """
    vr = str(vault_root.resolve())
    return f"""# GoldFlow Institutional Windows NTFS Hardening Script
# Run as Administrator in elevated PowerShell

$VaultRoot = "{vr}"
$HoldoutDir = Join-Path $VaultRoot "holdout_vault"
$ManifestsDir = Join-Path $VaultRoot "manifests"
$EvaluationsDir = Join-Path $VaultRoot "evaluations"

# 1. Disable permission inheritance and remove ordinary user write permissions from holdout
icacls $HoldoutDir /inheritance:d
icacls $HoldoutDir /remove:g "Users" "Authenticated Users"
icacls $HoldoutDir /grant:r "SYSTEM:(OI)(CI)F"
icacls $HoldoutDir /grant:r "Administrators:(OI)(CI)F"
# Grant evaluation service account read-only access
icacls $HoldoutDir /grant:r "GoldFlow_Evaluator:(OI)(CI)R"

# 2. Restrict manifest audit logs to append-only for the service
icacls $ManifestsDir /inheritance:d
icacls $ManifestsDir /grant:r "SYSTEM:(OI)(CI)F"
icacls $ManifestsDir /grant:r "GoldFlow_Evaluator:(OI)(CI)(R,W)"

Write-Host "GoldFlow NTFS ACLs successfully hardened for $VaultRoot"
"""


class HoldoutVaultManager:
    """
    Manages physical segregation and audited access for holdout evaluation data.
    
    Directory layout:
      {vault_root}/
        ├── development/      # Unrestricted research, exploration, backtests
        ├── raw_vault/        # Canonical raw tick/bar Parquet partitions
        ├── holdout_vault/    # Sealed datasets reserved for forward evaluation
        ├── manifests/        # Audit logs and cryptographic manifests
        └── evaluations/      # Pre-registrations, lifecycle locks, receipts
    """

    def __init__(self, vault_root: Optional[Union[str, Path]] = None) -> None:
        self.vault_root = Path(vault_root).resolve() if vault_root else get_default_vault_root()
        self.dev_dir = self.vault_root / "development"
        self.raw_vault_dir = self.vault_root / "raw_vault"
        self.holdout_dir = self.vault_root / "holdout_vault"
        self.manifests_dir = self.vault_root / "manifests"
        self.evaluations_dir = self.vault_root / "evaluations"

        # Initialize structure
        for d in (self.dev_dir, self.raw_vault_dir, self.holdout_dir, self.manifests_dir, self.evaluations_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.access_log_path = self.manifests_dir / "holdout_access_audit.log"
        self.audit_ledger = TamperEvidentAuditLedger(self.access_log_path)

    def log_access_event(
        self,
        event_type: str,
        dataset_path: Union[str, Path],
        caller: str,
        registration_id: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Append a cryptographically hash-chained JSON record to holdout_access_audit.log.
        """
        entry: Dict[str, Any] = {
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "event_type": event_type,
            "dataset": str(Path(dataset_path).name),
            "dataset_full_path": str(dataset_path),
            "caller": caller,
            "registration_id": registration_id,
            "reason": reason,
            "metadata": metadata or {},
        }
        return self.audit_ledger.append_entry(entry)

    def verify_audit_ledger(self) -> Tuple[bool, int, Optional[str]]:
        """Verify the cryptographic hash-chain of the holdout access audit log."""
        return self.audit_ledger.verify_chain()

    def seal_dataset(
        self,
        source_path: Union[str, Path],
        symbol: str,
        dataset_name: str,
        caller: str,
        reason: str = "FORWARD_HOLDOUT_SEALING",
        ingestion_receipt_utc: Optional[str] = None,
        start_observation_utc: Optional[str] = None,
        end_observation_utc: Optional[str] = None,
    ) -> Tuple[Path, Path, Dict[str, Any]]:
        """
        Copy dataset into holdout_vault/, compute SHA-256 manifest, apply advisory read-only lock,
        and record the sealing event in the hash-chained audit ledger.
        """
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {src}")

        symbol_holdout_dir = self.holdout_dir / symbol.upper()
        symbol_holdout_dir.mkdir(parents=True, exist_ok=True)

        target_file = symbol_holdout_dir / dataset_name
        target_manifest = Path(str(target_file) + ".manifest.json")

        # Copy file
        shutil.copy2(src, target_file)

        # Compute SHA-256
        sha256 = compute_sha256(target_file)
        file_size = target_file.stat().st_size

        now_utc = dt.datetime.now(dt.timezone.utc).isoformat()
        manifest: Dict[str, Any] = {
            "sealed_file_name": target_file.name,
            "symbol": symbol.upper(),
            "file_sha256": sha256,
            "file_size_bytes": file_size,
            "source_origin": str(src),
            "sealed_at_utc": now_utc,
            "sealed_by": caller,
            "ingestion_receipt_utc": ingestion_receipt_utc or now_utc,
            "start_time_utc": start_observation_utc,
            "end_time_utc": end_observation_utc,
            "status": "SEALED_HOLDOUT",
        }

        with open(target_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

        # Apply advisory read-only locks
        set_readonly_attribute(target_file)
        set_readonly_attribute(target_manifest)

        # Audit log with hash chain
        self.log_access_event(
            event_type="DATASET_SEALED",
            dataset_path=target_file,
            caller=caller,
            reason=reason,
            metadata={"sha256": sha256, "size_bytes": file_size},
        )

        return target_file, target_manifest, manifest

    def verify_holdout_integrity(self, dataset_path: Union[str, Path]) -> Tuple[bool, Dict[str, Any]]:
        """
        Verify that a sealed holdout dataset matches its cryptographic manifest.
        """
        target = Path(dataset_path)
        if not target.exists():
            return False, {"error": f"File does not exist: {target}"}

        manifest_path = Path(str(target) + ".manifest.json")
        if not manifest_path.exists():
            return False, {"error": f"Manifest not found for: {target}"}

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        live_sha = compute_sha256(target)
        if live_sha != manifest.get("file_sha256"):
            return False, {
                "error": "TAMPER_DETECTED: SHA-256 hash does not match manifest.",
                "expected": manifest.get("file_sha256"),
                "computed": live_sha,
            }

        return True, {
            "status": "VERIFIED",
            "file_sha256": live_sha,
            "is_readonly": is_readonly(target),
            "sealed_at_utc": manifest.get("sealed_at_utc"),
        }
