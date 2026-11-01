# GoldFlow — Independent Baseline Backtest Reproduction Report

**Date:** 2026-10-31  
**Execution Environment:** Windows 11 / Python 3.14  
**Pipeline Invoked:** `scripts/run_smc_backtest.py`  
**Git HEAD:** `1a529e2638832a4b6fcf88c388f68270fc6108a5`  
**Execution Mode:** `full-history`  
**Strategy Version:** SMC v1 (Frozen)  

---

## 1. Executive Summary

In compliance with Section 4 of the Master Engineering Directive, this report details the independent reproduction of the GoldFlow Pure-SMC baseline backtest from current source code and verified historical data.

The backtest was executed against all four available timeframes (**H4**, **H1**, **M15**, and **M5**) under strict fail-closed data readiness and broker execution specification gates.

The pipeline executed without errors or bypasses, writing full ledger artifacts to `reports/smc_backtest_trades_full_history.csv` and metrics to `reports/smc_backtest_metrics_full_history.json`.

---

## 2. Experimental Configuration & Broker Model

The backtest was conducted using the frozen Phase 3D execution parameters:

| Parameter | Value | Unit / Description |
|---|---|---|
| **Initial Capital** | \$10,000.00 | Account starting cash |
| **Risk Fraction per Trade** | 1.0% | \$100.00 base risk at account inception |
| **Contract Size** | 100.0 | Troy oz per standard lot |
| **Broker Point Size** | \$0.01 | 1 point = \$0.01 on XAUUSD |
| **Fallback Spread** | \$0.20 | 20 points adverse spread applied to market orders |
| **Adverse Slippage** | \$0.05 | \$0.05 per side (\$0.10 round turn per oz) |
| **Commission** | \$0.00 | Zero broker commission configured |
| **Min Lot / Step / Max** | 0.01 / 0.01 / 100.0 | Standard CFD lot constraints |
| **Max Concurrent Positions** | 1 | Strictly single position per timeframe |
| **Ambiguity Collision Rule** | Stop-First | Conservative fill assumption if both SL/TP touched in bar |
| **Execution Timing** | Next-Bar Open | Bar $i+1$ Open; zero look-ahead bias |
| **Data Readiness Gate** | `READY_WITH_WARNINGS` | Unverified provenance warnings disclosed |
| **Execution Spec Status** | `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE` | Broker specs aligned with MT5 defaults |

---

## 3. Reproduced Performance Metrics Across Timeframes

### 3.1 Aggregate Performance Matrix

| Timeframe | Candles Ingested | Setup Candidates | Closed Trades | Win Rate | Net Realized P&L | Total Return | Profit Factor | Max Drawdown | Max Holding Bars |
|---|---|---|---|---|---|---|---|---|---|
| **H4** | 2,000 | 15 | **13** | 30.77% | **+\$448.73** | **+4.49%** | **1.710** | \$751.76 (7.21%) | 64 |
| **H1** | 10,000 | 69 | **61** | 24.59% | **-\$339.41** | **-3.39%** | **0.871** | \$1,265.62 (12.28%) | 83 |
| **M15** | 5,000 | 54 | **40** | 20.00% | **-\$239.12** | **-2.39%** | **0.913** | \$1,632.95 (15.89%) | 94 |
| **M5** | 99,999 | 1,015 | **842** | 23.99% | **-\$4,955.63** | **-49.56%** | **0.835** | \$6,392.88 (58.37%) | 112 |

---

## 4. Deep Analysis of M15 Baseline Results (Candidate C0)

The M15 timeframe represents the primary candidate research domain established in Phase 6.

### 4.1 Trade & Metric Breakdown
- **Candidate Count Generated:** 54 setup candidates (Sweep $\to$ CHoCH $\to$ OB Retest)
- **Closed Trades:** 40 executed and resolved trades
- **Skipped Setups:** 14 setups (10 skipped due to concurrency limits; 4 expired/unfilled)
- **Winning Trades:** 8 (20.00% win rate)
- **Losing Trades:** 32 (80.00% loss rate)
- **Gross Profit:** \$2,508.82
- **Gross Loss:** \$2,747.94
- **Net Realized P&L:** **-\$239.12**
- **Profit Factor:** **0.913**
- **Average Win:** \$313.60
- **Average Loss:** \$85.87
- **Win/Loss Payoff Ratio:** 3.65 : 1
- **Max Drawdown:** \$1,632.95 (15.89%)
- **Transaction Costs (Spread + Slippage):** \$312.40 total friction paid

### 4.2 Reconciliation with Historical Reports
These results precisely match the C0 (Control Baseline) development numbers recorded across Phase 4 and Phase 6H:
- 40 closed trades
- Profit Factor = 0.913
- Net P&L = -\$239.12

This demonstrates complete deterministic reproducibility of the trading logic, state machine, and fill engine across environments.

---

## 5. Architectural Findings Regarding Strategy vs. Visualization Features

Section 6.1 of the Master Directive asked whether recently implemented features (Fair Value Gaps and Breaker Blocks) affected trading results.

### Critical Architecture Confirmation:
1. **Visualization-Only Decoupling:** In strict accordance with the SMC v1 frozen strategy specification (`configs/smc_v1_frozen.json`), SMC Fair Value Gaps and Breaker Blocks are **visualization and analytics overlays only**.
2. **State Machine Invariance:** The signal generation engine in `src/strategy/smc_setups.py` remains strictly:
   $$\text{Sweep of Liquidity Pool} \longrightarrow \text{Close-confirmed CHoCH} \longrightarrow \text{Order Block Retest}$$
   Neither FVGs nor Breaker Blocks are included in the execution conditions or entry filtering.
3. **Immutability Sign-Off:** The backtest reproduction confirmed that the trade ledger, entry signals, and performance metrics are identical to the frozen Phase 4 / Phase 6H benchmarks. Zero silent strategy alterations were introduced.

---

## 6. Generated Artifacts

- **Markdown Report:** [PHASE3D_SMC_EVENT_BACKTEST_FULL_HISTORY.md](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/PHASE3D_SMC_EVENT_BACKTEST_FULL_HISTORY.md)
- **JSON Metrics:** [smc_backtest_metrics_full_history.json](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/smc_backtest_metrics_full_history.json)
- **Trade Ledger CSV:** [smc_backtest_trades_full_history.csv](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/reports/smc_backtest_trades_full_history.csv)

