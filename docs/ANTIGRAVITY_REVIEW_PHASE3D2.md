# Antigravity Task — Independent Review of Phase 3D.2 Position Lifecycle

## Goal

Perform an independent correctness review of GoldFlow's new optional time-stop implementation and lifecycle sensitivity runner. Do **not** optimize the SMC entry hypothesis or choose the best-looking holding horizon. The purpose is to challenge simulator correctness before further strategy research.

## Files to review

- `src/backtesting/engine.py`
- `scripts/run_smc_lifecycle_stress.py`
- `scripts/run_smc_backtest.py`
- `pages/2_Backtesting.py`
- `tests/test_event_backtesting.py`
- `reports/PHASE3D_SMC_POSITION_LIFECYCLE_STRESS.md`
- `reports/smc_lifecycle_stress_metrics.json`
- `reports/smc_lifecycle_stress_trades.csv`

## Required checks

1. Reproduce `python -m pytest tests/ -q` and `python -m compileall src pages scripts tests app.py -q`.
2. Audit signal timing and entry timing for look-ahead bias: setup signals must be confirmed before entry at the next bar's open.
3. Audit event ordering: opening gaps, intrabar stop/target, ambiguous dual-touch stop-first, time-stop at close, and end-of-data liquidation. Explain whether stop/target always has priority over `TIME_STOP` and whether entry-bar counting is consistent.
4. Verify quote-side spread semantics under the documented assumption that OHLC is bid-side data. Check long/short entry and exit prices, spread application, slippage, commissions, and mark-to-market equity.
5. Verify time-stop exits are classified as rule exits, while `END_OF_DATA` remains separately reported. Confirm equity curves, final equity, drawdown, trade logs, and summary metrics reconcile.
6. Inspect concurrency and risk sizing: a position exiting later in a bar must not grant a new entry another slot at that same bar's open or leak later P&L into its opening risk budget.
7. Check how timeframe gaps/market closures affect the nominal hour-to-bars mapping. Confirm documentation avoids claiming a strict wall-clock timeout.
8. Investigate whether results are sensitive to the existing fallback spread/point-size assumptions and whether the MT5 `spread` field is being interpreted consistently with the CSV/metadata.
9. Identify any report/README/handoff statements that are stale or conflict with the current code.

## Current diagnostic finding to challenge—not optimize against

In the in-sample lifecycle stress report, time stops materially alter outcomes by timeframe: the nominal 4-hour scenario changes M15 from negative to positive rule-exit P&L, while several H4/H1/M5 results worsen. This is a sign of strong management sensitivity on already-inspected history, **not** permission to select the best horizon and claim an edge. Treat the scenarios as diagnostics only.

## Rules for your pass

- First deliver an independent audit report with findings sorted by severity, exact file/line references, concrete counterexamples, and tests that would prove each issue.
- Do not alter entry criteria, SMC detection rules, broker data, or report values just to improve results.
- Do not run live or demo orders.
- Do not make broad refactors. If you find a correctness defect, propose the smallest patch and a regression test; wait for review before making overlapping changes to the files another agent is working on.
- Explicitly state any issue you cannot verify from the bundled OHLC data alone.
