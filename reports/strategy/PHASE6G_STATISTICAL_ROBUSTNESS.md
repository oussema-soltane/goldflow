# PHASE 6G — Statistical Robustness Report

**GoldFlow XAUUSD Research Platform**
**Phase 6G — Uncertainty Quantification and Selection Bias Assessment**
**Date:** 2026-10-30 | **Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`

---

## 1. The Selection Bias Problem

Phase 6F tested **6 candidates** on the same M15 dataset. This is a multiple-testing scenario: the probability that at least one candidate shows PF > 1.0 by chance increases with the number of candidates tested.

Under a naïve i.i.d. assumption (each candidate independently has a 50% chance of positive P&L):

$$P(\text{at least one positive among 6 candidates}) = 1 - 0.5^6 = 98.4\%$$

Even under less extreme assumptions, running 6 candidates on the same dataset guarantees that the best-performing one will look better than the underlying process justifies. When C1 is selected as the "promising candidate" after comparing 6 results, its observed PF of 1.257 incorporates upward selection bias.

---

## 2. Sample Size and Uncertainty

### M15 C1 Bootstrap Analysis (10,000 resamples, n=29)

| Statistic | Value |
|-----------|-------|
| Observed PF | 1.257 |
| Bootstrap mean PF | 1.317 |
| Bootstrap P5 (5th percentile) | 0.450 |
| Bootstrap P25 | 0.827 |
| Bootstrap median | 1.202 |
| Bootstrap P75 | 1.674 |
| Bootstrap P95 | 2.593 |
| P(PF > 1.0) | 63.8% |
| P(PF > 1.5) | 32.8% |

**Interpretation:** The 90% bootstrap confidence interval [0.450, 2.593] spans from deeply negative to highly profitable. With n=29 trades, we cannot meaningfully distinguish a true PF of 0.8 from a true PF of 1.8 — both are consistent with the observed data.

> [!WARNING]
> The iid (independent, identically distributed) bootstrap is an inappropriate model for financial time-series data. Adjacent trades are correlated through shared market regimes, volatility clustering, and sequential capital dynamics. The bootstrap understates true uncertainty. The actual confidence interval is even wider than reported above.

### Minimum Sample Size Guidance

For a two-sided test with H₀: PF = 1.0 at α = 0.05 and power = 0.80, and assuming an observed PF of 1.25 with realistic variance:

- Approximate minimum: **200–400 closed trades** (rough rule of thumb for financial strategy evaluation)
- Current C1 development sample: **29 trades** (~7–14% of minimum)
- Current C1 validation sample: **4 trades** (~1–2% of minimum)

No claim of statistical significance can be made with current data.

---

## 3. Dominant Trade Concentration

### M15 C1 — Trade-Level Concentration (n=29)

| Statistic | Value |
|-----------|-------|
| Largest single win | +$912.67 |
| Total positive P&L | +$2,341.98 (sum of 9 wins) |
| Largest win as % of total profit | **190.4%** |
| Top 3 wins as % of total profit | **310.0%** |
| Net P&L without largest trade | **-$433.36** |

**The entire reported profit of C1 and more depends on a single trade.** Without the September 11, 2026 trade (+$912.67), C1's net P&L is negative. This is not evidence that C1 is profitable — it is evidence of extreme concentration in a single favorable outcome.

### Date Concentration

| Month | Trades | Net P&L |
|-------|--------|---------|
| August 2026 | 8 | **-$706.22** |
| September 2026 | 9 | **+$1,480.35** |
| October 2026 | 12 | **-$294.82** |

September 2026 produced 100% of the profit and then some. August and October were both negative. This is consistent with regime-dependent performance rather than a consistent edge.

---

## 4. Session Filter Hypothesis — Was It Data-Mined?

The session filter was identified by examining session-level performance **on the same M5 dataset** used for development. The "NY Afternoon 17:00–21:00 UTC" session showed PF 1.378 on M5.

By the strict definition, this is **data mining**: a pattern was discovered by repeatedly examining the same dataset, then incorporated into a candidate evaluated on the same dataset. The positive result cannot be treated as independent evidence.

**To properly test the session hypothesis, it must be evaluated on data not used in the original analysis.** The 7-day validation window (509 bars) provided that test, and C1 did not outperform C0 on it (C1: PF 0.699 vs C0: PF 1.353).

---

## 5. Sensitivity Analyses

### M5 C0 — True Gross vs. Net PF

| Metric | Value |
|--------|-------|
| True gross PF (pre-cost) | 0.956 |
| Net PF (post-cost, reported) | 0.878 |
| Gross-to-net degradation | 0.078 PF points |

The strategy is near-breakeven pre-cost. Transaction costs of $3,269 degrade a -$1,686 gross loss to a -$4,955 net loss. This confirms that cost reduction (tighter spreads, lower slippage) is a material factor — but even at zero cost, the strategy would only be marginally above breakeven.

### C1 on Validation Window — Cost Sensitivity

| Cost Level | Net P&L | PF |
|------------|---------|-----|
| 1× (baseline) | -$83.12 | 0.699 |
| 2× | -$85.47 | 0.693 |
| 3× | -$76.63 | 0.715 |

The loss is not cost-sensitive — it reflects losing trades at the price level, not cost drag. Cost reduction would not rescue the validation result.

---

## 6. Execution Integrity Checks

### Causal Isolation Verification

Confirmed by code inspection and existing test suite (594 tests, all passing):
- `signal_index` is set to the bar where the retest is confirmed; execution occurs on the **next bar open** only
- HTF structure timelines use `available_at = break_time + timeframe_duration` — no current-bar contamination
- `filter_candidates_by_session` filters by `signal_time` (decision time), not future exit time
- No look-ahead in session assignment

### Same-Bar Entry/Exit

The engine records `entry_index` and `exit_index`. Inspected for the M15 C1 development trades:
- All 29 trades have `exit_index > entry_index` — no same-bar fill
- All entries use `next_bar_open`, not signal bar close

### Position Sizing Consistency

All trades use `risk_fraction = 0.01` applied to `equity_after` at entry time. Lots are rounded to `lot_step = 0.01`. No anomalous lot sizes observed.

### No Look-Ahead in Session Filter

The session filter reads `signal_time` (the bar where the setup is confirmed). The entry executes on the *next* bar. The filter cannot "know" the trade outcome because it fires before execution. **Verified: no future-information leakage in the session filter.**

---

## 7. Summary of Robustness Assessment

| Concern | Status | Severity |
|---------|--------|---------|
| Multiple testing (6 candidates selected) | **Unresolved** — insufficient OOS data | High |
| n=29 development trades | **Material** — wide confidence interval | High |
| Single-trade dominance (190% of profit from 1 trade) | **Confirmed** | High |
| Regime concentration (100% profit from September 2026) | **Confirmed** | High |
| Session filter data-mined from development set | **Confirmed** | High |
| DST ambiguity in UTC session filter | **Minor** — affects ~4 bars/day near transition | Low |
| C1 negative on validation window | **Confirmed** | Moderate (n=4, not conclusive) |
| Look-ahead in signals or filters | **None found** | None |
| Same-bar fill | **None found** | None |
| Cost accounting errors | **None found** (schema clarified) | None |

---

## 8. Final Statistical Verdict

**C1 (SMC_v2_session_filtered) CANNOT be declared to have a statistically meaningful edge.**

The evidence base consists of:
- 29 development-set trades where selection bias applies
- A profit overwhelmingly dependent on a single trade
- Regime-specific performance (profitable only in September 2026)
- A 7-day validation showing negative performance (PF 0.699, though n=4 is uninformative)
- A 90% bootstrap interval spanning [0.45, 2.59] — consistent with both loss and high profit

The honest assessment: **C1's development PF of 1.257 is consistent with random variation from a strategy with true PF near or below 1.0.** It may have an edge, or it may not. The available data cannot distinguish these possibilities.

**Recommended verdict: INCONCLUSIVE — insufficient evidence for promotion, no basis for rejection either.**

