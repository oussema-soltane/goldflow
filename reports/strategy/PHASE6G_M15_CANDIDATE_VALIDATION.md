# PHASE 6G — M15 Candidate Validation Report

**GoldFlow XAUUSD Research Platform**
**Phase 6G — Frozen Candidate Evaluation on Untouched M15 Data**
**Date:** 2026-10-30 | **Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`

---

## 1. Evaluation Setup

### Validation Window

| Property | Value |
|----------|-------|
| Source | `data/raw/XAUUSD_M15_raw.csv` — bars beyond processed boundary |
| Window SHA-256 | `794f095a82a582200e4260b572aa68f08875ce321d902eb2610c16694657ced3` |
| Start (UTC) | 2026-10-22 09:30:00 |
| End (UTC) | 2026-10-29 22:30:00 |
| Total bars | 509 |
| Calendar days | 7 |
| Intra-window gaps (>30 min) | 5 (weekend/session close gaps — normal) |
| Price range | $3,977.79 – $4,098.79 |

### Frozen Candidate Specifications

| ID | Name | Session Filter | Target Method | HTF |
|----|------|---------------|--------------|-----|
| **C0** | SMC_v1_frozen_baseline v1.0.0 | None (24h) | Opposing Liquidity | No |
| **C1** | SMC_v2_session_filtered v2.0.0-alpha.1 | 07:00–21:00 UTC | Opposing Liquidity | No |
| **C2** | SMC_v2_target_rationalized v2.0.0-alpha.2 | None (24h) | Fixed 2.0R | No |

Specifications locked in `reports/strategy/phase6g_frozen_candidate_specs.json` (hash: `2d60421d…`) before any validation run.

### Execution Parameters (identical to Phase 6F)

| Parameter | Value |
|-----------|-------|
| Initial capital | $10,000.00 |
| Risk fraction | 1% per trade |
| Spread (per side) | $0.20 |
| Slippage (per side) | $0.05 |
| Commission | $0.00 |
| Max concurrent positions | 1 |

---

## 2. Validation Results

### Summary Table

| Candidate | Signals Detected | Filtered | Closed Trades | Win Rate | Net P&L | PF | Max DD | Expectancy |
|-----------|-----------------|----------|---------------|----------|---------|-----|--------|-----------|
| C0 Baseline | 5 | 5 | **5** | 40.0% | **+$97.61** | 1.353 | $177.48 | +$19.52 |
| **C1 Session Filter** | 5 | 4 | **4** | 25.0% | **-$83.12** | **0.699** | $177.48 | -$20.78 |
| C2 Target Rationalized | 7 | 7 | **6** | 50.0% | **+$265.02** | 1.959 | $177.48 | +$44.17 |

> [!CAUTION]
> **C1 is NEGATIVE on the only available unseen data.** PF = 0.699, net P&L = -$83.12 across 4 trades. This is the opposite direction from the Phase 6F development result (PF 1.257, +$479.31).

### C0 vs C1 Signal Delta

C0 detected 5 setups; C1 filtered 1 (fell outside 07:00–21:00 UTC). The excluded trade was presumably an off-hours signal. With 5 total setups on 509 bars, the signal density on this window (~1 per 100 bars) is consistent with the development data (~40 setups / 5,000 bars = 1 per 125 bars).

### C1 Individual Trades (all 4)

| # | Signal Time (UTC) | Direction | Net P&L | Reason |
|---|-------------------|-----------|---------|--------|
| 1 | 2026-10-23 ~09:45 | — | — | *ledger omitted for brevity — see phase6g_validation_trades_C1.csv* |
| … | | | Net: -$83.12 total | 1 win, 3 losses |

### Cost Sensitivity — C1 on Validation Window

| Cost Multiplier | Trades | Net P&L | Profit Factor |
|----------------|--------|---------|---------------|
| 1× (baseline: $0.25/side) | 4 | -$83.12 | 0.699 |
| 2× ($0.50/side) | 4 | -$85.47 | 0.693 |
| 3× ($0.75/side) | 4 | -$76.63 | 0.715 |

C1 is negative at all cost levels on this window. The loss is not cost-driven (costs are only ~$10 total on 4 trades); it is due to losing trades in the price-movement dimension.

---

## 3. Chronological Segment Analysis

With only 4 C1 trades across 7 calendar days, no meaningful chronological breakdown is possible. The entire validation window represents a single market episode (XAUUSD during the week of 22–29 October 2026).

---

## 4. Comparison: Development vs. Validation

| Metric | Phase 6F (Dev, 5,000 bars) | Phase 6G (Val, 509 bars) |
|--------|--------------------------|--------------------------|
| C0 trades | 40 | 5 |
| C0 PF | 0.913 | **1.353** |
| C0 net P&L | -$239.12 | **+$97.61** |
| C1 trades | 29 | **4** |
| C1 PF | 1.257 | **0.699** |
| C1 net P&L | +$479.31 | **-$83.12** |

**The sign of C1's net P&L reversed on the validation window.**
**C0, the unmodified baseline, was positive on the validation window.**

This is a single data point from a 7-day window and is not conclusive evidence of either direction. But it does not support the hypothesis that C1 has a persistent edge.

---

## 5. Session Filter Behavior on Validation Window

The validation window (2026-10-22 to 2026-10-29) spans the European daylight saving transition (clocks went back 2026-10-25 01:00 UTC). The session filter uses fixed UTC hours (07:00–21:00) without DST adjustment. This means:
- Pre-DST: London session = 07:00–16:00 UTC (correctly captured by filter)
- Post-DST (after Oct 25): London session = 08:00–17:00 UTC (the filter still admits 07:00 bars, which are now pre-market)

This DST ambiguity affects approximately 4 bars per day in the transition week — a minor but real specification defect in C1.

---

## 6. Promotion Decisions

### C0 — SMC_v1_frozen_baseline

**Verdict: INCONCLUSIVE**

C0 was negative on the 5,000-bar development set (PF 0.913, -$239.12) but positive on the 7-day validation window (PF 1.353, +$97.61). Neither result is statistically meaningful at these sample sizes. C0 remains the control benchmark.

### C1 — SMC_v2_session_filtered

**Verdict: INCONCLUSIVE**

The Phase 6F development PF of 1.257 was driven by 3 trades contributing 310% of total profit in a single month (September 2026). The bootstrap 90% interval for PF spans [0.450, 2.593]. The single available validation observation (4 trades, PF 0.699) is directionally negative but statistically uninformative. The session filter hypothesis — that London/NY hours produce better edge — was derived from the same dataset it is being tested on; it requires genuinely independent evaluation.

**C1 is not rejected but cannot be promoted.** The honest conclusion is: insufficient data exists to determine whether C1 has a repeatable edge.

### C2 — SMC_v2_target_rationalized

**Verdict: INCONCLUSIVE**

C2 was positive on both development (PF 1.082, +$282.81, n=59) and validation (PF 1.959, +$265.02, n=6). This is the only candidate with consistent directional positive performance, but n=6 on validation is statistically meaningless. C2 warrants further investigation with substantially more data.

---

## 7. What Is Required for a Meaningful Evaluation

To reach **ELIGIBLE FOR FURTHER EVALUATION** status, minimum requirements are:
- At least 200 out-of-sample closed trades per candidate
- Data spanning at least 6 months with multiple volatility regimes
- Independent of all development data used in Phase 6F
- Cleaned and validated through the canonical data pipeline

**Current available unseen data: 4–6 trades over 7 days. This is approximately 2% of the minimum threshold.**

