# PHASE 6F — UI Redesign Architecture Report

**GoldFlow XAUUSD Research Platform**
**Phase 6F — Professional Trading UI Redesign**
**Date:** 2026-10-29 | **Status:** COMPLETE

---

## 1. Executive Summary

Phase 6F redesigned two primary Streamlit pages (`pages/1_Market_Analysis.py` and `pages/2_Backtesting.py`) and the shared chart library (`src/visualization/charts.py`) from a functional-but-plain prototype into a professional-grade quantitative research interface.

The redesign preserved all existing research-integrity controls, frozen configurations, and audit mechanisms. No live-trading code was added. No external network calls were introduced.

---

## 2. Architecture Overview

```
src/visualization/charts.py        ← Core chart library (extended)
pages/1_Market_Analysis.py         ← Market analysis interface (redesigned)
pages/2_Backtesting.py             ← Backtesting interface (redesigned)
tests/test_ui_redesign.py          ← 8 automated UI tests (all passing)
```

### Design Principles

| Principle | Implementation |
|-----------|---------------|
| Dark professional theme | Background `#0c0f17`, panels `#121520`, borders `#1a1f2c` |
| Color semantics | Teal `#00c087` = bullish/profit, Crimson `#ff3b57` = bearish/loss |
| Zero external calls | All data from local `data/processed/` and `reports/` CSVs |
| Non-blocking UI | `@st.cache_data` decorators; no synchronous API calls |
| Research-grade metrics | Gross P&L, Net P&L, costs decomposed separately |

---

## 3. `src/visualization/charts.py` Changes

### 3.1 `create_candlestick_chart` — Signature Extensions

**New parameters added:**
```python
trades: Optional[List[Dict]] = None      # trade overlay records
show_trades: bool = True                 # toggle overlay display
show_dealing_range: bool = True          # 50% equilibrium line
visible_bars: Optional[int] = None       # window last-N-bars
```

### 3.2 Trade Overlay Rendering

- **Long entry markers:** `▲` teal triangles at signal bar
- **Short entry markers:** `▼` crimson inverted triangles  
- **Stop-loss lines:** Dotted crimson horizontal from entry to exit bar
- **Take-profit lines:** Dotted teal horizontal from entry to exit bar
- **Exit markers:** `●` (win, teal) or `✖` (loss, crimson) at exit bar
- **Hover cards:** Direction, entry price, SL, TP, session, P&L

### 3.3 Dealing Range & Equilibrium

50% equilibrium line drawn across visible range when `show_dealing_range=True`.

### 3.4 Four New Institutional Visualizers

| Function | Purpose | Panes |
|----------|---------|-------|
| `create_equity_curve_chart` | Realized & MTM equity vs. drawdown | 2 (equity + underwater DD%) |
| `create_pnl_distribution_chart` | P&L histogram with mean and zero reference | 1 |
| `create_trade_outcome_donut` | Exit reason composition | 1 |
| `create_performance_by_session_chart` | Net P&L per session bucket | 1 |

---

## 4. `pages/1_Market_Analysis.py` Changes

### 4.1 KPI Metrics Strip (6 columns)
```
[ Price ] [ High ] [ Low ] [ Audited Bars ] [ Structure Trend ] [ Dealing Zone ]
```

### 4.2 Chart Toolbar
- Visible candle window: `200 | 500 | 1000 | All`
- Trade overlay toggle (auto-loads matching timeframe CSVs from `reports/`)
- Dealing range toggle
- Chart height slider (400–900px)

### 4.3 Strategy Trades Tab
`🎯 Strategy Trades in Window` shows:
- Live trade count, win rate, average R:R
- Sortable trade table with direction, entry, exit, P&L, session

---

## 5. `pages/2_Backtesting.py` Changes

### 5.1 Executive Metrics (8 KPI cards)

```
Net P&L | Profit Factor | Win Rate | Max Drawdown
Closed Trades | Payoff Ratio | Expectancy/Trade | Avg Holding Duration
```

### 5.2 Integrated Chart Suite

Four tabs now include:
1. **Equity Curve** — Dual-pane realized equity + underwater drawdown %
2. **P&L Distribution** — Histogram with win/loss color coding, mean line
3. **Trade Outcomes** — Donut chart of exit reasons (SL hit / TP hit / time stop)
4. **Session Performance** — Net P&L bar chart across Asian / London / NY sessions

### 5.3 Trade Ledger Inspector

Interactive trade log with:
- Direction, session, entry/exit timestamps, gross P&L, costs, net P&L
- Column-level filtering
- CSV export download button

---

## 6. Test Evidence

```
tests/test_ui_redesign.py — 8 tests — 5.96s — ALL PASSED
```

| Test | Description |
|------|-------------|
| `test_create_candlestick_chart_returns_figure` | Chart creates valid Plotly figure |
| `test_trade_overlays_added` | Trade markers appear when trades list provided |
| `test_no_trades_overlay_skipped` | No markers rendered when trades=None |
| `test_dealing_range_toggle` | Equilibrium line added/omitted correctly |
| `test_equity_curve_chart_structure` | Dual-pane structure verified |
| `test_pnl_distribution_chart` | Histogram rendered with correct data |
| `test_trade_outcome_donut` | Donut slice counts match trade outcomes |
| `test_performance_by_session_chart` | Session bar chart has correct categories |

---

## 7. Constraints Verified

- ✅ `configs/smc_v1_frozen.json` hash unchanged: `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`
- ✅ Zero live trading code added
- ✅ Zero external network requests
- ✅ All charts use local CSV data sources only
- ✅ Prior +$506.56 boundary-leak result retracted; valid M15 causal result is +$5.44

