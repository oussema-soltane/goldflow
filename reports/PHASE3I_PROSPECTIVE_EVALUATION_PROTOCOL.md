# PHASE 3I: PROSPECTIVE EVALUATION PROTOCOL FOR SMC_CONFLUENCE_V2
**Subsystem:** Quantitative Governance, Evaluation Automation & Anti-Snooping Guardrails  
**Target Candidate:** `SMC_CONFLUENCE_V2` (Registered SHA-256: `1eaa40373f9e89c3f65fb216badd6604fa7df428c973cf495902bf8a0bd7eb8c`)  
**Runner Module:** `scripts/run_prospective_evaluation.py`  
**Protocol Status:** **LOCKED & PRE-REGISTERED (FAIL-CLOSED)**  
**Protocol Date:** 2026-11-17  

---

## 1. Executive Summary & Purpose

The Prospective Evaluation Protocol establishes an immutable, cryptographically enforced execution harness for evaluating `SMC_CONFLUENCE_V2` when an unconsumed XAU/USD historical dataset becomes available.

To eliminate hindsight bias, data snooping, and retrospective parameter tuning, this protocol:
1. Locks the candidate configuration, hash, and registration records.
2. Embeds an anti-snooping cryptographic blacklist that automatically blocks evaluation if any previously consumed dataset is supplied.
3. Pre-specifies all evaluation folds, execution friction models, bootstrap parameters, and promotion gates before seeing prospective data.

---

## 2. Cryptographic Pre-Requisites & Verification Workflow

Before running the evaluation harness, the prospective runner automatically verifies:

```
┌──────────────────────────────────────────────────────────┐
│          AUTOMATED GOVERNANCE VERIFICATION GATE          │
├──────────────────────────────────────────────────────────┤
│ 1. Candidate Config Hash == 1eaa4037...                  │
│ 2. Registration Record == SMC_CONFLUENCE_V2 (LOCKED)     │
│ 3. Target Dataset Hash NOT IN CONSUMED_DATASET_HASHES    │
│ 4. Target Dataset Duration >= 10,000 bars                │
└────────────────────────────┬─────────────────────────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
      [MATCH CONSUMED]                  [UNCONSUMED]
            │                                 │
            ▼                                 ▼
    [FAIL-CLOSED STOP]               [PROCEED TO WF EVAL]
   PermissionError Raised             10-Fold Simulation
```

### Script Execution Syntax:
```powershell
python scripts/run_prospective_evaluation.py `
  --dataset data/research/phase3i/processed/XAUUSD_M15_phase3i_clean.csv `
  --h4_dataset data/research/phase3i/processed/XAUUSD_H4_phase3i_clean.csv `
  --news_calendar data/news/usd_high_impact_news.csv
```

---

## 3. Evaluation Dimensions & Methodology

### 3.1 Dimension A: Chronological Walk-Forward Validation
- **Partitioning:** 10 equal-duration chronological folds spanning the entire unconsumed dataset.
- **Window Architecture:** Anchored expanding in-sample training window with rolling out-of-sample evaluation folds.
- **Fold Gate:** A fold with 0 trades is recorded as `NO_TRADES` (neither positive nor negative).
- **Minimum Threshold:** $\ge 70.0\%$ of active out-of-sample folds must achieve positive Net P&L.

### 3.2 Dimension B: Stationary Block Bootstrap Robustness
- **Algorithm:** Politis & Romano (1994) Stationary Block Bootstrap.
- **Mean Block Length ($L$):** $L = 5$ trades (continuation probability $p = 0.20$).
- **Resample Budget ($B$):** $10,000$ resamples.
- **Random Seed:** Fixed seed `42` initialized per evaluation.
- **Confidence Interval Gate:** 95% Confidence Interval Lower Bound for Profit Factor must be strictly $> 1.000$.
- **Hypothesis Test Gate:** One-tailed Student's $t$-test for mean net P&L $> 0$ must achieve $p < 0.05$.

### 3.3 Dimension C: Market Regime & Session Stability
- **Session Attribution:** Performance decomposed across London (07:00–13:00 UTC), NY Overlap (13:00–17:00 UTC), and off-hours.
- **Regime Attribution:** Performance decomposed into Trending ($\text{ADX} > 22.0$) and Ranging ($\text{ADX} \le 22.0$).
- **Stability Gate:** Trending regime out-of-sample Profit Factor must exceed $1.30$.

### 3.4 Dimension D: Execution Realism & Friction Stress
- **Baseline Friction:** \$0.20 spread + \$0.05 adverse slippage per side (\$0.30/oz roundtrip).
- **Friction Stress Multiplier (2.0x):** Strategy must be re-evaluated at \$0.40 spread + \$0.10 slippage per side (\$0.60/oz roundtrip).
- **Stress Gate:** Strategy must maintain positive Net P&L under 2.0x doubled friction.

---

## 4. Formal Institutional Promotion Gates

To achieve qualification for Demo Trading Incubation, `SMC_CONFLUENCE_V2` must pass ALL six gates simultaneously on the unconsumed dataset:

| Gate ID | Description | Benchmark / Threshold | Action on Failure |
|:---:|---|:---:|:---:|
| **GATE-1** | Minimum Out-of-Sample Trades | $N \ge 100$ completed trades | **FAIL (REMAIN IN RESEARCH)** |
| **GATE-2** | Walk-Forward Positive Fold Ratio | $\ge 70.0\%$ positive folds | **FAIL (REMAIN IN RESEARCH)** |
| **GATE-3** | Out-of-Sample Profit Factor | Aggregate OOS $\text{PF} \ge 1.30$ | **FAIL (REMAIN IN RESEARCH)** |
| **GATE-4** | Bootstrap Lower Bound | 95% CI Lower Bound $> 1.000$ | **FAIL (REMAIN IN RESEARCH)** |
| **GATE-5** | Statistical Hypothesis Test | Parametric $t$-test $p < 0.05$ | **FAIL (REMAIN IN RESEARCH)** |
| **GATE-6** | Friction Stress Resilience | Positive Net P&L at 2.0x costs | **FAIL (REMAIN IN RESEARCH)** |

**Strict Fiduciary Rule:** No gate may be lowered, waived, or averaged out. Failure of any single gate results in an immediate **FAIL** verdict. The strategy will remain in research.

