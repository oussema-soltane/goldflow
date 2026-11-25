"""
Provider-Neutral Dukascopy BI5 Binary Tick Decoder for GoldFlow.

Parses Dukascopy .bi5 LZMA-compressed binary files containing 20-byte big-endian
tick records (>IIIff), enforces strict UTC timestamp normalization, validates
decompression and record integrity, tracks record provenance and SHA-256 hashes,
and fails closed on unverified price scales.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
from enum import Enum
import hashlib
import logging
import lzma
import math
from pathlib import Path
import re
import struct
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from src.data.ingestion.instrument_spec import (
    ProviderInstrumentSpec,
    UnverifiedPriceScaleError,
)
from src.data.ingestion.models import DatasetClassification, RawTickObservation
from src.data.ingestion.validator import ValidationAuditReport

logger = logging.getLogger(__name__)

# Canonical Decoder Version
BI5_DECODER_VERSION = "1.0.0"

# Fixed Dukascopy Record Size (20 bytes: uint32, uint32, uint32, float32, float32)
BI5_RECORD_SIZE = 20
BI5_STRUCT_FORMAT = ">3I2f"  # Equivalent to >IIIff


class Bi5FileLayout(str, Enum):
    """File layout type defining the base timestamp anchor."""
    HOURLY = "HOURLY"  # Offset milliseconds from UTC hour boundary (0 to 3,599,999 ms)
    DAILY = "DAILY"    # Offset milliseconds from UTC day boundary (0 to 86,399,999 ms)


class Bi5DecoderError(Exception):
    """Base exception for BI5 decoding errors."""
    pass


class DecompressionError(Bi5DecoderError):
    """Raised when LZMA decompression fails."""
    pass


class InvalidPayloadLengthError(Bi5DecoderError):
    """Raised when decompressed byte length is not an exact multiple of 20 bytes."""
    pass


class AmbiguousLayoutError(Bi5DecoderError):
    """Raised when file layout (hourly vs daily) cannot be reliably determined."""
    pass


class CorruptedRecordError(Bi5DecoderError):
    """Raised when a record violates fundamental physical invariants."""
    pass


@dataclass(frozen=True)
class Bi5DecodedBatch:
    """
    Standardized result of a decoded BI5 file or byte stream.
    """
    observations: List[RawTickObservation]
    record_count: int
    source_file_sha256: str
    decoder_version: str
    file_layout: Bi5FileLayout
    base_timestamp_utc: pd.Timestamp
    instrument_spec: ProviderInstrumentSpec
    validation_report: ValidationAuditReport
    raw_compressed_bytes: Optional[bytes] = None
    decompressed_byte_length: int = 0
    source_path: Optional[str] = None


class DukascopyBi5Decoder:
    """
    Deterministic decoder for Dukascopy .bi5 compressed binary tick archives.
    
    Supports:
    - 20-byte big-endian record decoding (>3I2f / >IIIff).
    - Hourly and Daily layout anchors with strict boundary checks.
    - Zero-based month path extraction for Dukascopy CDN URLs.
    - Fail-closed price scale enforcement via ProviderInstrumentSpec.
    - Full record-level integrity checks (finite volume, positive prices, crossed quotes).
    """

    def __init__(
        self,
        instrument_spec: ProviderInstrumentSpec,
        allow_unverified_scale: bool = False,
    ) -> None:
        """
        Initialize the decoder with an explicit instrument specification.
        
        Parameters
        ----------
        instrument_spec : ProviderInstrumentSpec
            Specification defining scale, tick size, and verification status.
        allow_unverified_scale : bool
            Must be set to True to decode synthetic or unverified test feeds.
            If False and spec is not VERIFIED, initialization or decoding fails closed.
        """
        self.instrument_spec = instrument_spec
        self.allow_unverified_scale = allow_unverified_scale
        
        # Verify specification eligibility
        self.instrument_spec.validate_for_decoding(allow_unverified=self.allow_unverified_scale)

    @classmethod
    def parse_path_layout(
        cls,
        file_path: Union[str, Path],
    ) -> Tuple[str, pd.Timestamp, Bi5FileLayout]:
        """
        Extract symbol, UTC base timestamp, and file layout from a standard Dukascopy path.
        
        Supports two standard layouts:
        1. Hourly: .../{SYMBOL}/YYYY/MM/DD/{HH}h_ticks.bi5
           (Note: Month MM is 0-indexed in Dukascopy paths: 00 = Jan, 09 = Oct, 11 = Dec).
        2. Daily: .../{SYMBOL}/YYYY/MM/{DD}_ticks.bi5 or .../{SYMBOL}/YYYY/MM/DD_ticks.bi5
        
        Raises AmbiguousLayoutError if the layout cannot be deterministically inferred.
        """
        path_str = str(file_path).replace("\\", "/")
        
        # Pattern 1: Hourly (.../SYMBOL/YYYY/MM/DD/HHh_ticks.bi5)
        hourly_pattern = re.compile(
            r"(?P<symbol>[A-Za-z0-9_]+)/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/(?P<hour>\d{2})h_ticks\.bi5$",
            re.IGNORECASE,
        )
        m_hourly = hourly_pattern.search(path_str)
        if m_hourly:
            sym = m_hourly.group("symbol")
            year = int(m_hourly.group("year"))
            # Dukascopy month is 0-indexed! 00 = Jan, 11 = Dec
            month = int(m_hourly.group("month")) + 1
            day = int(m_hourly.group("day"))
            hour = int(m_hourly.group("hour"))
            
            if month < 1 or month > 12:
                raise AmbiguousLayoutError(f"Invalid zero-indexed month index '{m_hourly.group('month')}' in path: {file_path}")
            if hour < 0 or hour > 23:
                raise AmbiguousLayoutError(f"Invalid hour index '{hour}' in path: {file_path}")

            base_ts = pd.Timestamp(
                year=year, month=month, day=day, hour=hour, minute=0, second=0, tz="UTC"
            )
            return sym, base_ts, Bi5FileLayout.HOURLY

        # Pattern 2: Daily (.../SYMBOL/YYYY/MM/DD_ticks.bi5)
        daily_pattern = re.compile(
            r"(?P<symbol>[A-Za-z0-9_]+)/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})_ticks\.bi5$",
            re.IGNORECASE,
        )
        m_daily = daily_pattern.search(path_str)
        if m_daily:
            sym = m_daily.group("symbol")
            year = int(m_daily.group("year"))
            month = int(m_daily.group("month")) + 1
            day = int(m_daily.group("day"))
            
            if month < 1 or month > 12:
                raise AmbiguousLayoutError(f"Invalid zero-indexed month index in path: {file_path}")

            base_ts = pd.Timestamp(
                year=year, month=month, day=day, hour=0, minute=0, second=0, tz="UTC"
            )
            return sym, base_ts, Bi5FileLayout.DAILY

        raise AmbiguousLayoutError(
            f"Cannot deterministically infer Dukascopy file layout from path: '{file_path}'. "
            f"Expected hourly '.../YYYY/MM/DD/HHh_ticks.bi5' or daily '.../YYYY/MM/DD_ticks.bi5'. "
            f"Specify base_timestamp_utc and file_layout explicitly."
        )

    def decode_file(
        self,
        file_path: Union[str, Path],
        layout: Optional[Bi5FileLayout] = None,
        base_timestamp_utc: Optional[pd.Timestamp] = None,
        preserve_compressed_bytes: bool = True,
    ) -> Bi5DecodedBatch:
        """
        Read and decode a local .bi5 file.
        
        If layout or base_timestamp_utc are not provided, attempts to infer them from the path.
        """
        path_obj = Path(file_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"BI5 file not found: {path_obj}")

        if layout is None or base_timestamp_utc is None:
            _, inferred_ts, inferred_layout = self.parse_path_layout(path_obj)
            base_timestamp_utc = base_timestamp_utc or inferred_ts
            layout = layout or inferred_layout

        with open(path_obj, "rb") as f:
            raw_bytes = f.read()

        batch = self.decode_bytes(
            raw_compressed_bytes=raw_bytes,
            layout=layout,
            base_timestamp_utc=base_timestamp_utc,
            preserve_compressed_bytes=preserve_compressed_bytes,
            source_path=str(path_obj.resolve()),
        )
        return batch

    def decode_bytes(
        self,
        raw_compressed_bytes: bytes,
        layout: Bi5FileLayout,
        base_timestamp_utc: pd.Timestamp,
        preserve_compressed_bytes: bool = True,
        source_path: Optional[str] = None,
    ) -> Bi5DecodedBatch:
        """
        Decompress and decode raw BI5 bytes in memory.
        
        Parameters
        ----------
        raw_compressed_bytes : bytes
            Raw LZMA-compressed byte stream.
        layout : Bi5FileLayout
            Layout anchor (HOURLY or DAILY).
        base_timestamp_utc : pd.Timestamp
            Anchor timestamp in UTC.
        preserve_compressed_bytes : bool
            Whether to retain the original compressed bytes in the return batch.
        source_path : Optional[str]
            Optional path or origin identifier.
        """
        # 1. Enforce price scale verification check
        self.instrument_spec.validate_for_decoding(allow_unverified=self.allow_unverified_scale)

        # 2. Compute SHA-256 of the raw compressed bytes before any processing
        source_sha256 = hashlib.sha256(raw_compressed_bytes).hexdigest()

        # Enforce UTC timezone on base_timestamp_utc
        if not isinstance(base_timestamp_utc, pd.Timestamp):
            base_ts = pd.to_datetime(base_timestamp_utc, utc=True)
        elif base_timestamp_utc.tzinfo is None:
            base_ts = base_timestamp_utc.tz_localize("UTC")
        elif str(base_timestamp_utc.tz) != "UTC":
            base_ts = base_timestamp_utc.tz_convert("UTC")
        else:
            base_ts = base_timestamp_utc

        # 3. Handle empty payload (e.g. 0-byte file during market closure)
        if len(raw_compressed_bytes) == 0:
            return Bi5DecodedBatch(
                observations=[],
                record_count=0,
                source_file_sha256=source_sha256,
                decoder_version=BI5_DECODER_VERSION,
                file_layout=layout,
                base_timestamp_utc=base_ts,
                instrument_spec=self.instrument_spec,
                validation_report=ValidationAuditReport(total_input=0, valid_count=0),
                raw_compressed_bytes=raw_compressed_bytes if preserve_compressed_bytes else None,
                decompressed_byte_length=0,
                source_path=source_path,
            )

        # 4. Decompress LZMA stream
        try:
            decompressed_data = lzma.decompress(raw_compressed_bytes)
        except lzma.LZMAError as exc:
            raise DecompressionError(
                f"Failed to decompress BI5 LZMA stream (SHA-256: {source_sha256[:16]}...): {exc}"
            ) from exc

        decomp_len = len(decompressed_data)

        # Empty decompressed stream (zero ticks in archive)
        if decomp_len == 0:
            return Bi5DecodedBatch(
                observations=[],
                record_count=0,
                source_file_sha256=source_sha256,
                decoder_version=BI5_DECODER_VERSION,
                file_layout=layout,
                base_timestamp_utc=base_ts,
                instrument_spec=self.instrument_spec,
                validation_report=ValidationAuditReport(total_input=0, valid_count=0),
                raw_compressed_bytes=raw_compressed_bytes if preserve_compressed_bytes else None,
                decompressed_byte_length=0,
                source_path=source_path,
            )

        # 5. Strict Payload Length Validation (No unexplained trailing bytes!)
        if decomp_len % BI5_RECORD_SIZE != 0:
            trailing = decomp_len % BI5_RECORD_SIZE
            records = decomp_len // BI5_RECORD_SIZE
            raise InvalidPayloadLengthError(
                f"CORRUPTED BI5 PAYLOAD: Decompressed size is {decomp_len} bytes, which is not an exact "
                f"multiple of 20 bytes ({records} complete records, {trailing} trailing bytes). "
                f"Payload is truncated or malformed."
            )

        num_records = decomp_len // BI5_RECORD_SIZE

        # Maximum permitted timestamp offset based on layout
        max_offset_ms = 3_600_000 if layout == Bi5FileLayout.HOURLY else 86_400_000

        observations: List[RawTickObservation] = []
        val_report = ValidationAuditReport(total_input=num_records)

        price_scale = self.instrument_spec.price_scale
        digits = self.instrument_spec.digits
        canonical_sym = self.instrument_spec.canonical_symbol

        prev_offset_ms: Optional[int] = None
        # Phase 6D.1: Explicit Event Fingerprint Set for Duplicate Detection.
        # Catches both adjacent and non-adjacent identical duplicate records within the file.
        # Legitimate distinct events sharing a timestamp (e.g. different price or volume)
        # have different fingerprints and are preserved.
        # Memory footprint: ~8MB for 100k ticks.
        seen_event_fingerprints: set = set()

        # 6. Unpack and Validate 20-Byte Records
        for record_idx in range(num_records):
            offset_start = record_idx * BI5_RECORD_SIZE
            chunk = decompressed_data[offset_start : offset_start + BI5_RECORD_SIZE]
            
            # Big-endian unpack: 3 uint32 + 2 float32
            offset_ms, raw_ask, raw_bid, ask_vol, bid_vol = struct.unpack(
                BI5_STRUCT_FORMAT, chunk
            )

            # Check 1: Offset boundary check
            if offset_ms < 0 or offset_ms >= max_offset_ms:
                val_report.dropped_count += 1
                val_report.out_of_order += 1
                val_report.rejections.append({
                    "record_idx": record_idx,
                    "reason": "INVALID_TIMESTAMP_OFFSET",
                    "offset_ms": offset_ms,
                    "max_offset_ms": max_offset_ms,
                })
                continue

            # Check 2: Finite and non-negative volume
            if not math.isfinite(ask_vol) or not math.isfinite(bid_vol) or ask_vol < 0.0 or bid_vol < 0.0:
                val_report.dropped_count += 1
                val_report.invalid_prices += 1
                val_report.rejections.append({
                    "record_idx": record_idx,
                    "reason": "NON_FINITE_OR_NEGATIVE_VOLUME",
                    "ask_vol": ask_vol,
                    "bid_vol": bid_vol,
                })
                continue

            # Check 3: Valid raw prices (must be strictly positive integers)
            if raw_ask <= 0 or raw_bid <= 0:
                val_report.dropped_count += 1
                val_report.invalid_prices += 1
                val_report.rejections.append({
                    "record_idx": record_idx,
                    "reason": "NON_POSITIVE_RAW_PRICE",
                    "raw_ask": raw_ask,
                    "raw_bid": raw_bid,
                })
                continue

            # Price scaling
            ask_price = round(raw_ask / price_scale, digits)
            bid_price = round(raw_bid / price_scale, digits)

            # Check 4: Crossed quote check (Bid > Ask)
            if bid_price > ask_price:
                val_report.crossed_quotes += 1
                val_report.dropped_count += 1
                val_report.rejections.append({
                    "record_idx": record_idx,
                    "reason": "CROSSED_QUOTE",
                    "bid": bid_price,
                    "ask": ask_price,
                    "spread": round(ask_price - bid_price, digits),
                })
                continue

            # Check 5: Duplicate observation check via event fingerprint
            event_fingerprint = (
                offset_ms,
                raw_ask,
                raw_bid,
                round(float(ask_vol), 5),
                round(float(bid_vol), 5),
            )
            if event_fingerprint in seen_event_fingerprints:
                val_report.duplicates_dropped += 1
                val_report.dropped_count += 1
                continue
            seen_event_fingerprints.add(event_fingerprint)

            # Check 6: Out of order timestamp check within partition
            if prev_offset_ms is not None and offset_ms < prev_offset_ms:
                val_report.out_of_order += 1
                # Note: Out-of-order within a few ms can occur in fast markets;
                # we preserve the tick but increment out-of-order counter for audit.

            # Compute strictly UTC-aware timestamp
            tick_ts = base_ts + pd.Timedelta(milliseconds=offset_ms)

            # Construct canonical RawTickObservation
            # Phase 6D.1: Both ask volume and bid volume are preserved.
            # Ingestion time is preserved as None for historical records (never backdated).
            obs = RawTickObservation(
                timestamp_utc=tick_ts,
                symbol=canonical_sym,
                bid=bid_price,
                ask=ask_price,
                volume=round(float(ask_vol), 5),
                bid_volume=round(float(bid_vol), 5),
                sequence_id=None,
                provider="DUKASCOPY",
                flags=0,
                observation_time_utc=tick_ts,
                ingestion_time_utc=None,
                dataset_classification=DatasetClassification.HISTORICAL_ARCHIVE,
            )
            observations.append(obs)
            val_report.valid_count += 1

            prev_offset_ms = offset_ms

        return Bi5DecodedBatch(
            observations=observations,
            record_count=len(observations),
            source_file_sha256=source_sha256,
            decoder_version=BI5_DECODER_VERSION,
            file_layout=layout,
            base_timestamp_utc=base_ts,
            instrument_spec=self.instrument_spec,
            validation_report=val_report,
            raw_compressed_bytes=raw_compressed_bytes if preserve_compressed_bytes else None,
            decompressed_byte_length=decomp_len,
            source_path=source_path,
        )

