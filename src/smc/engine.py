"""Deterministic, standalone SMC market-structure analysis.

Operational v1 definitions are documented in ``docs/SMC_RULES.md``. The engine
uses confirmed swings, close-based structure breaks, equal-high/low pools,
wick-and-reclaim sweeps, break-confirmed order blocks, and a swing dealing range.
It deliberately does not depend on the ICT engine or require FVG/displacement
confluence. All event timestamps are UTC-aware and include availability indices.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.smc.models import (
    SMCAnalysisResult,
    SMCDirection,
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


def detect_smc_liquidity_pools(
    df: pd.DataFrame,
    swings: Sequence[SMCSwingPoint],
    tolerance: float = 0.50,
) -> List[SMCLiquidityPool]:
    """Create a pool from the first pair of confirmed pivots within tolerance.

    The pool level is frozen at the pair's midpoint and becomes known only when
    the later pivot confirms. This v1 intentionally uses one pair per pivot to
    avoid retrospectively moving a level after later touches.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")
    if df.empty or len(swings) < 2:
        return []
    frame = _prepare_frame(df)
    ordered = sorted(swings, key=lambda s: (s.confirmed_index, s.index))
    paired = set()
    pools: List[SMCLiquidityPool] = []
    for i, current in enumerate(ordered):
        if current.index in paired:
            continue
        for previous in reversed(ordered[:i]):
            if previous.index in paired or previous.swing_type != current.swing_type:
                continue
            if abs(current.price - previous.price) <= tolerance:
                created_index = max(current.confirmed_index, previous.confirmed_index)
                if created_index >= len(frame):
                    continue
                kind = SMCLiquidityType.BUY_SIDE if current.swing_type == SMCSwingType.SWING_HIGH else SMCLiquidityType.SELL_SIDE
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
                break
    return sorted(pools, key=lambda p: (p.created_index, p.liquidity_type.value))


def detect_smc_liquidity_sweeps(
    df: pd.DataFrame,
    pools: Sequence[SMCLiquidityPool],
    min_penetration: float = 0.0,
) -> List[SMCLiquiditySweep]:
    """Detect wick-through-and-close-back sweeps after a pool is knowable."""
    if min_penetration < 0:
        raise ValueError("min_penetration must be >= 0")
    if df.empty or not pools:
        return []
    frame = _prepare_frame(df)
    events: List[SMCLiquiditySweep] = []
    for pool in pools:
        # Pool's creation candle is not used as a sweep: the pool only becomes
        # actionable after that candle closes and confirms the second pivot.
        for i in range(pool.created_index + 1, len(frame)):
            row = frame.iloc[i]
            if pool.liquidity_type == SMCLiquidityType.BUY_SIDE:
                penetration = float(row["high"]) - pool.level
                swept = penetration > min_penetration and float(row["close"]) < pool.level
                extreme = float(row["high"])
            else:
                penetration = pool.level - float(row["low"])
                swept = penetration > min_penetration and float(row["close"]) > pool.level
                extreme = float(row["low"])
            if swept:
                events.append(SMCLiquiditySweep(
                    liquidity_pool=pool,
                    sweep_index=i,
                    sweep_time=row["time"],
                    sweep_price=extreme,
                    close_price=float(row["close"]),
                    penetration=float(penetration),
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
    blocks: List[SMCOrderBlock] = []
    for event in structure_breaks:
        direction = event.direction
        start = max(0, event.break_index - lookback)
        origin = None
        for j in range(event.break_index - 1, start - 1, -1):
            o = float(frame["open"].iloc[j])
            c = float(frame["close"].iloc[j])
            is_opposing = (direction == SMCDirection.BULLISH and c < o) or (direction == SMCDirection.BEARISH and c > o)
            if is_opposing:
                origin = j
                break
        if origin is None:
            continue
        row = frame.iloc[origin]
        if zone_basis == "wick":
            zone_high, zone_low = float(row["high"]), float(row["low"])
        else:
            zone_high = max(float(row["open"]), float(row["close"]))
            zone_low = min(float(row["open"]), float(row["close"]))
        block = SMCOrderBlock(
            direction=direction,
            origin_index=origin,
            origin_time=row["time"],
            high=zone_high,
            low=zone_low,
            open=float(row["open"]),
            close=float(row["close"]),
            created_index=event.break_index,
            created_time=event.break_time,
            confirming_break_type=event.break_type,
        )
        if track_lifecycle:
            for k in range(event.break_index + 1, len(frame)):
                future = frame.iloc[k]
                close = float(future["close"])
                high = float(future["high"])
                low = float(future["low"])
                invalidated = (direction == SMCDirection.BULLISH and close < zone_low) or (
                    direction == SMCDirection.BEARISH and close > zone_high
                )
                touched = high >= zone_low and low <= zone_high
                if invalidated:
                    block.status = SMCOrderBlockStatus.INVALIDATED
                    block.invalidation_index = k
                    block.invalidation_time = future["time"]
                    break
                if touched:
                    block.status = SMCOrderBlockStatus.MITIGATED
                    block.mitigation_index = k
                    block.mitigation_time = future["time"]
                    break
        blocks.append(block)
    return blocks


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
        equilibrium=equilibrium,
        dealing_range_high=range_high,
        dealing_range_low=range_low,
        current_zone=current_zone,
    )
