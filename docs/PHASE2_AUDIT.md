# GoldFlow Phase 2 Audit and Handoff

## Work performed in this update

- Fixed offline mocked MT5 tests: historical retrieval now checks whether the active `mt5` module reference is `None`, allowing a patched mock client in unit tests while still raising a clear error when the package/client is unavailable in normal execution.
- Integrated configurable displacement detection into `analyze_market_structure`, exposed detected candle indices and a count in `ICTAnalysisResult.summary()`.
- Added Streamlit sidebar controls for displacement ATR period, body/ATR multiplier, and minimum body/range ratio.
- Added chart annotations/hover details for UTC timestamps on structure breaks, FVGs, liquidity sweeps, order blocks, and displacement candles.
- Corrected order-block origin search to begin at the FVG's third/confirmation candle, so the middle candle is considered as the most recent opposing candle. Added a regression test.
- Added operational rule definitions, assumptions, ambiguity notes, and known limitations in `docs/ICT_RULES.md`.

## Files changed

- `src/data/loader.py`
- `src/ict/engine.py`
- `src/ict/order_blocks.py`
- `src/visualization/charts.py`
- `pages/1_Market_Analysis.py`
- `tests/test_ict_order_blocks.py`
- `tests/test_ict_engine.py`
- `tests/test_ict_adversarial.py`
- `README.md`
- `docs/ICT_RULES.md`
- `docs/PHASE2_AUDIT.md`

## Test results in this environment

- `python -m pytest tests -q`: **63 passed**
- `python -m compileall -q src pages tests`: **passed**

The original ZIP baseline had **60 passed, 1 failed** because the loader's import-time `MT5_AVAILABLE` flag blocked a mocked MT5 client. After the targeted fix, the full suite passed.

## Detection definitions

See `docs/ICT_RULES.md` for explicit rules covering:
- strict fractal swings and delayed confirmation
- BOS / CHoCH break rules
- three-candle FVGs and CE
- ATR/body-ratio displacement
- confirmed-level liquidity sweeps
- sweep-to-opposite-break MSS and optional FVG confluence
- FVG-derived order blocks and lifecycle tracking

## Unresolved / outstanding

1. **Live MT5 verification is outstanding.** This environment does not demonstrate a successful connection to the user's Windows MT5 terminal and retrieval of historical bars. Keep this item open until tested on the target machine.
2. MSS currently means sweep followed by an opposite-direction structure break within a bar window. Displacement is not a mandatory MSS condition unless separately incorporated into a stricter rule; optional FVG confluence is supported.
3. First break from neutral trend is labelled CHoCH by convention. Other ICT interpretations may label this differently.
4. Order blocks are currently derived from FVG events; structure breaks do not independently create OBs yet.
5. OHLC bars cannot resolve intrabar sequencing when a candle crosses multiple levels or reaches a zone and invalidation level in the same candle.

No strategy entries/exits, ML training, or automated execution were added.

---

# GoldFlow Phase 2.1: ICT Validation & Reliability Audit

## Objectives & Scope

Phase 2.1 audited detection correctness, temporal invariance (zero look-ahead bias), adversarial edge cases, and Streamlit user interface integration without modifying core trading rules or introducing live trading/strategy execution.

## Verification & Test Results

- Total tests: **79 passed** (previously 63 in Phase 2 baseline).
- Command: `py -3.13 -m pytest -v` (15.33s runtime, 100% pass rate).
- Bytecode compilation: `py -3.13 -m compileall src pages scripts tests app.py` (Exit code 0).

### Key Test Suites Added in Phase 2.1:

1. **`tests/test_ict_adversarial.py` (26 tests)**:
   - 14 temporal invariance property tests (prefix consistency, confirmation delay, UTC enforcement, look-ahead prevention).
   - 12 hand-crafted edge case tests:
     - Equal highs / equal lows strict rejection.
     - Consumed swing protection against repeated breaks.
     - Wick breaks vs. candle-close breaks independence.
     - Outside candles with bilateral breaches resolution.
     - Monotonic handling of missing candles & weekend gaps.
     - Doji candle handling (disqualified from opposing Order Block selection).
     - FVG lifecycle (creation at bar $i+1$, CE midpoint, partial & full mitigation).
     - Sweeps without structure breaks or with delayed breaks.
     - Displacement candles at exact ATR boundary conditions.
     - Order block origin selection backward from confirmation candle.
     - Dataset boundary conditions (0 to minimal candles).
     - Multi-timeframe switching (H4, H1, M15, M5) timestamp preservation.

2. **`tests/test_ui_and_integration.py` (4 tests)**:
   - Chart generation handles empty dataframes without crashing.
   - Dynamic overlay toggles correctly add/remove Plotly trace groups.
   - Tabular summary metrics and event counts match chart trace annotations.
   - Cleaned historical CSVs on disk load and validate without missing columns or errors.

## Temporal Invariance & Look-Ahead Bias Audit

| Event Type | Origin Bar | Confirmation Bar | Earliest Knowledge Time | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Swing Point** | Bar $i$ | Bar $i + k$ | Close of bar $i + k$ | Retrospective formation timestamp $i$; actionable only at $i + k$. |
| **BOS / CHoCH** | Bar $j$ | Bar $j$ | Close of bar $j$ | Can only break swings confirmed before bar $j$ ($j > \text{confirmed\_index}$). |
| **Fair Value Gap** | Bar $i$ | Bar $i + 1$ | Close of bar $i + 1$ | 3-bar pattern; known only upon close of 3rd candle. |
| **Displacement** | Bar $i$ | Bar $i$ | Close of bar $i$ | ATR baseline uses bars prior to $i$. |
| **Liquidity Sweep**| Bar $j$ | Bar $j$ | Close of bar $j$ | High/low penetrates swing level; close confirms rejection back inside. |
| **Market Structure Shift** | Bar $j$ | Bar $j$ | Close of bar $j$ | Sweep followed by opposite break within $N$ bars. |
| **Order Block** | Bar $k$ | Bar $i + 1$ | Close of bar $i + 1$ (FVG confirm) | Origin candle is historical, but OB is confirmed only at FVG close. |

## Streamlit Interface Verifications

- **Data Source Loading**: Verified CSV dataset loading and synthetic generation modes without requiring a live MT5 terminal.
- **Dynamic Timeframe Detection**: Automatic alignment with CSV filename prevents false intraday gap warnings.
- **Overlay Checkboxes**: Verified overlay toggles for Swings, BOS/CHoCH, FVGs, Liquidity Sweeps, Order Blocks, and Displacement Candles.
- **Tabular Synchronization**: Event counts and metrics in Tab 1 agree with chart annotations.
- **Provenance Preservation**: Data cleaning metadata (`.meta.json`) is maintained alongside cleaned CSV files.

