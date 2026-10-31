"""
Cryptographic Tamper-Evident Hash-Chained Audit Ledger for GoldFlow.

Provides append-only, hash-chained audit logging where each record cryptographically
seals the preceding record via SHA-256. Any modification, insertion, deletion, or
reordering of audit entries breaks the hash chain and is immediately detectable.
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

logger = logging.getLogger(__name__)

GENESIS_PREV_HASH = "0" * 64


def compute_entry_hash(prev_hash: str, payload_dict: Dict[str, Any]) -> str:
    """
    Compute deterministic SHA-256 hash of an audit entry chained to prev_hash.
    
    The payload dictionary is normalized by excluding 'entry_sha256' if present,
    sorted by key, and encoded to canonical UTF-8 JSON.
    """
    canonical_payload = {k: v for k, v in payload_dict.items() if k != "entry_sha256"}
    payload_json = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
    hasher = hashlib.sha256()
    hasher.update(prev_hash.encode("utf-8"))
    hasher.update(b":")
    hasher.update(payload_json.encode("utf-8"))
    return hasher.hexdigest()


class TamperEvidentAuditLedger:
    """
    Manages an append-only JSON Lines audit file with cryptographic SHA-256 hash-chaining.
    """

    def __init__(self, log_path: Union[str, Path]) -> None:
        self.log_path = Path(log_path).resolve()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append_entry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Append a structured event payload to the ledger with hash-chaining.

        Phase 6D.1 FIX: Now verifies the FULL existing chain before appending.
        A tampered or corrupted ledger raises ValueError rather than silently
        continuing from a corrupted final record.

        Parameters
        ----------
        payload : Dict[str, Any]
            Event dictionary.

        Returns
        -------
        Dict[str, Any]
            Committed entry including 'entry_index', 'prev_entry_sha256', and 'entry_sha256'.
        """
        # Phase 6D.1: Verify full chain integrity before appending to prevent
        # silently extending a tampered ledger.
        if self.log_path.exists() and self.log_path.stat().st_size > 0:
            is_valid, entry_count, error_msg = self.verify_chain()
            if not is_valid:
                raise ValueError(
                    f"AUDIT LEDGER CORRUPTED — cannot append new entry. "
                    f"Chain verification failed at entry {entry_count}: {error_msg}. "
                    f"Ledger path: {self.log_path}. "
                    f"Operator intervention required to restore ledger integrity."
                )

        record = dict(payload)

        # Ensure timestamp_utc is present
        if "timestamp_utc" not in record:
            record["timestamp_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()

        # Determine previous hash and next index
        last_index = -1
        prev_hash = GENESIS_PREV_HASH

        if self.log_path.exists() and self.log_path.stat().st_size > 0:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            if lines:
                try:
                    last_record = json.loads(lines[-1])
                    last_index = last_record.get("entry_index", len(lines) - 1)
                    prev_hash = last_record.get("entry_sha256", GENESIS_PREV_HASH)
                except Exception as exc:
                    logger.warning(f"Could not read previous record in {self.log_path}: {exc}")

        entry_index = last_index + 1
        record["entry_index"] = entry_index
        record["prev_entry_sha256"] = prev_hash

        entry_hash = compute_entry_hash(prev_hash, record)
        record["entry_sha256"] = entry_hash

        # Append to log file
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

        return record

    def read_all_entries(self) -> List[Dict[str, Any]]:
        """Read and parse all entries in the ledger."""
        if not self.log_path.exists() or self.log_path.stat().st_size == 0:
            return []
        entries = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                clean_line = line.strip()
                if clean_line:
                    try:
                        entries.append(json.loads(clean_line))
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"Corrupted JSON at line {line_no} in {self.log_path}: {exc}")
        return entries

    def verify_chain(self) -> Tuple[bool, int, Optional[str]]:
        """
        Cryptographically verify the entire audit ledger from genesis to tip.

        Returns
        -------
        Tuple[bool, int, Optional[str]]
            - isValid: True if chain is 100% verified and intact; False otherwise.
            - totalEntries: Number of verified entries.
            - errorMessage: Diagnostic string if verification fails, or None if valid.
        """
        if not self.log_path.exists() or self.log_path.stat().st_size == 0:
            return True, 0, None

        try:
            entries = self.read_all_entries()
        except ValueError as exc:
            return False, 0, f"Malformed entry in ledger: {exc}"
        except Exception as exc:
            return False, 0, f"Read failure in ledger: {exc}"
        expected_prev_hash = GENESIS_PREV_HASH

        for idx, entry in enumerate(entries):
            # 1. Check entry index sequencing
            reported_index = entry.get("entry_index")
            if reported_index != idx:
                return False, idx, (
                    f"Index sequence broken at position {idx}: reported {reported_index}, expected {idx}"
                )

            # 2. Check previous hash linkage
            reported_prev = entry.get("prev_entry_sha256")
            if reported_prev != expected_prev_hash:
                return False, idx, (
                    f"Hash chain broken at position {idx}: reported prev {reported_prev[:12]}..., "
                    f"expected {expected_prev_hash[:12]}..."
                )

            # 3. Check current entry hash
            reported_hash = entry.get("entry_sha256")
            computed_hash = compute_entry_hash(expected_prev_hash, entry)
            if reported_hash != computed_hash:
                return False, idx, (
                    f"Tamper detected at position {idx}: reported hash {reported_hash[:12]}..., "
                    f"computed hash {computed_hash[:12]}..."
                )

            expected_prev_hash = reported_hash

        return True, len(entries), None

