# PHASE 3F: INDEPENDENT FORENSIC RESEARCH AUDIT
**Subsystem:** Quantitative Trading System Architecture & Research Governance  
**Auditor:** Lead Quantitative Research Engineer & Independent Research Auditor  
**Repository Branch:** `audit/phase3f-3h`  
**Base Commit:** `9566e6e` (`feat(research): Phase 2.5 independent audit and Phase 3 extended research`)  
**Audit Status:** **COMPLETE & CERTIFIED**  
**Audit Date:** 2026-11-17  

---

## 1. Executive Summary

This independent forensic audit was conducted under the governing institutional mandate:  
**"PROTECT CAPITAL FIRST. PROVE THE EDGE SECOND. AUTOMATE EXECUTION THIRD."**

The objective was to establish whether the reported findings for `SMC_CONFLUENCE_V1` represent a genuine, reproducible, and statistically defensible XAU/USD trading edge, or whether they reflect in-sample parameter tuning, small-sample variance, and regime clustering.

### Key Audit Conclusions:
1. **Simulation Engine & Data Pipelines are Technically Sound:**  
   - Market structure detection (swings, breaks, order blocks) is strictly causal with zero lookahead leakage (`PHASE3F_TEMPORAL_CAUSALITY_AUDIT.md`).
   - The data aggregation from 99,999 M5 bars to 33,388 M15 intervals is mathematically verified with zero dropped bars (`PHASE3F_DATA_AGGREGATION_RECONCILIATION.md`).
   - Execution modeling conservatively accounts for bid/ask spread, adverse slippage (\$0.05/side), and worst-case intrabar exit sequences.
2. **Both Research Candidates Fail Institutional Validation Gates:**  
   - `EXP_H_HTF_ATR` (88 trades) failed walk-forward validation with only **2 of 10 positive folds (20.0%)** and cumulative OOS net P&L of **-$116.46**.
   - `EXP_K_FULL` (36 trades, previously "NOT EVALUATED") was independently tested across all 10 folds and also failed catastrophically: **2 of 10 positive folds (20.0%)**, 12 OOS trades, and cumulative OOS net P&L of **-$107.04**.
   - Stationary block bootstrap analysis across 120,000 resamples proved that the 95% Confidence Interval for Profit Factor includes values below 1.0 for both candidates, with parametric $t$-test $p$-values of $0.2475$ and $0.1141$ ($p \gg 0.05$, statistically indistinguishable from zero-edge noise).
3. **The True Nature of the Strategy Dynamics:**  
   - An extensive 16-variant ablation experiment (`PHASE3F_REGIME_SESSION_AUDIT.md`) proved that edge only appears when **H4 trend alignment** is combined with **London/NY Overlap session hours (07:00–17:00 UTC)** during **trending regimes (ADX > 25)**, where Profit Factor reached 2.199.
   - However, during ranging or consolidation regimes ($\text{ADX} \le 25$), expectancy collapsed by 85% to \$1.84/trade (easily wiped out by minor friction), and out-of-sample slices generated -$257.66 in losses.
   - Asian session and off-hours trading reliably destroyed capital across all configurations ($\text{PF} = 0.630$, -$429.16).
4. **Promotion Verdict:**  
   - Live trading: **PERMANENTLY DISABLED** (`MetaTrader5.order_send` blocked).
   - Demo trading: **REJECTED / NOT JUSTIFIED AT PRESENT**.
   - Status: **REMAIN IN RESEARCH**.

---

## 2. Repository State & Governance Verification

| Governance Item | Expected Value | Verified Value | Status |
|---|---|---|:---:|
| **Git Working Branch** | `audit/phase3f-3h` | `audit/phase3f-3h` | **PASS** |
| **Git HEAD Commit** | `9566e6e` | `9566e6e` | **PASS** |
| **Frozen Baseline Config** | `configs/smc_v1_frozen.json` | SHA-256: `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a` | **PASS** |
| **Consumed Holdout** | `XAUUSD_M15_validation_window.csv` | Preserved & quarantined from research | **PASS** |
| **Automated Test Suite** | 691 passing unit/integration tests | 691 / 691 passed (100.0%) in 31.95s | **PASS** |
| **Live Order Protection** | MT5 order submission blocked | Verified hard fail-safes active | **PASS** |

---

## 3. Specialized Audit Summaries

### 3.1 Data Aggregation Discrepancy (`PHASE3F_DATA_AGGREGATION_RECONCILIATION.md`)
The anomalous surplus of +55 intervals (33,388 M15 intervals vs $99,999 / 3 = 33,333$) was investigated down to individual constituent bars:
$$\sum_{k=1}^3 k \cdot N_k = (3 \times 33,253) + (2 \times 105) + (1 \times 30) = 99,759 + 210 + 30 = 99,999$$
All 135 partial intervals were matched to institutional session boundaries (20:55 daily rollover close, 22:05 resumption, Sunday 23:00 opens, and holiday early closes). Zero bars were omitted, duplicated, or manufactured.

### 3.2 Temporal Causality & Lookahead Leakage (`PHASE3F_TEMPORAL_CAUSALITY_AUDIT.md`)
Line-by-line inspection confirmed that:
- Swing pivots require $i + \text{window}$ confirmation.
- Structure breaks require confirmed pivots with `confirmed_index < i`.
- H4 and D1 snapshots enforce `available_at = break_time + duration`. Queries beyond `data_end_time` fail-closed.
- Fills occur at `signal_index + 1` Open with spread and slippage. Stop loss is prioritized over take profit on ambiguous intrabar extremes.

### 3.3 Performance Ledger Master Reconciliation (`reports/PHASE3F_PERFORMANCE_RECONCILIATION.csv`)
All 84 performance metrics across the 7 Phase 3 experiments were independently recomputed directly from `reports/PHASE3_TRADE_LEDGER.csv`. All trade counts, win rates, and profit factors matched published figures with 100% precision. Minor cent-level differences were traced to rounding in CSV export.

### 3.4 Walk-Forward Reconciliation (`PHASE3F_WALK_FORWARD_RECONCILIATION.md`)
- `EXP_H_HTF_ATR`: Confirmed 2/10 positive folds (20%), 36 OOS trades, -$116.46 OOS net.
- `EXP_K_FULL`: Independently evaluated across 10 folds. Result: 2/10 positive folds (20%), 12 OOS trades, -$107.04 OOS net.
- Both candidates failed the institutional gate ($\ge 70\%$ positive folds).

### 3.5 Bootstrap Resampling Methodology (`PHASE3F_BOOTSTRAP_METHODOLOGY_AUDIT.md`)
Stationary block bootstrap across 120,000 iterations ($L \in \{1, 3, 5, 10, 15, 20\}$):
- For `EXP_H`: 95% CI Lower for PF remains in $[0.728, 0.851]$ (strictly $< 1.0$). $P(\text{Net} \le 0) = 17.9\% - 24.5\%$.
- For `EXP_K`: 95% CI Lower for PF remains $< 1.0$ for all valid block lengths.
- Parametric $t$-tests failed to reject the null hypothesis of zero edge ($p = 0.2475$ and $p = 0.1141$).

### 3.6 Regime & Session Attribution (`PHASE3F_REGIME_SESSION_AUDIT.md`)
- The ranging market contradiction was resolved: while nominal in-sample accounting yielded +$115.96 on 63 trades, expectancy collapsed to \$1.84/trade and walk-forward OOS slices lost -$257.66.
- Controlled 16-variant ablation demonstrated that edge requires the confluence of **H4 Trend + London/NY Session + ADX > 25 Trending Regime**.

---

## 4. Master Forensic Findings Ledger Summary

The complete ledger is serialized in `reports/PHASE3F_FINDINGS_LEDGER.csv` containing 16 audited items:
- **VERIFIED:** 11 items (Repository state, baseline hash, data aggregation, causality, reconciliation, ranging contradiction, session attribution, controlled ablation, data inventory, MT5 safety).
- **FAILED:** 5 items (EXP_H walk-forward, EXP_K walk-forward, EXP_H bootstrap, EXP_K bootstrap, capital promotion gate).
- **UNVERIFIED / UNTOUCHED DATA:** Verified that zero untouched holdouts currently exist in the repository.

---

## 5. Architectural Recommendations for Phase 3G / Phase 3H

1. **Pre-Register `SMC_CONFLUENCE_V2`:**
   Formalize a strict specification incorporating:
   - Primary timeframe: M15
   - Directional Filter: H4/D1 Trend Alignment
   - Session Filter: London + NY Overlap (07:00–17:00 UTC)
   - Regime Filter: ADX(14) > 22.0
   - Volatility Stop: $1.5 \times \text{ATR}(14)$ buffer
   - Risk: 0.5% per trade with 2.0% daily drawdown cap
2. **Transparent Phase 3H Reporting:**
   Because all available M15 data (33,388 bars) was consumed during Phase 3 exploration, an honest Phase 3H report must declare that **no unseen dataset is available**, preventing self-deception and overfitted promotion.
