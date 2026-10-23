# GoldFlow Phase 3D — Event-Driven Backtest Engine

**Implementation date:** 2026-10-19  
**Status:** Implemented and smoke-tested against the bundled MT5-declared XAUUSD history. This is an exploratory OHLC simulation, not a validated profitable strategy or a broker fill record.

## Engine and runner

- `src/backtesting/engine.py`: deterministic bar-driven fill, position-sizing, exit, concurrency, trade-log, and metrics functions.
- `scripts/run_smc_backtest.py`: readiness-gated CLI that detects setup candidates, runs each timeframe, and produces JSON/CSV/Markdown artifacts.
- `pages/2_Backtesting.py`: Streamlit controls and result viewer.
- `tests/test_event_backtesting.py`: hand-built execution fixtures for fills, collisions, gap handling, sizing, concurrency, commissions, data validation, and end-of-data closure.

Run from the repository root:

```powershell
py -3.13 scripts/research_readiness.py
py -3.13 scripts/run_smc_backtest.py
py -3.13 scripts/run_smc_backtest.py --mode common-window
py -3.13 scripts/run_smc_backtest.py --max-holding-bars 48
py -3.13 scripts/run_smc_lifecycle_stress.py
py -3.13 -m pytest tests/ -v
```

The runner refuses the simulation if the research readiness gate returns `BLOCKED`. A `READY_WITH_WARNINGS` result is carried into the output; readiness is not authentication of the original broker feed.

## Execution policy

1. **Signal timing:** the setup detector must confirm its rejection close; entry is taken at `signal_index + 1` open. It is not filled at the signal close or an order-block boundary.
2. **Quote convention:** input OHLC is treated as bid-side price data. The spread field is treated as MT5 points and converted using the configurable `point_size` (default 0.01 price units per point); if a bar has no positive spread value, the configurable fallback spread (default $0.20/oz) is used.
3. **Slippage:** adverse slippage is applied per side (default $0.05/oz). Stops that gap through their level are filled at the worse opening quote plus slippage. Take-profit is modeled as a limit fill at the target after the quote-side trigger is touched.
4. **Ambiguous candles:** if both the stop and target are touched within one OHLC bar, the stop wins. OHLC does not contain the true tick sequence, so this is a conservative rule rather than a reconstruction of market path.
5. **Sizing:** risk fraction defaults to 1% of current realized equity. Position sizing uses the entry-to-stop exit price distance, expected stop slippage and round-trip commission, then rounds down to the configured lot step. Contract size defaults to 100 troy ounces per lot but must be verified against the broker's XAUUSD symbol specification.
6. **Concurrency:** each timeframe is run independently, with one concurrent position per timeframe by default. A position that exits during a bar still reserves that bar's opening slot; unknown intrabar event order cannot be used to grant another simultaneous signal a slot.
7. **Optional time stop:** when `max_holding_bars` is configured, stop/target/gap exits have priority. If no stop/target event occurs and the position has reached the cap, it exits at that completed bar's executable close with adverse slippage and quote-side spread treatment, labeled `TIME_STOP`. The entry bar counts as bar 1. Time-stop exits are counted as rule exits and reported separately.
8. **End-of-data:** any still-open position is liquidated at the last bar close with the configured spread/slippage model and labeled `END_OF_DATA`. This is a sample-boundary liquidation, not a stop/target outcome. It can materially influence reported net profit if a position remains open for many bars.
9. **Candidate accounting:** candidates that have no next bar, invalid executable stop/target orientation, insufficient minimum-lot risk budget, or no concurrency slot are retained in the CSV with a skip reason.

## Output files

The runner preserves each run mode and also updates the latest-run aliases:

- `reports/smc_backtest_metrics_full_history.json`
- `reports/smc_backtest_trades_full_history.csv`
- `reports/PHASE3D_SMC_EVENT_BACKTEST_FULL_HISTORY.md`
- `reports/smc_backtest_metrics_common_window.json`
- `reports/smc_backtest_trades_common_window.csv`
- `reports/PHASE3D_SMC_EVENT_BACKTEST_COMMON_WINDOW.md`
- `reports/smc_backtest_metrics.json`, `reports/smc_backtest_trades.csv`, and `reports/PHASE3D_SMC_EVENT_BACKTEST.md` are aliases for the most recently run mode.

Metrics separate rule exits (stop/target) from `END_OF_DATA` exits. Win rate, profit factor, expectancy, and average R exclude end-of-data exits; net P&L and return include the final liquidation P&L. Maximum drawdown now uses a close-to-close mark-to-market equity path, including estimated liquidation of open positions with spread/slippage/round-turn commission, and `max_realized_drawdown_cash` is reported separately. The curve does not reconstruct intrabar equity minima; OHLC stop-first remains an assumption. Stop gaps may exceed the intended risk amount and are explicitly counted. Position sizing uses the realized balance carried into the bar and does not use P&L from an exit occurring later in that same bar.

## Position lifecycle sensitivity (Phase 3D.2)

`src/backtesting/engine.py` now supports an optional `max_holding_bars` cap, and `scripts/run_smc_lifecycle_stress.py` compares an unlimited baseline against nominal 4h/8h/24h/48h holding caps without changing the entry rules or other execution assumptions. The configured bar limit counts the entry candle as bar 1. Stop/target logic takes precedence; the time stop otherwise exits at the completed bar close. Since the cap is converted into bars per timeframe, these scenarios are nominal active-bar horizons rather than strict wall-clock durations. Outputs are written to `reports/PHASE3D_SMC_POSITION_LIFECYCLE_STRESS.md`, `reports/smc_lifecycle_stress_metrics.json`, and `reports/smc_lifecycle_stress_trades.csv`. Treat this as sensitivity analysis; do not select the best horizon on these same inspected data and call it out-of-sample validated.

## Current limitations

- Broker source is declared as MetaTrader 5 API in the dataset sidecars and timestamp checks pass, but the sidecars say `declared_not_independently_verified`; the runner cannot independently authenticate MT5 history.
- Spread-point conversion, `point_size`, contract size, lot rules, commission, and slippage defaults are assumptions. Verify all of them against the account and exact broker symbol before interpreting cash P&L as broker-equivalent.
- The full-history report is in-sample, based on a 5,000-bar snapshot per timeframe, with a small number of SMC candidates. A frozen-rule chronological holdout and cost-stress diagnostic now exists in `scripts/run_smc_validation.py`, but the underlying historical data has already been examined; this is not an untouched out-of-sample test.
- Full-history metrics use different date ranges across timeframes. Use `--mode common-window` to align signal/exit dates. This mode retains prior bars as warm-up/context and filters executed signals into the shared window; therefore its H1 count can differ from the Phase 3C table, which re-detected events on a window-only slice. The shared sample still has a small number of rule-resolved trades.
- The ICT engine is intentionally not compared. The repository does not yet specify a complete standalone ICT entry/stop/target/management strategy.
- No live or demo orders are submitted. This engine is not a trading bot, and no profitability claim is made.


## Chronological holdout and cost-stress validator

`scripts/run_smc_validation.py` evaluates frozen setup rules on the final 30% of each timeframe's bars by default and reports the same eligible candidates under 1.0x, 1.5x, and 2.0x spread/slippage/commission assumptions.

```powershell
py -3.13 scripts/run_smc_validation.py
py -3.13 -m pytest tests/ -v
```

Outputs: `reports/PHASE3D_SMC_HOLDOUT_VALIDATION.md`, `reports/smc_oos_validation_metrics.json`, and `reports/smc_oos_validation_trades.csv`. Earlier bars remain available for structural context; candidates are filtered by their signal index so only holdout signals are eligible. The script does not optimize rules on the holdout.

This remains a **pseudo-out-of-sample temporal holdout** because Phase 3C/3D already examined the bundled historical window. It does not count as an untouched independent test. Use newly collected, post-freeze history for genuine forward validation. Cost stress is directional sensitivity analysis, not broker calibration; validate the exact symbol's contract size, tick/point value, spread and commission before interpreting cash outputs.
