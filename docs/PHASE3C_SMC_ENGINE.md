# GoldFlow SMC Engine v1 — Implementation Report

## Purpose

Add a pure-SMC analysis framework as the default market-analysis mode while preserving the existing ICT engine unchanged as an independent selectable mode.

## Implemented

- Added `src/smc/models.py` with independent SMC event types.
- Added `src/smc/engine.py` with strict swing confirmations, close-based structure breaks, `INITIAL_BREAK` / BOS / CHoCH classification, equal-high/low liquidity pools, post-formation wick-and-reclaim sweeps, break-confirmed order blocks, lifecycle timestamps, and current premium/discount context.
- Added `SMCConfig` for swing window, equal-level tolerance, minimum sweep penetration, order-block lookback, zone basis, and lifecycle tracking.
- Added a separate SMC chart overlay. Order-block drawings start at structure-break confirmation rather than at the earlier origin candle, to avoid visually backpainting the zone into an interval when it was not yet known.
- Updated the Market Analysis page so **SMC (Primary)** is the default framework and **ICT (Existing)** remains selectable with its previous controls and analysis.
- Added SMC rules and limitations in `docs/SMC_RULES.md`.
- Added `src/strategy/smc_setups.py`, a separate candidate detector for the pure-SMC hypothesis: a relevant liquidity sweep, a subsequent opposite CHoCH, then a post-confirmation order-block retest/rejection close. Complete entry-reference, stop, target, minimum-RR, and optional premium/discount rules are in `docs/SMC_SETUP_HYPOTHESIS.md`.
- Entry reference is the retest/rejection candle close. Stop reference is beyond the sweep extreme plus a configurable buffer. The nearest eligible opposing-side liquidity pool can be used as target if it was already known and unswept at signal time; otherwise the configured fixed-R target is used.
- Premium/discount filtering is optional and, when enabled, computes the range from pivots confirmed strictly before the candidate signal.
- Added hand-crafted tests for event confirmation, first-break labeling, BOS/CHoCH direction, truncation invariance, liquidity pools/sweeps, order-block origin/availability/lifecycle, setup chronology, stop/target references, target selection, optional premium/discount gating, input validation, engine independence, and chart overlays.

## Operational choices

SMC terms are not universally operationalized identically by all practitioners. GoldFlow therefore documents an explicit reproducible interpretation in `docs/SMC_RULES.md`. SMC v1 does not require ICT-specific FVG/CE, displacement, MSS, SMT, or kill-zone logic.

## Scope limitations

- The setup detector emits research candidates with reference entry/stop/target prices; it is not a backtested strategy and never places orders.
- These execution and portfolio components were added in Phase 3D under `src/backtesting/engine.py`; the model assumptions and limitations are documented in `docs/PHASE3D_BACKTEST_ENGINE.md`.
- Mitigation/invalidation status is retrospective as of the final loaded bar and must not be treated as information available at order-block creation.
- Phase 3C descriptive statistics and a preliminary Phase 3D simulation are present in `reports/`; they are not out-of-sample validation and do not establish future profitability.
- This document originally described the pre-reingestion data state. The current sidecars now preserve raw timestamp epochs and mark timestamp integrity verified. The current readiness is `READY_WITH_WARNINGS`; the source provenance is declared in metadata but not independently authenticated. Consult the current `reports/research_readiness.md` rather than relying on this historical audit note.

## Validation

The full repository suite passed with 240 tests after Phase 3D (including 10 backtesting execution tests); `python -m compileall src pages scripts tests app.py -q` passed. Software tests validate deterministic behavior, not profitability or independent MT5 provenance.
