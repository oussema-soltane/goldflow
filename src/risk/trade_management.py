"""Volatility-adjusted stops and dynamic trade management for XAU/USD."""
from __future__ import annotations

from dataclasses import replace
import math
from typing import Any, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from src.smc.models import SMCDirection
from src.strategy.smc_setups import SMCSetupCandidate


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR) with Wilder's exponential smoothing."""
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]

    tr1 = high - low
    tr2 = np.abs(high - prev_close)
    tr3 = np.abs(low - prev_close)

    true_range = np.maximum(tr1, np.maximum(tr2, tr3))
    tr_series = pd.Series(true_range, index=df.index)

    # Wilder's exponential moving average
    atr = tr_series.ewm(alpha=1.0 / period, adjust=False).mean()
    return atr


def adjust_candidate_with_atr(
    candidate: SMCSetupCandidate,
    current_atr: float,
    *,
    min_atr_multiple: float = 1.5,
    fixed_rr: float = 2.0,
) -> SMCSetupCandidate:
    """Expand structural stop if tighter than min_atr_multiple * ATR.

    Guarantees that trade stops respect instrument market noise on XAU/USD.
    When stop is expanded, take profit is adjusted to maintain the target R:R.
    """
    if not math.isfinite(current_atr) or current_atr <= 0:
        return candidate

    min_stop_distance = min_atr_multiple * current_atr
    entry = candidate.entry_reference_price
    current_stop = candidate.stop_loss_reference
    current_distance = abs(entry - current_stop)

    if current_distance >= min_stop_distance:
        # Structural stop is already sufficiently wide
        return candidate

    # Expand stop to min_stop_distance and adjust target
    if candidate.direction == SMCDirection.BULLISH:
        new_stop = entry - min_stop_distance
        new_target = entry + fixed_rr * min_stop_distance
    else:
        new_stop = entry + min_stop_distance
        new_target = entry - fixed_rr * min_stop_distance

    return replace(
        candidate,
        stop_loss_reference=new_stop,
        take_profit_reference=new_target,
        risk_distance=min_stop_distance,
        reward_risk_ratio=fixed_rr,
        target_source="atr_expanded_fixed_rr",
        baseline_atr=current_atr,
    )


def check_breakeven_trigger(
    position: Mapping[str, Any],
    current_high: float,
    current_low: float,
    *,
    be_r_trigger: float = 1.5,
    be_buffer_usd: float = 0.05,
) -> Tuple[bool, float]:
    """Check if unrealized gain has reached be_r_trigger * initial risk.

    If reached, moves stop loss to entry + buffer (protecting fees/spread).
    Returns (trigger_fired, new_stop_loss).
    """
    side = str(position.get("side", "")).upper()
    entry = float(position["entry_price"])
    stop_loss = float(position["stop_loss"])
    risk_distance = abs(entry - stop_loss)

    if risk_distance <= 1e-4:
        return False, stop_loss

    if side == "LONG":
        target_high_for_be = entry + be_r_trigger * risk_distance
        if current_high >= target_high_for_be:
            new_stop = entry + be_buffer_usd
            # Only advance stop forward, never widen
            if new_stop > stop_loss:
                return True, new_stop
    elif side == "SHORT":
        target_low_for_be = entry - be_r_trigger * risk_distance
        if current_low <= target_low_for_be:
            new_stop = entry - be_buffer_usd
            # Only advance stop forward, never widen
            if new_stop < stop_loss:
                return True, new_stop

    return False, stop_loss

