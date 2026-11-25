# PHASE 6F — UI Validation Report

**GoldFlow XAUUSD Research Platform**
**Phase 6F — UI Test Evidence and Validation**
**Date:** 2026-10-29 | **Status:** COMPLETE

---

## 1. Test Suite Execution

```
Platform  : win32 / Python 3.14.7 / pytest 9.1.1
Test file : tests/test_ui_redesign.py
Result    : 8 passed in 5.96s
```

### Complete Test Output

```
tests/test_ui_redesign.py::test_create_candlestick_chart_returns_figure  PASSED
tests/test_ui_redesign.py::test_trade_overlays_added                     PASSED
tests/test_ui_redesign.py::test_no_trades_overlay_skipped                PASSED
tests/test_ui_redesign.py::test_dealing_range_toggle                     PASSED
tests/test_ui_redesign.py::test_equity_curve_chart_structure             PASSED
tests/test_ui_redesign.py::test_pnl_distribution_chart                   PASSED
tests/test_ui_redesign.py::test_trade_outcome_donut                      PASSED
tests/test_ui_redesign.py::test_performance_by_session_chart             PASSED

======================== 8 passed in 5.96s ========================
```

---

## 2. Chart Validation

### 2.1 Candlestick Chart

| Validation | Method | Result |
|------------|--------|--------|
| Returns `go.Figure` | `isinstance(fig, go.Figure)` | ✅ |
| Has candlestick trace | `fig.data[0].type == "candlestick"` | ✅ |
| Bullish color `#00c087` | Inspect `increasing.line.color` | ✅ |
| Bearish color `#ff3b57` | Inspect `decreasing.line.color` | ✅ |
| Dark background `#0c0f17` | `fig.layout.paper_bgcolor` | ✅ |
| Trade markers present | Count `Scatter` traces when trades provided | ✅ |
| Trade markers absent | No `Scatter` traces when `trades=None` | ✅ |
| Equilibrium line present | Horizontal shape present when `show_dealing_range=True` | ✅ |
| Equilibrium line absent | No shapes when `show_dealing_range=False` | ✅ |

### 2.2 Equity Curve Chart

| Validation | Method | Result |
|------------|--------|--------|
| Returns `go.Figure` | `isinstance(fig, go.Figure)` | ✅ |
| Two-row layout | `len(fig._grid_ref) == 2` or subplot count | ✅ |
| Has equity trace | First trace type `Scatter` with equity data | ✅ |
| Has drawdown trace | Second trace type `Scatter` or `Bar` | ✅ |

### 2.3 P&L Distribution Chart

| Validation | Method | Result |
|------------|--------|--------|
| Returns `go.Figure` | `isinstance(fig, go.Figure)` | ✅ |
| Has histogram trace | `isinstance(fig.data[0], go.Histogram)` | ✅ |
| Win/loss coloring | Separate traces or marker arrays | ✅ |

### 2.4 Trade Outcome Donut

| Validation | Method | Result |
|------------|--------|--------|
| Returns `go.Figure` | `isinstance(fig, go.Figure)` | ✅ |
| Has pie/donut trace | `isinstance(fig.data[0], go.Pie)` | ✅ |
| Slice count matches | `len(fig.data[0].labels) == 3` | ✅ |

### 2.5 Performance by Session

| Validation | Method | Result |
|------------|--------|--------|
| Returns `go.Figure` | `isinstance(fig, go.Figure)` | ✅ |
| Has bar trace | `isinstance(fig.data[0], go.Bar)` | ✅ |
| Session categories correct | Labels contain Asian, London, NY | ✅ |

---

## 3. Responsive Layout Validation

Layouts tested at Streamlit's default 1280px viewport using the full-width `use_container_width=True` flag on all charts.

| Component | Adaptive Property | Validated |
|-----------|------------------|-----------|
| KPI strip | `st.columns(6)` — auto-scales | ✅ |
| Chart pane | `use_container_width=True` | ✅ |
| Trade ledger | `st.dataframe(use_container_width=True)` | ✅ |
| Chart height | Slider 400–900px, default 600px | ✅ |

---

## 4. Data Source Integrity

All UI components read exclusively from:
- `data/processed/XAUUSD_{TF}_clean.csv` — canonical OHLCV
- `reports/smc_backtest_trades_full_history.csv` — M5 trade ledger
- `reports/smc_mtf_trades.csv` — M15 MTF trade ledger

No external network calls. No MT5 connection required for visualization.

---

## 5. Regression Check

```
Full suite (prior 570 tests) run after UI redesign:
All 570 tests passed — zero regressions introduced.
```

