# GoldFlow Phase 4.1 — SMC v1 Robustness and Cost Sensitivity Analysis

**Generated UTC:** 2026-10-20T16:14:57.237544+00:00  
**Execution spec audit status:** `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE`  
**Data readiness status:** `READY_WITH_WARNINGS`  

> **PURPOSE & METHODOLOGY:**
> This audit separates cost sensitivity into two distinct, rigorous experiments:
> 1. **Experiment A (Fixed-Trade-Ledger Cost Replay)**: Freezes all baseline trades, fills, and lot sizes, recalculating only transaction costs. Proves mathematical monotonicity where higher costs cannot decrease charges.
> 2. **Experiment B (Full Resimulation Sensitivity)**: Re-runs the full event backtest under altered cost environments, capturing the feedback loop on position sizing, fill prices, and intrabar pathing.

## Predeclared Cost Scenarios

| Scenario | Spread Multiplier | Fallback Spread (USD) | Slippage/side (USD) | Commission/lot/side (USD) |
|---|---:|---:|---:|---:|
| baseline | 1.0x | $0.20 | $0.05 | $0.00 |
| 2x_spread | 2.0x | $0.40 | $0.05 | $0.00 |
| 3x_spread | 3.0x | $0.60 | $0.05 | $0.00 |
| 2x_slippage | 1.0x | $0.20 | $0.10 | $0.00 |
| 2x_all_costs | 2.0x | $0.40 | $0.10 | $0.00 |
| with_commission | 1.0x | $0.20 | $0.05 | $1.00 |
| worst_case | 3.0x | $0.60 | $0.20 | $2.00 |

---
## H4 Analysis (5,000 bars, 15 candidates)

**Data Range:** 2023-07-27 to 2026-10-20

### Experiment A: Fixed-Trade-Ledger Cost Replay (Identical Trades & Sizing)

| Scenario | Rule Exits | Raw Gross | Spread Cost | Slippage Cost | Commission | Total Costs | Net Profit | PF | Win Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 13 | $472.41 | $8.97 | $14.70 | $0.00 | $23.67 | $448.74 | 1.54 | 30.77% |
| 2x_spread | 13 | $472.41 | $17.94 | $14.70 | $0.00 | $32.64 | $439.77 | 1.52 | 30.77% |
| 3x_spread | 13 | $472.41 | $26.91 | $14.70 | $0.00 | $41.61 | $430.80 | 1.51 | 30.77% |
| 2x_slippage | 13 | $472.41 | $8.97 | $29.40 | $0.00 | $38.37 | $434.04 | 1.51 | 30.77% |
| 2x_all_costs | 13 | $472.41 | $17.94 | $29.40 | $0.00 | $47.34 | $425.07 | 1.50 | 30.77% |
| with_commission | 13 | $472.41 | $8.97 | $14.70 | $3.06 | $26.73 | $445.68 | 1.53 | 30.77% |
| worst_case | 13 | $472.41 | $26.91 | $58.80 | $6.12 | $91.83 | $380.58 | 1.43 | 30.77% |

### Experiment B: Full Resimulation Sensitivity (Dynamic Execution & Sizing)

| Scenario | Rule Exits | Wins | Losses | Win Rate | Net Profit | PF | Max DD | Avg R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 13 | 4 | 9 | 30.77% | $448.73 | 1.54 | $751.76 | 0.46 |
| 2x_spread | 13 | 4 | 9 | 30.77% | $446.83 | 1.54 | $751.06 | 0.46 |
| 3x_spread | 13 | 4 | 9 | 30.77% | $444.93 | 1.53 | $750.36 | 0.46 |
| 2x_slippage | 13 | 4 | 9 | 30.77% | $455.93 | 1.55 | $752.16 | 0.46 |
| 2x_all_costs | 13 | 4 | 9 | 30.77% | $454.03 | 1.55 | $751.46 | 0.46 |
| with_commission | 13 | 4 | 9 | 30.77% | $445.67 | 1.53 | $751.84 | 0.46 |
| worst_case | 13 | 4 | 9 | 30.77% | $445.04 | 1.54 | $711.68 | 0.44 |

#### Resimulation Traceable Causal Divergences from Baseline:
- **2x_slippage** setup `SMC_H4_0001`: lots: 0.07 -> 0.06
- **2x_slippage** setup `SMC_H4_0002`: lots: 0.46 -> 0.44
- **2x_slippage** setup `SMC_H4_0008`: lots: 0.34 -> 0.33
- **2x_all_costs** setup `SMC_H4_0001`: lots: 0.07 -> 0.06
- **2x_all_costs** setup `SMC_H4_0002`: lots: 0.46 -> 0.44
- **2x_all_costs** setup `SMC_H4_0008`: lots: 0.34 -> 0.33
- **worst_case** setup `SMC_H4_0001`: lots: 0.07 -> 0.06
- **worst_case** setup `SMC_H4_0002`: lots: 0.46 -> 0.40
- **worst_case** setup `SMC_H4_0003`: lots: 0.18 -> 0.17
- **worst_case** setup `SMC_H4_0008`: lots: 0.34 -> 0.31
- **worst_case** setup `SMC_H4_0011`: lots: 0.20 -> 0.19

## Diagnostic Insights & Resolution of Phase 4 Anomalies

1. **Unchanged Spread Anomaly (Resolved)**:
   - *Root Cause:* Previously, the engine queried historical bar spreads via `if 'spread' in row.index:` and completely ignored `fallback_spread_usd`. Because `2x_spread` only modified fallback spread, historical spreads were unchanged.
   - *Fix Verified:* Added `spread_multiplier` to `BacktestConfig` which multiplies historical bar spreads or fallback spreads. Both Experiment A and B now show proper monotonic spread cost scaling.

2. **H4 Slippage Anomaly (Resolved & Causally Traced)**:
   - *Root Cause:* In full resimulation, doubling slippage increased planned stop loss distance by $0.10. At fixed 1% risk budget ($100), the larger denominator quantized trade lot size downward (e.g. 0.07 lots down to 0.06 lots on a loss). The smaller loss saved more cash than the incremental slippage drag on other trades.
   - *Traceability:* Experiment A proves that when lot sizes are frozen, doubled slippage strictly reduces net P&L monotonically. Experiment B reveals the exact lot-sizing quantization step.

3. **M5 Common Window vs Full History Identity (Resolved)**:
   - *Root Cause:* In Phase 4, the M5 dataset was capped at 5,000 bars (~17 days), exactly coinciding with the common date window start.
   - *Fix Verified:* The expanded M5 dataset now contains 99,999 completed bars spanning ~17 months (May 2025 to Oct 2026), creating complete separation between full history and the common window.
