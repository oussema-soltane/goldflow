# CANDIDATE EXPERIMENTS REPORT

**GoldFlow XAUUSD Research Platform**
**Controlled Strategy Candidate Experiments — Phase 6F**
**Date:** 2026-10-29 | **Status:** COMPLETE

---

## 1. Mission Statement

This report documents the results of six controlled research candidate simulations executed against canonical canonical M5 (99,999 bars) and M15 (5,000 bars) datasets. All candidates operate under strict causal isolation: no future bar data is accessed, the frozen SMC v1 configuration is not modified, and transaction costs are applied uniformly.

---

## 2. Candidate Definitions

| ID | Name | Version | Session Filter | Target Method | HTF Required |
|----|------|---------|---------------|--------------|-------------|
| C0 | `SMC_v1_frozen_baseline` | 1.0.0 | None (24h) | Opposing Liquidity | No |
| C1 | `SMC_v2_session_filtered` | 2.0.0-alpha.1 | 07:00–21:00 UTC | Opposing Liquidity | No |
| C2 | `SMC_v2_target_rationalized` | 2.0.0-alpha.2 | None (24h) | Fixed 2.0R | No |
| C3 | `SMC_v2_composite_liquid` | 2.0.0-alpha.3 | 07:00–21:00 UTC | Fixed 2.0R | No |
| C4 | `SMC_v2_ny_session` | 2.0.0-alpha.4 | 13:00–21:00 UTC | Fixed 2.0R | No |
| C5 | `SMC_v2_mtf_aligned` | 2.0.0-alpha.5 | 07:00–21:00 UTC | Fixed 2.0R | Yes (H4+H1) |

---

## 3. Experimental Controls

| Control | Value |
|---------|-------|
| Initial Capital | $10,000 |
| Risk Fraction | 1% per trade |
| Spread | $0.20 per side |
| Slippage | $0.05 per side |
| Commission | $0.00 |
| Data | Canonical local CSVs (no external calls) |
| Causal window | Signal index strictly < current bar |
| HTF data end boundary | Enforced via `data_end_time` parameter |

---

## 4. Full Results Table

### 4.1 M5 Results (99,999 bars)

| Candidate | Trades | Win Rate | Gross P&L | Net P&L | PF | Max DD | Expectancy |
|-----------|--------|----------|-----------|---------|-----|--------|-----------|
| C0 — Baseline | 842 | 27.79% | — | **-$4,955.63** | 0.878 | $6,392.88 | -$5.89 |
| C1 — Session Filter | 539 | 27.83% | — | **-$2,365.82** | 0.928 | $3,975.45 | -$4.39 |
| C2 — Target Rationalized | 1,188 | 31.57% | — | **-$6,543.10** | 0.881 | $7,953.04 | -$5.51 |
| C3 — Composite Liquid | 779 | 32.86% | — | **-$3,507.86** | 0.921 | $4,930.95 | -$4.50 |
| C4 — NY Session | 415 | 31.57% | — | **-$3,623.11** | 0.849 | $4,811.22 | -$8.73 |
| C5 — MTF Aligned | 262 | 30.92% | — | **-$2,412.35** | 0.848 | $3,676.84 | -$9.21 |

### 4.2 M15 Results (5,000 bars)

| Candidate | Trades | Win Rate | Gross P&L | Net P&L | PF | Max DD | Expectancy |
|-----------|--------|----------|-----------|---------|-----|--------|-----------|
| C0 — Baseline | 40 | 20.00% | — | **-$239.12** | 0.913 | $1,632.95 | -$5.98 |
| **C1 — Session Filter** | **29** | **31.03%** | — | **+$479.31** | **1.257** | $900.38 | **+$16.53** |
| C2 — Target Rationalized | 59 | 35.59% | — | **+$282.81** | 1.082 | $846.88 | +$4.79 |
| C3 — Composite Liquid | 35 | 31.43% | — | **-$267.27** | 0.876 | $735.70 | -$7.64 |
| C4 — NY Session | 21 | 23.81% | — | **-$567.22** | 0.604 | $634.83 | -$27.01 |
| C5 — MTF Aligned | 6 | 0.00% | — | **-$515.58** | 0.000 | $515.58 | -$85.93 |

---

## 5. Key Findings

### 5.1 M15 Session Filter (C1) — Best Single Modification

> **M15 C1 result: +$479.31, PF 1.257, Win Rate 31.03%, Expectancy +$16.53/trade**

Simply restricting signals to 07:00–21:00 UTC on M15:
- Eliminates **27% of trades** (from 40 → 29 trades) — removes the poorest-quality off-hours setups
- **Flips M15 from loss (-$239.12) to profit (+$479.31)**
- Increases win rate from 20.00% to 31.03%
- PF improves from 0.913 → 1.257

This is the strongest single-variable improvement observed across all experiments.

### 5.2 M15 Target Rationalization (C2) — Second Best

> **M15 C2 result: +$282.81, PF 1.082, Win Rate 35.59%**

Replacing opposing-liquidity with fixed 2.0R:
- Increases trade count (40 → 59) — more candidates pass the minimum R:R threshold with a deterministic 2.0R target
- Win rate improves to 35.59% (highest of all M15 candidates)
- Positive expectancy at +$4.79/trade

### 5.3 Composite Candidate Underperformance (C3)

The combination of session filter + fixed 2.0R **does not compound** the individual improvements. On M15, C3 shows -$267.27 (PF 0.876) vs C1's +$479.31 and C2's +$282.81. This suggests the session filter and target rationalization address overlapping failure modes — combining them over-restricts the candidate pool to a regime where neither edge survives.

### 5.4 MTF Alignment Collapse (C5)

With only 5,000 M15 bars and a 5,000-bar H4 dataset, the HTF filter leaves only 6 trades — statistically insignificant and catastrophic (-$515.58, PF 0.0). The available data is insufficient to confirm HTF structural alignment across enough qualifying setups.

### 5.5 M5 — No Profitable Candidate Found

All six M5 candidates remain unprofitable. The best M5 result is C1 (session filter) at -$2,365.82 vs C0 baseline -$4,955.63. Session filtering reduces absolute losses by 52% but cannot overcome the structural cost floor at M5 frequency.

---

## 6. Statistical Notes

> [!WARNING]
> M15 sample sizes are small (6–59 closed trades per candidate). Results from 29–59 trades cannot be considered statistically significant. A 2σ confidence interval on a 31% win rate with n=29 spans approximately 14%–48%. The positive M15 results are directionally encouraging but require validation on an independent holdout dataset before drawing firm conclusions.

**Minimum trade count for 80% power (95% CI):** ~200 trades
**Current M15 max:** 59 trades (C2)
**Verdict:** Preliminary signal, not confirmed evidence of edge.

---

## 7. Conclusion and Research Authorization

| Candidate | M5 Verdict | M15 Verdict | Authorized for Holdout |
|-----------|------------|-------------|------------------------|
| C0 — Baseline | ❌ No edge | ❌ No edge | No |
| **C1 — Session Filter** | ❌ Not profitable | **✅ Positive** | **Conditional (more data)** |
| **C2 — Target Rationalized** | ❌ Not profitable | **✅ Positive** | **Conditional (more data)** |
| C3 — Composite Liquid | ❌ No edge | ❌ No edge | No |
| C4 — NY Session | ❌ No edge | ❌ No edge | No |
| C5 — MTF Aligned | ❌ No edge | ❌ Insufficient trades | No |

**Phase 6G recommendation:** Acquire additional M15 data (minimum 500+ additional bars across independent date ranges) to validate C1 and C2 on a held-out period before authorizing forward evaluation.

---

## 8. Artifacts

| File | Description |
|------|-------------|
| `reports/strategy/candidate_experiments_results.json` | Machine-readable full results |
| `reports/strategy/trades_M5_SMC_v1_frozen_baseline.csv` | M5 C0 trade ledger |
| `reports/strategy/trades_M5_SMC_v2_session_filtered.csv` | M5 C1 trade ledger |
| `reports/strategy/trades_M5_SMC_v2_target_rationalized.csv` | M5 C2 trade ledger |
| `reports/strategy/trades_M5_SMC_v2_composite_liquid.csv` | M5 C3 trade ledger |
| `reports/strategy/trades_M5_SMC_v2_ny_session.csv` | M5 C4 trade ledger |
| `reports/strategy/trades_M5_SMC_v2_mtf_aligned.csv` | M5 C5 trade ledger |
| `reports/strategy/trades_M15_SMC_v*.csv` | M15 equivalents |

