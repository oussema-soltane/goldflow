"""
Unit tests for Data Quality Validation Engine (Phase 1).

Tests run independently of MetaTrader 5 using deterministic synthetic data.
"""

import datetime as dt
import json
import pytest
import pandas as pd
import numpy as np

from src.data.validator import validate_market_data, DataQualityReport, is_weekend_closure


def create_sample_ohlc_df(n_bars: int = 10, start_dt: str = "2026-03-02 08:00:00") -> pd.DataFrame:
    """Helper to generate a clean, structurally valid M15 dataframe."""
    base_time = pd.to_datetime(start_dt)
    records = []
    price = 2650.0
    for i in range(n_bars):
        t = base_time + pd.Timedelta(minutes=15 * i)
        records.append({
            "time": t,
            "open": round(price, 2),
            "high": round(price + 2.5, 2),
            "low": round(price - 2.0, 2),
            "close": round(price + 0.8, 2),
            "tick_volume": 250,
            "spread": 18,
            "real_volume": 0,
        })
        price += 0.5
    return pd.DataFrame(records)


class TestDataQualityValidator:
    def test_valid_data_passes(self):
        """Verify that a compliant dataset receives PASSED status."""
        df = create_sample_ohlc_df(20)
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")

        assert report.status in ("PASSED", "PASSED_WITH_WARNINGS")
        assert report.total_rows == 20
        assert report.is_chronological is True
        assert report.duplicate_timestamps_count == 0
        assert report.invalid_ohlc_count == 0
        assert sum(report.missing_values_by_column.values()) == 0

    def test_detect_high_lower_than_open(self):
        """Violation: high < open must be flagged."""
        df = create_sample_ohlc_df(10)
        df.loc[3, "high"] = df.loc[3, "open"] - 1.0  # Invalid
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")

        assert report.status == "FAILED"
        assert report.invalid_ohlc_count == 1
        assert 3 in report.invalid_ohlc_indices

    def test_detect_high_lower_than_close(self):
        """Violation: high < close must be flagged."""
        df = create_sample_ohlc_df(10)
        df.loc[5, "high"] = df.loc[5, "close"] - 0.5  # Invalid
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")

        assert report.status == "FAILED"
        assert report.invalid_ohlc_count >= 1

    def test_detect_low_higher_than_open(self):
        """Violation: low > open must be flagged."""
        df = create_sample_ohlc_df(10)
        df.loc[2, "low"] = df.loc[2, "open"] + 1.0  # Invalid
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")

        assert report.status == "FAILED"
        assert report.invalid_ohlc_count >= 1

    def test_detect_low_higher_than_close(self):
        """Violation: low > close must be flagged."""
        df = create_sample_ohlc_df(10)
        df.loc[4, "low"] = df.loc[4, "close"] + 0.5  # Invalid
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")

        assert report.status == "FAILED"
        assert report.invalid_ohlc_count >= 1

    def test_detect_non_positive_price(self):
        """Violation: prices <= 0 or infinite must be flagged."""
        df = create_sample_ohlc_df(10)
        df.loc[1, "close"] = 0.0
        df.loc[7, "low"] = -5.0
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")

        assert report.status == "FAILED"
        assert report.invalid_ohlc_count == 2

    def test_detect_missing_values(self):
        """Missing values (NaN) must be detected and counted."""
        df = create_sample_ohlc_df(10)
        df.loc[2, "open"] = np.nan
        df.loc[4, "tick_volume"] = np.nan
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")

        assert report.status == "FAILED"
        assert report.missing_values_by_column["open"] == 1
        assert report.missing_values_by_column["tick_volume"] == 1

    def test_detect_duplicate_timestamps(self):
        """Duplicate candle timestamps must be identified."""
        df = create_sample_ohlc_df(10)
        # Duplicate row 3's timestamp into row 4
        df.loc[4, "time"] = df.loc[3, "time"]
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")

        assert report.status == "FAILED"
        assert report.duplicate_timestamps_count == 1

    def test_detect_non_chronological_ordering(self):
        """Out-of-order time sequence must be flagged."""
        df = create_sample_ohlc_df(10)
        # Swap row 2 and row 5
        t_temp = df.loc[2, "time"]
        df.loc[2, "time"] = df.loc[5, "time"]
        df.loc[5, "time"] = t_temp
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")

        assert report.status == "FAILED"
        assert report.is_chronological is False

    def test_gap_classification_weekend_vs_intraday(self):
        """Weekend gaps should be classified as expected; weekday gaps as abnormal."""
        # Create a Friday to Monday gap
        t_fri = pd.Timestamp("2026-03-06 21:00:00")  # Friday
        t_mon = pd.Timestamp("2026-03-08 22:00:00")  # Sunday night
        assert is_weekend_closure(t_fri, t_mon) is True

        # Midweek gap: Tuesday 10:00 to Tuesday 15:00
        t_tue1 = pd.Timestamp("2026-03-03 10:00:00")
        t_tue2 = pd.Timestamp("2026-03-03 15:00:00")
        assert is_weekend_closure(t_tue1, t_tue2) is False

    def test_report_export(self, tmp_path):
        """Report must save valid JSON and Markdown files."""
        df = create_sample_ohlc_df(15)
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")

        json_file = report.save_json(tmp_path / "report.json")
        md_file = report.save_markdown(tmp_path / "report.md")

        assert json_file.exists()
        assert md_file.exists()

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["symbol"] == "XAUUSD"
            assert data["total_rows"] == 15

        md_content = md_file.read_text(encoding="utf-8")
        assert "GoldFlow — Data Quality Report" in md_content
        assert "XAUUSD" in md_content

    def test_non_contiguous_index_validation(self):
        """
        Regression Test: Arbitrary/non-contiguous index labels must not cause KeyError.
        Labels [10, 25, 42, 99] with a time gap between row 1 and 2.
        """
        df = create_sample_ohlc_df(4)
        df.index = [10, 25, 42, 99]
        # Introduce a 2-hour intraday gap between second and third rows
        df.loc[42:, "time"] = df.loc[42:, "time"] + pd.Timedelta(hours=2)

        # Must execute cleanly without KeyError
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")
        assert report.total_rows == 4
        assert report.abnormal_gaps_count >= 1
        assert len(report.abnormal_gaps) >= 1
        assert "start_time" in report.abnormal_gaps[0]
        assert "end_time" in report.abnormal_gaps[0]

    def test_friday_daytime_outage_classification(self):
        """
        Regression Test: A daytime outage starting Friday morning (e.g. 10:00 UTC)
        must NOT be accepted as a normal weekend closure, even if it lasts >40 hours.
        """
        t_fri_day = pd.Timestamp("2026-03-06 10:00:00")  # Friday 10:00 AM (active London/NY session)
        t_sat_day = pd.Timestamp("2026-03-07 10:00:00")  # Saturday 10:00 AM (24 hours)
        t_sun_eve = pd.Timestamp("2026-03-08 22:00:00")  # Sunday 22:00 (60 hours)

        # Gap started during active trading, must be False (abnormal gap)
        assert is_weekend_closure(t_fri_day, t_sat_day) is False
        assert is_weekend_closure(t_fri_day, t_sun_eve) is False

        # Legitimate weekend closure: Friday 21:00 UTC to Sunday 22:00 UTC (49 hours)
        t_fri_close = pd.Timestamp("2026-03-06 21:00:00")
        assert is_weekend_closure(t_fri_close, t_sun_eve) is True

    def test_nan_prices_caught_in_ohlc_boundary_mask(self):
        """Verify that rows with NaN in OHLC columns are flagged under invalid OHLC boundaries."""
        df = create_sample_ohlc_df(6)
        df.loc[2, "high"] = np.nan
        df.loc[4, "open"] = np.nan
        report = validate_market_data(df, symbol="XAUUSD", timeframe="M15")

        assert report.invalid_ohlc_count >= 2
        assert 2 in report.invalid_ohlc_indices
        assert 4 in report.invalid_ohlc_indices
