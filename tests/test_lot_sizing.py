"""Unit tests for XAU/USD monetary risk lot sizing."""
from __future__ import annotations

import pytest

from src.risk.lot_sizing import calculate_xauusd_lot_size


def test_lot_sizing_standard():
    """Verify standard lot sizing calculation with $10,000 capital and 0.5% risk."""
    equity = 10_000.0
    risk_pct = 0.005  # $50 risk budget
    entry = 2300.0
    stop = 2295.0     # $5.00 distance -> $500 risk per standard lot (100 oz)

    result = calculate_xauusd_lot_size(equity, risk_pct, entry, stop)
    assert result.is_valid
    assert result.risk_usd == 50.0
    assert result.dollar_risk_per_lot == 500.0
    # 50 / 500 = 0.10 lots
    assert result.lots == 0.10
    assert result.actual_risk_usd == 50.0
    assert result.rejection_reason is None


def test_lot_sizing_strict_floor_rounding():
    """Verify lot sizing floors downward to prevent risk budget overage."""
    equity = 10_000.0
    risk_pct = 0.005  # $50 budget
    entry = 2300.0
    stop = 2296.80    # $3.20 distance -> $320 risk per lot
    # 50 / 320 = 0.15625 lots -> floor to 0.15 lots (0.15 * 320 = $48 <= $50)

    result = calculate_xauusd_lot_size(equity, risk_pct, entry, stop)
    assert result.is_valid
    assert result.lots == 0.15
    assert result.actual_risk_usd <= 50.0
    assert result.actual_risk_usd == pytest.approx(48.0)


def test_lot_sizing_stop_too_wide_for_min_lot():
    """When stop distance requires less than min_lot (0.01), reject setup."""
    equity = 1_000.0
    risk_pct = 0.005  # $5 budget
    entry = 2300.0
    stop = 2280.0     # $20 distance -> min lot (0.01) risk is 0.01 * 20 * 100 = $20 > $5

    result = calculate_xauusd_lot_size(equity, risk_pct, entry, stop, min_lot=0.01)
    assert not result.is_valid
    assert result.lots == 0.0
    assert result.rejection_reason == "REJECTED_STOP_TOO_WIDE_FOR_MIN_LOT"


def test_lot_sizing_invalid_inputs():
    """Verify handling of invalid equity and stop distance."""
    # Zero or negative equity
    res_eq = calculate_xauusd_lot_size(-100.0, 0.01, 2300.0, 2290.0)
    assert not res_eq.is_valid
    assert res_eq.rejection_reason == "REJECTED_INSUFFICIENT_EQUITY"

    # Zero stop distance
    res_dist = calculate_xauusd_lot_size(10_000.0, 0.01, 2300.0, 2300.0)
    assert not res_dist.is_valid
    assert res_dist.rejection_reason == "REJECTED_INVALID_STOP_DISTANCE"
