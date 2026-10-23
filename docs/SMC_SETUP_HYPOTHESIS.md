# Pure SMC Setup Hypothesis v1

**Name:** Liquidity Sweep → Opposite CHoCH → Order-Block Retest/Rejection

**Status:** implemented as a setup-candidate detector and evaluated by the preliminary Phase 3D OHLC simulator. It is not out-of-sample validated. No orders are placed.

## Why this setup

This is GoldFlow's initial pure-SMC hypothesis for future evaluation. It uses only liquidity pools/sweeps, structural change, order blocks, and an optional premium/discount filter. It does not require ICT FVG, displacement, MSS, Consequent Encroachment, SMT divergence, or ICT kill-zone confluence.

## Exact v1 rules

### Long candidate

1. A sell-side liquidity pool has a confirmed wick-through-and-close-back sweep.
2. Within `max_sweep_to_choch_bars` (default 20) after the sweep, price confirms a bullish CHoCH whose prior trend state is bearish.
3. A bullish order block is found from the last bearish candle within the configured order-block lookback before that CHoCH.
4. After the order block is confirmed, a candle trades into/overlaps the zone and later closes strictly above the zone's high boundary. The close-confirmed rejection must occur within `max_bars_choch_to_retest` (default 20) bars after the CHoCH. A close below the zone low invalidates the candidate before the rejection signal.
5. The signal time is the close time of the rejection candle. The reference entry is that candle's close; it is not an assumed fill at the earlier order-block boundary.

### Short candidate

The exact inverse: buy-side liquidity sweep, bearish CHoCH with prior bullish trend, bearish order block, and a post-confirmation retest/rejection candle that closes strictly below the zone's low boundary. A close above the zone high invalidates the candidate before signal confirmation.

## Risk and target references

- Long stop reference: swept low extreme minus `stop_buffer`.
- Short stop reference: swept high extreme plus `stop_buffer`.
- Default `stop_buffer`: $0.50 in XAUUSD price units, configurable and not a recommendation for live trading.
- Default fallback target: 2.0R from the close-confirmed entry reference.
- If enabled, the target prefers the nearest opposing-side liquidity pool that was already created strictly before the signal, remains unswept as of the signal, and lies in the target direction.
- A liquidity target must satisfy `minimum_reward_risk` (default 1.0). A too-close opposing-liquidity target rejects the candidate; the code does not silently replace it with a more distant fixed-R target.
- If no eligible opposing liquidity pool exists, the fixed-R fallback is used.
- Optional premium/discount filter defaults off. When enabled, it uses only swing points confirmed strictly before the signal bar; longs must signal at/below the known equilibrium, and shorts at/above it.

## Anti-look-ahead rules

- Sweep must precede CHoCH; CHoCH must precede the order-block retest.
- Order block is available only from the structure-break close that identifies it.
- Signal is available only at the retest/rejection candle close.
- The entry reference uses that close. OHLC alone does not justify an earlier intrabar fill assumption.
- Targets are restricted to liquidity pools known before the signal and not already swept before it.
- Premium/discount, when enabled, uses only prior confirmed pivots.
- Order-block lifecycle status calculated over the full dataset is not used as an input for earlier setup timing.

## Current limitations

- The Phase 3D event simulator currently models next-bar-open fills, bar spread, slippage, commissions, risk sizing, stop/target collisions, concurrency and sample-end liquidation. See `docs/PHASE3D_BACKTEST_ENGINE.md` for the explicit assumptions.
- There may be zero candidates on a given period; settings should not be tuned to force signals.
- The current readiness report is `READY_WITH_WARNINGS`; raw epochs and timestamp integrity are marked verified, but the MT5 source is not independently authenticated by the package. All reported backtest outcomes are in-sample and exploratory, not evidence of profitability. Use common-window results for aligned date ranges and reserve an untouched period for later validation.
