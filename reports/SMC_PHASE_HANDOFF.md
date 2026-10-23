# GoldFlow SMC-primary implementation handoff

**Review date:** 2026-10-19  
**Input package:** `GoldFlow_Phase3B_Reviewed.zip`  
**Git metadata:** Not present in the supplied archive; no commit hash can be truthfully reported.

## Architecture decision

- **Primary analysis framework:** independent Pure-SMC v1 engine in `src/smc/`.
- **Existing framework retained:** `src/ict/` and its Market Analysis UI settings remain separate/selectable. SMC does not import the ICT engine or require ICT-specific FVG, displacement, MSS, CE, or kill-zone conditions.
- **Current SMC setup candidate:** liquidity sweep → opposite CHoCH → order-block retest/rejection. The detector produces close-confirmed candidates and reference prices only; it is not an execution or backtested strategy.
- **ICT strategy scope caveat:** this uploaded snapshot has an ICT analysis/event engine, but no complete standalone ICT entry/exit strategy or validated ICT backtest was found. Do not invent entry, invalidation, target, or management rules and call them the user's existing strategy. Keep ICT engine unchanged and explicitly capture those rules before separately implementing a candidate detector/backtest.

## Main files

### Added

- `src/smc/__init__.py`
- `src/smc/models.py`
- `src/smc/engine.py`
- `src/strategy/smc_setups.py`
- `tests/test_smc_engine.py`
- `tests/test_smc_strategy.py`
- `docs/SMC_RULES.md`
- `docs/SMC_SETUP_HYPOTHESIS.md`
- `docs/PHASE3C_SMC_ENGINE.md`

### Updated

- `src/strategy/__init__.py`
- `src/visualization/charts.py`
- `pages/1_Market_Analysis.py` — defaults to SMC; existing ICT mode remains selectable
- `app.py` — SMC-primary platform framing and data-gate warning
- `pages/2_Backtesting.py` — current hypothesis, ICT limitation, and backtest gate
- `pages/4_About.py`
- `README.md`
- `reports/research_readiness.json` and `reports/research_readiness.md`

## Verification run in this workspace (Phase 3B.2 & Phase 3C Complete)

- `python -m pytest tests/ -q` — **254 passed** after Phase 3D.2 position-lifecycle tests.
- `python -m compileall src pages scripts tests app.py -q` — **passed, exit code 0**.
- Actual MT5 live retrieval — **SUCCESSFULLY PERFORMED**. Connected to interactive terminal `MetaQuotes-Demo` (Account #5057357767).
- Retrieved fresh history for `XAUUSD` across all 4 timeframes (5,000 bars each on H4, H1, M15, M5).
- Original MT5 integer epochs preserved in `time_raw_epoch` and verified against live tick diagnostics (`Europe/Athens` IANA timezone).
- `python scripts/research_readiness.py` — **PASSED (READY_WITH_WARNINGS), exit code 0**. Zero blockers across all timeframes.
- Phase 3C SMC Descriptive Research — **SUCCESSFULLY EXECUTED** via `scripts/run_smc_research.py`.
- Evaluated 20,000 verified MT5 bars across H4, H1, M15, M5.
- Analyzed 5,376 swing points, 1,884 structure breaks, 1,401 liquidity pools, 1,296 sweeps, and 1,833 order blocks.
- Detected 136 primary SMC setup candidates (68 Long / 68 Short): H4 (15), H1 (30), M15 (49), M5 (42).
- Look-ahead-free forward excursions computed using next-candle open as research entry proxy across 4 horizons per timeframe (544 evaluations, 0 censored).
- Reports written:
  - `reports/PHASE3C_SMC_DESCRIPTIVE_RESEARCH.md`
  - `reports/smc_descriptive_research.json`
  - `reports/smc_setups_all.csv` (136 setups)
  - `reports/smc_excursions.csv` (544 horizon rows)
  - `reports/smc_events_*.csv` and `reports/smc_setups_*.csv` per timeframe.

## Phase 3D — Event-Driven Backtesting (Implemented)

The first formal event-driven simulator is now implemented in `src/backtesting/engine.py` and driven by `scripts/run_smc_backtest.py`. It preserves the independent Pure-SMC candidate detector and does not alter the ICT engine.

- Next-bar-open entries with quote-side spread, configurable adverse slippage and commission.
- Conservative stop-first handling when one OHLC bar touches both stop and target, plus worse opening fills on gaps through stops.
- Fixed-fractional risk sizing using executable stop distance and round-turn commission assumptions; lot sizes round down to the configured step.
- Maximum concurrency constraints, skip reasons, trade-level audit logs, equity paths, expectancy, profit factor, and drawdown metrics.
- `END_OF_DATA` exits are reported separately from stop/target outcomes so sample-boundary liquidation does not masquerade as a planned win/loss.
- Full-history and common-window reports are both preserved. The shared window is **2026-09-22 23:15 UTC to 2026-10-19 13:00 UTC**.

### Preliminary results (defaults: $10,000 starting equity, 1% risk fraction, 100 oz/lot, 0.20 fallback spread, $0.05/oz adverse slippage, one concurrent position per timeframe)

| Timeframe / window | Candidates | Rule exits | End-of-data exits | Skipped | Rule-exit win rate | Net P&L incl. end-of-data | Max drawdown (MTM) |
|---|---:|---:|---:|---:|---:|---:|---:|
| H4 full history | 15 | 13 | 0 | 2 | 30.77% | +$448.73 | $751.76 |
| H1 full history | 30 | 27 | 0 | 3 | 29.63% | +$107.96 | $993.62 |
| M15 full history | 49 | 36 | 0 | 13 | 16.67% | -$878.99 | $1,411.38 |
| M5 full history | 42 | 31 | 1 | 10 | 22.58% | -$252.34 | $1,304.86 |
| H4 common window | 0 | 0 | 0 | 0 | N/A | $0.00 | $0.00 |
| H1 common window | 2 | 2 | 0 | 0 | 0.00% | -$185.64 | $454.92 |
| M15 common window | 20 | 2 | 1 | 17 | 100.00% | +$1,875.94 | $1,838.85 |
| M5 common window | 42 | 31 | 1 | 10 | 22.58% | -$503.62 | $1,304.86 |

**Interpretation caution:** M15 common-window net P&L includes a **+$1,637.74 `END_OF_DATA` mark-out** from a short position that did not reach its take-profit before the sample ended. Its two rule-resolved trades won, but that is a very small sample and the positive mark-out must not be described as validated strategy performance. Full-history date ranges differ across timeframes and are not a controlled cross-timeframe experiment. Several trades are skipped by the one-position concurrency rule. A stop gap can exceed the planned risk budget.

### New artifacts

- `src/backtesting/engine.py`
- `scripts/run_smc_backtest.py`
- `tests/test_event_backtesting.py` (20 execution-model tests, including time-stop ordering and validation)
- `docs/PHASE3D_BACKTEST_ENGINE.md`
- `reports/PHASE3D_SMC_EVENT_BACKTEST_FULL_HISTORY.md`
- `reports/PHASE3D_SMC_EVENT_BACKTEST_COMMON_WINDOW.md`
- `reports/smc_backtest_metrics_full_history.json` and `reports/smc_backtest_metrics_common_window.json`
- `reports/smc_backtest_trades_full_history.csv` and `reports/smc_backtest_trades_common_window.csv`

### Remaining Phase 3D follow-up

1. Independently verify broker/source provenance and confirm the exact XAUUSD symbol's `point`, `trade_contract_size`, volume minimum/step, tick value, spread units, and commission schedule.
2. Validate bid/ask and intrabar behavior against tick data or MT5 deal simulation; OHLC cannot reconstruct the true tick path.
3. Freeze the setup and execution rules, then collect a genuinely untouched forward period. The current chronological holdout uses data already examined in Phase 3C/3D and is not independent confirmation.
4. Position lifecycle is now configurable through an optional `max_holding_bars` time stop. Run the new sensitivity diagnostics and independently review execution semantics before treating any horizon as a preferred rule; structural invalidation rules remain a separate design decision.
5. Write down a complete ICT entry, invalidation, target, and management hypothesis before any fair ICT-vs-SMC comparison.

## Scope / no overclaiming

No live or demo orders, machine-learning training, or trading automation were added. Phase 3D cash P&L figures are outputs of the explicitly configured simulation, not broker-confirmed fills or claims of future profitability. The data sidecars declare the MetaTrader 5 API and report verified timestamp integrity, but `source_verification_status=declared_not_independently_verified`; independent authenticity is not established by the code. The workspace does not include `.git`, so this handoff is not a commit record.

## Verification at handoff

- `python -m pytest tests/ -q` — **256 passed** after holdout, accounting-hardening, Phase 3D.2 lifecycle tests, and Antigravity remediation regressions.
- `python -m compileall src pages scripts tests app.py -q` — **passed**.
- `python scripts/research_readiness.py` — **READY_WITH_WARNINGS**, zero blockers.
- `python scripts/run_smc_backtest.py` — **completed**, full-history artifacts written.
- `python scripts/run_smc_backtest.py --mode common-window` — **completed**, shared-window artifacts regenerated with mark-to-market drawdown.
- `python scripts/run_smc_validation.py` — **completed**, 70/30 frozen-rule chronological holdout and 1.0x/1.5x/2.0x cost stress artifacts written.

## Phase 3D validation tooling addendum (2026-10-19)

Added `scripts/run_smc_validation.py` and `tests/test_smc_validation.py` for a chronological 70/30 frozen-rule holdout and transaction-cost stress at 1.0x, 1.5x, and 2.0x. Artifacts are written to `reports/PHASE3D_SMC_HOLDOUT_VALIDATION.md`, `reports/smc_oos_validation_metrics.json`, and `reports/smc_oos_validation_trades.csv`.

The holdout is not an untouched independent OOS test: Phase 3C/3D already examined the same historical bars. The test is diagnostic for temporal stability and cost sensitivity only. The per-timeframe holdout dates differ, and reports keep `END_OF_DATA` liquidation separate from stop/target exits. Any P&L dominated by `END_OF_DATA` must not be treated as an established edge. Independent broker symbol specifications and genuinely new post-freeze history remain required.


## Execution-accounting hardening addendum (2026-10-19)

The Phase 3D engine was further hardened during holdout review:

- `max_drawdown_cash` and `max_drawdown_pct` now use a per-bar close-to-close mark-to-market equity curve, estimating open-position liquidation with current spread, adverse slippage, and round-turn commission. Realized-only drawdown is reported separately as `max_realized_drawdown_cash` / `max_realized_drawdown_pct`.
- New entries at a bar's open size from the realized equity balance at the start of that bar, so a position exit that occurs later in the same bar cannot increase the new entry's risk budget.
- The result object and full-history/common-window metrics now include both mark-to-market and realized equity curves. Intrabar equity minima remain unknowable from OHLC bars.
- Regression tests specifically cover floating drawdown that recovers before exit and prevent same-bar realized P&L from changing new-entry size.


### Holdout validation results summary

| Timeframe | Holdout candidates | 1.0x cost rule exits | 1.0x rule-exit net P&L | 2.0x cost rule-exit net P&L | Critical caveat |
|---|---:|---:|---:|---:|---|
| H4 | 5 | 4 | +$133.39 | +$135.03 | Only 4 resolved exits; insufficient sample for confidence |
| H1 | 10 | 10 | -$591.95 | -$582.67 | 10% win rate; profit factor about 0.27 |
| M15 | 18 | 0 | $0.00 | $0.00 | One `END_OF_DATA` mark-out (+$1,924.26 at 1.0x) after 1,422 bars; 17 candidates skipped by concurrency |
| M5 | 17 | 14 | +$150.58 | +$46.29 | Net P&L includes an additional +$300.82 end-of-data mark-out at 1.0x; profit factor falls to about 1.04 under 2.0x costs |

The holdout is per-timeframe and covers different calendar periods, so these figures are not a fair cross-timeframe ranking. They are diagnostics, not evidence that a strategy is ready for live execution. Maximum drawdown in new reports is close-to-close mark-to-market and reflects the floating drawdown hidden by the former realized-only calculation.


## Phase 3D.2 position-lifecycle diagnostic (2026-10-19)

Added optional time-based position exit handling to `src/backtesting/engine.py`. `max_holding_bars` is optional and counts the entry candle as bar 1. When configured, stop/target/gap execution is evaluated first; if none triggers and the bar count reaches the cap, the position closes at the completed candle's executable close with modeled spread and adverse slippage. `TIME_STOP` is included as a rule exit and is also reported separately.

Added `scripts/run_smc_lifecycle_stress.py`, which compares the no-time-stop baseline against nominal 4h, 8h, 24h and 48h holding caps while keeping entry rules and modeled costs fixed. Outputs: `reports/PHASE3D_SMC_POSITION_LIFECYCLE_STRESS.md`, `reports/smc_lifecycle_stress_metrics.json`, and `reports/smc_lifecycle_stress_trades.csv`. The nominal hour-to-bar conversion is not a strict wall-clock deadline because weekends, maintenance closures, holidays and missing candles create elapsed-time gaps.

### Lifecycle stress observations (in-sample diagnostic only)

| Timeframe | No-time-stop net P&L | Nominal 4h cap net P&L | 4h cap max MTM DD |
|---|---:|---:|---:|
| H4 | +$448.73 | -$378.82 | $386.11 |
| H1 | +$107.96 | -$445.78 | $780.04 |
| M15 | -$878.99 | +$1,328.55 | $654.15 |
| M5 | -$252.34 | -$781.23 | $1,782.65 |

These contrasting results demonstrate that trade management is highly sensitive on this small, previously inspected sample. They do **not** establish that 4h or any other cap is optimal. Choosing a horizon from this same sample would add another layer of in-sample selection bias. Keep these runs as diagnostics and require an independent review plus genuinely new post-freeze history before drawing conclusions.

### Phase 3D.2 verification

- `python -m pytest tests/ -q` — **254 passed**.
- `python -m compileall src pages scripts tests app.py -q` — **passed**.
- `python scripts/research_readiness.py` — **READY_WITH_WARNINGS**, zero critical blockers.
- `python scripts/run_smc_lifecycle_stress.py` — **completed** for H4/H1/M15/M5 and all five lifecycle scenarios.
- `python scripts/run_smc_backtest.py --timeframes M5 --max-holding-bars 48 --output-dir /tmp/goldflow_phase3d2_smoke` — **completed**, confirming the direct CLI flag and output generation.

Independent review prompt for the second agent is saved as `docs/ANTIGRAVITY_REVIEW_PHASE3D2.md`. The review should focus on execution correctness, timing, costs, and accounting—not tuning to the best P&L.


## Antigravity independent-review remediation (2026-10-20)

Antigravity's Phase 3D.2 review identified one medium-severity order-entry validation defect and two low-severity consistency issues. The following remediations were applied:

- **Pre-triggered stop rejection:** At entry, long candidates now require `stop < bid_open`; short candidates require `stop > ask_open` where `ask_open = bid_open + spread`. This prevents orders whose stop was already crossed by the executable quote from being accepted and then mislabeled as a new `STOP_GAP` exit. Two regression tests cover the long Bid-side and short Ask-side counterexamples.
- **Reproducible UI horizons:** The Backtesting page now offers the nominal holding bar values `1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 96, 192, 288, 576` plus `No time stop`, including values needed to reproduce lifecycle stress cases. These remain bar-count limits, not guaranteed wall-clock durations.
- **Verification count:** The prior stale verification entry is corrected. The current suite includes **256 passing tests** after adding the two stop-validation regressions.

Verification performed in the packaged environment:

- `python -m pytest tests/test_event_backtesting.py -q` — **22 passed**.
- `python -m pytest tests/ -q` — **256 passed**.
- `python -m compileall src pages scripts tests app.py -q` — **passed**.
- `python scripts/research_readiness.py` — **READY_WITH_WARNINGS**, no critical blockers.

The review's broader conclusions remain unchanged: core signal timing and accounting reconciliation passed its audit, but OHLC cannot reveal true intrabar path, point/contract assumptions still need broker confirmation, and the M15 nominal 4h result must not be selected as an optimized rule from this in-sample sample.


## Phase 3D.3 — Execution specification guardrails (2026-10-20)

This phase adds a broker-specification audit and strict execution-spec gate so that cash P&L/position size is not presented as broker-equivalent while key symbol properties are still assumptions. No SMC signal rules or lifecycle parameters were tuned.

- Added `src/research/execution_spec_audit.py` to validate point size, contract size, lot min/step/max, digits, tick size/value, XAU/USD/USD currency assumptions, symbol identity, and MT5 broker-server identity against `BacktestConfig`.
- Added `scripts/capture_mt5_execution_specs.py`. On the user's Windows environment with the intended MT5 terminal connected, it reads the actual `symbol_info`, account currency and server; only the JSON sidecars are modified, never OHLC CSV data. It refuses known symbol/server mismatches and synthetic datasets.
- Added `scripts/audit_execution_specs.py`, a Streamlit warning/config panel, and `--require-matched-execution-spec` gates to backtest, holdout and lifecycle runners. Exploratory mode remains available but labels outputs `ASSUMPTIONS_ONLY`; strict mode blocks until a captured specification matches the active config.
- Tick-value arithmetic is cross-checked under the supported XAU-base/USD-profit/USD-account assumptions. Direct config mismatches are reported ahead of derived tick-value arithmetic, while the full tick diagnostic remains recorded.
- Refreshed the execution-audit snapshot embedded in the main full-history, common-window, lifecycle and chronological-holdout JSON reports.

### Phase 3D.3 verification (2026-10-20)

- `python -m pytest tests/ -q` — **293 passed**.
- `python -m compileall src pages scripts tests app.py -q` — **passed**.
- `python scripts/research_readiness.py` — **READY_WITH_WARNINGS**, no critical blockers.
- `python scripts/audit_execution_specs.py` — **ASSUMPTIONS_ONLY** (expected exit 2; the processed sidecars still have no real captured MT5 instrument specification).
- Exploratory M5 CLI run completed with an `ASSUMPTIONS_ONLY` warning; strict mode returned exit 2 before simulation, as designed.
- The lifecycle and holdout outputs were refreshed separately per timeframe due execution limits; their merged scenario tables include H4, H1, M15 and M5. Embedded audit objects were then refreshed from the same current processed-data audit.

### Items that remain user-terminal dependent

The MT5 capture utility has **not** been run here against the user's logged-in terminal; the real broker specification is therefore still unknown. On the target Windows PC, connect the same MT5 broker/server used to acquire the history and run `python scripts/capture_mt5_execution_specs.py --symbol XAUUSD`, then inspect `reports/execution_spec_audit.md`. If symbol name/server differs, re-ingest with the exact symbol rather than attaching unrelated properties. A passing specification audit still does not authenticate the historical data source or reproduce tick-level execution.

The historic reports remain diagnostics only. The M15 lifecycle flip under a nominal 4-hour bar cap is still a conspicuous in-sample/concurrency-sensitive result and must not be adopted as an optimal rule. The present holdout uses historical data examined in earlier phases and is not genuine unseen out-of-sample validation.

The Antigravity review brief for this milestone is `docs/ANTIGRAVITY_REVIEW_PHASE3D3.md`. Request independent findings with specific file/line references and reproductions; do not ask that agent to optimize the entry or time-stop rules.


## Phase 3D.3.1 — Independent audit remediation (2026-10-20)

Antigravity's follow-up correctness audit identified one medium-severity cross-sidecar partial-write risk and three lower-severity validation/diagnostic gaps. Remediation details are in `reports/PHASE3D3_ANTIGRAVITY_REMEDIATION.md`.

- `scripts/capture_mt5_execution_specs.py` stages byte-exact same-filesystem rollback backups for all matching sidecars before writing. If a write fails, attempted sidecars are restored with atomic replacements; any rollback failure is surfaced explicitly. OHLC CSV files remain untouched.
- `src/research/execution_spec_audit.py` now emits `wrong_type_fields` for present-but-invalid numeric fields and rejects `digits < 1`. The Markdown audit exposes that diagnostic column. The follow-up allowlists only documented linear contract-size profit calculation modes for the tick-value formula; futures/tick-price, bonds, collateral, unknown, and malformed modes block strict validation.
- Added tests for NaN, infinity, boolean and malformed-string numeric fields, missing account currency, zero/negative/fractional digits, missing account/server identity, rollback on a simulated second-sidecar write failure, failure after a replacement, and rollback failure with preserved recovery backup. The captured-spec test fixture now includes `trade_tick_value`.
- Verification: `python -m pytest tests/ -q` — **304 passed**; compilation passed. `python scripts/audit_execution_specs.py` still returns `ASSUMPTIONS_ONLY` (exit 2, expected) because actual live-terminal specifications have not been captured.
- No SMC signal or holding-period parameters were changed. The results remain exploratory, and this fix does not establish a trading edge.


## Phase 3D.3.2 — Calculation-mode formula guard (2026-10-20)

- Official MQL5 symbol-property documentation distinguishes profit calculation formulas by `ENUM_SYMBOL_CALC_MODE`. GoldFlow's current risk engine uses a price-distance × contract-size model, so the execution-spec audit now explicitly allowlists only the modes whose documented profit formula is `(close_price - open_price) × Contract_Size × Lots`: FOREX, FOREX_NO_LEVERAGE, CFD, CFDINDEX, CFDLEVERAGE, EXCH_STOCKS, and EXCH_STOCKS_MOEX.
- Futures/tick-price modes, bond modes, collateral mode, unknown enum values, and missing/malformed/non-integral modes are blocked from strict validation. Tick-value arithmetic is not evaluated unless both the USD/XAU currency gate and calculation-mode allowlist pass.
- Audit output now reports the numeric calculation mode, its known name where available, allowlist status, and an explicit blocking reason. The capture fixture now includes `trade_calc_mode` and `trade_tick_value`.
- The official formula reference is https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants.
- This changes only specification validation and diagnostics—not SMC signals, exits, holding periods, or historical trade calculations. The actual installed broker's calculation mode still must be captured from the user's intended MT5 terminal.


### Phase 3D.3.2 verification addendum

- Full suite after calculation-mode allowlist and loader completeness hardening: **322 passed**.
- `compileall` passed across `src`, `pages`, `scripts`, `tests`, and `app.py`.
- `research_readiness.py`: `READY_WITH_WARNINGS` (exit 0).
- `audit_execution_specs.py`: `ASSUMPTIONS_ONLY` (exit 2, expected; actual terminal specifications are not available in this workspace).
- Strict mode remains fail-closed. A dedicated regression test proves an unsupported futures calculation mode is rejected before OHLC CSV loading.
- `reports/execution_spec_audit.json` was regenerated, and its snapshot was synchronized into the full-history, common-window, lifecycle and holdout metrics JSON files. Historical trade calculations are unchanged.
- Independent follow-up review brief: `docs/ANTIGRAVITY_REVIEW_PHASE3D3_2.md`. The actual broker's calc mode, point/tick/contract/lot values still need capture from the user's intended MT5 terminal.


## Phase 3D.3.2.1 — Dynamic calculation-mode resolution hardening (2026-10-20)

- Avoided hard-coded numeric enum IDs. MT5 calculation-mode names are resolved from the active MetaTrader5 Python package's `SYMBOL_CALC_MODE_*` constants, with the observed name-to-code map saved in the metadata sidecar and validated by the audit. Ambiguous or missing matches fail closed.
- Corrected completeness classification: a module constant map alone is not an instrument capture; `symbol_info() is None` stays `unavailable`, while a real but incomplete symbol record stays `captured_incomplete`.
- Added regressions for empty/ambiguous constant maps and numeric/name/map mismatches; audit output now has explicit `CALC_MODE_MISMATCH` diagnostics.
- No SMC signals, entry/exit criteria, holding-period choices, or trade calculations were changed.
- Final verification on 2026-10-20: **327 tests passed**; `compileall` passed; `research_readiness.py` returned `READY_WITH_WARNINGS` (exit 0); `audit_execution_specs.py` returned `ASSUMPTIONS_ONLY` (exit 2, expected without live terminal capture); strict M5 backtest refused before execution (exit 2, expected).
- Refreshed all five embedded metric audit snapshots from `reports/execution_spec_audit.json`. Compared against the Phase 3D.3.1 package, each snapshot's trade/config payload is unchanged; only audit metadata/timestamp fields differ.


## Phase 3D.3.2.2 — Cross-platform audit path normalization (2026-10-20)

Antigravity's review passed all eight Phase 3D.3.2.1 calculation-mode checks and identified one informational issue: audit `sidecar_path` strings used platform-native separators, yielding cosmetic Windows/POSIX snapshot differences. The audit now serializes paths through `_stable_path_text(PurePath)` / `PurePath.as_posix()`. A regression test uses `PureWindowsPath` so the Windows path case is exercised even on non-Windows runners.

- `python -m pytest tests/ -q` — **328 passed**.
- `python -m compileall -q src pages scripts tests app.py` — passed.
- `python scripts/research_readiness.py` — `READY_WITH_WARNINGS`, exit 0.
- Execution specification audit — `ASSUMPTIONS_ONLY`, exit 2, expected until actual specs are captured from the intended MT5 terminal.
- Strict M5 backtest — blocked before simulation with `ASSUMPTIONS_ONLY`, exit 2, as intended.
- Audit status/dataset count remains consistent across all five metrics JSON artifacts. No SMC rules or historical trade calculations were changed.

The remaining external dependency is live MT5 capture on the user's Windows machine and independent confirmation that historical feed provenance is authentic. Antigravity follow-up instructions are in `docs/ANTIGRAVITY_REVIEW_PHASE3D3_2_2.md`.


## Phase 3D.3.3 — M15 Integrity Recovery, Execution-Spec Validation, and Research Reproducibility (2026-10-20)

Comprehensive handoff details are recorded in `reports/PHASE3D3_3_INTEGRITY_AND_RESEARCH_HANDOFF.md`.

- **M15 Integrity Recovery:** Re-downloaded 5,000 completed bars for M15 from live MT5 (`server_wall_clock`, `Europe/Athens`). Zero future candles, zero duplicates, monotonic UTC timestamps, full raw epoch preservation. Legacy 1,500-bar partial files quarantined to `data/quarantine/legacy_m15_quarantine/`.
- **Downloader Hardening:** Implemented fail-closed transactional data replacement (`scripts/download_data.py`) with staging files, atomic promotion, rollback protection on error, and explicit nonzero exit codes on any timeframe failure or bar deficit. Added full test coverage in `tests/test_download_safety.py`.
- **Timestamp Integrity Test Fix:** Resolved the stale test failure honestly by distinguishing all three states: `verified`, `normalized_by_explicit_mode` (unverified, blocked by readiness), and `blocked_legacy_fixed_offset`.
- **Shared Research Gate Enforcement:** Refactored `src/research/smc_research.py::load_and_verify_inputs` to enforce authoritative data readiness, raw hash checking, row count verification, future candle exclusion, and OHLC validity.
- **Execution-Spec Capture & Tick-Value Reconciliation:** Live MT5 `symbol_info` captured for `XAUUSD` across all 4 sidecars (`trade_calc_mode = 4` / `SYMBOL_CALC_MODE_CFDLEVERAGE`, contract size = 100, tick size = 0.01, tick value = 0.1). Read-only inquiry via `order_calc_profit` confirmed $1.00 profit for 1.0 lot and $0.10 for 0.1 lot. Formulas were NOT altered to force a pass; strict audit remains fail-closed on `TICK_VALUE_MISMATCH`, and strict backtest refuses execution as designed.
- **Phase 3C Deliverables Regenerated:** Reran `scripts/run_smc_research.py` on the verified datasets, regenerating `reports/PHASE3C_SMC_DESCRIPTIVE_RESEARCH.md`, `reports/smc_descriptive_research.json`, setups, and excursions.
- **Final Verification:**
  - `py -3.13 -m pytest tests/ -v`: **350 passed, 0 failed**.
  - `py -3.13 -m compileall src pages scripts tests app.py -q`: **passed, exit code 0**.
  - `py -3.13 scripts/research_readiness.py`: **READY_WITH_WARNINGS (exit 0)**.
  - `py -3.13 scripts/audit_execution_specs.py`: **TICK_VALUE_MISMATCH (exit 1, fail-closed)**.
  - `py -3.13 scripts/run_smc_backtest.py --timeframes M5 --require-matched-execution-spec`: **Blocked (exit 1, fail-closed)**.


## Phase 3D.3.4 — Tick-Value Reconciliation and SMC Backtest Calibration (2026-10-20)

Comprehensive handoff details and evidence logs are recorded in `reports/PHASE3D3_4_TICK_VALUE_AND_BACKTEST_HANDOFF.md` and `reports/mt5_live_tick_reconciliation_inquiry.json`.

- **Live MT5 Empirical Inquiry & Root Cause:**
  - Conducted live terminal inquiry (`order_calc_profit`) against connected MT5 terminal (MetaQuotes-Demo, Build 6274, Account #5057357767).
  - Confirmed empirical reality: while `symbol_info.trade_tick_value` reports `0.1` (calibrated to a mini 0.1-lot or 10-point tick unit), MT5's actual profit calculation engine under `SYMBOL_CALC_MODE_CFDLEVERAGE` evaluates $(\text{close} - \text{open}) \times \text{contract\_size} (100) \times \text{lots}$, yielding exactly **+$1.00 USD** per 0.01 tick for 1.0 lot, and **+$0.10 USD** for 0.1 lot.
  - GoldFlow's internal linear model in `src/backtesting/engine.py` matches the true MT5 execution engine.
- **Reconciliation Engine & Cross-Dataset Audit:**
  - Added live inquiry function `inquire_mt5_symbol_execution_reconciliation()` in `src/data/loader.py` testing BUY/SELL across 5 volume tiers (0.01 to 1.0 lot).
  - Enhanced `src/research/execution_spec_audit.py` to reconcile `trade_tick_value = 0.1` when supported by live terminal inquiry evidence, setting status to `MATCHED_CAPTURED_DEFAULTS` with an explicit, visible warning `TICK_VALUE_RECONCILED` (never silent suppression).
  - Implemented cross-dataset specification consistency check (`check_cross_dataset_spec_consistency()`) validating essential calculation fields (`digits`, `point`, `trade_contract_size`, `trade_tick_size`, `volume_min`, `volume_step`, `volume_max`, `trade_calc_mode`, `currency_base`, `currency_profit`, `account_currency`, `authoritative_calculation_method`) across all 4 timeframes.
- **Sidecar Synchronization:**
  - Refreshed all 4 sidecars (`H4`, `H1`, `M15`, `M5`) via `scripts/capture_mt5_execution_specs.py --symbol XAUUSD` to embed live terminal inquiry evidence and calculation bindings.
- **Preflight Gates & Calibrated Backtests:**
  - `scripts/audit_execution_specs.py`: Exit code 0 (`MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE`).
  - `scripts/research_readiness.py`: Exit code 0 (`READY_WITH_WARNINGS`).
  - Strict execution gate `--require-matched-execution-spec` now opens cleanly for all calibrated backtests.
  - Executed full-history backtest (`reports/PHASE3D_SMC_EVENT_BACKTEST_FULL_HISTORY.md`, `reports/smc_backtest_metrics_full_history.json`).
  - Executed common-window backtest (`reports/PHASE3D_SMC_EVENT_BACKTEST_COMMON_WINDOW.md`, `reports/smc_backtest_metrics_common_window.json`).
  - Executed holdout validation (`reports/PHASE3D_SMC_HOLDOUT_VALIDATION.md`, `reports/smc_oos_validation_metrics.json`).
  - Executed lifecycle position stress (`reports/PHASE3D_SMC_POSITION_LIFECYCLE_STRESS.md`, `reports/smc_lifecycle_stress_metrics.json`).
- **Final Verification:**
  - Pytest suite: **358 passed, 0 failed** (added 8 new execution audit & backtest regression tests).
  - Compilation: **0 errors** across `src`, `pages`, `scripts`, `tests`, `app.py`.
  - Strategy separation: Pure SMC primary engine remained completely decoupled from the existing ICT engine; no strategy parameters were optimized.


## Phase 4 — SMC Strategy Validation, Robustness Testing, and Performance Evaluation (2026-10-20)

Comprehensive deliverables: `reports/PHASE4_STRATEGY_VALIDATION.md`, `reports/PHASE4_ROBUSTNESS_ANALYSIS.md`, `configs/smc_v1_frozen.json`, `reports/smc_phase4_validation_metrics.json`, and `reports/smc_phase4_robustness_metrics.json`.

### 1. Strategy Version 1 Frozen Specification
- Created `configs/smc_v1_frozen.json` freezing the exact version-1 rules prior to primary evaluation:
  - Setup sequence: Liquidity Sweep => Opposite CHoCH => Order-Block Retest/Rejection.
  - Strict fractal pivot detection (k=2 bars, 2-bar confirmation delay).
  - Close-based CHoCH opposite to prior swing trend (wick breaks ignored).
  - Buy/sell pool definition: 2 confirmed swing pivots within 0.50 price units.
  - Order-block origin: Most recent opposite candle prior to CHoCH, wick-based zone.
  - Retest & rejection: Candle range touches OB zone, rejection confirms on close (20-bar limit).
  - Entry: Next-bar-open quote fill (bid_open + spread + slippage for longs; bid_open - slippage for shorts).
  - Stop loss: Sweep price +/- 0.50 price unit buffer.
  - Take profit: Opposing liquidity pool with 2.0R fixed fallback (minimum 1.0R).
  - Risk management: 1% fixed-fractional risk of realized cash equity; 100 oz/lot; rounded down to 0.01 lot step; max concurrency: 1 position.
  - Intrabar collision convention: Stop-first wins; gaps through stop receive worse opening quote fill.
  - Zero ICT elements: No FVG, displacement, kill zones, or MSS incorporated into SMC.

### 2. Independent Backtest Audit & Reproducibility
- Conducted independent metric recalculation and code audit:
  - **M5 Common-Window Identity:** Verified that M5 common-window results are identical to full-history results because M5 data coverage begins on 2026-09-22 23:15 UTC, which is exactly the latest start among all timeframes (`common_start = max(starts)`). No earlier M5 bars or signals exist.
  - **M15 Common-Window END_OF_DATA Audit:** Revealed that M15's nominal 100% win rate in common-window mode was driven by only 2 resolved rule wins (+$238.20), while the reported +$1,875.94 net profit was dominated by a **+$1,637.74 forced `END_OF_DATA` mark-out** from an unresolved short position. Handled transparently by isolating `end_of_data_pnl` and excluding EOD exits from win rate, profit factor, and average R-multiple.
  - **Realized vs Mark-to-Market Accounting:** Separated realized cash equity from mark-to-market floating equity, logging both series in all results.

### 3. Chronological Out-of-Sample Validation
Implemented chronological 60/20/20 train/validate/holdout split across all 4 timeframes (5,000 bars each) in `scripts/run_smc_phase4_validation.py` using `src/backtesting/split.py`:
- **H4 (2023-07-26 to 2026-10-19):**
  - Train (60%): 7 candidates, 6 rule exits, WR=33.3%, Net=+$566.48, PF=2.48, Max DD=$751.76.
  - Validate (20%): 4 candidates, 0 rule exits (skipped due to portfolio concurrency/filters).
  - Holdout (20%): 4 candidates, 0 rule exits (skipped).
- **H1 (2025-12-05 to 2026-10-20):**
  - Train (60%): 14 candidates, 11 rule exits, WR=45.5%, Net=+$768.25, PF=2.54, Max DD=$356.30.
  - Validate (20%): 2 candidates, 0 rule exits.
  - Holdout (20%): 2 candidates, 1 rule exit, WR=0.0%, Net=$-97.52, PF=0.00, Max DD=$146.24.
- **M15 (2026-07-31 to 2026-10-20):**
  - Train (60%): 25 candidates, 19 rule exits, 1 EOD, WR=21.1%, Net=+$156.67, PF=1.02, Max DD=$1,048.52.
  - Validate (20%): 7 candidates, 2 rule exits, WR=50.0%, Net=$-58.99, PF=0.28, Max DD=$128.94.
  - Holdout (20%): 7 candidates, 0 rule exits.
- **M5 (2026-09-22 to 2026-10-19):**
  - Train (60%): 20 candidates, 13 rule exits, 1 EOD, WR=15.4%, Net=$-828.53, PF=0.21, Max DD=$1,204.73.
  - Validate (20%): 8 candidates, 1 rule exit, WR=0.0%, Net=$-94.92, PF=0.00, Max DD=$122.92.
  - Holdout (20%): 8 candidates, 0 rule exits.

### 4. Robustness and Cost Sensitivity Analysis
Evaluated frozen SMC v1 under 7 predeclared cost scenarios in `scripts/run_smc_robustness.py`:
1. Baseline: $0.20 spread, $0.05 slippage, $0 commission.
2. 2x Spread: $0.40 spread.
3. 3x Spread: $0.60 spread.
4. 2x Slippage: $0.10 slippage per side.
5. 2x All Costs: $0.40 spread, $0.10 slippage.
6. With Commission: $0.20 spread, $0.05 slippage, $1.00/lot/side commission.
7. Worst Case: $0.60 spread, $0.20 slippage, $2.00/lot/side commission.

**Findings:**
- **H4:** Consistently positive across all scenarios (+$445 to +$455, PF=1.53 to 1.55), but based on only 13 rule exits.
- **H1:** Marginally positive across all scenarios (+$74 to +$107, PF=1.04 to 1.06), but suffers degradation under higher slippage and commissions.
- **M15:** Consistently unprofitable across all scenarios (-$884 to -$1,003, PF=0.62 to 0.67).
- **M5:** Consistently unprofitable across all scenarios (-$240 to -$291, PF=0.76 to 0.79). Lower timeframes suffer from adverse friction and low signal-to-noise ratios.

### 5. Streamlit Research Interface Upgraded
- Enhanced `pages/2_Backtesting.py` with 5 dedicated research tabs:
  1. Interactive Backtest (simulation runner, metrics table, equity curves, filtered trade ledger, CSV export).
  2. Out-of-Sample Validation (train/validate/holdout breakdown, segment comparison, segment equity curves).
  3. Robustness & Cost Sensitivity (7 scenarios, P&L bar charts, friction analysis).
  4. Frozen Strategy v1 Rules (rule breakdown and schema viewer).
  5. Independent ICT Status (clear verification of ICT decoupling and navigation).

### 6. Phase 4 Verification Results
- `py -3.13 -m pytest tests/ -v`: **397 passed, 0 failed** (including 39 dedicated Phase 4 validation & split tests in `tests/test_phase4_validation.py`).
- `py -3.13 -m compileall src pages scripts tests app.py -q`: **Passed, 0 errors**.
- Data Readiness: `READY_WITH_WARNINGS` (verified timestamp integrity, 5,000 bars on H4, H1, M15, M5).
- Execution Spec Status: `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE` (tick value empirically reconciled).



