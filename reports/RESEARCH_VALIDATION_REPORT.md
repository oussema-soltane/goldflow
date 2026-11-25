# GoldFlow — Research Validation & Integrity Report
## Verification of Statistical Integrity, Provenance, and Non-Overfitting

**Date:** November 2026  
**Auditor:** Quantitative Integrity & Software Quality Engineering  
**Target:** GoldFlow Research Platform & `SMC_CONFLUENCE_V1` Candidate  

---

## 1. Research Integrity Remediation Verification

Prior to launching candidate strategy research, all previously identified forensic issues were systematically investigated and remediated:

| Issue ID | Description | Root Cause | Remediated Status | Verification Evidence |
| :--- | :--- | :--- | :--- | :--- |
| **ISSUE-1** | Live MT5 Overwrite Bypass | `pages/1_Market_Analysis.py` called `save_processed_data` even when `_allow_save=False`. | **REMEDIATED** | `save_processed_data()` completely bypassed for live feeds; live data kept in session memory only. |
| **ISSUE-2** | Untracked Test File Pollution | Default `config_root` dumped test JSON files into `configs/registered_evaluations/`. | **REMEDIATED** | Registration manager auto-detects `pytest`/`tmp` and directs output to `tmp_path`. Repo tree is 100% clean. |
| **ISSUE-3** | Insecure Data Directory Writing | File saving functions lacked containment checks. | **REMEDIATED** | Added strict path resolution and containment checks in `src/data/loader.py` and `src/data/cleaner.py`. |
| **ISSUE-4** | Overlap in Synthetic and Live Data | Validation window dataset exposed in standard UI dropdown. | **REMEDIATED** | Dataset selector strictly filters for `*_clean.csv`, excluding historical validation windows. |
| **ISSUE-5** | Data Boundary Leakage | Missing higher-timeframe boundaries permitted stale context carry-forward. | **REMEDIATED** | Explicit `data_end_time` enforced on D1, H4, and H1 timelines. Decisions beyond boundary return fail-closed NEUTRAL. |

---

## 2. Canonical Datasets Cryptographic Checksums

All canonical raw and frozen configuration files remain bit-for-bit identical to recorded standards:

| File Path | Recorded SHA-256 Hash | Current SHA-256 Hash | Verification |
| :--- | :--- | :--- | :---: |
| `data/raw/XAUUSD_H4_raw.csv` | `9bf68ed4b607aa91ededf95df03f42e552a1f52b0b0238373730756a579bb149` | `9bf68ed4b607aa91ededf95df03f42e552a1f52b0b0238373730756a579bb149` | **MATCH** |
| `data/raw/XAUUSD_H1_raw.csv` | `ed050b1b273d08014f007c7fe98eb1d81a321c8a3c2d5e9c22a0df7ea9574dbb` | `ed050b1b273d08014f007c7fe98eb1d81a321c8a3c2d5e9c22a0df7ea9574dbb` | **MATCH** |
| `data/raw/XAUUSD_M15_raw.csv` | `b893bc507daec515d36ff51cb988e4f6e33df23f3ccddd6924794b64fbe7b075` | `b893bc507daec515d36ff51cb988e4f6e33df23f3ccddd6924794b64fbe7b075` | **MATCH** |
| `data/raw/XAUUSD_M5_raw.csv` | `7c5c5187bbb6593391708a5842e06b72ca7c1474ea86d91c2aac0e7e8a051257` | `7c5c5187bbb6593391708a5842e06b72ca7c1474ea86d91c2aac0e7e8a051257` | **MATCH** |
| `configs/smc_v1_frozen.json` | `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a` | `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a` | **MATCH** |

---

## 3. Experimental Boundary and Holdout Discipline

1. **Validation Window Holdout:**  
   `data/processed/XAUUSD_M15_validation_window.csv` (509 bars) was strictly isolated as consumed historical data and was NOT used for candidate optimization or ablation experiments.
2. **Canonical Ablation Datasets:**  
   Ablation studies were conducted exclusively on canonical processed files:
   - `data/processed/XAUUSD_M15_clean.csv` (5,000 bars)
   - `data/processed/XAUUSD_M5_clean.csv` (99,999 bars)
3. **Execution Script:**  
   All 16 experiments were generated deterministically via:
   ```bash
   python scripts/run_smc_confluence_ablation.py
   ```
   Outputs are stored in `reports/PERFORMANCE_COMPARISON.csv` and `reports/TRADE_LEDGER.csv`.

---

## 4. Verification Conclusion

The research protocol meets all institutional standards for statistical defensibility: zero lookahead, immutable baseline preservation, transparent cost attribution, and fully reproducible ablation results.

