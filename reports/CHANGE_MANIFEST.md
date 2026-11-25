# GoldFlow — Change Manifest
## SMC_CONFLUENCE_V1 Development Sprint

**Generated:** 2026-11-14  
**Branch:** `main`  
**Session Scope:** Quantitative Edge Development Mission — Part 17 (SMC Confluence Strategy)

---

## Canonical Hash Verification (as of 2026-11-14)

All canonical raw datasets verified INTACT:

| File | SHA-256 | Status |
|------|---------|--------|
| `data/raw/XAUUSD_H4_raw.csv` | `9bf68ed4b607aa91ededf95df03f42e552a1f52b0b0238373730756a579bb149` | ✅ OK |
| `data/raw/XAUUSD_H1_raw.csv` | `ed050b1b273d08014f007c7fe98eb1d81a321c8a3c2d5e9c22a0df7ea9574dbb` | ✅ OK |
| `data/raw/XAUUSD_M15_raw.csv` | `b893bc507daec515d36ff51cb988e4f6e33df23f3ccddd6924794b64fbe7b075` | ✅ OK |
| `data/raw/XAUUSD_M5_raw.csv` | `7c5c5187bbb6593391708a5842e06b72ca7c1474ea86d91c2aac0e7e8a051257` | ✅ OK |
| `configs/smc_v1_frozen.json` | `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a` | ✅ OK |

---

## New Files Added

### Strategy Layer (`src/strategy/`)

| File | Size | Description |
|------|------|-------------|
| `src/strategy/htf_bias.py` | 14,125 b | **HTF Bias Engine** — aggregates H4→D1 bars, runs SMC analysis on D1, determines bullish/bearish/neutral bias. Used as the primary confluence filter in SMC_CONFLUENCE_V1. |
| `src/strategy/session_filter.py` | 6,913 b | **Session Filter** — enforces London (07:00–11:00 UTC) and New York (13:00–17:00 UTC) session windows. Rejects setups outside active-session windows. |
| `src/strategy/news_filter.py` | 8,277 b | **News Filter** — loads `data/news/usd_high_impact_news.csv`, blackouts ±30 minutes around high-impact USD events. Fail-closed: no news data → all filtered. |
| `src/strategy/smc_confluence.py` | 23,919 b | **SMC_CONFLUENCE_V1 Backtester** — orchestrates HTF bias + session + news + ATR filters into a complete walk-forward backtesting engine. Produces `ConfluenceBacktestResult` with trade ledger, equity curve, and performance metrics. |

### Risk Package (`src/risk/`)

| File | Size | Description |
|------|------|-------------|
| `src/risk/__init__.py` | 591 b | Package init — exports `CapitalPreservationEngine`, `ATRLotSizer`, `TradeManager`. |
| `src/risk/engine.py` | 5,588 b | **Capital Preservation Engine** — enforces daily loss limit (2% account), weekly limit (5%), max concurrent trades (3), minimum R:R (1.5). Gate checks before each trade. |
| `src/risk/lot_sizing.py` | 3,539 b | **ATR Lot Sizer** — computes lot size from account equity, risk %, ATR, and stop distance. Enforces 1.5×ATR minimum stop expansion. Respects broker min/max lot and pip-value for XAU/USD. |
| `src/risk/trade_management.py` | 3,751 b | **Trade Manager** — implements breakeven move (at 1R profit) and partial close (50% at 1R), tracking state per trade. |

### Tests (`tests/`)

| File | Size | Tests | Status |
|------|------|-------|--------|
| `tests/test_htf_bias.py` | 5,761 b | 4 | ✅ All pass |
| `tests/test_session_filter.py` | 4,897 b | 6 | ✅ All pass |
| `tests/test_news_filter.py` | 4,755 b | 5 | ✅ All pass |
| `tests/test_lot_sizing.py` | 2,351 b | 4 | ✅ All pass |
| `tests/test_risk_engine.py` | 5,644 b | 5 | ✅ All pass |
| `tests/test_smc_confluence.py` | 4,728 b | 3 | ✅ All pass |

**Total new tests: 27**  
**Total test suite: 691 collected (690 pass, 1 pre-existing intermittent)**

### Scripts (`scripts/`)

| File | Size | Description |
|------|------|-------------|
| `scripts/run_smc_confluence_ablation.py` | 12,254 b | **Ablation Runner** — 8 experiments × 2 timeframes (M15, M5). Saves results to `reports/PERFORMANCE_COMPARISON.csv` and `reports/TRADE_LEDGER.csv`. Fully reproducible. |

### Reports (`reports/`)

| File | Size | Description |
|------|------|-------------|
| `reports/PERFORMANCE_COMPARISON.csv` | 2,285 b | 16-row ablation matrix: 8 experiments × 2 timeframes with Trades, WR, PF, Net P&L, Max DD |
| `reports/TRADE_LEDGER.csv` | 765,791 b | 2,749-trade forensic ledger with entry/exit times, prices, P&L, filters applied |
| `reports/STRATEGY_ABLATION_REPORT.md` | 7,995 b | Full ablation study narrative — methodology, results, honest interpretation |
| `reports/QUANTITATIVE_EDGE_RESEARCH_REPORT.md` | 8,146 b | Complete quantitative edge research report with findings and next steps |
| `reports/RISK_ENGINE_SPECIFICATION.md` | 5,480 b | Capital preservation engine technical specification |
| `reports/RESEARCH_VALIDATION_REPORT.md` | 4,011 b | Research integrity and reproducibility validation |
| `reports/TEST_VERIFICATION_REPORT.md` | 2,778 b | Test suite verification report with actual pytest output |
| `reports/CHANGE_MANIFEST.md` | *this file* | Complete change manifest for this sprint |

### Data (`data/`)

| File | Size | Description |
|------|------|-------------|
| `data/news/usd_high_impact_news.csv` | 9,512 b | 152 USD high-impact news events (2025–2026): NFP, FOMC, CPI, PPI. Used by news filter at runtime. |

### Configs (`configs/`)

| File | Size | Description |
|------|------|-------------|
| `configs/smc_confluence_v1.json` | 1,386 b | SMC_CONFLUENCE_V1 mutable config. **NOT frozen** — may be tuned. Distinct from `smc_v1_frozen.json`. |

### Docs (`docs/`)

| File | Size | Description |
|------|------|-------------|
| `docs/PROJECT_ARCHITECTURE.md` | 8,468 b | Full project architecture document covering all modules, data flow, and integration points. |

### Scratch (`scratch/`)

| File | Size | Description |
|------|------|-------------|
| `scratch/generate_news_calendar.py` | 4,938 b | Script to generate/extend the news calendar CSV. |
| `scratch/test_d1_agg.py` | 1,065 b | D1 aggregation verification script. |

---

## Modified Files

### Strategy Layer

| File | Change Summary |
|------|----------------|
| `src/strategy/smc_mtf.py` | Added `"D1": timedelta(days=1)` to `TIMEFRAME_DURATIONS` dict (required for HTFBiasEngine to process daily timeframe). Added data boundary enforcement to prevent lookahead bias. |

### Application Pages

| File | Change Summary |
|------|----------------|
| `pages/1_Market_Analysis.py` | Added **Confluence & Risk Diagnostics** expandable section: HTF bias status, active session indicator, news blackout indicator, ATR value panel. Live diagnostics using real data. |
| `pages/2_Backtesting.py` | Added **tab_confluence** (7th tab): interactive ablation matrix table, confluence simulator with per-filter toggles, real-time equity curve rendering. |
| `pages/3_BI_Dashboard.py` | Added `SMC_CONFLUENCE_V1` as first source option. Full ablation dashboard with heatmaps, drawdown analysis, filter contribution charts. |

### Data Infrastructure

| File | Change Summary |
|------|----------------|
| `src/data/cleaner.py` | Path containment hardening — rejects any output path that escapes the project root. |
| `src/data/loader.py` | Path containment hardening — rejects any source path that escapes the project root. |
| `src/vault/registration.py` | Auto-detects pytest environment and `/tmp` paths to prevent test pollution in production registry. |
| `src/vault/evaluation_gate.py` | Strengthened gate enforcement — gate remains closed after first validation consumption. |

---

## Test Suite Summary

**Run command:** `python -m pytest tests/ -q` (from `GoldFlow_SMC_Primary_Updated/`)  
**Result:** 690 passed, 1 failed in 53.45s  
**Isolated run:** 691 passed, 0 failed

### Pre-existing Intermittent Failure

```
FAILED tests/test_chart_performance_and_statistics.py::TestChartPerformanceAndWindowFiltering::test_chart_renders_under_one_second_on_large_smc_result
```

**Root cause:** System load during full suite run (690+ tests executing concurrently) causes CPU contention that pushes chart rendering past the 1.5s threshold.  
**Evidence:** Test passes every time when run in isolation (3.69s total wall time, rendering itself < 1.0s).  
**Classification:** Pre-existing environmental timing sensitivity — NOT a code regression introduced in this sprint.  
**Decision:** Do NOT weaken assertion. Do NOT skip test. This is a valid performance regression detector for clean environments. The test is correctly specified.

---

## Ablation Study Key Findings

| Finding | Evidence |
|---------|---------|
| HTF Bias is the strongest edge filter | M15 WR: 20.51% → 40.00% (+95%); M5 max DD: 34.44% → 14.00% (-59%) |
| Session filter alone is destructive on M5 | PF drops from 0.879 → 0.693 when session-only applied |
| ATR stop expansion is critical on M5 | M5 net loss shrinks from -$2,733 to -$134 with ATR filter |
| PF 1.6 target NOT achieved | Best M15 PF: 1.144 (EXP_A_HTF). Best M5 PF: 0.892. Honest reporting. |
| Optimal combination not yet found | 8 experiments completed; further research needed on HTF+ATR combined on M15 |

---

## Constraints Respected

- ✅ `MetaTrader5.order_send` permanently disabled — no live execution
- ✅ `configs/smc_v1_frozen.json` SHA-256 unchanged
- ✅ `data/processed/XAUUSD_M15_validation_window.csv` not reused
- ✅ Canonical raw datasets not overwritten (all 5 hashes verified)
- ✅ No tests modified to pass
- ✅ No test assertions weakened
- ✅ All results honestly reported — PF 1.6 not achieved, documented clearly
- ✅ All research reproducible via `scripts/run_smc_confluence_ablation.py`

