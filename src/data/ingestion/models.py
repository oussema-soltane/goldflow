"""
Data Ingestion Models for GoldFlow.

Defines standardized, provider-neutral representations for raw tick observations,
aggregated bars, ingestion status codes, and batch metadata.

# Timestamp Provenance Policy (Phase 6D.1)
---------------------------------------------
Three timestamps are distinct and must not be conflated:

1. timestamp_utc / observation_time_utc
   The market event time — when the price quote occurred in the market.
   For historical archives this is in the past.

2. ingestion_time_utc
   The trusted GoldFlow receipt timestamp — when the data physically entered
   the GoldFlow pipeline from the provider.  For real-time feeds this is the
   socket arrival time.  For archived historical files this is the file
   *retrieval* time (when GoldFlow downloaded/opened the file), NOT the
   observation time.

   CRITICAL: ingestion_time_utc must NEVER be backdated to the observation time
   for historical data.  If the ingestion time is genuinely unknown (e.g. data
   arrived from an external archive with no retrieval receipt), preserve None
   explicitly rather than substituting the observation time.

3. provider_sequence_ts
   Optional provider-internal ordering timestamp or sequence number, if supplied.

The evaluation gate uses ingestion_time_utc (not timestamp_utc) to determine
whether data is forward-eligible.  Fabricating ingestion_time_utc from
observation_time_utc would allow historical data to pass as newly acquired data.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Union

import numpy as np
import pandas as pd


class IngestionStatus(str, Enum):
    """Standardized operational status for data ingestion batches."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"


class DatasetClassification(str, Enum):
    """
    Classification of a dataset's temporal relationship to the GoldFlow pipeline.

    HISTORICAL_ARCHIVE : Data retrieved from an external archive after the fact.
        ingestion_time_utc reflects the retrieval time, NOT the observation time.
    FORWARD_REAL_TIME  : Data received in real time as observations occur.
        ingestion_time_utc ≈ timestamp_utc (within provider latency).
    UNKNOWN            : Classification cannot be determined from available metadata.
    """
    HISTORICAL_ARCHIVE = "HISTORICAL_ARCHIVE"
    FORWARD_REAL_TIME = "FORWARD_REAL_TIME"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RawTickObservation:
    """
    Standardized raw tick observation representing a market quote or trade.

    All timestamps must be strictly UTC-aware where set.

    Timestamp semantics
    -------------------
    - timestamp_utc        : Market observation time (when the price occurred).
    - observation_time_utc : Alias / provider-reported observation time.
    - ingestion_time_utc   : GoldFlow pipeline receipt time.  For historical
                             archives this is the FILE RETRIEVAL TIME, not the
                             observation time.  May be None when unknown.
                             MUST NOT be defaulted to observation_time_utc.
    - provider_sequence_ts : Provider-internal ordering reference (optional).

    Volume semantics
    ----------------
    - volume     : Ask-side volume from the provider feed.
    - bid_volume : Bid-side volume from the provider feed.
    Neither field represents exchange-traded contract volume unless the provider
    explicitly documents it as such.  Do not equate provider volume with
    exchange-cleared notional.
    """
    timestamp_utc: pd.Timestamp
    symbol: str
    bid: float
    ask: float
    volume: float = 1.0          # ask-side volume (provider feed)
    bid_volume: float = 0.0      # bid-side volume (provider feed) — Phase 6D.1 fix
    sequence_id: Optional[int] = None
    provider: str = "UNKNOWN"
    flags: int = 0
    observation_time_utc: Optional[pd.Timestamp] = None
    ingestion_time_utc: Optional[pd.Timestamp] = None   # None = unknown, do NOT default to obs time
    provider_sequence_ts: Optional[pd.Timestamp] = None
    dataset_classification: DatasetClassification = DatasetClassification.UNKNOWN

    def __post_init__(self) -> None:
        # Enforce UTC timezone awareness on timestamp_utc
        if not isinstance(self.timestamp_utc, pd.Timestamp):
            ts = pd.to_datetime(self.timestamp_utc, utc=True, format="ISO8601")
            object.__setattr__(self, "timestamp_utc", ts)
        elif self.timestamp_utc.tzinfo is None:
            ts = self.timestamp_utc.tz_localize("UTC")
            object.__setattr__(self, "timestamp_utc", ts)
        elif str(self.timestamp_utc.tz) != "UTC":
            ts = self.timestamp_utc.tz_convert("UTC")
            object.__setattr__(self, "timestamp_utc", ts)

        # Observation time defaults to timestamp_utc (same event, different label)
        obs_ts = self.observation_time_utc or self.timestamp_utc
        if not isinstance(obs_ts, pd.Timestamp):
            obs_ts = pd.to_datetime(obs_ts, utc=True, format="ISO8601")
        elif obs_ts.tzinfo is None:
            obs_ts = obs_ts.tz_localize("UTC")
        elif str(obs_ts.tz) != "UTC":
            obs_ts = obs_ts.tz_convert("UTC")
        object.__setattr__(self, "observation_time_utc", obs_ts)

        # Phase 6D.1 FIX: ingestion_time_utc must NOT default to observation_time_utc.
        # For historical archives the observation time and ingestion time are completely
        # different: a tick from 2025 downloaded in 2026 must have ingestion_time=2026.
        # If ingestion time is genuinely unknown, preserve None. The evaluation gate
        # interprets None as "ingestion time unknown" and applies conservative policy.
        if self.ingestion_time_utc is not None:
            ingest_ts = self.ingestion_time_utc
            if not isinstance(ingest_ts, pd.Timestamp):
                ingest_ts = pd.to_datetime(ingest_ts, utc=True, format="ISO8601")
            elif ingest_ts.tzinfo is None:
                ingest_ts = ingest_ts.tz_localize("UTC")
            elif str(ingest_ts.tz) != "UTC":
                ingest_ts = ingest_ts.tz_convert("UTC")
            object.__setattr__(self, "ingestion_time_utc", ingest_ts)
        # else: leave as None — do NOT substitute observation_time_utc

    @property
    def has_known_ingestion_time(self) -> bool:
        """True if ingestion_time_utc is set (not None)."""
        return self.ingestion_time_utc is not None

    @property
    def spread(self) -> float:
        """Bid-Ask spread in price units ($/oz)."""
        return round(self.ask - self.bid, 5)

    @property
    def mid(self) -> float:
        """Mid-market price."""
        return round((self.ask + self.bid) / 2.0, 5)

    @property
    def is_crossed(self) -> bool:
        """Return True if bid > ask or negative spread."""
        return self.bid > self.ask

    def to_dict(self) -> Dict[str, Any]:
        """Convert observation to primitive dictionary."""
        return {
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "observation_time_utc": self.observation_time_utc.isoformat() if self.observation_time_utc is not None else None,
            # Phase 6D.1: ingestion_time_utc is None when unknown — preserve that honestly
            "ingestion_time_utc": self.ingestion_time_utc.isoformat() if self.ingestion_time_utc is not None else None,
            "provider_sequence_ts": self.provider_sequence_ts.isoformat() if self.provider_sequence_ts is not None else None,
            "has_known_ingestion_time": self.has_known_ingestion_time,
            "dataset_classification": self.dataset_classification.value,
            "symbol": self.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "spread": self.spread,
            "mid": self.mid,
            "volume": self.volume,         # ask-side volume (provider feed)
            "bid_volume": self.bid_volume, # bid-side volume (provider feed)
            "sequence_id": self.sequence_id,
            "provider": self.provider,
            "flags": self.flags,
        }


@dataclass(frozen=True)
class AggregatedBar:
    """
    Standardized aggregated candlestick bar (e.g. M1) synthesized from raw ticks.

    The bar interval covers [timestamp_utc, timestamp_utc + interval_duration).
    """
    timestamp_utc: pd.Timestamp
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    volume: float
    spread_open: float
    spread_close: float
    spread_min: float
    spread_max: float
    spread_mean: float
    tick_count: int
    is_incomplete: bool = False
    first_sequence_id: Optional[int] = None
    last_sequence_id: Optional[int] = None
    price_source: str = "bid"

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp_utc, pd.Timestamp):
            ts = pd.to_datetime(self.timestamp_utc, utc=True, format="ISO8601")
            object.__setattr__(self, "timestamp_utc", ts)
        elif self.timestamp_utc.tzinfo is None:
            ts = self.timestamp_utc.tz_localize("UTC")
            object.__setattr__(self, "timestamp_utc", ts)
        elif str(self.timestamp_utc.tz) != "UTC":
            ts = self.timestamp_utc.tz_convert("UTC")
            object.__setattr__(self, "timestamp_utc", ts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert bar to primitive dictionary."""
        return {
            "time": self.timestamp_utc.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "tick_volume": self.tick_volume,
            "real_volume": self.volume,
            "spread": round(self.spread_mean, 5),
            "spread_open": self.spread_open,
            "spread_close": self.spread_close,
            "spread_min": self.spread_min,
            "spread_max": self.spread_max,
            "spread_mean": self.spread_mean,
            "tick_count": self.tick_count,
            "is_incomplete": self.is_incomplete,
            "first_sequence_id": self.first_sequence_id,
            "last_sequence_id": self.last_sequence_id,
            "price_source": self.price_source,
        }


@dataclass
class IngestionBatchMetadata:
    """
    Metadata recording provenance and audit details for an ingestion batch.
    """
    batch_id: str
    provider: str
    symbol: str
    retrieval_time_utc: str
    start_time: Optional[str]
    end_time: Optional[str]
    raw_tick_count: int
    valid_tick_count: int
    rejected_tick_count: int
    partition_path: Optional[str] = None
    partition_sha256: Optional[str] = None
    status: IngestionStatus = IngestionStatus.SUCCESS
    error_message: Optional[str] = None
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    custom_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        data = asdict(self)
        data["status"] = self.status.value
        return data



@dataclass(frozen=True)
class AggregatedBar:
    """
    Standardized aggregated candlestick bar (e.g. M1) synthesized from raw ticks.
    
    The bar interval covers [timestamp_utc, timestamp_utc + interval_duration).
    """
    timestamp_utc: pd.Timestamp
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    volume: float
    spread_open: float
    spread_close: float
    spread_min: float
    spread_max: float
    spread_mean: float
    tick_count: int
    is_incomplete: bool = False
    first_sequence_id: Optional[int] = None
    last_sequence_id: Optional[int] = None
    price_source: str = "bid"

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp_utc, pd.Timestamp):
            ts = pd.to_datetime(self.timestamp_utc, utc=True, format="ISO8601")
            object.__setattr__(self, "timestamp_utc", ts)
        elif self.timestamp_utc.tzinfo is None:
            ts = self.timestamp_utc.tz_localize("UTC")
            object.__setattr__(self, "timestamp_utc", ts)
        elif str(self.timestamp_utc.tz) != "UTC":
            ts = self.timestamp_utc.tz_convert("UTC")
            object.__setattr__(self, "timestamp_utc", ts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert bar to primitive dictionary."""
        return {
            "time": self.timestamp_utc.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "tick_volume": self.tick_volume,
            "real_volume": self.volume,
            "spread": round(self.spread_mean, 5),
            "spread_open": self.spread_open,
            "spread_close": self.spread_close,
            "spread_min": self.spread_min,
            "spread_max": self.spread_max,
            "spread_mean": self.spread_mean,
            "tick_count": self.tick_count,
            "is_incomplete": self.is_incomplete,
            "first_sequence_id": self.first_sequence_id,
            "last_sequence_id": self.last_sequence_id,
            "price_source": self.price_source,
        }


@dataclass
class IngestionBatchMetadata:
    """
    Metadata recording provenance and audit details for an ingestion batch.
    """
    batch_id: str
    provider: str
    symbol: str
    retrieval_time_utc: str
    start_time: Optional[str]
    end_time: Optional[str]
    raw_tick_count: int
    valid_tick_count: int
    rejected_tick_count: int
    partition_path: Optional[str] = None
    partition_sha256: Optional[str] = None
    status: IngestionStatus = IngestionStatus.SUCCESS
    error_message: Optional[str] = None
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    custom_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        data = asdict(self)
        data["status"] = self.status.value
        return data
