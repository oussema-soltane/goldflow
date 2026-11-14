# GOLDFLOW MASTER REPORT INDEX & RESEARCH LINEAGE
## Authoritative Document Catalog, Historical Provenance, and Governance Roadmap

**Last Updated:** 2026-10-30  
**Current Phase:** Phase 6I.0 (Repository Cleanup, Artifact Consolidation, and Structural Integrity)  
**Evaluated Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Git Object Format:** `sha1`  
**Frozen SMC v1 Configuration Hash:** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`  
**Frozen C2 Candidate Specification Hash:** `d09474e02c3dc45165a667742cec5012662e58b95cea78bfd6e5e8d782849916`  

---

## 1. Governance Principles & Index Purpose

The GoldFlow research repository represents a multi-phase quantitative trading and Smart Money Concepts (SMC) research project. Over iterative development cycles, strategies have been formulated, backtested, diagnosed, refuted, or refined.

### Core Documentation Invariants:
1. **Historical Immutability:** Historical research reports are **never deleted, rewritten, or falsified** to match newer findings. Retracted or superseded claims are preserved with explicit status tags.
2. **Clear Successor Lineage:** Every superseded or retracted document explicitly identifies its authoritative successor document.
3. **Cryptographic Identity:** Real Git identifiers are resolved via Git itself (`git rev-parse HEAD`). Discrepancies in historical reports are documented without rewriting history.
4. **Preservation of Raw Research Artifacts:** Trade ledgers, equity curves, validation matrices, and data quality indices are preserved to guarantee scientific reproducibility.

---

## 2. Master Directory Topology

```text
reports/
├── REPORT_INDEX.md                                   <-- This Master Index
├── data_quality_index.json                           <-- Audit ledger of all data quality runs
├── execution_spec_audit.md                           <-- MT5 broker specification audit
├── research_readiness.md                             <-- Initial research readiness baseline
├── phase3e/                                          <-- Phase 3E multi-timeframe experiment outputs
├── phase5/                                           <-- Phase 5 validation reports and metrics
├── phase6/                                           <-- Phase 6 security, decoder, pilot, and calibration reports
├── strategy/                                         <-- Phase 6F, 6G, and 6H strategy research & candidate validations
├── synthetic/                                        <-- Synthetic data quality test reports
└── archive/                                          <-- Pre-recovery and pre-regeneration historical archives
```

---

## 3. Comprehensive Phase-by-Phase Report Catalog

### Phase 3 — SMC Descriptive Research, Event Backtesting & Multi-Timeframe Exploration

| Document Path | Phase | Document Purpose | Status | Successor Document / Notes |
|:---|:---:|:---|:---:|:---|
| [`reports/PHASE3C_SMC_DESCRIPTIVE_RESEARCH.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3C_SMC_DESCRIPTIVE_RESEARCH.md) | 3C | Initial descriptive statistics of SMC structures (FVGs, Order Blocks) on M5/H1 | **HISTORICAL EVIDENCE** | Foundation for event backtester |
| [`reports/PHASE3D_SMC_EVENT_BACKTEST.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D_SMC_EVENT_BACKTEST.md) | 3D | Initial event-driven backtest results for SMC v1 on M5 | **RETRACTED / SUPERSEDED** | **SUPERSEDED** by Phase 6F `LOSS_DECOMPOSITION.md` (unmodeled transaction costs inflated apparent profitability) |
| [`reports/PHASE3D_SMC_EVENT_BACKTEST_COMMON_WINDOW.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D_SMC_EVENT_BACKTEST_COMMON_WINDOW.md) | 3D | Backtest metrics across common temporal window | **RETRACTED / SUPERSEDED** | **SUPERSEDED** by Phase 6F `BASELINE_RECONCILIATION.md` |
| [`reports/PHASE3D_SMC_EVENT_BACKTEST_FULL_HISTORY.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D_SMC_EVENT_BACKTEST_FULL_HISTORY.md) | 3D | Full historical backtest simulation metrics | **RETRACTED / SUPERSEDED** | **SUPERSEDED** by Phase 6F `BASELINE_RECONCILIATION.md` |
| [`reports/PHASE3D_SMC_HOLDOUT_VALIDATION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D_SMC_HOLDOUT_VALIDATION.md) | 3D | Initial holdout validation of SMC v1 | **HISTORICAL EVIDENCE** | Superseded by Phase 6G holdout gate |
| [`reports/PHASE3D_SMC_POSITION_LIFECYCLE_STRESS.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D_SMC_POSITION_LIFECYCLE_STRESS.md) | 3D | Stress-testing fill and exit state machine | **AUTHORITATIVE** | Validates engine state transitions |
| [`reports/PHASE3D2_ANTIGRAVITY_REMEDIATION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D2_ANTIGRAVITY_REMEDIATION.md) | 3D.2 | Remediation of timestamp and path bugs | **HISTORICAL EVIDENCE** | Predecessor to Phase 3D.3 |
| [`reports/PHASE3D3_ANTIGRAVITY_REMEDIATION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D3_ANTIGRAVITY_REMEDIATION.md) | 3D.3 | Remediation of execution specifications | **HISTORICAL EVIDENCE** | Predecessor to Phase 3D.3.2 |
| [`reports/PHASE3D3_EXECUTION_SPEC_GUARDRAILS.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D3_EXECUTION_SPEC_GUARDRAILS.md) | 3D.3 | Implementation of fail-closed MT5 execution checks | **AUTHORITATIVE** | Live contract specification guard |
| [`reports/PHASE3D3_2_CALC_MODE_GUARD.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D3_2_CALC_MODE_GUARD.md) | 3D.3.2 | Dynamic MT5 calculation-mode safety guard | **AUTHORITATIVE** | Rejects non-Forex/CFD modes |
| [`reports/PHASE3D3_2_2_PATH_NORMALIZATION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D3_2_2_PATH_NORMALIZATION.md) | 3D.3.2 | Windows/POSIX path normalization audit | **AUTHORITATIVE** | Prevents cross-platform file bugs |
| [`reports/PHASE3D3_3_INTEGRITY_AND_RESEARCH_HANDOFF.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D3_3_INTEGRITY_AND_RESEARCH_HANDOFF.md) | 3D.3.3 | Integrity handoff and test evidence | **HISTORICAL EVIDENCE** | Predecessor to Phase 3D.3.4 |
| [`reports/PHASE3D3_4_TICK_VALUE_AND_BACKTEST_HANDOFF.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D3_4_TICK_VALUE_AND_BACKTEST_HANDOFF.md) | 3D.3.4 | Tick value calculation and backtest handoff | **AUTHORITATIVE** | Defines contract valuation |
| [`reports/PHASE3E_SMC_MULTI_TIMEFRAME_EXPERIMENT.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3E_SMC_MULTI_TIMEFRAME_EXPERIMENT.md) | 3E | Multi-timeframe (H1/M5) SMC confluence evaluation | **HISTORICAL EVIDENCE** | Predecessor to Phase 5 MTF engine |

---

### Phase 4 — Robustness Analysis & Strategy Validation

| Document Path | Phase | Document Purpose | Status | Successor Document / Notes |
|:---|:---:|:---|:---:|:---|
| [`reports/PHASE4_STRATEGY_VALIDATION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE4_STRATEGY_VALIDATION.md) | 4 | Initial parameter sensitivity and holdout validation | **HISTORICAL EVIDENCE** | Outdated cost assumptions; updated in Phase 6F |
| [`reports/PHASE4_ROBUSTNESS_ANALYSIS.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE4_ROBUSTNESS_ANALYSIS.md) | 4 | Monte Carlo and bootstrap robustness analysis | **HISTORICAL EVIDENCE** | Methodology adopted by Phase 6G |

---

### Phase 5 — Multi-Timeframe Implementation & Dashboard Integration

| Document Path | Phase | Document Purpose | Status | Successor Document / Notes |
|:---|:---:|:---|:---:|:---|
| `reports/phase5/*` | 5 | Phase 5 MTF validation reports, metrics, and Power BI summaries | **HISTORICAL EVIDENCE** | Preserved in `reports/phase5/` (14 files) |

---

### Phase 6 — Enterprise Security, Market Data Ingestion & Calibration

| Document Path | Phase | Document Purpose | Status | Successor Document / Notes |
|:---|:---:|:---|:---:|:---|
| [`reports/phase6/PHASE6_ARCHITECTURE_PROPOSAL.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6_ARCHITECTURE_PROPOSAL.md) | 6 | Architecture proposal for independent data ingestion vault | **HISTORICAL SPEC** | Implemented across Phase 6A–6D |
| [`reports/phase6/PHASE6A_ARCHITECTURE.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6A_ARCHITECTURE.md) | 6A | Partition vault architecture, layout, and hashing model | **AUTHORITATIVE** | Canonical vault layout specification |
| [`reports/phase6/PHASE6A_1_SECURITY_MODEL.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6A_1_SECURITY_MODEL.md) | 6A.1 | Zero-Trust security model and fail-closed network gate | **AUTHORITATIVE** | Security enforcement specification |
| [`reports/phase6/PHASE6A_1_FINAL_VERIFICATION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6A_1_FINAL_VERIFICATION.md) | 6A.1 | Final security verification and test evidence | **AUTHORITATIVE** | Audit sign-off for Phase 6A.1 |
| [`reports/phase6/PHASE6B_PROVIDER_REQUIREMENTS.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6B_PROVIDER_REQUIREMENTS.md) | 6B | Market data provider evaluation requirements | **AUTHORITATIVE** | Evaluates Dukascopy, MT5, TrueFX |
| [`reports/phase6/PHASE6B_RECOMMENDATION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6B_RECOMMENDATION.md) | 6B | Primary provider recommendation (Dukascopy Bank SA) | **AUTHORITATIVE** | Selects Dukascopy historical feed |
| [`reports/phase6/PHASE6C_DECODER_SPECIFICATION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6C_DECODER_SPECIFICATION.md) | 6C | Specification for binary `.bi5` LZMA record parser | **AUTHORITATIVE** | Details 20-byte record format `>3I2f` |
| [`reports/phase6/PHASE6D_CALIBRATION_REPORT.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6D_CALIBRATION_REPORT.md) | 6D | Initial feed calibration attempt and reconciliation | **HISTORICAL EVIDENCE** | Identifies unverified XAUUSD scale prerequisite |
| [`reports/phase6/PHASE6D_1_REMEDIATION_REPORT.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6D_1_REMEDIATION_REPORT.md) | 6D.1 | Ingestion remediation (provenance, immutable partitions) | **AUTHORITATIVE** | Enforces `validate_for_real_network_ingestion` |
| [`reports/phase6/PHASE6D_2_INTEGRITY_VERIFICATION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6D_2_INTEGRITY_VERIFICATION.md) | 6D.2 | Independent adversarial verification of Phase 6D controls | **AUTHORITATIVE** | Authorizes advancement to strategy research |
| [`reports/phase6/PHASE6F_UI_REDESIGN.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6F_UI_REDESIGN.md) | 6F | Professional UI overhaul for Market Analysis & Backtesting | **AUTHORITATIVE** | Implemented on Streamlit pages 1, 2, 3 |
| [`reports/phase6/PHASE6I_DECODER_AUDIT.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6I_DECODER_AUDIT.md) | 6I | Stage A offline price-scale and decoder audit | **AUTHORITATIVE** | Verifies fail-closed gates and struct format |
| [`reports/phase6/PHASE6I_CALIBRATION_PROTOCOL.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6I_CALIBRATION_PROTOCOL.md) | 6I | Stage B single-hour XAUUSD calibration protocol | **AUTHORITATIVE** | Defines 2026-10-15 10:00 UTC calibration quote |
| [`reports/phase6/PHASE6I_CALIBRATION_EVIDENCE.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6I_CALIBRATION_EVIDENCE.md) | 6I | Stage C calibration evidence report | **CURRENT STATUS** | **STATUS: NOT EXECUTED — PENDING OPERATOR AUTHORIZATION** |
| [`reports/phase6/PHASE6I_HISTORICAL_ACQUISITION_PLAN.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6I_HISTORICAL_ACQUISITION_PLAN.md) | 6I | Stage D 12–24-month M15 data acquisition architecture | **AUTHORITATIVE** | Defines polite crawler and 3-tier holdouts |
| [`reports/phase6/PHASE6I_RESEARCH_DATA_ELIGIBILITY.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6I_RESEARCH_DATA_ELIGIBILITY.md) | 6I | Stage E data classification and sample size harmonization | **AUTHORITATIVE** | Reconciles $N \ge 400\text{–}900$ vs $N \approx 3,300$ |
| [`reports/phase6/PHASE6I_0_REPOSITORY_INVENTORY.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6I_0_REPOSITORY_INVENTORY.md) | 6I.0 | Complete repository inventory across Categories A–D | **AUTHORITATIVE** | Established baseline file counts and sizes |
| [`reports/phase6/PHASE6I_0_CLEANUP_REPORT.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6I_0_CLEANUP_REPORT.md) | 6I.0 | Execution report of Level 1 cleanup and Level 2 reviews | **AUTHORITATIVE** | Verification and test results post-cleanup |
| [`reports/phase6/PHASE6I_0_PRESERVATION_MANIFEST.json`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/phase6/PHASE6I_0_PRESERVATION_MANIFEST.json) | 6I.0 | Machine-readable cryptographic preservation manifest | **AUTHORITATIVE** | Records 27 critical immutable assets |

---

### Strategy Research & Candidate Validation (`reports/strategy/`)

| Document Path | Phase | Document Purpose | Status | Key Findings / Outcome |
|:---|:---:|:---|:---:|:---|
| [`reports/strategy/BASELINE_RECONCILIATION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/strategy/BASELINE_RECONCILIATION.md) | 6F | Forensic baseline reconciliation across M5 and M15 | **AUTHORITATIVE** | Uncovered cost model divergence and off-hours drag |
| [`reports/strategy/LOSS_DECOMPOSITION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/strategy/LOSS_DECOMPOSITION.md) | 6F | Forensic loss decomposition of M5 baseline losses | **AUTHORITATIVE** | Proved $3,032 cost drag; identified off-hours decay |
| [`reports/strategy/CANDIDATE_EXPERIMENTS.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/strategy/CANDIDATE_EXPERIMENTS.md) | 6F | Formulation and initial evaluation of candidates C1 and C2 | **AUTHORITATIVE** | M15 C1 (+479, PF 1.257) & C2 (+283, PF 1.082) identified |
| [`reports/strategy/PHASE6G_M15_CANDIDATE_VALIDATION.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/strategy/PHASE6G_M15_CANDIDATE_VALIDATION.md) | 6G | Independent validation gate on unseen holdout | **AUTHORITATIVE** | **C1 REJECTED / NOT PROMOTED** (validation failed: 1 trade, -$11.43). C2 advanced for research. |
| [`reports/strategy/PHASE6G_STATISTICAL_ROBUSTNESS.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/strategy/PHASE6G_STATISTICAL_ROBUSTNESS.md) | 6G | Bootstrap and permutation statistical tests on C1/C2 | **AUTHORITATIVE** | Demonstrated statistical insignificance of small sample ($N=6$) |
| [`reports/strategy/PHASE6G_DATA_ELIGIBILITY.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/strategy/PHASE6G_DATA_ELIGIBILITY.md) | 6G | Data eligibility audit for Phase 6G holdout | **AUTHORITATIVE** | Confirmed all existing M15 bars are now examined |
| [`reports/strategy/PHASE6H_SIMULATION_INTEGRITY_AUDIT.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/strategy/PHASE6H_SIMULATION_INTEGRITY_AUDIT.md) | 6H | Investigation of Phase 6G numerical anomalies | **AUTHORITATIVE** | Resolved Anomaly A ($177.48 identical DD) and Anomaly B (lot size rounding down at 3x costs) |
| [`reports/strategy/PHASE6H_C2_TARGET_AUDIT.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/strategy/PHASE6H_C2_TARGET_AUDIT.md) | 6H | Deep audit of C2 Target Rationalized exit mechanics | **AUTHORITATIVE** | Reconciled fixed 2.0R target vs trailing liquidity exits |
| [`reports/strategy/PHASE6H_STATISTICAL_PLAN.md`](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/strategy/PHASE6H_STATISTICAL_PLAN.md) | 6H | Independent statistical evaluation roadmap for C2 | **AUTHORITATIVE** | Established sample size and power requirements |

---

## 4. Git Revision Discrepancy Note

In several early development reports (Phases 3D through 5), commit identifiers were occasionally abbreviated or recorded from temporary branch states.  
As established by Phase 6D.1 and Phase 6I governance:
- **Canonical Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`
- **Verification Command:** `git rev-parse --verify HEAD`
- **Object Format:** `sha1`

New documentation explicitly references this canonical full hash while preserving historical reports without retroactive alteration.

