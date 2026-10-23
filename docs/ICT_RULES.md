# GoldFlow ICT Engine — Operational Rules (Phase 2)

This document defines the current deterministic implementation. These are project rules for reproducible analysis, not a claim that all ICT practitioners use identical definitions.

## Input and time convention

- Input bars must be chronological OHLC rows with `time`, `open`, `high`, `low`, and `close`.
- All emitted event timestamps are normalized to UTC-aware pandas timestamps.
- Index fields are positional row indices, not dataframe labels.
- The engine assumes input bars are completed candles. The MT5 loader excludes the forming candle by default; CSV inputs must follow the same convention.
- Prices are evaluated from candle OHLC only. No order execution, strategy entry/exit, or ML scoring is performed in Phase 2.

## Swing highs and lows

With configurable radius `k` (`swing_window`), bar `i` is a swing high only when its high is strictly greater than the highs of all `k` bars immediately to its left and right. A swing low is strictly lower than the lows of all `k` bars on both sides. Equal highs/lows do not qualify as a swing under this strict-fractal rule.

- Formation time: timestamp at `i`.
- Confirmation index/time: `i + k`, when all required right-hand bars have closed.
- A swing is not available to the structure or sweep detector before confirmation.
- HH/LH and HL/LL classifications compare the price with the preceding detected swing of the same type.

## BOS and CHoCH

The engine keeps the latest confirmed, unconsumed swing high and low as active structure levels.

- Bullish break: close above the active swing high when `break_on_close=True`; otherwise the candle high must exceed it.
- Bearish break: close below the active swing low when `break_on_close=True`; otherwise the candle low must fall below it.
- The broken swing must have been confirmed on an earlier bar (`break_index > confirmed_index`). A swing level is consumed after its first break to prevent duplicate events.
- A break is labelled BOS when it continues the current directional trend; otherwise it is labelled CHoCH. Because the initial trend is neutral, the first detected break is currently labelled CHoCH. This is an explicit implementation convention and may differ from other ICT interpretations.
- If a single candle breaks both active levels, the close-based mode resolves direction by whichever condition the close satisfies. Wick mode may produce both directional breaks on one outside candle; this case is ambiguous and should be reviewed.

## Fair Value Gaps (FVG)

For three consecutive bars, where `i` is the middle candle:

- Bullish FVG if `low[i+1] > high[i-1]`; zone is `[high[i-1], low[i+1]]`.
- Bearish FVG if `high[i+1] < low[i-1]`; zone is `[high[i+1], low[i-1]]`.
- Gap size must be at least the configurable `min_gap_points`; boundary equality creates no gap.
- The FVG becomes known only when bar `i+1` closes (`creation_index = i+1`). Consequent encroachment (CE) is the midpoint of the zone.
- Mitigation is evaluated only on bars after creation. Entering the zone marks partial mitigation; touching/crossing the far boundary marks full mitigation. The full-mitigation status uses OHLC extremes and does not infer intrabar order.

## Displacement

A displacement candle's absolute body must be at least `multiplier × ATR`, and body/range must be at least `min_body_ratio`. ATR is a simple rolling mean of true range over `atr_period` bars, and the candidate candle is compared with the ATR baseline ending on the preceding bar. Zero-range candidates and non-positive/undefined ATR baselines are skipped. The parameters are configurable in the Streamlit sidebar.

This is a mechanical size/body filter, not proof of institutional participation. Direction is determined by close versus open; a doji may be classified as bullish for display because close equals open.

## Liquidity sweeps

Only confirmed swing levels are eligible, and the sweep candle must occur after confirmation.

- Buy-side sweep: high penetrates above a swing high and close returns to or below the level.
- Sell-side sweep: low penetrates below a swing low and close returns to or above the level.
- Touching a level exactly is not a sweep. Each swing can generate at most one sweep; a close beyond the level removes it from sweep consideration.
- The engine supports a minimum wick penetration argument, defaulting to zero.

## MSS (current operational definition)

A market structure shift is a liquidity sweep followed by a structure break in the opposite direction within `max_lag_bars` (default 10). A buy-side sweep expects a bearish break; a sell-side sweep expects a bullish break. An FVG of the same direction between the sweep and break can be required with `require_fvg=True`.

**Important limitation:** the current MSS detector does not independently require a displacement candle or require an FVG by default, despite the stricter use of “MSS” in some ICT descriptions. It is therefore a configurable sweep-to-opposite-break event, not a complete sweep → displacement → MSS confirmation model.

## Order blocks

For each detected FVG, the engine searches up to three preceding candles from the FVG's third/confirmation candle backward:

- Bullish OB: most recent candle with `close < open`.
- Bearish OB: most recent candle with `close > open`.
- Doji candles are not opposing candles.
- The OB is known at FVG confirmation time, not at the historical origin candle's time.
- Mitigation/invalidation tracking starts on the bar after confirmation. Bullish OB invalidation is a close below its low; bearish invalidation is a close above its high. A wick re-entry can count as mitigation.

This version derives OBs from FVGs; the optional `structure_breaks` argument is not yet used to independently create OBs from structure breaks. Multiple FVGs can point to the same origin candle, and this implementation de-duplicates by origin index, so a candle is assigned only one OB type.

## Visualization and known limitations

- Swing points show formation and confirmation times in hover details.
- BOS/CHoCH annotations include the event UTC timestamp.
- FVG and OB zones are drawn with event markers and hover details; sweeps and displacement markers expose UTC event timestamps.
- Historical mitigation/invalidation fields are retrospective summaries. They must not be used as if known at the original formation time; consumers should use each event's confirmation/mitigation timestamp.
- This is a deterministic research baseline. It does not prove profitability, model intrabar tick order, or implement trade entries/exits.
- Live MT5 integration remains unverified until a successful real terminal connection and historical-bar retrieval are demonstrated in the target Windows environment.

## Phase 2.1 Adversarial Validation Summary

The engine's deterministic behavior was formally verified across 12 adversarial edge cases:
1. **Equal Highs/Lows**: Strictly disqualified from being swing points (`highs[i-j] >= curr_high` strict inequality check).
2. **Repeated Breaks**: A swing level is consumed upon its first break and cannot trigger duplicate BOS/CHoCH events.
3. **Wick vs Close Breaks**: Under `break_on_close=True`, wick penetrations that close inside the range do not trigger structure breaks.
4. **Outside Bars**: A bar that breaches both high and low wicks resolves its break solely by close price in institutional mode; if it closes within range, zero breaks occur.
5. **Gaps & Missing Candles**: Missing bars/weekend gaps retain strictly monotonic UTC ordering without interpolating artificial prices.
6. **Dojis & Zero-Range**: Doji candles (`open == close`) are strictly disqualified from serving as opposing Order Block origins and skipped by displacement filters.
7. **FVG Lifecycle**: Created at bar $i+1$, Consequent Encroachment (CE) at midpoint, partial mitigation on touch, full mitigation on breach.
8. **Delayed Sweeps**: Sweeps with absent or lagged opposite-side breaks (> `max_lag_bars`) are safely kept as isolated liquidity events without false MSS triggers.
9. **Displacement ATR Threshold**: Evaluated against prior bar's ATR (`abs_body >= multiplier * ATR`).
10. **Order Block Origin**: Scans backward up to 3 bars from FVG confirmation bar $i+1$, picking the most recent opposing close.
11. **Boundary Conditions**: Safe execution on datasets with zero or fewer bars than `swing_window * 2 + 1` without exceptions.
12. **Timeframe Independence**: Tested across H4, H1, M15, M5 without timestamp distortion or look-ahead leakage.

