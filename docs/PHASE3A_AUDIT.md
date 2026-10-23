> **Historical audit notice (2026-10-19):** This document describes the pre-reingestion data state. Current readiness is recorded in `reports/research_readiness.md` (`READY_WITH_WARNINGS`), and current backtest assumptions/results are in the Phase 3C/3D reports. The current MT5-declared source remains not independently authenticated.

# GoldFlow Phase 3A — Historical Data Readiness & Research Design Audit


> **Historical snapshot — superseded.** This document describes the repository/data snapshot from the original Phase 3A audit. Its dataset counts and identical-OHLC finding do not describe the current uploaded files. See `reports/REVIEW_AND_REMEDIATION.md` and the current `reports/research_readiness.md` for the latest disposition.

## 1. Repository State at Phase 3A Start

- **Commit:** `66eb055` — Phase 2.1 ICT Validation & Reliability Audit (79 tests pass)
- **Compilation:** `py -3.13 -m compileall src pages scripts tests app.py` → **exit code 0**
- **Full test suite (Phase 3A baseline):** `py -3.13 -m pytest -v` → **79 passed** (confirmed before any changes)

---

## 2. Historical Data Audit

### 2.1 Available Datasets

| Timeframe | File | Rows | Date Range (UTC) | Source Flag |
|---|---|---|---|---|
| H4 | `XAUUSD_H4_clean.csv` | 200 | 2026-09-10 to 2026-10-13 | **No `is_synthetic` flag** |
| H1 | `XAUUSD_H1_clean.csv` | 200 | 2026-10-05 to 2026-10-13 | **No `is_synthetic` flag** |
| M15 | `XAUUSD_M15_clean.csv` | 1500 | 2026-09-28 to 2026-10-13 | **No `is_synthetic` flag** |
| M5 | `XAUUSD_M5_clean.csv` | 200 | 2026-10-12 to 2026-10-13 | **No `is_synthetic` flag** |

### 2.2 CRITICAL Finding: H4, H1, and M5 Are Identical OHLC Sequences

**All three datasets share the exact same 200-bar OHLC price sequence**, with only the timestamps reassigned to fit each timeframe's bar interval.

Evidence:
```
H4 OHLC hash: cedcf66e...   |  first 3 closes: 2649.48, 2650.55, 2648.88
H1 OHLC hash: 872d084a...   |  first 3 closes: 2649.48, 2650.55, 2648.88   ← same
M5 OHLC hash: 48ae1c82...   |  first 3 closes: 2649.48, 2650.55, 2648.88   ← same
```

The hashes differ because `pd.read_csv` preserves string timestamps before conversion, but the float OHLC columns are numerically identical across H4, H1, and M5.

**The ICT engine produces identical event counts on all three:**
```
H4 / H1 / M5 (identical): 56 swings, 13 BOS, 8 CHoCH, 127 FVGs, 14 sweeps, 5 MSS, 82 OBs
```

**Root Cause:**  
The `generate_synthetic_gold_data()` function creates data with `seed=42` and a random-walk price process. When `download_data.py --synthetic` was run, it saved the **same underlying random sequence** into all four files, only varying the timestamp step size.

> [!WARNING]
> This data is **synthetic and partially identical across timeframes**. It cannot be used for multi-timeframe research. It cannot be mistaken for real MT5 market data because:
> - The `.meta.json` sidecars lack `is_synthetic: true` (they were generated before the `is_synthetic` key was added to the metadata schema).
> - No weekend gaps exist in H4, H1, or M5.
> - All three timeframes produce identical ICT event statistics.

### 2.3 M15 Dataset (Distinct, Synthetic)

M15 has 1500 bars and a different random seed/range, producing distinct events:
```
M15: 421 swings, 88 BOS, 99 CHoCH, 922 FVGs, 161 sweeps, 78 MSS, 589 OBs
```

However, M15 is still synthetic (no weekend gaps in the 15-day window, continuous timestamps on weekends). It is suitable for ICT engine testing but **not for real-market statistical research**.

### 2.4 Per-Dataset Quality Checks

| Check | H4 | H1 | M15 | M5 |
|---|---|---|---|---|
| UTC-aware timestamps | ✅ | ✅ | ✅ | ✅ |
| Chronologically ordered | ✅ | ✅ | ✅ | ✅ |
| Duplicate timestamps | 0 | 0 | 0 | 0 |
| OHLC violations | 0 | 0 | 0 | 0 |
| Zero/negative prices | 0 | 0 | 0 | 0 |
| Weekend gaps | ❌ None | ❌ None | ❌ None | ❌ None |
| `is_synthetic` in meta | ❌ Missing | ❌ Missing | ❌ Missing | ❌ Missing |
| Identical to another TF | ⚠️ H1, M5 | ⚠️ H4, M5 | ✅ Distinct | ⚠️ H4, H1 |

### 2.5 Displacement Count = 0

The displacement detector returned 0 displacement candles across all four datasets. This is consistent with the synthetic data's mild volatility (σ ≈ 1.8 USD per bar), which does not produce ATR-relative body spikes that exceed 1.5× ATR with a ≥ 0.6 body/range ratio.

### 2.6 Real Data Status

**Live MT5 connection has not been verified in this environment.** No real XAUUSD historical data from a broker has been downloaded. The data in `data/raw/` and `data/processed/` is entirely synthetic.

---

## 3. ICT Event Availability Audit (Unchanged from Phase 2.1)

| Event | Origin Bar | Confirmation Bar | Earliest Knowledge | Look-Ahead Free? |
|:---|:---|:---|:---|:---|
| Swing Point | Bar `i` | Bar `i + k` | Close of bar `i + k` | ✅ |
| BOS / CHoCH | Bar `j` | Bar `j` | Close of bar `j` | ✅ (checks `j > confirmed_index`) |
| Fair Value Gap | Middle bar `i` | Bar `i + 1` | Close of bar `i + 1` | ✅ |
| Displacement | Bar `i` | Bar `i` | Close of bar `i` | ✅ (ATR from bars < i) |
| Liquidity Sweep | Bar `j` | Bar `j` | Close of bar `j` | ✅ |
| Market Structure Shift | Bar `j` | Bar `j` | Close of bar `j` | ✅ |
| Order Block | Origin `k` | FVG bar `i + 1` | Close of FVG's 3rd bar | ✅ |

No look-ahead issues were introduced in Phase 3A.

---

## 4. Unresolved Issues (Carried Forward from Phase 2.1)

1. **MSS ≠ strict ICT MSS** — Current MSS is sweep → opposite break within N bars. Displacement is not a mandatory pre-condition.
2. **OBs from FVGs only** — Structure breaks do not independently create Order Blocks yet.
3. **First break labelled CHoCH** — From neutral initial trend, by explicit convention (documented).
4. **Intrabar sequencing** — OHLC bars cannot resolve order of events within a single candle.
5. **`is_synthetic` missing from old meta.json sidecars** — Generated before the flag was added to the schema. The new `audit_dataset()` function in `src/research/data_readiness.py` detects this condition via gap analysis and OHLC hash cross-comparison.

---

## 5. Research-Only Framework Design

### 5.1 Protocol Scope

This protocol describes **descriptive statistics only**. It is not a strategy backtest. No entry, exit, spread, slippage, or execution assumptions are made. Results describe ICT event behavior on historical price data.

### 5.2 Data Requirements (Before Research Begins)

**Current data is unsuitable for real-market research.** The following steps are required:

1. Connect a live MetaTrader 5 terminal on the target Windows machine.
2. Run: `py -3.13 scripts/download_data.py --symbol YOUR_BROKER_GOLD_SYMBOL --bars 10000` (replace the placeholder with the exact symbol shown in MT5 Market Watch; the terminal may limit retrievable history).
3. Verify the `.meta.json` files report `source: MetaTrader 5 API`.
4. Confirm the `audit_all_datasets()` function returns **zero CRITICAL warnings** about identical OHLC sequences.

Minimum recommended bars for meaningful statistics:
| Timeframe | Minimum Bars | Approximate Coverage |
|---|---|---|
| H4 | 2,000 | ~15 months |
| H1 | 5,000 | ~7 months |
| M15 | 10,000 | ~25 weeks |
| M5 | 10,000 | ~35 days |

### 5.3 Chronological Split Protocol

All analysis must use **strictly chronological splits — no shuffling, no lookahead**.

| Period | Proportion | Purpose |
|---|---|---|
| Train | 70% (earliest) | Exploratory analysis, parameter observation only |
| Validation | 15% | Verify that observations from train hold |
| Test | 15% (latest) | Final held-out evaluation, used at most once |

Implemented in `src/research/event_statistics.py` → `PeriodSplit.from_ratios()`.

### 5.4 Event Definitions for Research

Each event is measured from its **confirmation bar index** only. The origin bar is retrospective metadata.

**Forward Excursion Horizons (proposed starting values):**
- Short: 5 bars
- Medium: 20 bars  
- Long: 50 bars

These are observation windows for descriptive statistics, not targets or stop levels.

**Excursion measurement** (`measure_forward_excursion()`):
- Reference price = close of the event confirmation bar.
- MFE (Maximum Favorable Excursion) = maximum high (bullish) or minimum low (bearish) in the forward window, relative to reference close.
- MAE (Maximum Adverse Excursion) = worst-case adverse high (bearish) or low (bullish) in the forward window, relative to reference close.
- Implementation guarantees: `start = event_bar_index + 1`; event bar itself is excluded.

### 5.5 Session Classification

Events are classified by UTC hour at confirmation time:
- **Asia**: 22:00–07:59 UTC
- **London**: 08:00–11:59 UTC
- **NY_AM**: 12:00–16:59 UTC
- **NY_PM**: 17:00–21:59 UTC

### 5.6 Proposed Descriptive Statistics

For each event type × timeframe × period:
- Total event count
- Event rate per 100 bars
- Session distribution (Asia / London / NY_AM / NY_PM)
- MFE statistics at each horizon: mean, median, 25th/75th percentile, max
- MAE statistics at each horizon: mean, median, 25th/75th percentile, max
- For FVGs: mitigation rate (partial / full / unmitigated)

### 5.7 What Is NOT Measured Here

- Win rate or profit factor (no entry/exit defined).
- Risk-adjusted returns (no position size, spread, or slippage).
- Strategy performance (no trade execution modelled).
- ML model scores (no training or inference).

---

## 6. Files Added in Phase 3A

| File | Purpose |
|---|---|
| `src/research/__init__.py` | Package marker |
| `src/research/data_readiness.py` | Data integrity checker: synthetic detection, OHLC hash, gap audit, cross-TF identity detection |
| `src/research/event_statistics.py` | `PeriodSplit`, `measure_forward_excursion`, `classify_session`, `EventDescriptiveReport` |
| `tests/test_research_framework.py` | 36 tests covering provenance, period splitting, MFE/MAE leakage prevention, session classification, gap classification |
| `docs/PHASE3A_AUDIT.md` | This document |

---

## 7. Test & Compilation Results

```
py -3.13 -m pytest tests/test_research_framework.py -v
============================= 36 passed in 1.72s ==============================

py -3.13 -m pytest -v
============================= 115 passed in ~17s ==============================

py -3.13 -m compileall src pages scripts tests app.py -q
(exit code 0)
```

---

## 8. Next Steps (Phase 3B)

1. **Obtain real MT5 XAUUSD data** — launch the MT5 terminal, run the pipeline, verify `source: MetaTrader 5 API` in meta.json.
2. **Re-run `audit_all_datasets()`** — confirm zero CRITICAL IDENTICAL warnings.
3. **Run `PeriodSplit.from_ratios()` on each timeframe** — record train/val/test date boundaries.
4. **Compute descriptive statistics** via `build_structure_break_report()` and `build_fvg_report()` on each period separately.
5. **Report descriptive statistics honestly** — event rates, MFE/MAE distributions, session breakdowns, with all limitation notes retained.
6. **Do not proceed to Phase 3 Strategy Hypothesis** until real data has been validated.

No strategy entries/exits, ML training, automated execution, or live trading are planned for Phase 3B.


---

## 9. Follow-up Code Review and Remediation (2026-10-14)

A review of the Phase 3A implementation identified and corrected the following issues before proceeding to Phase 3B:

1. **Weekend gap false classification:** the previous classifier could label a long outage starting during Friday trading as a normal weekend closure merely because it ended Sunday. The classifier now requires a plausible Friday-close/Saturday-early start, a Sunday-evening/Monday-early end, and at least 40 hours.
2. **Unknown provenance:** missing `is_synthetic` metadata no longer silently means real data. Provenance is tri-state/qualified (`synthetic`, `real_source_declared`, `non_synthetic_unverified`, or `unknown`).
3. **Provenance propagation:** the ingestion pipeline now passes loader metadata into processed sidecars, including `source`, `is_synthetic`, retrieval time, and incomplete-bar policy.
4. **OHLC NaN/inf handling:** the research readiness audit now counts non-finite OHLC rows as invalid.
5. **Structure-break report bug:** descriptive statistics now use the explicit `StructureBreak.direction` field rather than referencing a nonexistent `.level` attribute.
6. **Partial forward horizons:** MFE/MAE summary statistics now exclude events without the full requested forward window, preventing edge-of-sample partial windows from biasing the summary. Individual excursion measurements still report `bars_available` and `complete_horizon`.
7. **Research gates:** added `evaluate_research_readiness()` and `scripts/research_readiness.py` to block research when provenance is unknown, source is not verified, history is insufficient, data quality fails, timeframes are missing, or cross-timeframe OHLC sequences are identical.

At the time of this historical audit, the then-bundled datasets were **BLOCKED** for real-market research. Their metadata did not establish an MT5 source and some OHLC sequences were duplicated. The data package was subsequently re-ingested; use the current readiness report for the present dataset state.
