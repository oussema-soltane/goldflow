"""
Deterministic Mock Data Ingestion Provider for GoldFlow.

Enables reproducible offline testing of ingestion, validation, vault storage,
and error-handling pipelines without external API dependencies or network calls.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.data.ingestion.base import (
    AuthenticationError,
    DataIngestionProvider,
    DataUnavailableError,
    RateLimitError,
)
from src.data.ingestion.models import RawTickObservation


class MockDataIngestionProvider(DataIngestionProvider):
    """
    Deterministic pseudo-random market data feed for XAUUSD research testing.
    
    Supports controllable anomaly injection to rigorously test the validation pipeline:
    - Crossed quotes (bid > ask)
    - Out-of-order timestamps
    - Duplicate timestamps
    - Non-positive or absurdly high prices
    - Intermittent time gaps
    - Authentication and rate-limit error simulation
    """

    def __init__(
        self,
        provider_name: str = "MOCK_ECN",
        seed: int = 42,
        base_price: float = 2650.0,
        typical_spread: float = 0.25,
        simulate_auth_failure: bool = False,
        simulate_rate_limit: bool = False,
    ) -> None:
        self._provider_name = provider_name
        self.seed = seed
        self.base_price = base_price
        self.typical_spread = typical_spread
        self.simulate_auth_failure = simulate_auth_failure
        self.simulate_rate_limit = simulate_rate_limit

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def is_authenticated(self) -> bool:
        return not self.simulate_auth_failure

    def get_instrument_specification(self, symbol: str) -> Dict[str, Any]:
        """Return canonical XAUUSD instrument specification."""
        if symbol.upper() not in ("XAUUSD", "GOLD"):
            raise DataUnavailableError(f"Symbol '{symbol}' not supported by {self.provider_name}.")
        return {
            "symbol": symbol.upper(),
            "provider": self.provider_name,
            "currency_base": "XAU",
            "currency_profit": "USD",
            "currency_margin": "USD",
            "digits": 2,
            "point": 0.01,
            "trade_contract_size": 100.0,
            "volume_min": 0.01,
            "volume_step": 0.01,
            "volume_max": 100.0,
            "trade_tick_size": 0.01,
            "trade_tick_value": 1.0,
            "spread_typical": self.typical_spread,
            "feed_type": "top_of_book_quotes",
        }

    def fetch_historical_ticks(
        self,
        symbol: str,
        start_time: dt.datetime,
        end_time: dt.datetime,
        tick_interval_ms: int = 1000,
        inject_crossed_quotes: int = 0,
        inject_out_of_order: int = 0,
        inject_duplicates: int = 0,
        inject_invalid_prices: int = 0,
    ) -> Tuple[List[RawTickObservation], Dict[str, Any]]:
        """
        Generate a deterministic sequence of historical ticks with optional anomaly injection.
        """
        if self.simulate_auth_failure:
            raise AuthenticationError(f"Failed to authenticate with {self.provider_name}: Invalid API token.")
        if self.simulate_rate_limit:
            raise RateLimitError(f"Rate limit exceeded on {self.provider_name}: 429 Too Many Requests.")

        # Ensure UTC datetimes
        start_ts = pd.to_datetime(start_time, utc=True)
        end_ts = pd.to_datetime(end_time, utc=True)

        if start_ts >= end_ts:
            raise ValueError(f"start_time ({start_ts}) must be strictly earlier than end_time ({end_ts}).")

        # Determine number of ticks based on interval
        delta_total_seconds = (end_ts - start_ts).total_seconds()
        n_ticks = max(1, int(delta_total_seconds * 1000 / tick_interval_ms))

        rng = np.random.default_rng(self.seed)

        # Generate timestamps
        timestamps = [
            start_ts + pd.Timedelta(milliseconds=i * tick_interval_ms)
            for i in range(n_ticks)
        ]

        # Generate price walk
        price = self.base_price
        bids: List[float] = []
        asks: List[float] = []
        volumes: List[float] = []

        for _ in range(n_ticks):
            # Random price increment
            step = rng.normal(0, 0.05)
            price = max(100.0, round(price + step, 2))
            half_spread = round(rng.uniform(0.08, 0.20), 2)
            bid = round(price - half_spread, 2)
            ask = round(price + half_spread, 2)
            vol = round(float(rng.uniform(0.1, 5.0)), 2)
            bids.append(bid)
            asks.append(ask)
            volumes.append(vol)

        ticks: List[RawTickObservation] = []
        for i in range(n_ticks):
            ticks.append(
                RawTickObservation(
                    timestamp_utc=timestamps[i],
                    symbol=symbol.upper(),
                    bid=bids[i],
                    ask=asks[i],
                    volume=volumes[i],
                    sequence_id=i + 1,
                    provider=self.provider_name,
                )
            )

        # Inject anomalies if requested
        if inject_crossed_quotes > 0 and len(ticks) > 10:
            for idx in rng.choice(range(5, len(ticks) - 1), size=min(inject_crossed_quotes, len(ticks) - 6), replace=False):
                bad_bid = ticks[idx].ask + 0.50
                ticks[idx] = RawTickObservation(
                    timestamp_utc=ticks[idx].timestamp_utc,
                    symbol=ticks[idx].symbol,
                    bid=bad_bid,
                    ask=ticks[idx].ask,
                    volume=ticks[idx].volume,
                    sequence_id=ticks[idx].sequence_id,
                    provider=ticks[idx].provider,
                    flags=1,
                )

        if inject_invalid_prices > 0 and len(ticks) > 10:
            for idx in rng.choice(range(5, len(ticks) - 1), size=min(inject_invalid_prices, len(ticks) - 6), replace=False):
                ticks[idx] = RawTickObservation(
                    timestamp_utc=ticks[idx].timestamp_utc,
                    symbol=ticks[idx].symbol,
                    bid=-25.0 if idx % 2 == 0 else 999999.0,
                    ask=2650.0,
                    volume=ticks[idx].volume,
                    sequence_id=ticks[idx].sequence_id,
                    provider=ticks[idx].provider,
                    flags=2,
                )

        if inject_duplicates > 0 and len(ticks) > 10:
            for idx in rng.choice(range(5, len(ticks) - 2), size=min(inject_duplicates, len(ticks) - 6), replace=False):
                # Duplicate the tick with identical timestamp
                dup_tick = RawTickObservation(
                    timestamp_utc=ticks[idx].timestamp_utc,
                    symbol=ticks[idx].symbol,
                    bid=ticks[idx].bid,
                    ask=ticks[idx].ask,
                    volume=ticks[idx].volume,
                    sequence_id=ticks[idx].sequence_id,
                    provider=ticks[idx].provider,
                )
                ticks.insert(idx + 1, dup_tick)

        if inject_out_of_order > 0 and len(ticks) > 10:
            for idx in rng.choice(range(5, len(ticks) - 3), size=min(inject_out_of_order, len(ticks) - 6), replace=False):
                # Swap two adjacent ticks to create non-monotonic order
                ticks[idx], ticks[idx + 1] = ticks[idx + 1], ticks[idx]

        metadata: Dict[str, Any] = {
            "provider": self.provider_name,
            "symbol": symbol.upper(),
            "start_time": start_ts.isoformat(),
            "end_time": end_ts.isoformat(),
            "requested_ticks": n_ticks,
            "generated_ticks": len(ticks),
            "seed": self.seed,
            "anomalies_injected": {
                "crossed_quotes": inject_crossed_quotes,
                "out_of_order": inject_out_of_order,
                "duplicates": inject_duplicates,
                "invalid_prices": inject_invalid_prices,
            },
        }
        return ticks, metadata

    def stream_incremental_ticks(
        self,
        symbol: str,
        max_ticks: Optional[int] = None,
    ) -> Iterator[RawTickObservation]:
        """
        Simulate real-time streaming of ticks with deterministic increments.
        """
        if self.simulate_auth_failure:
            raise AuthenticationError(f"Failed to authenticate with {self.provider_name}: Stream connection refused.")

        rng = np.random.default_rng(self.seed + 100)
        current_time = pd.Timestamp.now(tz="UTC")
        price = self.base_price
        count = 0

        while max_ticks is None or count < max_ticks:
            current_time = current_time + pd.Timedelta(milliseconds=500)
            step = rng.normal(0, 0.04)
            price = max(100.0, round(price + step, 2))
            half_spread = round(rng.uniform(0.10, 0.25), 2)
            bid = round(price - half_spread, 2)
            ask = round(price + half_spread, 2)
            count += 1

            yield RawTickObservation(
                timestamp_utc=current_time,
                symbol=symbol.upper(),
                bid=bid,
                ask=ask,
                volume=1.0,
                sequence_id=count,
                provider=self.provider_name,
            )

