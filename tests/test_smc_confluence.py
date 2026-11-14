"""Unit tests for SMC_CONFLUENCE_V1 strategy candidate."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from src.backtesting.engine import BacktestConfig
from src.strategy.smc_confluence import (
    SMCConfluenceConfig,
    SMCConfluenceStrategy,
    run_confluence_backtest,
)


@pytest.fixture
def h4_data():
    h4_path = Path("data/processed/XAUUSD_H4_clean.csv")
    if not h4_path.exists():
        pytest.skip("H4 clean data not found")
    df = pd.read_csv(h4_path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


@pytest.fixture
def m15_data():
    m15_path = Path("data/processed/XAUUSD_M15_clean.csv")
    if not m15_path.exists():
        pytest.skip("M15 clean data not found")
    df = pd.read_csv(m15_path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def test_smc_confluence_generation(h4_data, m15_data):
    """Verify that SMCConfluenceStrategy processes candidates and applies filters."""
    # Test on a 1000-bar slice of M15
    m15_slice = m15_data.iloc[:1000].copy()

    # Strategy with all filters enabled
    strategy = SMCConfluenceStrategy(
        h4_df=h4_data,
        news_calendar_source="data/news/usd_high_impact_news.csv",
        config=SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=True,
            enable_news_filter=True,
            enable_atr_stop=True,
            enable_breakeven=True,
        ),
    )

    accepted, funnel, audit_rows = strategy.generate_candidates(m15_slice, timeframe="M15")

    assert funnel["raw_candidates_input"] >= 0
    assert len(audit_rows) == funnel["raw_candidates_input"]
    assert len(accepted) == funnel["confluence_accepted"]
    assert funnel["active_filters"]["htf_bias"] is True
    assert funnel["active_filters"]["session_filter"] is True
    assert funnel["active_filters"]["news_filter"] is True


def test_smc_confluence_filter_toggles(h4_data, m15_data):
    """Disabling filters should allow more candidates through (monotonicity)."""
    m15_slice = m15_data.iloc[:1500].copy()

    # All filters disabled (should equal raw candidates)
    strat_raw = SMCConfluenceStrategy(
        h4_df=h4_data,
        news_calendar_source="data/news/usd_high_impact_news.csv",
        config=SMCConfluenceConfig(
            enable_htf_bias=False,
            enable_session_filter=False,
            enable_news_filter=False,
            enable_atr_stop=False,
        ),
    )
    acc_raw, funnel_raw, _ = strat_raw.generate_candidates(m15_slice, timeframe="M15")

    # HTF bias only
    strat_htf = SMCConfluenceStrategy(
        h4_df=h4_data,
        news_calendar_source="data/news/usd_high_impact_news.csv",
        config=SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=False,
            enable_news_filter=False,
            enable_atr_stop=False,
        ),
    )
    acc_htf, funnel_htf, _ = strat_htf.generate_candidates(m15_slice, timeframe="M15")

    # All filters enabled
    strat_all = SMCConfluenceStrategy(
        h4_df=h4_data,
        news_calendar_source="data/news/usd_high_impact_news.csv",
        config=SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=True,
            enable_news_filter=True,
            enable_atr_stop=True,
        ),
    )
    acc_all, funnel_all, _ = strat_all.generate_candidates(m15_slice, timeframe="M15")

    # Monotonic filtering: raw >= HTF >= all
    assert len(acc_raw) >= len(acc_htf)
    assert len(acc_htf) >= len(acc_all)


def test_smc_confluence_backtest_execution(h4_data, m15_data):
    """Verify run_confluence_backtest runs cleanly with breakeven enabled."""
    m15_slice = m15_data.iloc[:1500].copy()

    strat = SMCConfluenceStrategy(
        h4_df=h4_data,
        news_calendar_source="data/news/usd_high_impact_news.csv",
        config=SMCConfluenceConfig(
            enable_htf_bias=False,  # Allow more trades to test execution
            enable_session_filter=True,
            enable_news_filter=False,
            enable_atr_stop=True,
            enable_breakeven=True,
        ),
    )
    accepted, _, _ = strat.generate_candidates(m15_slice, timeframe="M15")

    b_config = BacktestConfig(
        initial_capital=10_000.0,
        risk_fraction=0.005,
    )
    result = run_confluence_backtest(
        m15_slice,
        accepted,
        config=b_config,
        timeframe="M15",
        enable_breakeven=True,
        breakeven_r_trigger=1.5,
    )

    assert result is not None
    assert "profit_factor" in result.metrics
    assert "win_rate_pct" in result.metrics
    assert len(result.equity_curve) == len(m15_slice)

