# PHASE 3I: CANDIDATE SPECIFICATION RECONCILIATION & GOVERNANCE AUDIT
**Subsystem:** Strategy Specification Governance, Parameter Provenance & In-Sample Selection Disclosure  
**Candidate:** `SMC_CONFLUENCE_V2` (Registered SHA-256: `1eaa40373f9e89c3f65fb216badd6604fa7df428c973cf495902bf8a0bd7eb8c`)  
**Audit Status:** **RECONCILED & FULL IN-SAMPLE SELECTION DISCLOSED**  
**Audit Date:** 2026-11-17  

---

## 1. Executive Summary

This forensic audit investigates the transition between the exploratory research observations of Phase 3 and the formalized pre-registered specification of `SMC_CONFLUENCE_V2`.

A critical discrepancy was raised:
- Historical research described: H4 trend alignment, London/NY session restriction, and $\text{ADX} > 25.0$.
- Registered V2 specifies: D1 and H4 confirmation, London/NY 07:00–17:00 UTC, $\text{ADX}(14) > 22.0$, and $\text{ATR}(14) \times 1.5$ stop buffer.

In strict compliance with quantitative research integrity, this report provides exhaustive answers to the 6 mandated questions, openly acknowledges where parameters were derived from the consumed dataset, and confirms that `SMC_CONFLUENCE_V2` remains frozen prior to future out-of-sample evaluation.

---

## 2. Answers to Mandated Specification Questions

### Question 1: Why is V2 using ADX > 22 instead of ADX > 25?
**Answer:**  
In the Phase 3 exploration report and the 16-variant controlled ablation matrix (`scratch/CONTROLLED_FILTER_MATRIX.csv`), testing an aggressive threshold of $\text{ADX} > 25.0$ on the full confluence configuration (`G_HTF_ATR_SESSION`) collapsed the total trade count down to **13 trades across 17 months** (an average of only 0.76 trades per month).

A strategy generating fewer than 1 trade per month suffers from acute sample size starvation, making statistical verification and walk-forward validation impossible. When specifying V2, the researcher relaxed the threshold from $25.0$ down to $22.0$ to expand the expected trade frequency to ~40–60 trades over 17 months while still barring ultra-flat consolidation chop ($\text{ADX} \le 20.0$).

---

### Question 2: What evidence supports D1 confirmation in addition to H4?
**Answer:**  
In Phase 3E multi-timeframe research, relying solely on H4 structure breaks resulted in false trend entries during extended macro consolidations. Intermediate H4 swings often reversed sharply when colliding with major Daily (D1) order blocks and swing levels. 

In `src/strategy/htf_bias.py`, the `HTFDirectionalBiasEngine` combines D1 daily completed bars with H4 bars, requiring both timeframes to be in unanimous structural agreement (`D1 == BULLISH` and `H4 == BULLISH`). When D1 and H4 conflict, the bias is classified as neutral and trades are fail-closed. This reduced counter-trend whipsaws in trending gold macro moves.

---

### Question 3: Was the ADX threshold selected using the already-consumed historical dataset?
**EXPLICIT DISCLOSURE: YES.**  
The threshold of $\text{ADX}(14) > 22.0$ was selected by the researcher after examining the in-sample distribution of trade returns and trade frequencies across `data/research/phase3/processed/XAUUSD_M15_extended.csv`. 

**Governance Impact:** Because this threshold was chosen with prior knowledge of the 33,388-bar dataset, evaluating `SMC_CONFLUENCE_V2` on this same dataset would constitute Type I data snooping (in-sample confirmation bias). Pre-registering V2 does NOT magically convert previously examined data into an untouched holdout. V2 must be evaluated exclusively on an unconsumed dataset.

---

### Question 4: Were London and NY session windows tested under daylight-saving transitions?
**Answer:**  
The backtesting engine evaluated session filtering using **fixed UTC hours** (`07:00:00` to `16:59:59` UTC). It did not adjust for seasonal Daylight Saving Time (DST) transitions between London (GMT vs BST) and New York (EST vs EDT).

Because the UK and US enter and exit DST on different calendar dates in March and October/November, there are 2 to 3 weeks each year where the actual cash market open shifts by 1 hour relative to UTC. In backtesting, fixed UTC boundaries meant that during these transition weeks, simulated entries were offset by 1 hour relative to local exchange opening bells.

---

### Question 5: Does 07:00–17:00 UTC mean fixed UTC hours or actual London/New York local market hours?
**Answer:**  
In `src/strategy/session_filter.py`, the filter is strictly coded as **fixed UTC hours**:
```python
# Fixed UTC clock filtering
hour = candle_time.hour
if 7 <= hour < 17:
    return True # Allowed
return False    # Blocked
```
It is explicitly fixed UTC clock time, NOT local exchange time. For live deployment, an institutional system should migrate to local exchange time (e.g. `Europe/London` and `America/New_York`) to maintain precise alignment with cash market liquidity.

---

### Question 6: Are the execution-cost assumptions consistent across experiments?
**Answer:**  
**YES.** All Phase 3 experiments (EXP_A through EXP_K) and Phase 3F audits utilized identical, standardized execution parameters:
- Fallback Spread: \$0.20 per ounce (\$20.00 per standard lot).
- Adverse Slippage: \$0.05 per ounce per side (\$10.00 roundtrip per standard lot).
- Broker Commission: \$0.00 per lot.
- Total Roundtrip Friction: \$0.30 per ounce (\$30.00 per standard lot).
- Fill Timing: Simulated strictly at `next_bar_open` (bar $i+1$ Open).

---

## 3. Candidate Specification Invariance Statement

In accordance with strict research governance:
1. `SMC_CONFLUENCE_V2` remains **FROZEN** as registered in `configs/candidate_specs/smc_confluence_v2.json`.
2. The cryptographic SHA-256 hash `1eaa40373f9e89c3f65fb216badd6604fa7df428c973cf495902bf8a0bd7eb8c` is locked.
3. Zero parameters have been or will be adjusted on this corrective branch.
4. Evaluation of V2 is deferred until an unconsumed, pristine dataset is acquired and verified.

