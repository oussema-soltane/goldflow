# GoldFlow — SMC-Primary Market Structure & Trading Analytics Platform

**GoldFlow** is a quantitative Data Science and Business Intelligence research platform for financial market analysis, focused on Gold (**XAU/USD**).

GoldFlow now treats a standalone Smart Money Concepts (SMC) engine as its primary market-analysis framework while retaining the existing ICT engine as a separate selectable framework. Phase 3C descriptive research has been run, and Phase 3D now provides a readiness-gated event-driven simulation. The bundled history passes the repository’s timestamp and structural checks with `READY_WITH_WARNINGS`; its MT5 source is declared in metadata but is not independently authenticated, so the resulting simulations remain exploratory.

---

## 🏛️ Project Architecture

```
goldflow/
├── app.py                      # Main Streamlit overview dashboard
├── pages/
│   ├── 1_Market_Analysis.py    # Live MT5 ingestion, quality audit & Plotly charts
│   ├── 2_Backtesting.py        # Phase 3D SMC event-driven backtest UI
│   ├── 3_BI_Dashboard.py       # Power BI executive summary (Phase 6)
│   └── 4_About.py              # Academic methodology & project details
├── src/
│   ├── smc/                    # Primary, independent SMC event-detection engine
│   ├── ict/                    # Existing ICT engine; retained separately
│   ├── data/
│   │   ├── loader.py           # MT5 connectivity, symbol discovery & data extraction
│   │   ├── validator.py        # OHLC geometric audits, missing values & gap analysis
│   │   └── cleaner.py          # Deduplication & cleaning (zero price fabrication)
│   ├── strategy/               # Pure-SMC setup-candidate hypothesis (not performance-validated)
│   ├── backtesting/            # Event-driven OHLC execution simulator (Phase 3D)
│   └── visualization/
│       └── charts.py           # Institutional Plotly candlestick & volume charts
├── scripts/
│   └── download_data.py        # CLI data download and pipeline script
├── data/
│   ├── raw/                    # Auditable, unmodified raw CSV files
│   └── processed/              # Cleaned, standardized historical datasets
├── reports/
│   ├── data_quality_report.json # Machine-readable data audit report
│   └── data_quality_report.md   # Human-readable data audit report
├── tests/
│   ├── test_smc_engine.py      # SMC pivots, BOS/CHoCH, pools, sweeps, OBs, no-look-ahead, chart overlays
│   ├── test_smc_strategy.py    # Sweep → CHoCH → OB retest setup-candidate tests
│   ├── test_validator.py       # Unit tests for OHLC constraints, gaps, duplicates
│   ├── test_cleaner.py         # Unit tests for deduplication & zero interpolation
│   ├── test_loader.py          # Unit tests for loader, synthetic generation & MT5
│   ├── test_ict_structure.py   # BOS and CHoCH structural break tests
│   ├── test_ict_fvg.py         # Fair Value Gaps & Consequent Encroachment tests
│   ├── test_ict_liquidity.py   # Liquidity sweeps & MSS tests
│   ├── test_ict_order_blocks.py# Institutional Order Blocks & mitigation tests
│   ├── test_ict_engine.py      # Integrated market structure engine tests
│   ├── test_ict_adversarial.py # Adversarial temporal invariance & anti-look-ahead tests (Phase 2.1)
│   └── test_ui_and_integration.py  # Chart overlay, table consistency & disk load tests (Phase 2.1)
├── requirements.txt            # Pinned Python dependencies
├── README.md                   # Documentation and operating guide
└── .gitignore                  # Git ignore rules
```

---

## ⚙️ Installation & Setup (Windows 11)

### 1. Prerequisites
- **Python**: Python 3.11 or 3.13 (64-bit).
- **MetaTrader 5**: Desktop terminal installed with a Demo account configured.

### 2. Install Dependencies
Open **Windows PowerShell** in the project directory:

```powershell
# Step-by-step:
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# Or run as a single chained command in PowerShell (separated by semicolons):
py -3.13 -m venv .venv; .\.venv\Scripts\Activate.ps1; python -m pip install -r requirements.txt
```

---

## 🚀 Running the Platform

### A. Run Automated Unit Tests
To verify all data validation rules, OHLC constraints, and deduplication logic:

```powershell
py -3.13 -m pytest tests -v
```

*The current suite includes Phase 2.1 adversarial checks and Phase 3A research-readiness tests. The exact test count may change as regressions are added.*

### B. Ingest Historical Market Data (CLI)
To run the automated ingestion pipeline across H4, H1, M15, and M5:

```powershell
# If MT5 terminal is open and logged in:
python scripts/download_data.py --symbol YOUR_BROKER_GOLD_SYMBOL --bars 2000

# Offline / Synthetic benchmark mode (works without MT5 open):
python scripts/download_data.py --synthetic --bars 2000
```

Raw files will be saved in `data/raw/`, cleaned files in `data/processed/`, and audit reports in `reports/`.

### C. Phase 3B — Audit Research Data Readiness

After downloading data from a logged-in MT5 terminal, run:

```powershell
py -3.13 scripts/download_data.py --symbol YOUR_BROKER_GOLD_SYMBOL --bars 10000
py -3.13 scripts/research_readiness.py
```

This writes `reports/research_readiness.json` and `reports/research_readiness.md`. The command exits with code `2` when research is blocked by unknown provenance, synthetic data, duplicated OHLC sequences, data-quality failures, missing timeframes, or insufficient history. Recommended minimum history is H4: 2,000 bars; H1: 5,000; M15: 10,000; M5: 10,000. These are research guidelines, not guarantees of statistical power.

**Current bundled-data state (2026-10-19):** `scripts/research_readiness.py` reports `READY_WITH_WARNINGS`, not `BLOCKED`. The current processed data includes original timestamp epoch values and has `timestamp_integrity_status=verified` plus a verified `server_wall_clock` / `Europe/Athens` mode in its sidecars. However, `source_verification_status=declared_not_independently_verified`, so the package's metadata does not independently authenticate the claimed MT5 source. Read the generated readiness report before every run; its status is a gate, not proof of data authenticity or profitability.

MT5's official Python documentation says returned bar/tick times are UTC. The prior live report showed a three-hour discrepancy for this particular terminal, so GoldFlow supports two explicit modes rather than silently assuming either:
- `posix_utc` (default): follow the documented MT5 timestamp contract; no offset is applied.
- `server_wall_clock`: use only if a fresh live diagnostic confirms that this feed's integer timestamps encode server-local wall-clock values. Supply an IANA timezone so historical daylight-saving changes are handled per bar.

First run the read-only live diagnostic while Gold is actively ticking and Windows time synchronization is enabled:
```powershell
py -3.13 scripts/diagnose_mt5_timestamps.py --symbol XAUUSD --server-timezone Europe/Athens
```
If the result is `INCONCLUSIVE`, do not choose a mode yet. The timezone argument is a candidate, not a fact; verify that its DST rules match the server. If the diagnostic clearly supports the documented POSIX mode, download with:
```powershell
py -3.13 scripts/download_data.py --symbol XAUUSD --bars 10000 --timestamp-mode posix_utc --confirm-timestamp-mode-verified
```
If the diagnostic instead supports server-local wall-clock encoding and the IANA timezone has been confirmed, use:
```powershell
py -3.13 scripts/download_data.py --symbol XAUUSD --bars 10000 --timestamp-mode server_wall_clock --server-timezone Europe/Athens --confirm-timestamp-mode-verified
```
`--confirm-timestamp-mode-verified` is an explicit operator attestation that the live diagnostic was reviewed. The loader preserves the original MT5 integer in the raw CSV and records the selected conversion in the sidecar. Do not use the confirmation flag if the diagnostic is inconclusive.

### D. Launch the Interactive Streamlit Web Application
To launch the interactive dashboard:

```powershell
streamlit run app.py
```

The application will open in your default browser at `http://localhost:8501`.

---


### E. SMC as the Primary Framework

The Market Analysis page defaults to **SMC (Primary)**. Use the sidebar's **Primary Analysis Framework** selector to switch to **ICT (Existing)**. These engines are kept separate; the SMC engine does not require ICT FVG, CE, displacement, MSS, or kill-zone logic. Its implemented v1 definitions are documented in `docs/SMC_RULES.md`.

SMC v1 currently detects confirmed swings, close-based BOS/CHoCH, equal-high/low liquidity pools, wick-and-reclaim liquidity sweeps, structure-break-confirmed order blocks, and current premium/discount context. The primary research setup hypothesis is Sweep → opposite CHoCH → OB Retest/Rejection; it emits candidates only and does not place trades or claim profitability. The existing ICT analysis engine remains available separately. **This archive does not contain a complete standalone ICT entry/exit strategy or validated ICT backtest**; preserve the intended ICT rules explicitly before implementing/comparing that strategy. The currently bundled historical data passes the configured readiness gate with warnings; its source authentication remains a limitation, and its backtest results are exploratory only.

## Phase 3D — Frozen-Rule Holdout and Cost Stress Validation

After the event-driven backtest, run a chronological holdout assessment with fixed SMC rules and 1.0x / 1.5x / 2.0x transaction-cost scenarios:

```powershell
py -3.13 scripts/run_smc_validation.py
py -3.13 scripts/run_smc_validation.py --timeframes H4 H1 M15 M5 --train-fraction 0.70
```

The command writes `reports/PHASE3D_SMC_HOLDOUT_VALIDATION.md`, `reports/smc_oos_validation_metrics.json`, and `reports/smc_oos_validation_trades.csv`. The holdout begins after the first 70% of bars in each selected timeframe; the earlier bars provide structural context, but only candidates with signal indices in the final 30% can be executed. No setup parameters are optimized by this runner. The backtest engine's maximum drawdown is close-to-close mark-to-market (open positions are conservatively estimated at executable liquidation cost); a realized-only drawdown is shown separately. New entries at a bar's open use the realized balance entering that bar, not P&L from later same-bar exits.

**Important:** this is a temporal holdout within historical data that has already been examined during Phase 3C/3D. It is useful for temporal stability and execution-cost stress testing, but it is not an untouched independent out-of-sample proof. The timeframe date windows differ, samples can be small, and `END_OF_DATA` liquidation P&L is separately reported. Use a future data collection after freezing the rules for a genuinely independent forward test. Verify broker contract size, point size, spread units, lot step, tick value, and commission before interpreting simulated cash P&L as broker-equivalent.


## Phase 3D.2 — Position lifecycle and time-stop sensitivity

The event-driven engine supports an optional maximum holding duration in bars. Stop/target/gap exits always have priority; when none triggers and the limit is reached, the position closes at the completed bar close using the modeled quote-side spread and adverse slippage. The entry candle counts as bar 1.

Run a direct backtest with a time stop, or compare a baseline against nominal elapsed-time horizons converted to each timeframe's bar count:

```powershell
py -3.13 scripts/run_smc_backtest.py --max-holding-bars 48
py -3.13 scripts/run_smc_lifecycle_stress.py
py -3.13 -m pytest tests/ -v
```

The lifecycle runner writes `reports/PHASE3D_SMC_POSITION_LIFECYCLE_STRESS.md`, `reports/smc_lifecycle_stress_metrics.json`, and `reports/smc_lifecycle_stress_trades.csv`. Horizons are converted to bars based on nominal timeframe duration; actual wall-clock holding time can be longer around closures and data gaps. This is a frozen-entry-rule sensitivity check, not an optimization or profitability claim.

## Phase 3D.3 — Broker Execution Specification Guardrails

Before treating modeled cash P&L as broker-equivalent, capture the exact XAUUSD instrument specification from the same MT5 terminal/server that supplied the history:

```powershell
py -3.13 scripts/capture_mt5_execution_specs.py --symbol XAUUSD
py -3.13 scripts/audit_execution_specs.py
py -3.13 scripts/run_smc_backtest.py --require-matched-execution-spec
```

The capture command updates only metadata sidecars; it does not modify OHLC CSVs. It refuses synthetic datasets, symbol mismatches, and known server mismatches. If the broker uses a suffix or different name, re-ingest the historical data using that exact symbol rather than silently attaching another symbol's contract data. The audit checks point size, contract size, volume bounds/step, tick size/value, XAU/USD/USD currency assumptions, and symbol/server identity. Tick-value arithmetic is cross-checked against contract size × tick size. Exploratory backtests remain possible without captured specs, but outputs carry `ASSUMPTIONS_ONLY` and a prominent warning. Strict mode blocks missing or mismatched specs. Even a passing spec audit does not authenticate historical data provenance or reproduce actual tick-level fills.

More detail: `docs/PHASE3D3_EXECUTION_VALIDATION.md`. The independent-review task for Antigravity is in `docs/ANTIGRAVITY_REVIEW_PHASE3D3.md`.

## 🔍 MetaTrader 5 Broker Symbol Discovery

Brokers use different ticker symbols for Gold:
- Common tickers: `XAUUSD`, `GOLD`, `XAUUSD.a`, `XAUUSDm`, `XAUUSD.pro`.

### How GoldFlow Handles This:
1. GoldFlow automatically queries your connected MT5 terminal's symbol list for candidates matching `*XAU*` or `*GOLD*`.
2. On the **Market Analysis** page (`pages/1_Market_Analysis.py`), the dropdown automatically populates with all detected broker symbols along with their spread, digits, and contract description.
3. You can confirm the exact instrument matching your broker's Market Watch.

---

## 🛡️ Data Quality Standards

GoldFlow adheres to strict data science best practices:
- **No Price Interpolation**: Missing candles are never artificially fabricated or interpolated.
- **Gap Detection**: Weekend and maintenance gaps are classified using UTC timestamps, but broker-specific maintenance windows remain assumptions until verified.
- **Look-Ahead Prevention**: The actively forming, unclosed candle is excluded from historical datasets by default.
- **Auditable Reports**: Every download generates both `data_quality_report.json` and `data_quality_report.md`.

---

## 🗺️ Project Roadmap
- [x] **Phase 1**: Market Data Pipeline (MT5 connectivity, historical extraction, OHLC validation, data cleaning, Plotly charts, Streamlit dashboard, pytest suite).
- [x] **Phase 2**: Existing ICT Market Structure Engine (swing highs/lows, BOS/CHoCH, FVG, displacement, MSS, sweeps, order blocks).
- [x] **Phase 2.1**: ICT Validation & Reliability Audit (adversarial tests, look-ahead checks, Streamlit integration tests).
- [x] **Phase 3A**: Research framework, provenance checks, chronological splits, forward-excursion helpers, and data-readiness audit.
- [x] **Phase 3B.2**: Retrieve 5,000 MT5-declared bars per timeframe, preserve raw timestamp epochs, audit the `server_wall_clock` conversion against the timestamp diagnostic, and pass `scripts/research_readiness.py` with `READY_WITH_WARNINGS`. Independent source authentication remains a caveat.
- [x] **SMC Engine v1 (analysis framework)**: Independent `src/smc/` engine, default primary framework in Market Analysis, swing/structure/liquidity/order-block overlays, explicit temporal rules, and hand-crafted tests. It has been run on the bundled MT5-declared history but is not out-of-sample validated.
- [x] **SMC Setup Candidate Hypothesis**: Sweep → opposite CHoCH → order-block retest/rejection, with stop reference beyond the sweep extreme, opposing-liquidity target when already known, configurable fixed-R fallback, minimum reward/risk filtering, and optional prior-confirmed premium/discount filter. Candidate detection is separated from execution and evaluated in Phase 3D; no orders are sent and profitability is not validated. See `docs/SMC_SETUP_HYPOTHESIS.md`.
- [x] **Phase 3C**: Pure-SMC event census, setup candidate funnel, and forward MFE/MAE research on the bundled MT5-declared history. Descriptive statistics only.
- [ ] **ICT Continued Research**: Keep ICT available as a separate framework and evaluate it independently rather than silently combining its conditions with SMC.
- [x] **Phase 3D engine implementation**: Event-driven OHLC simulation with next-bar-open fills, spread/slippage/commission, stop-first collisions, sizing, concurrency, trade logs, and performance metrics. See `docs/PHASE3D_BACKTEST_ENGINE.md`.
- [x] **Phase 3D validation tooling**: Frozen-rule chronological holdout and 1.0x/1.5x/2.0x execution-cost stress runner; outputs separate rule exits and end-of-data mark-outs. This is not an untouched out-of-sample test.
- [x] **Phase 3D.2 position lifecycle diagnostics**: Optional time-stop handling and frozen-entry-rule lifecycle sensitivity runner; time exits, end-of-data liquidations, P&L, and drawdown are reported separately. This is not an optimization or out-of-sample validation.
- [x] **Phase 3D.3 execution-specification guardrails**: MT5 symbol-spec capture utility, broker/symbol mismatch detection, execution assumptions embedded in backtest output, a strict config-match gate, and an explicit allowlist for documented linear contract-size calculation modes. See `docs/PHASE3D3_EXECUTION_VALIDATION.md`.
- [ ] **Phase 3D validation follow-up**: Run the capture utility on the user's intended MT5 terminal; verify the live `trade_calc_mode` against the allowlist; reconcile broker/config mismatches; test with tick/deal-level execution; and collect a genuinely untouched forward period after rules are frozen.
- [ ] **Phase 5**: Multi-page Streamlit application polish and comparison view.
- [ ] **Phase 6**: Business Intelligence (Power BI) dashboard.
- [ ] **Phase 7**: Optional machine-learning setup scoring after sufficient real data and a baseline strategy exist.
- [ ] **Phase 8**: Optional supervised demo execution only after validation and explicit approval.


### Phase 3D.3.2.1 — Dynamic MT5 calculation-mode resolution

The execution-spec capture now resolves symbolic calculation-mode names from the active MetaTrader5 package and preserves the code/name mapping for audit. It does not hard-code enum IDs. Audit sidecar paths are serialized with stable POSIX separators across Windows/POSIX. Missing/ambiguous mappings and unsupported calculation formulas block strict execution. The latest suite is **328 passed**; compilation passes, readiness is `READY_WITH_WARNINGS`, and the bundled data correctly remains `ASSUMPTIONS_ONLY` until live terminal specifications are captured. See `reports/PHASE3D3_2_CALC_MODE_GUARD.md`, `reports/PHASE3D3_2_2_PATH_NORMALIZATION.md`, and `docs/ANTIGRAVITY_REVIEW_PHASE3D3_2_2.md`.
