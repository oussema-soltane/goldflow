# PHASE 3H: UNSEEN EVALUATION & DATASET INVENTORY REPORT
**Subsystem:** Financial Data Engineering, Holdout Integrity & Out-of-Sample Verification  
**Auditor:** Lead Quantitative Research Engineer & Independent Research Auditor  
**Repository Branch:** `audit/phase3f-3h`  
**Base Commit:** `9566e6e`  
**Audit Status:** **EVALUATION HALTED (ZERO UNTOUCHED HOLDOUTS AVAILABLE IN REPOSITORY)**  
**Audit Date:** 2026-11-17  

---

## 1. Executive Summary & Governance Directive

The Master Quantitative Research Directive establishes an uncompromised standard of scientific integrity:
> *"The existing 17-month dataset has already been used for research and candidate selection. Do not describe it as an untouched holdout. Use a clearly identified evaluation dataset that was not used to choose the V2 rules or parameters. If no suitable untouched dataset is available, report this explicitly. Do not silently use previously consumed validation data... Only generate Phase 3H evaluation results when a genuinely suitable untouched dataset is available. Otherwise, document the missing evidence and stop before evaluation."*

Following this directive, an exhaustive cryptographic inventory of all data assets in the GoldFlow repository was conducted.

**Forensic Finding:** Every historical XAU/USD dataset currently residing in `data/` has been consumed during Phase 2 or Phase 3 exploratory research. **Zero untouched out-of-sample datasets exist in the repository.**

In strict adherence to research governance, simulated backtesting of `SMC_CONFLUENCE_V2` on the existing dataset was **HALTED**. Evaluating `SMC_CONFLUENCE_V2` on the same 33,388 bars used to formulate its ADX and session parameters would constitute circular in-sample curve fitting and violate Non-Negotiable Rules 9 and 10.

---

## 2. Complete Repository Data Asset Inventory

| File Path | Bar Count | Time Span Covered | Historical Research Consumption Status | Cryptographic SHA-256 Hash |
|---|:---:|:---:|---|---|
| `data/processed/XAUUSD_M15_validation_window.csv` | 5,760 | Consumed in Phase 2 | **CONSUMED & QUARANTINED:** Must NEVER be reused for validation. | `41c88820c78a15993e1bfbb1eb808a735071190bc1e92d6e06b3fa203b5f7be8` |
| `data/research/phase3/processed/XAUUSD_M15_extended.csv` | 33,388 | Oct 2024 – Mar 2026 | **CONSUMED:** Exhaustively backtested in Phase 3 (EXP_A through EXP_K) and Phase 3F ablation matrix. | `fcd5aba9b5e62a20216d6701bc6f9f1b31bb5ad95e26f5cfa928e4c334521fb9` |
| `data/raw/XAUUSD_M5_raw.csv` | 99,999 | Oct 2024 – Mar 2026 | **CONSUMED:** Direct source dataset used to aggregate `XAUUSD_M15_extended.csv`. | `5020bc8f7e25fb843c088325ef537d130a108b981249b6b72a6bca0ee2169736` |
| `data/processed/XAUUSD_M15_clean.csv` | 24,960 | 2024 – 2025 | **CONSUMED:** Used in early Phase 2 baseline calibration. | `f8ab51a8bc43ff9e30a57e3c1264c126839aa03a0ea7d5c56d78a87265be7234` |
| `data/raw/XAUUSD_M15_raw.csv` | 25,000 | 2024 – 2025 | **CONSUMED:** Source of `XAUUSD_M15_clean.csv`. | `9e3067eb215a77484d5df6bbd1ffb6bc16d8d66a6a9bebbd7fcf7c793fffae30` |
| `data/processed/XAUUSD_H4_clean.csv` | 2,750 | 2022 – 2026 | **CONSUMED:** Used continuously for higher-timeframe trend context. | `91d9237ff4d3ff5c13b2c3fae6dbe69db6e5e8e7b39a444a7f0e9fa658e39097` |
| `data/processed/XAUUSD_H1_clean.csv` | 11,000 | 2023 – 2026 | **CONSUMED:** Used in Multi-Timeframe Phase 3E experiments. | `e1d4d80a1c97a5e82b7b252ce5ea4ef0da040c5f42c30084f7b6009825b39be3` |
| `data/synthetic/*` | Synthetic | Mocks | **TEST MOCKS ONLY:** Non-market data used solely for pytest assertions. | N/A (Mocks) |
| `data/quarantine/*` | Various | Corrupted | **QUARANTINED:** Defective legacy files isolated during historical audits. | Quarantined |

---

## 3. Methodological Justification for Halting Evaluation

1. **Circular Optimization Risk:**  
   The quantitative specifications for `SMC_CONFLUENCE_V2` (specifically the $\text{ADX} > 22.0$ regime threshold and the 07:00–17:00 UTC session restriction) were derived directly from the empirical observations of the Phase 3 trade ledger and the Phase 3F 16-variant ablation matrix. Running a backtest of V2 on this same data would merely confirm what is already known: that filtering out ranging bars and Asian hours improves in-sample numbers. It would prove nothing about whether the edge persists on future unseen data.
2. **Protection Against Overfitting Illusions:**  
   In institutional quantitative finance, treating consumed data as an "unseen holdout" is classified as scientific fraud (Type I data snooping). True out-of-sample validation requires data that was physically unavailable or completely sequestered during the hypothesis formulation stage.
3. **Strict Adherence to Research Protocol:**  
   The pre-registration document `reports/SMC_CONFLUENCE_V2_REGISTRATION.json` explicitly mandates:
   > *"Must be evaluated exclusively on an unconsumed historical dataset strictly disjoint from all consumed data... No retrospective parameter adjustment permitted within an evaluation dataset."*

---

## 4. Requirements for Future Phase 3H Execution

To resume Phase 3H and execute a valid out-of-sample evaluation of `SMC_CONFLUENCE_V2`, the data engineering team must ingest and cryptographically verify one of the following pristine datasets:

1. **Forward Out-of-Sample Window:**  
   High-quality M5/M15 tick-aggregated XAU/USD data from April 1, 2026 to the current calendar date, sourced from a commercial institutional liquidity provider (e.g. Dukascopy, LMAX, or Darwinex).
2. **Historical Holdout Window (Pre-October 2024):**  
   Continuous M5/M15 tick-aggregated XAU/USD data covering January 2023 through September 2024 that has never been ingested into GoldFlow.
3. **Cross-Asset / Broker Feed Replication:**  
   Independent tick feed from an alternate institutional broker covering the same time window to test spread and quote sensitivity.

Until such a dataset is ingested, hashed, and registered in a new manifest, `SMC_CONFLUENCE_V2` remains in **PRE_REGISTERED_FROZEN** status.
