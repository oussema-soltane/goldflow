# GoldFlow Phase 3D — Pure-SMC Event-Driven Backtest

**Generated UTC:** 2026-10-20T15:38:22.255266+00:00
**Mode:** common-window
**Data readiness:** READY_WITH_WARNINGS
**Execution specification audit:** MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE

> **Interpretation warning:** This is a model-based historical simulation, not a live/broker execution record or a claim of future profitability. The sidecars declare MT5 API provenance, but this project does not independently authenticate the broker data or contract specification.

> **TICK-VALUE RECONCILIATION NOTICE:** The execution specification audit reconciled a broker property discrepancy (`symbol_info.trade_tick_value = 0.1` vs linear contract formula expected 1.00 USD/tick) using live MT5 `order_calc_profit` inquiries. Profit calculations use the empirically authoritative linear formula `(exit - entry) * contract_size * lots`.

## Execution assumptions

- **Ohlc Quote Convention:** Input OHLC treated as bid-side prices
- **Entry:** next bar open; long fills at ask (bid open + bar spread) and short fills at bid; adverse slippage applied
- **Spread:** MT5 bar spread points multiplied by configurable point_size when positive; otherwise fixed fallback USD spread
- **Slippage:** Adverse price slippage per side; stops and end-of-data exits slippage-adjusted; take-profit limit fill assumes no exit slippage after touch
- **Intrabar Collision:** If a candle touches both stop and target, stop is filled first
- **Gap Handling:** A gap through stop fills at the worse opening executable quote plus slippage
- **Sizing:** Fixed fractional equity risk with executable stop distance including stop slippage and round-trip commission estimate; lot sizes rounded down to lot_step
- **Concurrency:** Concurrent positions are capped independently within each timeframe run; a slot is not reused based on unknown intrabar exit order
- **End Of Data:** Remaining positions are closed at the last close with spread/slippage assumptions and marked END_OF_DATA
- **Time Stop:** Optional maximum holding cap of None bars; entry bar counts as bar 1. Stop/target logic has priority, otherwise exits occur at the completed bar close with adverse slippage and quote-side spread treatment.
- **Common Window Method:** In common-window mode, earlier history is retained as warm-up/context; only signal bars at or after common_start are eligible, and execution stops at common_end. This can differ from Phase 3C counts produced by re-running detection on a window-only slice.

## Results by timeframe

| Timeframe | Candidates | Rule exits | Time stops | End-of-data | Skipped | Win rate* | Net P&L** | Return** | Profit factor* | Max DD** | Avg R* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H4 | 0 | 0 | 0 | 0 | 0 | N/A | $0.00 | 0.00% | N/A | $0.00 (0.00%) | N/A |
| H1 | 2 | 2 | 0 | 0 | 0 | 0.00% | $-185.64 | -1.86% | 0.00 | $454.92 (4.43%) | -1.00 |
| M15 | 20 | 2 | 0 | 1 | 17 | 100.00% | $1,875.94 | 18.76% | infinite | $1,838.85 (14.07%) | 1.23 |
| M5 | 42 | 31 | 0 | 1 | 10 | 22.58% | $-503.62 | -5.04% | 0.78 | $1,304.86 (12.80%) | -0.14 |

* Win rate and profit factor exclude END_OF_DATA exits, which are sample-boundary marks rather than stop/target outcomes.
** Net P&L and return include END_OF_DATA liquidation P&L. Inspect `end_of_data_pnl` before interpreting these metrics. Max drawdown is close-to-close mark-to-market; `max_realized_drawdown_cash` is also present in the JSON for comparison.

## Candidate exclusions

### H4
- No candidates skipped by the execution layer.

### H1
- No candidates skipped by the execution layer.

### M15
- max_concurrent_positions: 17

### M5
- max_concurrent_positions: 10

## Method notes and limitations

- Signals are produced by the documented Pure-SMC setup detector; entries use the next candle open rather than the signal close or order-block edge.
- Stop/target references come from the setup candidate. Candidates with levels invalid relative to the cost-adjusted fill are rejected and logged.
- The simulator uses OHLC bars, not tick data. Stop-first is a conservative rule for bars that touch both stop and target; it cannot reconstruct the true intrabar path.
- Position sizing assumes the configured contract size and price-value relationship. Verify contract size, point size, lot step, and commissions against the broker symbol specification before interpreting cash P&L as broker-equivalent.
- An END_OF_DATA exit is a forced liquidation at the sample boundary; it is not a stop/target result. Net P&L and return include it; win rate, profit factor, expectancy and average R exclude it. TIME_STOP exits are included among rule exits and counted separately.
- Optional `max_holding_bars` time stops use the completed bar close after checking stop/target exits. The entry bar counts as bar 1; the same number of bars represents different elapsed time across timeframes.
- Maximum drawdown uses a close-to-close mark-to-market equity path that estimates open-position liquidation at the executable close quote with modeled slippage and round-turn commission. A realized-only drawdown metric is available separately. OHLC cannot reconstruct intrabar equity minima.
- Stop gaps can exceed the planned risk budget. The trade log records such cases; fixed-fractional sizing does not guarantee a maximum loss under gaps.
- Timeframes may cover different historical ranges in full-history mode. Do not treat those as a controlled cross-timeframe comparison. Use `--mode common-window` for a shared date window. Common-window mode retains pre-window bars as warm-up/context and filters executed signals to the shared dates; counts may differ from Phase 3C's window-only re-detection at the boundary.
- This is not a walk-forward or out-of-sample validation. The candidate rules and parameters have been examined on these data; reserve a later untouched period for validation before drawing strategy conclusions.
- ICT remains a separate event engine and is not benchmarked here because the repository handoff says no complete ICT entry/exit strategy is specified.

## Artifacts

- `smc_backtest_metrics_common_window.json` — assumptions, readiness state, metrics, and equity curves.
- `smc_backtest_trades_common_window.csv` — closed trades and skipped candidates with traceable setup IDs.
- `PHASE3D_SMC_EVENT_BACKTEST_COMMON_WINDOW.md` — human-readable summary.
