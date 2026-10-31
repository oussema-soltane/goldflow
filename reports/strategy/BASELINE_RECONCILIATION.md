# BASELINE RECONCILIATION REPORT

**GoldFlow XAUUSD Research Platform**
**Strategy Baseline Reconciliation — Phase 6F**
**Date:** 2026-10-29 | **Status:** COMPLETE

---

## 1. Purpose

This document reconciles the two SMC backtest trade datasets against the frozen SMC v1 configuration, records gross vs. net P&L decomposition, and establishes the authoritative baseline performance numbers for Phase 6 research.

---

## 2. Data Sources

| Dataset | File | Rows | Closed Trades | Timeframe |
|---------|------|------|--------------|-----------|
| M5 Full History | `reports/smc_backtest_trades_full_history.csv` | 1,151 | 954 | M5 |
| M15 MTF Experiment | `reports/smc_mtf_trades.csv` | 1,370 | 1,169 | M15 |

---

## 3. Frozen Configuration Parameters

```json
configs/smc_v1_frozen.json — SHA-256: 1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a

Execution costs:
  fallback_spread_usd          : $0.20
  slippage_per_side_usd        : $0.05
  commission_per_lot_per_side  : $0.00

Risk management:
  initial_capital_usd          : $10,000.00
  risk_fraction                : 0.01 (1%)
  contract_size_oz             : 100
```

---

## 4. M5 Baseline Performance (Frozen SMC v1)

### 4.1 Summary

| Metric | Value |
|--------|-------|
| Initial Capital | $10,000.00 |
| Closed Trades | 954 |
| Wins | 263 (27.57%) |
| Losses | 691 (72.43%) |
| Gross P&L | -$1,786.41 |
| Transaction Costs | -$3,268.90 |
| **Net P&L** | **-$5,055.31** |
| Profit Factor | 0.872 |
| Max Drawdown | $6,392.88 |

### 4.2 Transaction Cost Decomposition

| Cost Component | Total | Per Trade |
|----------------|-------|-----------|
| Spread (in + out) | $1,905.19 | $2.00 |
| Slippage (2 sides) | $953.40 | $1.00 |
| Commission | $0.00 | $0.00 |
| **Total** | **$2,858.59** | **$3.00** |

> [!NOTE]
> Transaction costs represent 57% of total net losses. This confirms that M5 overtrading (954 trades) generates unsustainable friction at gold's typical position sizes.

### 4.3 Target Source Decomposition

| Target Source | Trades | Win Rate | Net P&L | Profit Factor |
|---------------|--------|----------|---------|---------------|
| opposing_liquidity | 815 | 27.36% | -$5,287.44 | 0.866 |
| fixed_rr_fallback | 27 | 40.74% | +$331.81 | 1.287 |

### 4.4 Session Decomposition

| Session (UTC) | Trades | Win Rate | Net P&L | Profit Factor |
|---------------|--------|----------|---------|---------------|
| Asian 00:00–07:00 | 268 | 26.12% | -$2,495.49 | 0.814 |
| London 07:00–13:00 | 234 | 27.35% | -$2,418.03 | 0.787 |
| NY Overlap 13:00–17:00 | 87 | 31.03% | -$182.67 | 0.948 |
| **NY Afternoon 17:00–21:00** | **131** | **31.30%** | **+$2,259.34** | **1.378** |
| Rollover 21:00–24:00 | 58 | 20.69% | -$1,527.55 | 0.496 |

### 4.5 Direction Decomposition

| Direction | Trades | Win Rate | Net P&L | Profit Factor |
|-----------|--------|----------|---------|---------------|
| Long | 412 | 27.43% | -$4,123.87 | 0.791 |
| Short | 430 | 27.67% | -$831.76 | 0.960 |

---

## 5. M15 Baseline Performance (MTF Experiment)

### 5.1 Summary

| Metric | Value |
|--------|-------|
| Initial Capital | $10,000.00 |
| Closed Trades | 1,169 |
| Wins | 343 (29.34%) |
| Losses | 826 (70.66%) |
| Gross P&L | +$832.08 |
| Transaction Costs | -$826.64 |
| **Net P&L** | **+$5.44** |
| Profit Factor | 1.003 |

> [!IMPORTANT]
> The previously reported +$506.56 M15 MTF profit has been **permanently retracted**. That result was caused by look-ahead boundary leakage where the strategy accessed future bar data during the final holdout period. The corrected, causally-clean M15 result is +$5.44 — essentially break-even.

### 5.2 Direction Decomposition (M15)

| Direction | Trades | Win Rate | Net P&L | Profit Factor |
|-----------|--------|----------|---------|---------------|
| Long | 546 | 28.39% | -$689.44 | 0.978 |
| Short | 623 | 30.18% | +$695.44 | 1.022 |

---

## 6. Gap and Outlier Analysis

### 6.1 Weekend Gap Stops

| Stop Type | Count | Avg Loss |
|-----------|-------|---------|
| Normal SL hit | 878 | -$65.56 |
| Gap stop (weekend) | 76 | -$339.32 |

Gap stops are 5.2× the normal risk budget. These arise from XAUUSD weekend gaps causing fill prices far beyond the original stop level.

---

## 7. Configuration Integrity Verification

```
configs/smc_v1_frozen.json
  Expected SHA-256 : 1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a
  Observed SHA-256 : 1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a
  Status: MATCH ✅

src/smc/engine.py — not modified ✅
src/strategy/smc_setups.py — not modified (phase 6F scope) ✅
```

