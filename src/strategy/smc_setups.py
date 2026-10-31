"""Pure-SMC reversal setup hypothesis: sweep -> CHoCH -> order-block retest.

This module emits setup candidates only. It does not place orders, claim fills,
size positions, or evaluate profitability. It deliberately does not require ICT
FVG, displacement, MSS, CE, or kill-zone confluence.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.smc.models import (
    SMCAnalysisResult,
    SMCDirection,
    SMCLiquidityType,
    SMCOrderBlock,
    SMCStructureType,
)


@dataclass(frozen=True)
class SMCSetupConfig:
    max_sweep_to_choch_bars: int = 20
    max_bars_choch_to_retest: int = 20
    stop_buffer: float = 0.50
    fixed_rr: float = 2.0
    minimum_reward_risk: float = 1.0
    use_opposing_liquidity_target: bool = True
    require_premium_discount: bool = False

    def __post_init__(self) -> None:
        if self.max_sweep_to_choch_bars < 1:
            raise ValueError("max_sweep_to_choch_bars must be >= 1")
        if self.max_bars_choch_to_retest < 1:
            raise ValueError("max_bars_choch_to_retest must be >= 1")
        if self.stop_buffer < 0:
            raise ValueError("stop_buffer must be >= 0")
        if self.fixed_rr <= 0:
            raise ValueError("fixed_rr must be > 0")
        if self.minimum_reward_risk < 0:
            raise ValueError("minimum_reward_risk must be >= 0")


@dataclass(frozen=True)
class SMCSetupCandidate:
    direction: SMCDirection
    sweep_index: int
    sweep_time: pd.Timestamp
    choch_index: int
    choch_time: pd.Timestamp
    order_block_origin_index: int
    order_block_created_index: int
    order_block_created_time: pd.Timestamp
    signal_index: int
    signal_time: pd.Timestamp
    entry_reference_price: float
    stop_loss_reference: float
    take_profit_reference: float
    target_source: str
    risk_distance: float
    reward_risk_ratio: float
    next_bar_open: Optional[float] = None
    next_bar_time: Optional[pd.Timestamp] = None
    baseline_atr: Optional[float] = None

    def to_dict(self):
        d = {
            "direction": self.direction.value,
            "sweep_index": self.sweep_index,
            "sweep_time": self.sweep_time.isoformat(),
            "choch_index": self.choch_index,
            "choch_time": self.choch_time.isoformat(),
            "order_block_origin_index": self.order_block_origin_index,
            "order_block_created_index": self.order_block_created_index,
            "order_block_created_time": self.order_block_created_time.isoformat(),
            "signal_index": self.signal_index,
            "signal_time": self.signal_time.isoformat(),
            "entry_reference_price": self.entry_reference_price,
            "stop_loss_reference": self.stop_loss_reference,
            "take_profit_reference": self.take_profit_reference,
            "target_source": self.target_source,
            "risk_distance": self.risk_distance,
            "reward_risk_ratio": self.reward_risk_ratio,
        }
        if self.next_bar_open is not None:
            d["next_bar_open"] = self.next_bar_open
        if self.next_bar_time is not None:
            d["next_bar_time"] = self.next_bar_time.isoformat()
        if self.baseline_atr is not None:
            d["baseline_atr"] = self.baseline_atr
        return d


def _latest_known_equilibrium(analysis: SMCAnalysisResult, signal_index: int) -> Optional[float]:
    """Compute an equilibrium using only swings confirmed strictly before signal bar."""
    known = [s for s in analysis.swings if s.confirmed_index < signal_index]
    highs = [s for s in known if s.swing_type.value == "SWING_HIGH"]
    lows = [s for s in known if s.swing_type.value == "SWING_LOW"]
    if not highs or not lows:
        return None
    high = max(highs, key=lambda s: s.confirmed_index).price
    low = max(lows, key=lambda s: s.confirmed_index).price
    if high <= low:
        return None
    return (high + low) / 2.0


def _find_target(
    entry: float,
    risk: float,
    direction: SMCDirection,
    signal_index: int,
    analysis: SMCAnalysisResult,
    config: SMCSetupConfig,
    *,
    pools_by_type: Optional[Dict[SMCLiquidityType, Sequence]] = None,
    first_sweep_index_by_pool: Optional[Dict[int, int]] = None,
) -> tuple[float, str, float]:
    target_pools = []
    if config.use_opposing_liquidity_target:
        target_type = SMCLiquidityType.BUY_SIDE if direction == SMCDirection.BULLISH else SMCLiquidityType.SELL_SIDE
        if pools_by_type is None:
            candidate_pools = analysis.liquidity_pools
        else:
            candidate_pools = pools_by_type[target_type]
        if first_sweep_index_by_pool is None:
            swept_before_signal = {
                id(event.liquidity_pool)
                for event in analysis.liquidity_sweeps
                if event.sweep_index < signal_index
            }
            is_unswept = lambda pool: id(pool) not in swept_before_signal
        else:
            # A pool swept only after this signal was still unswept at signal time.
            is_unswept = lambda pool: first_sweep_index_by_pool.get(id(pool), signal_index) >= signal_index
        target_pools = [
            pool for pool in candidate_pools
            if pool.liquidity_type == target_type
            and pool.created_index < signal_index
            and is_unswept(pool)
            and ((direction == SMCDirection.BULLISH and pool.level > entry)
                 or (direction == SMCDirection.BEARISH and pool.level < entry))
        ]
    if target_pools:
        pool = min(target_pools, key=lambda p: abs(p.level - entry))
        reward = (pool.level - entry) if direction == SMCDirection.BULLISH else (entry - pool.level)
        return pool.level, "opposing_liquidity", reward / risk
    target = entry + config.fixed_rr * risk if direction == SMCDirection.BULLISH else entry - config.fixed_rr * risk
    return target, "fixed_rr_fallback", config.fixed_rr


def detect_smc_setups_with_funnel(
    df: pd.DataFrame,
    analysis: SMCAnalysisResult,
    config: Optional[SMCSetupConfig] = None,
) -> tuple[List[SMCSetupCandidate], dict]:
    """Produce close-confirmed SMC setup candidates and detailed funnel accounting.

    Long: sell-side sweep -> bullish CHoCH from bearish structure -> bullish OB
    retest/rejection. Short is the inverse.
    """
    config = config or SMCSetupConfig()
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"SMC setup detection requires columns: {', '.join(missing)}")
    if df.empty or analysis.total_bars == 0:
        return [], {
            "total_bars": 0,
            "total_structure_breaks": 0,
            "choch_breaks_evaluated": 0,
            "choch_trend_aligned": 0,
            "choch_with_preceding_sweep": 0,
            "choch_with_order_block": 0,
            "ob_retest_evaluated": 0,
            "ob_retest_invalidated": 0,
            "ob_retest_timed_out": 0,
            "ob_retest_confirmed": 0,
            "passed_premium_discount": 0,
            "rejected_premium_discount": 0,
            "valid_risk_and_rr": 0,
            "rejected_risk_or_rr": 0,
            "final_candidates": 0,
            "next_bar_open_available": 0,
        }
    frame = df.copy().reset_index(drop=True)
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    if frame["time"].isna().any() or not frame["time"].is_monotonic_increasing or frame["time"].duplicated().any():
        raise ValueError("SMC setup input timestamps must be valid, unique, and chronological")
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if not np.isfinite(frame[column].to_numpy(dtype=float)).all():
            raise ValueError(f"SMC setup input contains invalid {column} prices")
    invalid = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    )
    if invalid.any():
        raise ValueError(f"SMC setup input contains {int(invalid.sum())} invalid OHLC row(s)")
    if len(frame) != analysis.total_bars:
        raise ValueError("SMC analysis result bar count does not match the supplied dataframe")

    funnel = {
        "total_bars": len(frame),
        "total_structure_breaks": len(analysis.structure_breaks),
        "choch_breaks_evaluated": 0,
        "choch_trend_aligned": 0,
        "choch_with_preceding_sweep": 0,
        "choch_with_order_block": 0,
        "ob_retest_evaluated": 0,
        "ob_retest_invalidated": 0,
        "ob_retest_timed_out": 0,
        "ob_retest_confirmed": 0,
        "passed_premium_discount": 0,
        "rejected_premium_discount": 0,
        "valid_risk_and_rr": 0,
        "rejected_risk_or_rr": 0,
        "final_candidates": 0,
        "next_bar_open_available": 0,
    }

    setups: List[SMCSetupCandidate] = []
    used_breaks = set()

    # Index the two event collections that were previously rescanned in full for
    # every CHoCH. Insertion order is preserved so tie-breaking remains identical
    # to the frozen v1 implementation.
    sweeps_by_type: Dict[SMCLiquidityType, List] = {
        SMCLiquidityType.BUY_SIDE: [],
        SMCLiquidityType.SELL_SIDE: [],
    }
    for sweep_event in analysis.liquidity_sweeps:
        sweeps_by_type[sweep_event.liquidity_type].append(sweep_event)
    for side_events in sweeps_by_type.values():
        side_events.sort(key=lambda item: item.sweep_index)  # stable for same-bar tie behavior
    sweep_indices_by_type = {
        side: [int(sweep_event.sweep_index) for sweep_event in side_events]
        for side, side_events in sweeps_by_type.items()
    }
    first_block_by_break_and_direction = {}
    for order_block in analysis.order_blocks:
        first_block_by_break_and_direction.setdefault(
            (int(order_block.created_index), order_block.direction), order_block
        )
    pools_by_type: Dict[SMCLiquidityType, List] = {
        SMCLiquidityType.BUY_SIDE: [],
        SMCLiquidityType.SELL_SIDE: [],
    }
    for pool in analysis.liquidity_pools:
        pools_by_type[pool.liquidity_type].append(pool)
    first_sweep_index_by_pool = {
        id(sweep_event.liquidity_pool): int(sweep_event.sweep_index)
        for sweep_event in analysis.liquidity_sweeps
    }

    # Array access removes pandas row construction from the short retest loop.
    opens = frame["open"].to_numpy(dtype=float)
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    times = frame["time"].to_numpy()

    for event in analysis.structure_breaks:
        if event.break_type != SMCStructureType.CHOCH:
            continue
        funnel["choch_breaks_evaluated"] += 1
        direction = event.direction
        if direction == SMCDirection.BULLISH and event.prior_trend != SMCDirection.BEARISH:
            continue
        if direction == SMCDirection.BEARISH and event.prior_trend != SMCDirection.BULLISH:
            continue
        if event.break_index in used_breaks:
            continue
        funnel["choch_trend_aligned"] += 1

        matching_side = SMCLiquidityType.SELL_SIDE if direction == SMCDirection.BULLISH else SMCLiquidityType.BUY_SIDE
        side_sweeps = sweeps_by_type[matching_side]
        side_indices = sweep_indices_by_type[matching_side]
        # Find the newest sweep strictly before the break. If several pools are
        # swept on that same candle, keep the first one in the original event
        # ordering, matching max(..., key=sweep_index)'s stable tie behavior.
        prior_pos = bisect_left(side_indices, int(event.break_index)) - 1
        if prior_pos < 0:
            continue
        newest_sweep_index = side_indices[prior_pos]
        if int(event.break_index) - newest_sweep_index > config.max_sweep_to_choch_bars:
            continue
        first_pos_at_same_index = bisect_left(side_indices, newest_sweep_index)
        sweep = side_sweeps[first_pos_at_same_index]
        funnel["choch_with_preceding_sweep"] += 1

        block = first_block_by_break_and_direction.get((int(event.break_index), direction))
        if block is None:
            continue
        funnel["choch_with_order_block"] += 1
        funnel["ob_retest_evaluated"] += 1
        signal_index = None
        invalidated = False
        last_index = min(len(frame) - 1, block.created_index + config.max_bars_choch_to_retest)
        for i in range(block.created_index + 1, last_index + 1):
            close, high, low = float(closes[i]), float(highs[i]), float(lows[i])
            if direction == SMCDirection.BULLISH:
                if close < block.low:
                    invalidated = True
                    break
                touched = low <= block.high and high >= block.low
                rejected = close > block.high
            else:
                if close > block.high:
                    invalidated = True
                    break
                touched = high >= block.low and low <= block.high
                rejected = close < block.low
            if touched and rejected:
                signal_index = i
                break

        if invalidated:
            funnel["ob_retest_invalidated"] += 1
            continue
        if signal_index is None:
            funnel["ob_retest_timed_out"] += 1
            continue

        funnel["ob_retest_confirmed"] += 1

        if config.require_premium_discount:
            equilibrium = _latest_known_equilibrium(analysis, signal_index)
            if equilibrium is None:
                funnel["rejected_premium_discount"] += 1
                continue
            signal_close = float(closes[signal_index])
            if direction == SMCDirection.BULLISH and signal_close > equilibrium:
                funnel["rejected_premium_discount"] += 1
                continue
            if direction == SMCDirection.BEARISH and signal_close < equilibrium:
                funnel["rejected_premium_discount"] += 1
                continue
            funnel["passed_premium_discount"] += 1
        else:
            funnel["passed_premium_discount"] += 1

        entry = float(closes[signal_index])
        if direction == SMCDirection.BULLISH:
            stop = float(sweep.sweep_price) - config.stop_buffer
            if stop >= entry:
                funnel["rejected_risk_or_rr"] += 1
                continue
        else:
            stop = float(sweep.sweep_price) + config.stop_buffer
            if stop <= entry:
                funnel["rejected_risk_or_rr"] += 1
                continue
        risk = abs(entry - stop)
        target, target_source, rr = _find_target(
            entry, risk, direction, signal_index, analysis, config,
            pools_by_type=pools_by_type,
            first_sweep_index_by_pool=first_sweep_index_by_pool,
        )
        if rr < config.minimum_reward_risk:
            funnel["rejected_risk_or_rr"] += 1
            continue
        if (direction == SMCDirection.BULLISH and target <= entry) or (direction == SMCDirection.BEARISH and target >= entry):
            funnel["rejected_risk_or_rr"] += 1
            continue

        funnel["valid_risk_and_rr"] += 1

        next_open = float(opens[signal_index + 1]) if (signal_index + 1 < len(frame)) else None
        next_time = pd.Timestamp(times[signal_index + 1]) if (signal_index + 1 < len(frame)) else None
        if next_open is not None:
            funnel["next_bar_open_available"] += 1

        setups.append(SMCSetupCandidate(
            direction=direction,
            sweep_index=sweep.sweep_index,
            sweep_time=sweep.sweep_time,
            choch_index=event.break_index,
            choch_time=event.break_time,
            order_block_origin_index=block.origin_index,
            order_block_created_index=block.created_index,
            order_block_created_time=block.created_time,
            signal_index=signal_index,
            signal_time=pd.Timestamp(times[signal_index]),
            entry_reference_price=entry,
            stop_loss_reference=stop,
            take_profit_reference=target,
            target_source=target_source,
            risk_distance=risk,
            reward_risk_ratio=rr,
            next_bar_open=next_open,
            next_bar_time=next_time,
        ))
        used_breaks.add(event.break_index)

    funnel["final_candidates"] = len(setups)
    return sorted(setups, key=lambda s: s.signal_index), funnel


def detect_smc_setup_candidates(
    df: pd.DataFrame,
    analysis: SMCAnalysisResult,
    config: Optional[SMCSetupConfig] = None,
) -> List[SMCSetupCandidate]:
    """Produce close-confirmed SMC setup candidates from an SMC event result.

    Long: sell-side sweep -> bullish CHoCH from bearish structure -> bullish OB
    retest/rejection. Short is the inverse. The signal is the confirming close of
    the retest rejection candle, so the reference entry uses that candle's close
    rather than assuming an intrabar fill at an OB edge.
    """
    candidates, _ = detect_smc_setups_with_funnel(df, analysis, config)
    return candidates
