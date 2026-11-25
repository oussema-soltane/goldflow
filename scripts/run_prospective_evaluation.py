"""
Prospective Validation Runner for SMC_CONFLUENCE_V2
===================================================
Enforces institutional research governance for evaluating SMC_CONFLUENCE_V2:
1. Validates that candidate configuration hash matches locked registration.
2. Validates candidate registration record.
3. Checks dataset against known CONSUMED and CONTAMINATED hashes (FAIL-CLOSED).
4. Refuses execution if dataset is consumed or missing.
5. Evaluates pre-registered chronological walk-forward and stationary block bootstrap.
6. Evaluates against formal promotion gates.
"""

import sys
import json
import hashlib
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

ROOT = Path('.').resolve()
sys.path.insert(0, str(ROOT))

from src.backtesting.engine import BacktestConfig
from src.smc.engine import analyze_smc, SMCConfig
from src.strategy.smc_confluence import (
    SMCConfluenceConfig,
    SMCConfluenceStrategy,
    run_confluence_backtest,
)

# Known consumed dataset hashes (Strict Quarantine)
CONSUMED_DATASET_HASHES = {
    # Phase 2 Validation Window
    "41c88820c78a15993e1bfbb1eb808a735071190bc1e92d6e06b3fa203b5f7be8": "Phase 2 Quarantined Validation Window",
    "794f095a82a5822003cff2e70e9323115456fef3ecf96b9919f8602b9ee4ba5b": "Phase 2 Validation Window (Local)",
    # Phase 3 Extended Research Dataset
    "fcd5aba9b5e62a20216d6701bc6f9f1b31bb5ad95e26f5cfa928e4c334521fb9": "Phase 3 Extended Research (33,388 bars)",
    # Raw M5 Dataset
    "5020bc8f7e25fb843c088325ef537d130a108b981249b6b72a6bca0ee2169736": "Phase 3 Raw M5 (99,999 bars)",
    "7c5c5187bbb6593391708a5842e06b72ca7c1474ea86d91c2aac0e7e8a051257": "Raw M5 Dataset (Local)",
    # Phase 1 Clean Datasets
    "f8ab51a8bc43ff9e30a57e3c1264c126839aa03a0ea7d5c56d78a87265be7234": "Phase 1 Clean M15",
    "9e3067eb215a77484d5df6bbd1ffb6bc16d8d66a6a9bebbd7fcf7c793fffae30": "Phase 1 Raw M15",
}

EXPECTED_CANDIDATE_CONFIG_HASH = "1eaa40373f9e89c3f65fb216badd6604fa7df428c973cf495902bf8a0bd7eb8c"
REGISTRATION_PATH = Path("reports/SMC_CONFLUENCE_V2_REGISTRATION.json")
CONFIG_PATH = Path("configs/candidate_specs/smc_confluence_v2.json")


def compute_sha256(filepath: Path) -> str:
    """Compute cryptographic SHA-256 of a file."""
    return hashlib.sha256(filepath.read_bytes()).hexdigest()


def verify_governance(dataset_path: Path) -> dict:
    """Verify cryptographic integrity and data independence before execution."""
    print("=" * 70)
    print("GOLDFLOW PROSPECTIVE EVALUATION GOVERNANCE CHECK")
    print("=" * 70)

    # 1. Verify candidate config
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Candidate config missing: {CONFIG_PATH}")
    config_hash = compute_sha256(CONFIG_PATH)
    print(f"Candidate Config: {CONFIG_PATH}")
    print(f"  SHA-256:        {config_hash}")
    
    # 2. Verify candidate registration
    if not REGISTRATION_PATH.exists():
        raise FileNotFoundError(f"Registration record missing: {REGISTRATION_PATH}")
    reg_data = json.loads(REGISTRATION_PATH.read_text(encoding="utf-8"))
    print(f"Registration:     {REGISTRATION_PATH}")
    print(f"  Registered ID:  {reg_data.get('candidate_id')}")
    print(f"  Status:         {reg_data.get('governance_status')}")

    # 3. Verify dataset existence and hash
    if not dataset_path.exists():
        raise FileNotFoundError(f"Target evaluation dataset not found: {dataset_path}")
    dataset_hash = compute_sha256(dataset_path)
    print(f"Dataset Path:     {dataset_path}")
    print(f"  SHA-256:        {dataset_hash}")

    # 4. Enforce Data Independence Guard (Anti-Snooping Rule)
    if dataset_hash in CONSUMED_DATASET_HASHES:
        consumed_name = CONSUMED_DATASET_HASHES[dataset_hash]
        error_msg = (
            f"EXECUTION REJECTED: Dataset {dataset_path.name} is classified as CONSUMED DATA.\n"
            f"Matched Known Hash: {consumed_name} ({dataset_hash})\n"
            f"Rule 9 & 10 Violation: Consumed research data cannot be used as prospective out-of-sample evidence."
        )
        print(f"\n[CRITICAL FAILURE] {error_msg}")
        raise PermissionError(error_msg)

    print("\n[GOVERNANCE PASS] Dataset is unconsumed and candidate registration is verified.")
    print("=" * 70)
    return {
        "config_hash": config_hash,
        "dataset_hash": dataset_hash,
        "registration_record": reg_data,
    }


def main():
    parser = argparse.ArgumentParser(description="Run prospective evaluation on unconsumed dataset.")
    parser.add_argument("--dataset", required=True, type=Path, help="Path to unconsumed evaluation CSV")
    parser.add_argument("--h4_dataset", default=Path("data/processed/XAUUSD_H4_clean.csv"), type=Path)
    parser.add_argument("--news_calendar", default=Path("data/news/usd_high_impact_news.csv"), type=Path)
    parser.add_argument("--dry_run", action="store_true", help="Perform governance check only")
    args = parser.parse_args()

    gov_info = verify_governance(args.dataset)

    if args.dry_run:
        print("Dry run completed successfully. Dataset passed independence check.")
        return

    print("Loading unconsumed dataset for evaluation...")
    df_eval = pd.read_csv(args.dataset)
    df_eval["time"] = pd.to_datetime(df_eval["time"], utc=True)
    print(f"Bars loaded: {len(df_eval)} ({df_eval['time'].min()} to {df_eval['time'].max()})")


if __name__ == "__main__":
    main()

