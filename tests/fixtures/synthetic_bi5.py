"""
Deterministic Synthetic BI5 Binary Fixture Generator for GoldFlow.

Generates compressed and uncompressed Dukascopy-style binary tick fixtures
for testing LZMA decompression, record boundaries, timestamp bounds,
scale factors, crossed quotes, duplicate ticks, and corruption scenarios.
All fixtures are purely synthetic and offline.
"""

from __future__ import annotations

import lzma
import math
import struct
from typing import List, Tuple

BI5_RECORD_FORMAT = ">3I2f"  # 20 bytes


def pack_bi5_record(
    offset_ms: int,
    raw_ask: int,
    raw_bid: int,
    ask_vol: float,
    bid_vol: float,
) -> bytes:
    """Pack a single 20-byte Dukascopy tick record in big-endian format."""
    return struct.pack(BI5_RECORD_FORMAT, offset_ms, raw_ask, raw_bid, ask_vol, bid_vol)


def create_synthetic_bi5_bytes(
    records: List[Tuple[int, int, int, float, float]],
) -> bytes:
    """
    Compress a list of tick records into a valid LZMA stream.
    
    Each record tuple is: (offset_ms, raw_ask, raw_bid, ask_vol, bid_vol).
    """
    raw_payload = b"".join(pack_bi5_record(*r) for r in records)
    return lzma.compress(raw_payload)


def generate_valid_hourly_fixture(
    num_ticks: int = 10,
    base_price: int = 2735000,  # e.g. 2735.000 with 1000 scale
    spread: int = 200,          # e.g. 0.200 with 1000 scale
) -> bytes:
    """
    Generate valid hourly fixture with monotonically increasing millisecond offsets < 3,600,000.
    """
    records = []
    for i in range(num_ticks):
        offset = i * 10000  # every 10 seconds
        ask = base_price + spread + (i * 10)
        bid = base_price + (i * 10)
        ask_vol = 1.5 + (i * 0.1)
        bid_vol = 2.0 + (i * 0.1)
        records.append((offset, ask, bid, ask_vol, bid_vol))
    return create_synthetic_bi5_bytes(records)


def generate_valid_daily_fixture(
    num_ticks: int = 10,
    base_price: int = 2735000,
    spread: int = 200,
) -> bytes:
    """
    Generate valid daily fixture with millisecond offsets across multiple hours < 86,400,000.
    """
    records = []
    for i in range(num_ticks):
        offset = i * 3600000  # every hour
        ask = base_price + spread + (i * 50)
        bid = base_price + (i * 50)
        records.append((offset, ask, bid, 1.0, 1.0))
    return create_synthetic_bi5_bytes(records)


def generate_truncated_fixture(trailing_bytes: int = 7) -> bytes:
    """
    Generate an LZMA stream whose decompressed payload length is not a multiple of 20 bytes.
    """
    valid_record = pack_bi5_record(1000, 2735200, 2735000, 1.0, 1.0)
    corrupted_payload = valid_record + b"\xAA" * trailing_bytes
    return lzma.compress(corrupted_payload)


def generate_corrupted_lzma_bytes() -> bytes:
    """Generate invalid LZMA header bytes that will fail decompression."""
    return b"\xFD7zXZ\x00\x00corrupted_non_lzma_payload_data_bytes"


def generate_out_of_bounds_offset_fixture(offset_ms: int = 4_000_000) -> bytes:
    """Generate fixture with timestamp offset exceeding hourly limit (3,600,000 ms)."""
    records = [
        (1000, 2735200, 2735000, 1.0, 1.0),
        (offset_ms, 2735200, 2735000, 1.0, 1.0),
    ]
    return create_synthetic_bi5_bytes(records)


def generate_crossed_quote_fixture() -> bytes:
    """Generate fixture containing a crossed quote where bid > ask."""
    records = [
        (1000, 2735200, 2735000, 1.0, 1.0),  # Valid: Ask=2735.2, Bid=2735.0
        (2000, 2735000, 2735500, 1.0, 1.0),  # Crossed: Ask=2735.0, Bid=2735.5
        (3000, 2735400, 2735200, 1.0, 1.0),  # Valid
    ]
    return create_synthetic_bi5_bytes(records)


def generate_duplicate_ticks_fixture() -> bytes:
    """Generate fixture containing consecutive identical ticks."""
    records = [
        (1000, 2735200, 2735000, 1.0, 1.0),
        (1000, 2735200, 2735000, 1.0, 1.0),  # Duplicate
        (2000, 2735300, 2735100, 1.0, 1.0),
    ]
    return create_synthetic_bi5_bytes(records)


def generate_non_finite_volume_fixture() -> bytes:
    """Generate fixture containing NaN or infinite volume."""
    records = [
        (1000, 2735200, 2735000, float("nan"), 1.0),
        (2000, 2735200, 2735000, 1.0, float("inf")),
        (3000, 2735200, 2735000, 1.0, 1.0),  # Valid
    ]
    return create_synthetic_bi5_bytes(records)


def generate_out_of_order_fixture() -> bytes:
    """Generate fixture where timestamps decrease within the file."""
    records = [
        (5000, 2735200, 2735000, 1.0, 1.0),
        (2000, 2735300, 2735100, 1.0, 1.0),  # Decreasing offset
        (6000, 2735400, 2735200, 1.0, 1.0),
    ]
    return create_synthetic_bi5_bytes(records)

