# GoldFlow Pure SMC Engine — Operational Rules (v1)

**Status:** implemented as a separate, unit-tested event detector. It is not yet a validated or profitable trading strategy. The Phase 3B data-readiness gate remains in force.

## Scope and separation from ICT

GoldFlow treats SMC as the primary analysis framework and retains the existing ICT engine as a separate selectable framework. The SMC module lives in `src/smc/` and does not import or call `src/ict/`.

This document defines GoldFlow's reproducible operational interpretation of SMC. Trading communities do not use every SMC term with a single universal algorithm, so these definitions are explicit engineering choices rather than a claim that all practitioners use identical rules.

The pure-SMC v1 engine covers confirmed swing structure, close-based BOS/CHoCH, equal-high/low liquidity pools, liquidity sweeps, order blocks confirmed by structure breaks, and a latest confirmed swing dealing range. It does **not** require or detect ICT-specific FVG/CE confluence, displacement ATR thresholds, ICT kill zones, MSS sequencing, or SMT divergence.

## Input contract

- Required columns: `time`, `open`, `high`, `low`, `close`; timestamps are converted to UTC.
- Timestamps must be valid, unique, and chronologically ordered.
- OHLC data must be finite and geometrically valid.
- Price tolerance controls are absolute XAUUSD price units (dollars), not broker points or ticks.
- This engine does not certify dataset provenance. Real-market research remains prohibited when the separate readiness audit says `BLOCKED`.

## Swing highs and lows

For a configurable swing window `k >= 1`, a swing high at bar `i` requires its high to be strictly greater than highs on each of the `k` bars to its left and right. Swing lows use the corresponding strict minimum of lows. Equal-high plateaus are not independently recognized as pivot points by this strict detector.

- Pivot formation time: `time[i]`.
- Confirmation/availability index: `i + k`.
- Confirmation/availability time: `time[i + k]`.
- A structure event at bar `j` may use only swings with `confirmed_index < j`. A swing confirmed at the close of bar `j` is not treated as previously known for a break on that same bar.
- HH/LH and LL/HL labels compare a newly confirmed pivot with the prior pivot of the same type.

## Structure breaks

Breaks are close-based only in SMC v1.

- Bullish break: a candle closes strictly above the latest eligible confirmed swing-high level.
- Bearish break: a candle closes strictly below the latest eligible confirmed swing-low level.
- Only the latest confirmed swing level per side is tracked for structure. After a level is broken, that active level is consumed; a subsequent newly confirmed pivot of that type can become the next active level.
- `INITIAL_BREAK`: the first directional break while trend is neutral. GoldFlow does not guess whether this first break is a continuation or a reversal.
- `BOS`: a later break in the current established trend direction.
- `CHoCH`: a later break opposite the current established trend. The resulting trend state updates to the break direction.
- Wick-only breaches that do not close beyond the level are not structural breaks in this engine; liquidity-pool sweeps are detected separately.
- If invalid/crossed levels would imply both sides breaking on the same close, that bar is skipped rather than inventing intrabar order.

## Equal-high and equal-low liquidity pools

- Buy-side liquidity pool: two confirmed swing highs within `equal_level_tolerance`.
- Sell-side liquidity pool: two confirmed swing lows within that tolerance.
- Pool level: arithmetic midpoint of the first matched pair.
- Pool creation/availability time: confirmation time of the later pivot. No sweep is allowed on or before the creation bar.
- The level is frozen after creation; later pivots do not retrospectively move the level. v1 uses each pivot in at most one pair to avoid unstable duplicate clusters.

## Liquidity sweeps

A pool has at most one sweep event in v1.

- Buy-side sweep: after pool creation, `high > level + minimum_penetration` and `close < level` on the same candle.
- Sell-side sweep: after pool creation, `low < level - minimum_penetration` and `close > level` on the same candle.
- Sweep availability time is the close time of the candle confirming the wick-through-and-reclaim condition.
- A close beyond the pool is not a sweep under this rule; it is a breakout/continuation candidate and is outside this sweep event definition.

## Order blocks

- On a close-confirmed structure break, search backward from the prior candle up to `order_block_lookback` bars.
- For a bullish structure break, the order-block origin is the most recent bearish candle (`close < open`). For a bearish break, it is the most recent bullish candle (`close > open`). Doji candles are ignored.
- `wick` zone basis uses the origin candle's full high-low range; `body` uses the min/max of open and close.
- The order block is **known at the structure-break candle close**, not at the origin candle timestamp. Charts therefore start the drawn zone at its confirmation time to avoid backpainting a zone into a period when it was not yet known.
- An order block does not require an FVG or displacement candle in SMC v1.
- Optional lifecycle tracking marks the first later touch as `MITIGATED`, unless a close through the far edge invalidates it first (`INVALIDATED`). Lifecycle fields describe what happened by the end of the loaded dataset; they must not be used as information available at block creation time.

## Premium/discount context

The current dealing range uses the latest confirmed swing high and the latest confirmed swing low when high price exceeds low price. Equilibrium is their arithmetic midpoint. The latest close is classified as `PREMIUM`, `DISCOUNT`, or `EQUILIBRIUM` relative to that midpoint. This is a current-context descriptor, not an entry signal. Because the value uses the latest confirmed pivots, the label is not meant to be projected backward through the historical chart.

## Look-ahead and unresolved market detail

- Confirmation indices and times are stored explicitly.
- Structure breaks use only swings confirmed strictly before the break candle.
- Liquidity pools are only active after the later pivot confirms; sweeps begin on following bars.
- Order blocks are only active after their confirming structure break.
- OHLC bars do not reveal exact intrabar sequencing. SMC v1 avoids interpreting wick-only penetrations as closes and does not simulate fills.
- A completed-history `SMCAnalysisResult` may expose future mitigation/invalidation timestamps. Downstream setup/backtest code must use `created_index` and event-specific availability times, never use the final lifecycle status as though it were known earlier.

## Not included yet

This module does not decide entries/exits, position size, stop distance, target selection, spread/slippage, risk limits, or performance. A subsequent strategy layer needs a written setup hypothesis and chronological validation. The current bundled data passes the configured readiness gate with `READY_WITH_WARNINGS` (see `reports/research_readiness.md`); its source is declared as MT5 but is not independently authenticated. Tests on controlled fixtures validate code behavior only, while current-history results remain exploratory.
