"""
Unit & Integration Tests for GoldFlow Phase 6A Data Ingestion & M1 Bar Synthesis.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from src.data.ingestion.base import (
    AuthenticationError,
    DataUnavailableError,
    RateLimitError,
)
from src.data.ingestion.bar_builder import M1BarBuilder, synthesize_m1_bars
from src.data.ingestion.mock_provider import MockDataIngestionProvider
from src.data.ingestion.models import (
    AggregatedBar,
    IngestionStatus,
    RawTickObservation,
)
from src.data.ingestion.validator import (
    TickDataValidator,
    validate_and_canonicalize_ticks,
)


class TestRawTickObservation:
    """Test raw tick data representation and integrity constraints."""

    def test_utc_timezone_enforcement(self) -> None:
        # Naive datetime localized to UTC
        naive_dt = dt.datetime(2026, 10, 28, 12, 0, 0)
        tick = RawTickObservation(
            timestamp_utc=naive_dt,
            symbol="XAUUSD",
            bid=2650.10,
            ask=2650.35,
        )
        assert tick.timestamp_utc.tzinfo is not None
        assert str(tick.timestamp_utc.tz) == "UTC"
        assert tick.spread == 0.25
        assert tick.mid == 2650.225
        assert not tick.is_crossed

    def test_crossed_quote_property(self) -> None:
        tick = RawTickObservation(
            timestamp_utc=pd.Timestamp("2026-10-28 12:00:00", tz="UTC"),
            symbol="XAUUSD",
            bid=2651.00,
            ask=2650.00,
        )
        assert tick.is_crossed
        assert tick.spread == -1.00

    def test_serialization(self) -> None:
        tick = RawTickObservation(
            timestamp_utc=pd.Timestamp("2026-10-28 12:00:00", tz="UTC"),
            symbol="XAUUSD",
            bid=2650.00,
            ask=2650.25,
            volume=2.5,
            sequence_id=42,
            provider="TEST_ECN",
        )
        data = tick.to_dict()
        assert data["symbol"] == "XAUUSD"
        assert data["bid"] == 2650.00
        assert data["ask"] == 2650.25
        assert data["volume"] == 2.5
        assert data["sequence_id"] == 42
        assert data["provider"] == "TEST_ECN"


class TestMockDataIngestionProvider:
    """Test mock feed generator and anomaly injection capabilities."""

    def test_deterministic_generation(self) -> None:
        provider1 = MockDataIngestionProvider(seed=123)
        provider2 = MockDataIngestionProvider(seed=123)

        start = dt.datetime(2026, 10, 28, 10, 0, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 10, 28, 10, 5, 0, tzinfo=dt.timezone.utc)

        ticks1, meta1 = provider1.fetch_historical_ticks("XAUUSD", start, end, tick_interval_ms=1000)
        ticks2, meta2 = provider2.fetch_historical_ticks("XAUUSD", start, end, tick_interval_ms=1000)

        assert len(ticks1) == len(ticks2)
        assert len(ticks1) == 300
        assert [t.bid for t in ticks1] == [t.bid for t in ticks2]
        assert meta1["seed"] == 123

    def test_instrument_specification(self) -> None:
        provider = MockDataIngestionProvider()
        spec = provider.get_instrument_specification("XAUUSD")
        assert spec["symbol"] == "XAUUSD"
        assert spec["trade_contract_size"] == 100.0
        assert spec["currency_profit"] == "USD"
        assert spec["point"] == 0.01

        with pytest.raises(DataUnavailableError):
            provider.get_instrument_specification("EURUSD")

    def test_authentication_and_rate_limit_simulation(self) -> None:
        auth_failed_provider = MockDataIngestionProvider(simulate_auth_failure=True)
        assert not auth_failed_provider.is_authenticated()

        start = dt.datetime(2026, 10, 28, 10, 0, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 10, 28, 10, 1, 0, tzinfo=dt.timezone.utc)

        with pytest.raises(AuthenticationError):
            auth_failed_provider.fetch_historical_ticks("XAUUSD", start, end)

        rate_limited_provider = MockDataIngestionProvider(simulate_rate_limit=True)
        with pytest.raises(RateLimitError):
            rate_limited_provider.fetch_historical_ticks("XAUUSD", start, end)

    def test_anomaly_injection(self) -> None:
        provider = MockDataIngestionProvider(seed=42)
        start = dt.datetime(2026, 10, 28, 10, 0, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 10, 28, 10, 2, 0, tzinfo=dt.timezone.utc)

        ticks, meta = provider.fetch_historical_ticks(
            "XAUUSD",
            start,
            end,
            tick_interval_ms=1000,
            inject_crossed_quotes=3,
            inject_invalid_prices=2,
            inject_duplicates=2,
            inject_out_of_order=2,
        )

        crossed = [t for t in ticks if t.is_crossed]
        assert len(crossed) >= 3

        invalid = [t for t in ticks if t.bid < 0 or t.bid > 10000.0]
        assert len(invalid) >= 2

    def test_streaming_generation(self) -> None:
        provider = MockDataIngestionProvider(seed=99)
        stream = provider.stream_incremental_ticks("XAUUSD", max_ticks=10)
        ticks = list(stream)
        assert len(ticks) == 10
        assert all(t.symbol == "XAUUSD" for t in ticks)


class TestTickDataValidator:
    """Test validation pipeline filtering and anomaly isolation."""

    def test_clean_ticks_validation(self) -> None:
        provider = MockDataIngestionProvider(seed=42)
        start = dt.datetime(2026, 10, 28, 10, 0, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 10, 28, 10, 5, 0, tzinfo=dt.timezone.utc)
        raw_ticks, _ = provider.fetch_historical_ticks("XAUUSD", start, end)

        cleaned_df, report = validate_and_canonicalize_ticks(raw_ticks)
        assert report.total_input == 300
        assert report.valid_count == 300
        assert report.dropped_count == 0
        assert len(cleaned_df) == 300
        assert cleaned_df["timestamp_utc"].is_monotonic_increasing

    def test_crossed_quotes_rejection(self) -> None:
        provider = MockDataIngestionProvider(seed=42)
        start = dt.datetime(2026, 10, 28, 10, 0, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 10, 28, 10, 2, 0, tzinfo=dt.timezone.utc)
        raw_ticks, _ = provider.fetch_historical_ticks("XAUUSD", start, end, inject_crossed_quotes=4)

        cleaned_df, report = validate_and_canonicalize_ticks(raw_ticks)
        assert report.crossed_quotes >= 4
        assert report.dropped_count >= 4
        # Assert no crossed quotes remain in cleaned DataFrame
        assert (cleaned_df["bid"] > cleaned_df["ask"]).sum() == 0

    def test_duplicates_and_out_of_order_handling(self) -> None:
        provider = MockDataIngestionProvider(seed=42)
        start = dt.datetime(2026, 10, 28, 10, 0, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 10, 28, 10, 3, 0, tzinfo=dt.timezone.utc)
        raw_ticks, _ = provider.fetch_historical_ticks(
            "XAUUSD",
            start,
            end,
            inject_duplicates=5,
            inject_out_of_order=3,
        )

        cleaned_df, report = validate_and_canonicalize_ticks(raw_ticks)
        assert report.duplicates_dropped >= 5
        assert report.out_of_order >= 1
        # Result must be strictly monotonic
        assert cleaned_df["timestamp_utc"].is_monotonic_increasing
        # Duplicates removed
        assert not cleaned_df.duplicated(subset=["timestamp_utc", "bid", "ask"]).any()


class TestM1BarBuilder:
    """Test deterministic M1 bar aggregation without artificial interpolation."""

    def test_left_closed_right_open_aggregation(self) -> None:
        ticks = [
            # Bar 10:00: [10:00:00, 10:01:00)
            RawTickObservation(pd.Timestamp("2026-10-28 10:00:00.000", tz="UTC"), "XAUUSD", bid=2650.0, ask=2650.2, volume=1.0),
            RawTickObservation(pd.Timestamp("2026-10-28 10:00:15.500", tz="UTC"), "XAUUSD", bid=2652.5, ask=2652.7, volume=2.0),
            RawTickObservation(pd.Timestamp("2026-10-28 10:00:59.999", tz="UTC"), "XAUUSD", bid=2649.0, ask=2649.3, volume=1.5),
            # Bar 10:01: [10:01:00, 10:02:00)
            RawTickObservation(pd.Timestamp("2026-10-28 10:01:00.000", tz="UTC"), "XAUUSD", bid=2651.0, ask=2651.3, volume=1.0),
            RawTickObservation(pd.Timestamp("2026-10-28 10:01:30.000", tz="UTC"), "XAUUSD", bid=2653.0, ask=2653.3, volume=3.0),
        ]

        bars, bar_df = synthesize_m1_bars(ticks, price_source="bid")
        assert len(bars) == 2
        assert len(bar_df) == 2

        # Verify Bar 1 (10:00)
        b1 = bars[0]
        assert b1.timestamp_utc == pd.Timestamp("2026-10-28 10:00:00", tz="UTC")
        assert b1.open == 2650.0
        assert b1.high == 2652.5
        assert b1.low == 2649.0
        assert b1.close == 2649.0
        assert b1.tick_volume == 3
        assert b1.volume == 4.5
        assert b1.spread_open == 0.2
        assert b1.spread_close == 0.3

        # Verify Bar 2 (10:01)
        b2 = bars[1]
        assert b2.timestamp_utc == pd.Timestamp("2026-10-28 10:01:00", tz="UTC")
        assert b2.open == 2651.0
        assert b2.high == 2653.0
        assert b2.low == 2651.0
        assert b2.close == 2653.0
        assert b2.tick_volume == 2
        assert b2.volume == 4.0

    def test_no_interpolation_across_gaps(self) -> None:
        # Tick at 10:00, then gap of 15 minutes, tick at 10:15
        ticks = [
            RawTickObservation(pd.Timestamp("2026-10-28 10:00:10", tz="UTC"), "XAUUSD", bid=2650.0, ask=2650.2),
            RawTickObservation(pd.Timestamp("2026-10-28 10:15:20", tz="UTC"), "XAUUSD", bid=2655.0, ask=2655.2),
        ]

        bars, bar_df = synthesize_m1_bars(ticks)
        # Exactly 2 bars; zero phantom bars created in between
        assert len(bars) == 2
        assert bars[0].timestamp_utc == pd.Timestamp("2026-10-28 10:00:00", tz="UTC")
        assert bars[1].timestamp_utc == pd.Timestamp("2026-10-28 10:15:00", tz="UTC")

