# GoldFlow Phase 3D.3 — Execution Specification Guardrails

**Milestone date:** 2026-10-20 (Africa/Tunis)  
**Research posture:** Frozen SMC entry and lifecycle rules; execution assumptions only  
**Current broker-spec status:** `ASSUMPTIONS_ONLY`

## Executive summary

Phase 3D.3 adds a preflight audit for XAUUSD instrument properties and a capture utility that reads the intended MetaTrader 5 terminal. It makes cash-P&L and position-sizing assumptions visible in backtest output and provides an opt-in strict gate that refuses to simulate when the captured instrument specification does not match the active configuration.

This milestone deliberately does **not** change SMC signals, tune time stops, rank timeframes, or attempt to maximize historical win rate. The objective is a trustworthy research process: an attractive historical percentage is not meaningful when contract, point, tick value, spreads, and actual broker execution remain unverified.

## Changes delivered

- `src/research/execution_spec_audit.py` validates point size, contract size, volume min/step/max, digits, tick size/value, symbol/server identity and the supported XAU/USD/USD currency assumptions.
- `scripts/capture_mt5_execution_specs.py` captures actual `MT5.symbol_info` values and account currency on the user's Windows environment. It updates metadata sidecars only, not OHLC CSV files, and blocks known symbol/server mismatches.
- `scripts/audit_execution_specs.py` generates machine-readable and Markdown audit reports.
- Full-history, common-window, holdout, and lifecycle runners embed the specification audit and support `--require-matched-execution-spec`.
- Streamlit Backtesting shows the current audit state, exposes the principal execution parameters, and defaults to requiring matched captured specs.
- Regression tests cover incomplete/nonpositive specifications, configuration mismatches, tick-value inconsistency, currency and identity checks, capture refusal cases, strict-mode blocking, and sidecar-only updates.
- A fresh independent review brief is available at `docs/ANTIGRAVITY_REVIEW_PHASE3D3.md`.

## Current status and required user action

The bundled metadata sidecars do not yet contain a real captured instrument specification. The audit correctly returns `ASSUMPTIONS_ONLY`. The capture command has **not** been run against the user's logged-in terminal from this environment; therefore the actual broker specification is still unknown.

On the PC that runs the intended MT5 terminal:

```powershell
py -3.13 scripts/capture_mt5_execution_specs.py --symbol XAUUSD
py -3.13 scripts/audit_execution_specs.py
py -3.13 scripts/run_smc_backtest.py --require-matched-execution-spec
```

The first command requires the connected terminal to use the same server and exact instrument symbol represented by the saved data. If the broker uses `GOLD`, `XAUUSD.a`, or another alias, re-ingest the data with that exact symbol rather than attaching unrelated instrument metadata. Review the audit report before changing configuration values. The strict command is expected to block until audit status matches the active config.

Even a passing instrument-specification audit is not authentication of the historical feed and does not reproduce tick-level execution. Broker/data provenance is still declared but not independently verified.

## Verification completed

- `python -m pytest tests/ -q` — **293 passed**.
- `python -m compileall src pages scripts tests app.py -q` — **passed**.
- `python scripts/research_readiness.py` — `READY_WITH_WARNINGS`, zero critical blockers.
- `python scripts/audit_execution_specs.py` — `ASSUMPTIONS_ONLY`; exit code 2 is expected because no real MT5 specifications have been captured.
- Exploratory M5 CLI smoke test — completed and surfaced the specification warning.
- Strict M5 CLI smoke test — blocked before simulation with exit code 2, as intended.
- The full-history, common-window, lifecycle, and holdout JSON payloads contain a refreshed execution-spec audit snapshot. The snapshot refresh changes audit metadata only, not the historical trade calculations.

## Historical research guardrails

Existing full-history output remains exploratory: H4 +$448.73, H1 +$107.96, M15 −$878.99, M5 −$252.34 under the current model assumptions. These figures are not a profitability claim and can change when broker specifications are reconciled.

The M15 common-window result includes +$1,637.74 from an end-of-sample mark-out within a reported +$1,875.94 total. The chronological holdout also includes open end-of-sample positions, including an M15 mark-out after a long-held position. These boundary marks must not be treated as ordinary take-profit exits.

The M15 nominal 4-hour lifecycle cap's historical improvement is highly sensitive to truncating trades and freeing concurrency slots; the identical cap worsened results on other timeframes. Do not adopt that cap based on this same sample. This holdout also uses history already examined in earlier phases and is not untouched independent out-of-sample validation.

## Next gate

1. Capture actual instrument metadata from the intended MT5 terminal and reconcile any config mismatch.
2. Ask Antigravity to independently review the capture utility, currency/tick assumptions, strict gates, report consistency, and test coverage using `docs/ANTIGRAVITY_REVIEW_PHASE3D3.md`.
3. Resolve concrete correctness findings and rerun tests/compilation.
4. Freeze rules and evaluate on genuinely new, post-freeze history; do not select parameters by looking for the highest win rate in the current sample.
