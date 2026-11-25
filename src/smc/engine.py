"""Deterministic, standalone SMC market-structure analysis.

Operational v1 definitions are documented in ``docs/SMC_RULES.md``. The engine
uses confirmed swings, close-based structure breaks, equal-high/low pools,
wick-and-reclaim sweeps, break-confirmed order blocks, and a swing dealing range.
It deliberately does not depend on the ICT engine or require FVG/displacement
confluence. All event timestamps are UTC-aware and include availability indices.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.smc.models import (
    SMCAnalysisResult,
    SMCBreakerBlock,
    SMCBreakerBlockStatus,
    SMCBreakerBlockType,
    SMCDirection,
    SMCFairValueGap,
    SMCFVGStatus,
    SMCFVGType,
    SMCLiquidityPool,
    SMCLiquiditySweep,
    SMCLiquidityType,
    SMCOrderBlock,
    SMCOrderBlockStatus,
    SMCStructureBreak,
    SMCStructureType,
    SMCSwingPoint,
    SMCSwingType,
)


@dataclass(frozen=True)
class SMCConfig:
    """SMC detector parameters expressed in instrument price units where applicable."""
    swing_window: int = 2
    equal_level_tolerance: float = 0.50
    min_sweep_penetration: float = 0.0
    order_block_lookback: int = 5
    order_block_zone_basis: str = "wick"  # ``wick`` or ``body``
    track_order_block_lifecycle: bool = True
    min_fvg_size: float = 0.0  # Minimum gap size in price units to record an FVG.
    track_breaker_blocks: bool = True

    def __post_init__(self) -> None:
        if self.swing_window < 1:
            raise ValueError("swing_window must be >= 1")
        if self.equal_level_tolerance < 0:
            raise ValueError("equal_level_tolerance must be >= 0")
        if self.min_sweep_penetration < 0:
            raise ValueError("min_sweep_penetration must be >= 0")
        if self.order_block_lookback < 1:
            raise ValueError("order_block_lookback must be >= 1")
        if self.order_block_zone_basis not in {"wick", "body"}:
            raise ValueError("order_block_zone_basis must be 'wick' or 'body'")
        if self.min_fvg_size < 0:
            raise ValueError("min_fvg_size must be >= 0")


def _prepare_frame(df: pd.DataFrame) -> pd.DataFrame:
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"SMC analysis requires columns: {', '.join(missing)}")
    frame = df.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    if frame["time"].isna().any():
        raise ValueError("SMC input contains missing or invalid timestamps")
    if not frame["time"].is_monotonic_increasing:
        raise ValueError("SMC input timestamps must be in chronological order")
    if frame["time"].duplicated().any():
        raise ValueError("SMC input timestamps must be unique")
    for col in ("open", "high", "low", "close"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
        if not np.isfinite(frame[col].to_numpy(dtype=float)).all():
            raise ValueError(f"SMC input contains non-finite {col} prices")
    invalid = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    )
    if invalid.any():
        raise ValueError(f"SMC input contains {int(invalid.sum())} invalid OHLC row(s)")
    return frame.reset_index(drop=True)


def detect_smc_swings(df: pd.DataFrame, window: int = 2) -> List[SMCSwingPoint]:
    """Find strict fractal pivots; a pivot is only known at ``index + window``.

    High/low plateaus are not pivots under this strict rule. Equal-level pools are
    formed from separate confirmed pivots rather than treating a plateau as one.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if df.empty or len(df) < 2 * window + 1:
        return []
    frame = _prepare_frame(df)
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    times = frame["time"]
    swings: List[SMCSwingPoint] = []
    last_high: Optional[float] = None
    last_low: Optional[float] = None

    for i in range(window, len(frame) - window):
        is_high = all(highs[i] > highs[i - j] and highs[i] > highs[i + j] for j in range(1, window + 1))
        is_low = all(lows[i] < lows[i - j] and lows[i] < lows[i + j] for j in range(1, window + 1))
        confirmed = i + window
        if is_high:
            classification = "INIT" if last_high is None else ("HH" if highs[i] > last_high else "LH")
            swings.append(SMCSwingPoint(i, times.iloc[i], float(highs[i]), SMCSwingType.SWING_HIGH,
                                         classification, confirmed, times.iloc[confirmed]))
            last_high = float(highs[i])
        if is_low:
            classification = "INIT" if last_low is None else ("LL" if lows[i] < last_low else "HL")
            swings.append(SMCSwingPoint(i, times.iloc[i], float(lows[i]), SMCSwingType.SWING_LOW,
                                         classification, confirmed, times.iloc[confirmed]))
            last_low = float(lows[i])
    return sorted(swings, key=lambda item: (item.index, item.swing_type.value))


def detect_smc_structure_breaks(
    df: pd.DataFrame, swings: Sequence[SMCSwingPoint]
) -> Tuple[List[SMCStructureBreak], SMCDirection]:
    """Detect close-based breaks using only pivots confirmed before each break bar.

    The first directional break in a neutral state is labeled ``INITIAL_BREAK``
    instead of guessing whether it is a continuation or reversal. Thereafter a
    trend-aligned break is BOS and a counter-trend break is CHoCH.
    """
    if df.empty or not swings:
        return [], SMCDirection.NEUTRAL
    frame = _prepare_frame(df)
    swings_by_confirmation = sorted(swings, key=lambda s: (s.confirmed_index, s.index))
    next_swing = 0
    active_high: Optional[SMCSwingPoint] = None
    active_low: Optional[SMCSwingPoint] = None
    trend = SMCDirection.NEUTRAL
    events: List[SMCStructureBreak] = []

    for i, row in frame.iterrows():
        # Strictly less than i: a swing confirmed at this bar cannot also be
        # treated as prior information for a break on the same bar.
        while next_swing < len(swings_by_confirmation) and swings_by_confirmation[next_swing].confirmed_index < i:
            swing = swings_by_confirmation[next_swing]
            if swing.swing_type == SMCSwingType.SWING_HIGH:
                active_high = swing
            else:
                active_low = swing
            next_swing += 1

        broke_high = active_high is not None and float(row["close"]) > active_high.price
        broke_low = active_low is not None and float(row["close"]) < active_low.price
        # An OHLC close cannot normally break both structurally valid sides.
        # If malformed/crossed levels make that possible, don't invent sequence.
        if broke_high and broke_low:
            continue
        if not broke_high and not broke_low:
            continue

        broken = active_high if broke_high else active_low
        direction = SMCDirection.BULLISH if broke_high else SMCDirection.BEARISH
        prior = trend
        if trend == SMCDirection.NEUTRAL:
            event_type = SMCStructureType.INITIAL_BREAK
        elif direction == trend:
            event_type = SMCStructureType.BOS
        else:
            event_type = SMCStructureType.CHOCH
        trend = direction
        events.append(SMCStructureBreak(
            break_type=event_type,
            direction=direction,
            broken_swing=broken,
            break_index=int(i),
            break_time=row["time"],
            break_price=float(row["close"]),
            prior_trend=prior,
            resulting_trend=trend,
        ))
        if broke_high:
            active_high = None
        else:
            active_low = None
    return events, trend


class _LatestUnpairedSwingByPrice:
    """Dynamic price-range index that returns the latest active swing position.

    The former pool detector scanned ``ordered[:i]`` backwards for every pivot,
    causing quadratic work and repeated list allocations. This segment-tree index
    answers the same query: latest earlier, unpaired pivot of one swing type whose
    price lies inside the inclusive tolerance band. Paired pivot indices are
    removed from both type indexes, matching the original global ``paired`` set.
    """

    def __init__(self, swings: Sequence[SMCSwingPoint]) -> None:
        self.prices = sorted({float(swing.price) for swing in swings})
        self.price_to_leaf = {price: i for i, price in enumerate(self.prices)}
        self.size = 1
        while self.size < len(self.prices):
            self.size *= 2
        self.tree = [-1] * (2 * self.size)
        self.stacks: list[list[int]] = [[] for _ in self.prices]
        self.position_to_leaf: dict[int, int] = {}
        self.position_active: dict[int, bool] = {}
        self.positions_by_pivot_index: dict[int, list[int]] = {}

    def _set_leaf(self, leaf: int, position: int) -> None:
        node = self.size + leaf
        self.tree[node] = position
        node //= 2
        while node:
            self.tree[node] = max(self.tree[node * 2], self.tree[node * 2 + 1])
            node //= 2

    def add(self, position: int, swing: SMCSwingPoint) -> None:
        leaf = self.price_to_leaf[float(swing.price)]
        self.position_to_leaf[position] = leaf
        self.position_active[position] = True
        self.stacks[leaf].append(position)
        self.positions_by_pivot_index.setdefault(int(swing.index), []).append(position)
        self._set_leaf(leaf, position)

    def remove_pivot_index(self, pivot_index: int) -> None:
        for position in self.positions_by_pivot_index.get(int(pivot_index), ()):
            if not self.position_active.get(position, False):
                continue
            self.position_active[position] = False
            leaf = self.position_to_leaf[position]
            stack = self.stacks[leaf]
            if stack and stack[-1] == position:
                while stack and not self.position_active.get(stack[-1], False):
                    stack.pop()
                self._set_leaf(leaf, stack[-1] if stack else -1)

    def latest_in_band(self, price: float, tolerance: float) -> int:
        """Return the greatest active ordered-position in [price-tol, price+tol]."""
        left = bisect_left(self.prices, float(price) - tolerance)
        right = bisect_right(self.prices, float(price) + tolerance)
        if left >= right:
            return -1
        left += self.size
        right += self.size
        latest = -1
        while left < right:
            if left & 1:
                latest = max(latest, self.tree[left])
                left += 1
            if right & 1:
                right -= 1
                latest = max(latest, self.tree[right])
            left //= 2
            right //= 2
        return latest


def detect_smc_liquidity_pools(
    df: pd.DataFrame,
    swings: Sequence[SMCSwingPoint],
    tolerance: float = 0.50,
) -> List[SMCLiquidityPool]:
    """Create a pool from the first eligible pair of confirmed pivots within tolerance.

    The pool level is frozen at the pair's midpoint and becomes known only when
    the later pivot confirms. Each pivot index is paired at most once. The index
    selects the same latest eligible earlier pivot as the original backward scan,
    but avoids repeatedly slicing and scanning the full swing history.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")
    if df.empty or len(swings) < 2:
        return []
    frame = _prepare_frame(df)
    ordered = sorted(swings, key=lambda s: (s.confirmed_index, s.index))
    high_index = _LatestUnpairedSwingByPrice(
        [swing for swing in ordered if swing.swing_type == SMCSwingType.SWING_HIGH]
    )
    low_index = _LatestUnpairedSwingByPrice(
        [swing for swing in ordered if swing.swing_type == SMCSwingType.SWING_LOW]
    )
    paired: set[int] = set()
    pools: List[SMCLiquidityPool] = []

    for position, current in enumerate(ordered):
        if current.index in paired:
            continue
        index = high_index if current.swing_type == SMCSwingType.SWING_HIGH else low_index
        previous_position = index.latest_in_band(current.price, tolerance)
        if previous_position < 0:
            index.add(position, current)
            continue

        previous = ordered[previous_position]
        created_index = max(current.confirmed_index, previous.confirmed_index)
        if created_index >= len(frame):
            # Keep parity with the old detector: this pair is consumed even when
            # its creation timestamp would be outside the available frame.
            paired.add(current.index)
            paired.add(previous.index)
            high_index.remove_pivot_index(current.index)
            low_index.remove_pivot_index(current.index)
            high_index.remove_pivot_index(previous.index)
            low_index.remove_pivot_index(previous.index)
            continue

        kind = (
            SMCLiquidityType.BUY_SIDE
            if current.swing_type == SMCSwingType.SWING_HIGH
            else SMCLiquidityType.SELL_SIDE
        )
        pools.append(SMCLiquidityPool(
            liquidity_type=kind,
            level=(current.price + previous.price) / 2.0,
            first_swing_index=previous.index,
            second_swing_index=current.index,
            first_swing_time=previous.time,
            second_swing_time=current.time,
            created_index=created_index,
            created_time=frame["time"].iloc[created_index],
            tolerance=float(tolerance),
        ))
        paired.add(current.index)
        paired.add(previous.index)
        # The original `paired` set is keyed only by pivot index, not pivot type.
        # Remove both indices from both trees to preserve this exact behavior.
        high_index.remove_pivot_index(current.index)
        low_index.remove_pivot_index(current.index)
        high_index.remove_pivot_index(previous.index)
        low_index.remove_pivot_index(previous.index)

    return sorted(pools, key=lambda p: (p.created_index, p.liquidity_type.value))


def detect_smc_liquidity_sweeps(
    df: pd.DataFrame,
    pools: Sequence[SMCLiquidityPool],
    min_penetration: float = 0.0,
) -> List[SMCLiquiditySweep]:
    """Detect the first wick-through-and-close-back sweep after each pool forms.

    The scan is chunk-vectorized rather than iterating through every pandas row.
    It still stops at the first matching candle for each pool, preserving the v1
    event definition while making long histories practical to analyze.
    """
    if min_penetration < 0:
        raise ValueError("min_penetration must be >= 0")
    if df.empty or not pools:
        return []
    frame = _prepare_frame(df)
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    times = frame["time"].to_numpy()
    events: List[SMCLiquiditySweep] = []
    chunk_size = 512
    n = len(frame)

    for pool in pools:
        # The creation candle cannot sweep its own pool: the level is only
        # actionable after that candle has closed and confirmed the second pivot.
        first = max(0, int(pool.created_index) + 1)
        for chunk_start in range(first, n, chunk_size):
            chunk_stop = min(n, chunk_start + chunk_size)
            if pool.liquidity_type == SMCLiquidityType.BUY_SIDE:
                chunk_high = highs[chunk_start:chunk_stop]
                penetration_values = chunk_high - pool.level
                mask = (penetration_values > min_penetration) & (closes[chunk_start:chunk_stop] < pool.level)
            else:
                chunk_low = lows[chunk_start:chunk_stop]
                penetration_values = pool.level - chunk_low
                mask = (penetration_values > min_penetration) & (closes[chunk_start:chunk_stop] > pool.level)

            matching = np.flatnonzero(mask)
            if matching.size == 0:
                continue

            i = chunk_start + int(matching[0])
            if pool.liquidity_type == SMCLiquidityType.BUY_SIDE:
                penetration = float(highs[i] - pool.level)
                extreme = float(highs[i])
            else:
                penetration = float(pool.level - lows[i])
                extreme = float(lows[i])
            events.append(SMCLiquiditySweep(
                liquidity_pool=pool,
                sweep_index=i,
                sweep_time=pd.Timestamp(times[i]),
                sweep_price=extreme,
                close_price=float(closes[i]),
                penetration=penetration,
            ))
            break  # One sweep event per pool in v1.
    return sorted(events, key=lambda e: (e.sweep_index, e.liquidity_type.value))


def detect_smc_order_blocks(
    df: pd.DataFrame,
    structure_breaks: Sequence[SMCStructureBreak],
    lookback: int = 5,
    zone_basis: str = "wick",
    track_lifecycle: bool = True,
) -> List[SMCOrderBlock]:
    """Identify the last opposing candle before a close-based structure break.

    Unlike the existing ICT OB detector, this SMC definition does not require an
    FVG or displacement condition. The zone is only confirmed at the structure
    break bar, not retroactively at the origin candle.
    """
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    if zone_basis not in {"wick", "body"}:
        raise ValueError("zone_basis must be 'wick' or 'body'")
    if df.empty and not structure_breaks:
        return []
    frame = _prepare_frame(df)
    opens = frame["open"].to_numpy(dtype=float)
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    blocks: List[SMCOrderBlock] = []
    for event in structure_breaks:
        direction = event.direction
        start = max(0, event.break_index - lookback)
        origin = None
        for j in range(event.break_index - 1, start - 1, -1):
            o = float(opens[j])
            c = float(closes[j])
            is_opposing = (direction == SMCDirection.BULLISH and c < o) or (direction == SMCDirection.BEARISH and c > o)
            if is_opposing:
                origin = j
                break
        if origin is None:
            continue
        origin_time = frame["time"].iloc[origin]
        if zone_basis == "wick":
            zone_high, zone_low = float(highs[origin]), float(lows[origin])
        else:
            zone_high = max(float(opens[origin]), float(closes[origin]))
            zone_low = min(float(opens[origin]), float(closes[origin]))
        block = SMCOrderBlock(
            direction=direction,
            origin_index=origin,
            origin_time=origin_time,
            high=zone_high,
            low=zone_low,
            open=float(opens[origin]),
            close=float(closes[origin]),
            created_index=event.break_index,
            created_time=event.break_time,
            confirming_break_type=event.break_type,
        )
        if track_lifecycle:
            # Scan small NumPy chunks and stop at the first terminal lifecycle
            # event. Invalidation keeps precedence when the same candle also
            # overlaps the zone, matching the original row-wise rule.
            future_start = int(event.break_index) + 1
            chunk_size = 512
            for chunk_start in range(future_start, len(frame), chunk_size):
                chunk_stop = min(len(frame), chunk_start + chunk_size)
                future_closes = closes[chunk_start:chunk_stop]
                future_highs = highs[chunk_start:chunk_stop]
                future_lows = lows[chunk_start:chunk_stop]
                if direction == SMCDirection.BULLISH:
                    invalidated_mask = future_closes < zone_low
                else:
                    invalidated_mask = future_closes > zone_high
                touched_mask = (future_highs >= zone_low) & (future_lows <= zone_high)
                terminal_mask = invalidated_mask | touched_mask
                matches = np.flatnonzero(terminal_mask)
                if matches.size == 0:
                    continue
                k = chunk_start + int(matches[0])
                # Keep the invalidation-first behavior if both conditions hold.
                if bool(invalidated_mask[int(matches[0])]):
                    block.status = SMCOrderBlockStatus.INVALIDATED
                    block.invalidation_index = k
                    block.invalidation_time = frame["time"].iloc[k]
                else:
                    block.status = SMCOrderBlockStatus.MITIGATED
                    block.mitigation_index = k
                    block.mitigation_time = frame["time"].iloc[k]
                break
        blocks.append(block)
    return blocks


def detect_smc_fvgs(
    df: pd.DataFrame,
    min_gap_size: float = 0.0,
) -> List[SMCFairValueGap]:
    """Detect SMC Fair Value Gaps (3-candle price imbalances).

    An SMC FVG requires no displacement condition — it is a pure structural
    imbalance between the first and third candle of a 3-candle sequence:

    - Bullish FVG: ``low[i+2] > high[i]`` (upside gap; price skipped over).
    - Bearish FVG: ``high[i+2] < low[i]`` (downside gap; price skipped over).

    The gap becomes knowable only at the close of candle ``i+2``.
    ``min_gap_size`` filters out gaps smaller than the given dollar threshold.

    After detection, each FVG's lifecycle status is tracked forward:

    - ``PARTIAL``: any subsequent candle closes inside the zone.
    - ``CLOSED``: a subsequent candle fully covers the zone (closes through or
      beyond the opposite boundary), or the candle's low (bullish) / high
      (bearish) fully covers the zone.

    Returns a list of SMCFairValueGap ordered by creation_index.
    """
    if min_gap_size < 0:
        raise ValueError("min_gap_size must be >= 0")
    if df.empty or len(df) < 3:
        return []
    frame = _prepare_frame(df)
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    times = frame["time"]
    n = len(frame)
    fvgs: List[SMCFairValueGap] = []

    for i in range(n - 2):
        creation_index = i + 2

        # Bullish imbalance: gap above high[i] up to low[i+2].
        if lows[i + 2] > highs[i]:
            bottom = float(highs[i])
            top = float(lows[i + 2])
            size = top - bottom
            if size > min_gap_size:
                fvgs.append(SMCFairValueGap(
                    fvg_type=SMCFVGType.BULLISH,
                    origin_index=i,
                    origin_time=times.iloc[i],
                    creation_index=creation_index,
                    creation_time=times.iloc[creation_index],
                    top=top,
                    bottom=bottom,
                    midpoint=(top + bottom) / 2.0,
                    size=size,
                ))

        # Bearish imbalance: gap below low[i] down to high[i+2].
        elif highs[i + 2] < lows[i]:
            top = float(lows[i])
            bottom = float(highs[i + 2])
            size = top - bottom
            if size > min_gap_size:
                fvgs.append(SMCFairValueGap(
                    fvg_type=SMCFVGType.BEARISH,
                    origin_index=i,
                    origin_time=times.iloc[i],
                    creation_index=creation_index,
                    creation_time=times.iloc[creation_index],
                    top=top,
                    bottom=bottom,
                    midpoint=(top + bottom) / 2.0,
                    size=size,
                ))

    # Forward-scan lifecycle for each gap.
    chunk_size = 512
    for fvg in fvgs:
        future_start = fvg.creation_index + 1
        if future_start >= n:
            continue
        bullish = fvg.fvg_type == SMCFVGType.BULLISH
        done = False
        for chunk_start in range(future_start, n, chunk_size):
            if done:
                break
            chunk_stop = min(n, chunk_start + chunk_size)
            for offset in range(chunk_stop - chunk_start):
                k = chunk_start + offset
                close_k = float(closes[k])
                high_k = float(highs[k])
                low_k = float(lows[k])
                # Fully closed: candle closes through/beyond the far boundary.
                full_close = (bullish and close_k >= fvg.top) or (not bullish and close_k <= fvg.bottom)
                # Fully covered: the candle's wick fully spans the zone.
                full_wick = (bullish and low_k <= fvg.bottom) or (not bullish and high_k >= fvg.top)
                inside_close = fvg.bottom < close_k < fvg.top
                ce_reached = (bullish and close_k >= fvg.midpoint) or (not bullish and close_k <= fvg.midpoint)
                if full_close or full_wick:
                    if fvg.first_touch_index is None:
                        fvg.first_touch_index = k
                        fvg.first_touch_time = times.iloc[k]
                    if fvg.ce_index is None and ce_reached:
                        fvg.ce_index = k
                        fvg.ce_time = times.iloc[k]
                    fvg.closed_index = k
                    fvg.closed_time = times.iloc[k]
                    fvg.status = SMCFVGStatus.CLOSED
                    done = True
                    break
                elif inside_close:
                    if fvg.first_touch_index is None:
                        fvg.first_touch_index = k
                        fvg.first_touch_time = times.iloc[k]
                        fvg.status = SMCFVGStatus.PARTIAL
                    if fvg.ce_index is None and ce_reached:
                        fvg.ce_index = k
                        fvg.ce_time = times.iloc[k]

    return sorted(fvgs, key=lambda f: f.creation_index)


def detect_smc_breaker_blocks(
    df: pd.DataFrame,
    order_blocks: Sequence[SMCOrderBlock],
) -> List[SMCBreakerBlock]:
    """Detect Breaker Blocks formed by invalidated Order Blocks in the SMC framework.

    When an Order Block is invalidated:
    - An invalidated Bullish Order Block (breached downward by candle close < low)
      inverts into a Bearish Breaker Block, becoming a supply/resistance zone.
    - An invalidated Bearish Order Block (breached upward by candle close > high)
      inverts into a Bullish Breaker Block, becoming a demand/support zone.

    The Breaker Block is established at the exact bar where the OB was invalidated
    (close beyond the zone). Its lifecycle is then tracked forward:
    - Retest (TESTED): A subsequent candle overlaps the breaker zone [low, high].
    - Invalidation: A subsequent candle closes beyond the opposite boundary of the breaker
      (close < low for Bullish breaker, close > high for Bearish breaker).
    """
    if df.empty or not order_blocks:
        return []

    frame = _prepare_frame(df)
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    times = frame["time"]

    breakers: List[SMCBreakerBlock] = []
    for ob in order_blocks:
        if ob.status != SMCOrderBlockStatus.INVALIDATED or ob.invalidation_index is None:
            continue

        if ob.direction == SMCDirection.BULLISH:
            breaker_type = SMCBreakerBlockType.BEARISH
        elif ob.direction == SMCDirection.BEARISH:
            breaker_type = SMCBreakerBlockType.BULLISH
        else:
            continue

        inval_idx = ob.invalidation_index
        inval_time = ob.invalidation_time if ob.invalidation_time is not None else times.iloc[inval_idx]

        breaker = SMCBreakerBlock(
            breaker_type=breaker_type,
            source_order_block=ob,
            high=ob.high,
            low=ob.low,
            created_index=inval_idx,
            created_time=inval_time,
            status=SMCBreakerBlockStatus.ACTIVE,
        )

        # Track breaker forward lifecycle starting from the bar after creation
        start_idx = inval_idx + 1
        for k in range(start_idx, len(frame)):
            c_k = closes[k]
            h_k = highs[k]
            l_k = lows[k]
            t_k = times.iloc[k]

            # Invalidation check:
            # Bullish breaker: support invalidated if close < breaker.low
            # Bearish breaker: resistance invalidated if close > breaker.high
            if breaker_type == SMCBreakerBlockType.BULLISH and c_k < breaker.low:
                breaker.status = SMCBreakerBlockStatus.INVALIDATED
                breaker.invalidation_index = k
                breaker.invalidation_time = t_k
                break
            elif breaker_type == SMCBreakerBlockType.BEARISH and c_k > breaker.high:
                breaker.status = SMCBreakerBlockStatus.INVALIDATED
                breaker.invalidation_index = k
                breaker.invalidation_time = t_k
                break

            # Retest / mitigation check: price enters the zone [low, high]
            if breaker.status == SMCBreakerBlockStatus.ACTIVE and (h_k >= breaker.low and l_k <= breaker.high):
                breaker.status = SMCBreakerBlockStatus.TESTED
                breaker.retest_index = k
                breaker.retest_time = t_k

        breakers.append(breaker)

    return sorted(breakers, key=lambda b: b.created_index)


def _current_dealing_range(swings: Sequence[SMCSwingPoint]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    highs = [s for s in swings if s.swing_type == SMCSwingType.SWING_HIGH]
    lows = [s for s in swings if s.swing_type == SMCSwingType.SWING_LOW]
    if not highs or not lows:
        return None, None, None
    high = max(highs, key=lambda s: s.confirmed_index)
    low = max(lows, key=lambda s: s.confirmed_index)
    upper, lower = high.price, low.price
    if upper <= lower:
        return None, None, None
    return upper, lower, (upper + lower) / 2.0


def analyze_smc(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    config: Optional[SMCConfig] = None,
) -> SMCAnalysisResult:
    """Run the independent SMC v1 detector over a chronologically ordered OHLC frame."""
    config = config or SMCConfig()
    if df.empty:
        return SMCAnalysisResult(symbol=symbol, timeframe=timeframe, total_bars=0)
    frame = _prepare_frame(df)
    swings = detect_smc_swings(frame, window=config.swing_window)
    breaks, trend = detect_smc_structure_breaks(frame, swings)
    pools = detect_smc_liquidity_pools(frame, swings, tolerance=config.equal_level_tolerance)
    sweeps = detect_smc_liquidity_sweeps(frame, pools, min_penetration=config.min_sweep_penetration)
    blocks = detect_smc_order_blocks(
        frame,
        breaks,
        lookback=config.order_block_lookback,
        zone_basis=config.order_block_zone_basis,
        track_lifecycle=config.track_order_block_lifecycle,
    )
    breakers = []
    if config.track_breaker_blocks:
        breakers = detect_smc_breaker_blocks(frame, blocks)
    fvgs = detect_smc_fvgs(frame, min_gap_size=config.min_fvg_size)
    range_high, range_low, equilibrium = _current_dealing_range(swings)
    current_zone = "UNAVAILABLE"
    if equilibrium is not None:
        final_close = float(frame["close"].iloc[-1])
        current_zone = "PREMIUM" if final_close > equilibrium else "DISCOUNT" if final_close < equilibrium else "EQUILIBRIUM"
    return SMCAnalysisResult(
        symbol=symbol,
        timeframe=timeframe,
        total_bars=len(frame),
        current_trend=trend,
        swings=swings,
        structure_breaks=breaks,
        liquidity_pools=pools,
        liquidity_sweeps=sweeps,
        order_blocks=blocks,
        breaker_blocks=breakers,
        fair_value_gaps=fvgs,
        equilibrium=equilibrium,
        dealing_range_high=range_high,
        dealing_range_low=range_low,
        current_zone=current_zone,
    )
