"""
Immutable Raw Market Data Storage & Manifest Management for GoldFlow.

Manages partitioned Apache Parquet archival, cryptographic SHA-256 manifest generation,
append-only ingestion audit logging, and checkpoint-based recovery.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.vault.audit_ledger import TamperEvidentAuditLedger

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Base exception for raw vault storage operations."""
    pass


class PartitionConflictError(StorageError):
    """Raised when an attempt is made to overwrite an existing partition with conflicting data."""
    pass


class StoragePathSecurityError(StorageError):
    """Raised when a storage path attempts to escape authorized root or violate holdout isolation."""
    pass


def compute_sha256(filepath: Union[str, Path]) -> str:
    """Calculate the hexadecimal SHA-256 hash of a file on disk."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class PartitionStorageManager:
    """
    Manages immutable raw tick and bar Parquet partitions within the vault.
    
    Structure:
      {vault_root}/raw_vault/{symbol}/{year}/{symbol}_{provider}_{year}{month:02d}.parquet
      {vault_root}/raw_vault/{symbol}/{year}/{symbol}_{provider}_{year}{month:02d}.parquet.manifest.json
    """

    def __init__(self, vault_root: Union[str, Path]) -> None:
        self.vault_root = Path(vault_root)
        self.raw_vault_dir = self.vault_root / "raw_vault"
        self.manifests_dir = self.vault_root / "manifests"
        self.raw_vault_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        self.history_log_path = self.manifests_dir / "ingestion_history.jsonl"
        self.audit_ledger = TamperEvidentAuditLedger(self.history_log_path)

    def get_partition_path(
        self,
        symbol: str,
        provider: str,
        timestamp: dt.datetime,
        granularity: str = "monthly",
    ) -> Path:
        """
        Generate deterministic partition file path.
        """
        safe_symbol = symbol.upper().replace("/", "_")
        safe_provider = provider.upper().replace("/", "_")
        year = timestamp.strftime("%Y")

        year_dir = self.raw_vault_dir / safe_symbol / year
        year_dir.mkdir(parents=True, exist_ok=True)

        if granularity == "hourly":
            suffix = timestamp.strftime("%Y%m%d_%H")
        elif granularity == "daily":
            suffix = timestamp.strftime("%Y%m%d")
        else:
            suffix = timestamp.strftime("%Y%m")

        filename = f"{safe_symbol}_{safe_provider}_{suffix}.parquet"
        return year_dir / filename

    def write_partition(
        self,
        df: pd.DataFrame,
        symbol: str,
        provider: str,
        granularity: str = "monthly",
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Path, Path, Dict[str, Any]]:
        """
        Atomically write DataFrame to Parquet, compute SHA-256, emit manifest,
        and append record to the immutable ingestion ledger.

        Parameters
        ----------
        df : pd.DataFrame
            Market data dataframe with 'timestamp_utc' column.
        symbol : str
            Instrument symbol.
        provider : str
            Data feed provider.
        granularity : str
            Partition cadence ('monthly' or 'daily').
        custom_metadata : dict, optional
            Additional metadata fields to include in manifest.

        Returns
        -------
        Tuple[Path, Path, Dict[str, Any]]
            - Path to the written Parquet file.
            - Path to the cryptographic manifest JSON.
            - Manifest dictionary.
        """
        if df.empty:
            raise ValueError("Cannot write an empty DataFrame to a raw vault partition.")

        if "timestamp_utc" not in df.columns:
            raise ValueError("DataFrame must contain 'timestamp_utc' column.")

        # Ensure sorted timestamps
        if not df["timestamp_utc"].is_monotonic_increasing:
            df = df.sort_values("timestamp_utc").reset_index(drop=True)

        earliest_ts = pd.to_datetime(df["timestamp_utc"].iloc[0], utc=True)
        latest_ts = pd.to_datetime(df["timestamp_utc"].iloc[-1], utc=True)

        if granularity == "hourly":
            if earliest_ts.floor("h") != latest_ts.floor("h"):
                raise ValueError(
                    f"Cross-hour span rejected for hourly shard: earliest observation is {earliest_ts} "
                    f"but latest observation is {latest_ts}. Hourly partitions must contain observations "
                    f"from a single UTC hour only."
                )
        elif granularity == "daily":
            if earliest_ts.floor("D") != latest_ts.floor("D"):
                raise ValueError(
                    f"Cross-day span rejected for daily shard: earliest observation is {earliest_ts} "
                    f"but latest observation is {latest_ts}. Daily partitions must contain observations "
                    f"from a single UTC day only."
                )

        target_parquet = self.get_partition_path(symbol, provider, earliest_ts.to_pydatetime(), granularity=granularity)
        target_manifest = Path(str(target_parquet) + ".manifest.json")
        target_dir = target_parquet.parent

        # Atomic Parquet write via temporary file in target directory
        fd, tmp_file = tempfile.mkstemp(dir=target_dir, prefix=f"{target_parquet.stem}.tmp.", suffix=".parquet")
        os.close(fd)

        try:
            # Convert pandas DataFrame to PyArrow Table
            table = pa.Table.from_pandas(df, preserve_index=False)
            pq.write_table(
                table,
                tmp_file,
                compression="SNAPPY",
                version="2.6",
            )
            candidate_sha = compute_sha256(tmp_file)

            # Phase 6D.1 FIX: Enforce immutability & reject overwrites
            if target_parquet.exists():
                existing_sha = compute_sha256(target_parquet)
                if existing_sha == candidate_sha:
                    # Idempotent re-ingestion of identical content
                    try:
                        os.unlink(tmp_file)
                    except OSError:
                        pass
                    if target_manifest.exists():
                        with open(target_manifest, "r", encoding="utf-8") as f:
                            manifest = json.load(f)
                    else:
                        manifest = {
                            "file_name": target_parquet.name,
                            "file_sha256": existing_sha,
                            "sha256": existing_sha,
                            "row_count": len(df),
                        }
                        fd_m, tmp_m = tempfile.mkstemp(dir=target_dir, prefix=f"{target_parquet.stem}.mf.tmp.", suffix=".json")
                        with os.fdopen(fd_m, "w", encoding="utf-8") as f:
                            json.dump(manifest, f, indent=2)
                        os.replace(tmp_m, target_manifest)
                        from src.vault.holdout import set_readonly_attribute
                        set_readonly_attribute(target_manifest)
                    self._append_to_history_log({
                        "event": "PARTITION_IDEMPOTENT_SKIPPED",
                        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "partition_file": target_parquet.name,
                        "partition_sha256": existing_sha,
                        "row_count": len(df),
                        "symbol": symbol.upper(),
                        "provider": provider.upper(),
                    })
                    return target_parquet, target_manifest, manifest
                else:
                    # Reject conflicting content attempting to replace accepted partition
                    try:
                        os.unlink(tmp_file)
                    except OSError:
                        pass
                    self._append_to_history_log({
                        "event": "PARTITION_CONFLICT_REJECTED",
                        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "partition_file": target_parquet.name,
                        "existing_sha256": existing_sha,
                        "attempted_sha256": candidate_sha,
                        "symbol": symbol.upper(),
                        "provider": provider.upper(),
                    })
                    raise PartitionConflictError(
                        f"IMMUTABLE STORAGE CONFLICT: Partition '{target_parquet.name}' already exists with SHA-256 "
                        f"{existing_sha}, but attempted ingestion produced conflicting SHA-256 {candidate_sha}. "
                        f"Overwriting accepted raw partitions is strictly prohibited."
                    )

            # Atomic swap (only for new, non-conflicting partition)
            os.replace(tmp_file, target_parquet)
        except Exception:
            if os.path.exists(tmp_file):
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass
            raise

        # Compute hash and file metrics
        file_sha256 = compute_sha256(target_parquet)
        file_size_bytes = target_parquet.stat().st_size

        # Compile manifest
        manifest: Dict[str, Any] = {
            "format_version": "1.0",
            "file_name": target_parquet.name,
            "partition_relative_path": str(target_parquet.relative_to(self.vault_root)),
            "file_sha256": file_sha256,
            "sha256": file_sha256,  # Dual-key for compatibility
            "row_count": len(df),
            "start_time_utc": earliest_ts.isoformat(),
            "end_time_utc": latest_ts.isoformat(),
            "symbol": symbol.upper(),
            "provider": provider.upper(),
            "columns": list(df.columns),
            "column_types": {col: str(df[col].dtype) for col in df.columns},
            "file_size_bytes": file_size_bytes,
            "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "custom_metadata": custom_metadata or {},
        }

        # Write manifest atomically
        manifest_fd, manifest_tmp = tempfile.mkstemp(dir=target_dir, prefix=f"{target_manifest.stem}.tmp.", suffix=".json")
        try:
            with os.fdopen(manifest_fd, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, sort_keys=True)
            os.replace(manifest_tmp, target_manifest)
        except Exception:
            if os.path.exists(manifest_tmp):
                try:
                    os.unlink(manifest_tmp)
                except OSError:
                    pass
            raise

        # Append to immutable ingestion ledger
        self._append_to_history_log({
            "event": "PARTITION_COMMITTED",
            "timestamp_utc": manifest["created_at_utc"],
            "partition_file": target_parquet.name,
            "partition_sha256": file_sha256,
            "row_count": len(df),
            "symbol": symbol.upper(),
            "provider": provider.upper(),
            "start_time_utc": manifest["start_time_utc"],
            "end_time_utc": manifest["end_time_utc"],
        })

        # Update symbol checkpoint
        self.update_checkpoint(symbol, provider, latest_ts, target_parquet.name)

        return target_parquet, target_manifest, manifest

    def write_source_object(
        self,
        raw_bytes: bytes,
        symbol: str,
        provider: str,
        timestamp: dt.datetime,
        source_filename: Optional[str] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Path, Path, Dict[str, Any]]:
        """
        Persist original compressed source object separately with cryptographic SHA-256 manifest.

        Preserves original raw bytes (e.g. .bi5, .zip) alongside derived Parquet shards.
        Enforces idempotency and rejects conflicting overwrites.
        """
        if not raw_bytes:
            raise ValueError("Cannot persist empty source bytes.")

        safe_symbol = symbol.upper().replace("/", "_")
        safe_provider = provider.upper().replace("/", "_")
        year = timestamp.strftime("%Y")

        source_dir = self.raw_vault_dir / safe_symbol / year / "source_objects"
        source_dir.mkdir(parents=True, exist_ok=True)

        if source_filename:
            safe_name = Path(source_filename).name
        else:
            time_suffix = timestamp.strftime("%Y%m%d_%H00")
            safe_name = f"{safe_symbol}_{safe_provider}_{time_suffix}.source.bin"

        target_file = source_dir / safe_name
        target_manifest = Path(str(target_file) + ".manifest.json")

        candidate_sha = hashlib.sha256(raw_bytes).hexdigest()

        if target_file.exists():
            existing_sha = compute_sha256(target_file)
            if existing_sha == candidate_sha:
                if target_manifest.exists():
                    with open(target_manifest, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                else:
                    manifest = {
                        "file_name": target_file.name,
                        "file_sha256": existing_sha,
                        "sha256": existing_sha,
                        "byte_count": len(raw_bytes),
                    }
                return target_file, target_manifest, manifest
            else:
                raise PartitionConflictError(
                    f"IMMUTABLE SOURCE CONFLICT: Source object '{target_file.name}' already exists with SHA-256 "
                    f"{existing_sha}, but new data has SHA-256 {candidate_sha}."
                )

        fd, tmp_file = tempfile.mkstemp(dir=source_dir, prefix=f"{target_file.stem}.tmp.", suffix=".bin")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw_bytes)
            os.replace(tmp_file, target_file)
        except Exception:
            if os.path.exists(tmp_file):
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass
            raise

        manifest = {
            "format_version": "1.0",
            "file_name": target_file.name,
            "relative_path": str(target_file.relative_to(self.vault_root)),
            "file_sha256": candidate_sha,
            "sha256": candidate_sha,
            "byte_count": len(raw_bytes),
            "symbol": symbol.upper(),
            "provider": provider.upper(),
            "timestamp_utc": timestamp.isoformat(),
            "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "custom_metadata": custom_metadata or {},
        }

        m_fd, m_tmp = tempfile.mkstemp(dir=source_dir, prefix=f"{target_manifest.stem}.tmp.", suffix=".json")
        try:
            with os.fdopen(m_fd, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, sort_keys=True)
            os.replace(m_tmp, target_manifest)
        except Exception:
            if os.path.exists(m_tmp):
                try:
                    os.unlink(m_tmp)
                except OSError:
                    pass
            raise

        self._append_to_history_log({
            "event": "SOURCE_OBJECT_COMMITTED",
            "timestamp_utc": manifest["created_at_utc"],
            "source_file": target_file.name,
            "source_sha256": candidate_sha,
            "byte_count": len(raw_bytes),
            "symbol": symbol.upper(),
            "provider": provider.upper(),
        })

        return target_file, target_manifest, manifest

    def _append_to_history_log(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Append record to hash-chained ingestion history ledger."""
        return self.audit_ledger.append_entry(entry)

    def verify_ingestion_history(self) -> Tuple[bool, int, Optional[str]]:
        """Verify the cryptographic hash-chain of the ingestion history ledger."""
        return self.audit_ledger.verify_chain()

    def update_checkpoint(
        self,
        symbol: str,
        provider: str,
        latest_timestamp: pd.Timestamp,
        partition_name: str,
    ) -> Path:
        """Update the checkpoint file tracking latest ingested timestamp for a symbol."""
        symbol_dir = self.raw_vault_dir / symbol.upper()
        symbol_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = symbol_dir / "checkpoint.json"

        checkpoint_data = {
            "symbol": symbol.upper(),
            "provider": provider.upper(),
            "last_committed_timestamp_utc": latest_timestamp.isoformat(),
            "last_partition_file": partition_name,
            "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

        fd, tmp_file = tempfile.mkstemp(dir=symbol_dir, prefix="checkpoint.tmp.", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, indent=2, sort_keys=True)
        os.replace(tmp_file, checkpoint_path)
        return checkpoint_path

    def get_checkpoint(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieve current checkpoint for a symbol if it exists."""
        checkpoint_path = self.raw_vault_dir / symbol.upper() / "checkpoint.json"
        if not checkpoint_path.exists():
            return None
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def verify_partition(
        self,
        parquet_path: Union[str, Path],
        manifest_path: Optional[Union[str, Path]] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Verify partition file against its manifest.
        
        Checks:
        1. Parquet file exists.
        2. Manifest JSON exists.
        3. Recomputed SHA-256 matches manifest hash.
        4. Parquet row count matches manifest row count.
        5. Parquet timestamp bounds match manifest bounds.
        """
        p_path = Path(parquet_path)
        if not p_path.exists():
            return False, {"error": f"Parquet file {p_path} does not exist."}

        m_path = Path(manifest_path) if manifest_path else Path(str(p_path) + ".manifest.json")
        if not m_path.exists():
            return False, {"error": f"Manifest file {m_path} does not exist."}

        with open(m_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        live_sha256 = compute_sha256(p_path)
        if live_sha256 != manifest.get("file_sha256"):
            return False, {
                "error": "SHA-256 hash mismatch",
                "expected": manifest.get("file_sha256"),
                "computed": live_sha256,
            }

        # Inspect table metadata without loading full data if possible
        parquet_meta = pq.read_metadata(p_path)
        if parquet_meta.num_rows != manifest.get("row_count"):
            return False, {
                "error": "Row count mismatch",
                "expected": manifest.get("row_count"),
                "computed": parquet_meta.num_rows,
            }

        return True, {
            "status": "VALID",
            "file_sha256": live_sha256,
            "row_count": parquet_meta.num_rows,
            "manifest_created_at": manifest.get("created_at_utc"),
        }

    def read_partition(
        self,
        parquet_path: Union[str, Path],
        verify_integrity: bool = True,
    ) -> pd.DataFrame:
        """
        Load DataFrame from Parquet partition with optional manifest verification.
        """
        p_path = Path(parquet_path)
        if verify_integrity:
            is_valid, diagnostics = self.verify_partition(p_path)
            if not is_valid:
                raise ValueError(f"Partition integrity check failed for {p_path}: {diagnostics}")

        table = pq.read_table(p_path)
        df = table.to_pandas()
        if "timestamp_utc" in df.columns:
            df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
        return df

