# PHASE 6G — Baseline Reconciliation

**GoldFlow XAUUSD Research Platform**
**Phase 6G — Independent Baseline Verification**
**Date:** 2026-10-30 | **Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`
**Frozen config hash:** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`

---

## 1. Verification Methodology

All Phase 6F reported metrics were independently recalculated from the stored trade-ledger CSVs (`reports/strategy/trades_*.csv`). Recalculation used a purpose-written script (`scratch/phase6g_stage_a_verify.py`) that reads raw trade records, identifies `CLOSED` rows, and computes closed-trade count, net P&L, and profit factor from scratch without reading the stored JSON summary.

**Result: All 12 reported figures verified exactly. Zero discrepancies.**

---

## 2. Verified Phase 6F Results

| Key | Claimed Trades | Recalc | Claimed Net P&L | Recalc | Claimed PF | Recalc |
|-----|----------------|--------|-----------------|--------|------------|--------|
| M5 C0 Baseline | 842 | **842** | -$4,955.63 | **-$4,955.63** | 0.878 | **0.878** |
| M5 C1 Session | 539 | **539** | -$2,365.82 | **-$2,365.82** | 0.928 | **0.928** |
| M5 C2 Target Rat. | 1,188 | **1,188** | -$6,543.10 | **-$6,543.10** | 0.881 | **0.881** |
| M5 C3 Composite | 779 | **779** | -$3,507.86 | **-$3,507.86** | 0.921 | **0.921** |
| M5 C4 NY Session | 415 | **415** | -$3,623.11 | **-$3,623.11** | 0.849 | **0.849** |
| M5 C5 MTF Aligned | 262 | **262** | -$2,412.35 | **-$2,412.35** | 0.848 | **0.848** |
| M15 C0 Baseline | 40 | **40** | -$239.12 | **-$239.12** | 0.913 | **0.913** |
| **M15 C1 Session** | **29** | **29** | **+$479.31** | **+$479.31** | **1.257** | **1.257** |
| M15 C2 Target Rat. | 59 | **59** | +$282.81 | **+$282.81** | 1.082 | **1.082** |
| M15 C3 Composite | 35 | **35** | -$267.27 | **-$267.27** | 0.876 | **0.876** |
| M15 C4 NY Session | 21 | **21** | -$567.22 | **-$567.22** | 0.604 | **0.604** |
| M15 C5 MTF Aligned | 6 | **6** | -$515.58 | **-$515.58** | 0.000 | **0.000** |

---

## 3. Cost Schema Clarification (Phase 6F Report Correction)

The Phase 6F Baseline Reconciliation report stated a transaction cost drag of "approximately $3,032." This figure was imprecisely described.

**Actual cost schema (verified from ledger columns):**

| Column | Meaning |
|--------|---------|
| `raw_gross_pnl` | True pre-cost P&L (price movement × position size) |
| `total_transaction_costs` | Sum of spread + slippage costs (positive value) |
| `gross_pnl` | Same as `net_pnl` — already post-cost; naming is misleading |
| `net_pnl` | Post-cost P&L = `raw_gross_pnl` − `total_transaction_costs` |

**M5 C0 reconciliation (842 closed trades):**

| Item | Amount |
|------|--------|
| True gross P&L (pre-cost) | -$1,686.43 |
| Total transaction costs | +$3,269.20 |
| **Net P&L (post-cost)** | **-$4,955.63** |
| True gross Profit Factor | 0.956 |
| **Reported Net Profit Factor** | **0.878** |

The strategy is slightly better pre-cost (PF 0.956 ≈ break-even) but the $3,269.20 in transaction costs push it to PF 0.878. The Phase 6F report's "$3,032" figure was an earlier estimate; the exact ledger total is **$3,269.20**.

The reported "implied cost drag = $0.00" in `scratch/phase6g_stage_b_c.py` was an artifact of column misidentification: `gross_pnl = net_pnl` in the output schema. **All net P&L figures remain correct as verified.**

---

## 4. M15 C1 Detail (the candidate under investigation)

| Metric | Value |
|--------|-------|
| Closed trades | 29 |
| Wins | 9 |
| Losses | 20 |
| Win rate | 31.03% |
| Average win | +$260.46 |
| Average loss | -$93.24 |
| Total transaction costs | $50.83 |
| Net P&L | +$479.31 |
| Max drawdown | $800.78 |
| Expectancy/trade | +$16.53 |
| Profit Factor | 1.257 |

The positive result is driven by a high payoff ratio (avg win / avg loss = 2.79) rather than win rate. However, the single largest trade (+$912.67) contributes **190% of total net profit** — meaning without that one trade, the net P&L would be -$433.36.

---

## 5. C0 vs C1 Trade Count Anomaly

C0 has 842 trades and 513 fall in the 07:00–20:59 UTC window.  
C1 has 539 trades — **26 more** than the C0 liquid-hours subset.

**Cause:** The session filter is applied at setup detection, not execution. When off-hours setups are eliminated early, fewer positions saturate the `max_concurrent_positions=1` lock. This allows additional liquid-hours setups that were previously blocked by an active off-hours position to execute. **C1 is not a subset of C0 at signal level** — 29 C1 signal times do not appear in C0 at all.

This is expected engine behavior but means C0 and C1 are evaluating different opportunity sets, not the same opportunities with a filter applied post-hoc.

---

## 6. Uniform Configuration Confirmation

All Phase 6F simulations used identical `BacktestConfig`:
- Initial capital: $10,000
- Risk fraction: 1% per trade
- Spread: $0.20/side
- Slippage: $0.05/side  
- Commission: $0.00
- Contract size: 100 oz
- Max concurrent positions: 1

