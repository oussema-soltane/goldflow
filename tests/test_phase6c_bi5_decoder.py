"""
Phase 6C Test Suite: Dukascopy BI5 Binary Decoder, Instrument Specs & Reconciliation.

Verifies:
- LZMA decompression and 20-byte record boundaries (>3I2f).
- Hourly vs Daily layout boundary enforcement.
- Dukascopy zero-indexed month path parsing.
- Fail-closed price scale enforcement for unverified instruments.
- Handling of crossed quotes, duplicate ticks, and corrupted payloads.
- SHA-256 source hash preservation and audit tracking.
- Offline provider operations and feed reconciliation logic.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
from typing import List

import numpy as np
import pandas as pd
import pytest

from scripts.reconcile_feeds import reconcile_market_feeds
from src.data.ingestion.base import DataUnavailableError, IngestionError
from src.data.ingestion.bi5_decoder import (
    BI5_DECODER_VERSION,
    BI5_RECORD_SIZE,
    AmbiguousLayoutError,
    Bi5DecodedBatch,
    Bi5FileLayout,
    DecompressionError,
    DukascopyBi5Decoder,
    InvalidPayloadLengthError,
)
from src.data.ingestion.dukascopy_provider import DukascopyIngestionProvider
from src.data.ingestion.instrument_spec import (
    DUKASCOPY_EURUSD_SPEC,
    DUKASCOPY_XAUUSD_SPEC,
    SYNTHETIC_XAUUSD_FIXTURE_SPEC,
    UnverifiedPriceScaleError,
    VerificationStatus,
    get_provider_instrument_spec,
)
from tests.fixtures.synthetic_bi5 import (
    create_synthetic_bi5_bytes,
    generate_corrupted_lzma_bytes,
    generate_crossed_quote_fixture,
    generate_duplicate_ticks_fixture,
    generate_non_finite_volume_fixture,
    generate_out_of_bounds_offset_fixture,
    generate_out_of_order_fixture,
    generate_truncated_fixture,
    generate_valid_daily_fixture,
    generate_valid_hourly_fixture,
    pack_bi5_record,
)


class TestBi5DecoderStructureAndDecompression:
    """Tests binary record formatting, LZMA decompression, and payload validation."""

    def test_record_packing_and_unpacking_format(self):
        """Verify that 20-byte big-endian record format matches >3I2f exactly."""
        packed = pack_bi5_record(
            offset_ms=1500,
            raw_ask=2735500,
            raw_bid=2735250,
            ask_vol=1.25,
            bid_vol=2.50,
        )
        assert len(packed) == BI5_RECORD_SIZE == 20

    def test_valid_hourly_decompression_and_decoding(self):
        """Verify that a valid hourly synthetic fixture decodes correctly."""
        raw_bytes = generate_valid_hourly_fixture(num_ticks=10)
        base_ts = pd.Timestamp("2026-10-20 09:00:00", tz="UTC")

        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        batch = decoder.decode_bytes(
            raw_compressed_bytes=raw_bytes,
            layout=Bi5FileLayout.HOURLY,
            base_timestamp_utc=base_ts,
        )

        assert batch.record_count == 10
        assert len(batch.observations) == 10
        assert batch.file_layout == Bi5FileLayout.HOURLY
        assert batch.decoder_version == BI5_DECODER_VERSION
        assert batch.source_file_sha256 == hashlib.sha256(raw_bytes).hexdigest()

        # Check first observation
        first_obs = batch.observations[0]
        assert first_obs.timestamp_utc == base_ts
        assert first_obs.ask == 2735.200
        assert first_obs.bid == 2735.000
        assert first_obs.volume == 1.5

    def test_corrupted_lzma_stream_raises_decompression_error(self):
        """Corrupted LZMA stream must raise DecompressionError."""
        corrupted = generate_corrupted_lzma_bytes()
        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        with pytest.raises(DecompressionError) as exc_info:
            decoder.decode_bytes(
                raw_compressed_bytes=corrupted,
                layout=Bi5FileLayout.HOURLY,
                base_timestamp_utc=pd.Timestamp("2026-10-20 09:00:00", tz="UTC"),
            )
        assert "Failed to decompress BI5 LZMA stream" in str(exc_info.value)

    def test_truncated_payload_raises_invalid_payload_length_error(self):
        """Decompressed stream with non-multiple of 20 bytes must raise InvalidPayloadLengthError."""
        truncated = generate_truncated_fixture(trailing_bytes=7)
        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        with pytest.raises(InvalidPayloadLengthError) as exc_info:
            decoder.decode_bytes(
                raw_compressed_bytes=truncated,
                layout=Bi5FileLayout.HOURLY,
                base_timestamp_utc=pd.Timestamp("2026-10-20 09:00:00", tz="UTC"),
            )
        assert "CORRUPTED BI5 PAYLOAD" in str(exc_info.value)
        assert "7 trailing bytes" in str(exc_info.value)

    def test_empty_compressed_bytes_returns_empty_batch(self):
        """0-byte compressed file returns an empty batch without raising an exception."""
        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        batch = decoder.decode_bytes(
            raw_compressed_bytes=b"",
            layout=Bi5FileLayout.HOURLY,
            base_timestamp_utc=pd.Timestamp("2026-10-20 09:00:00", tz="UTC"),
        )
        assert batch.record_count == 0
        assert len(batch.observations) == 0


class TestPathParsingAndLayoutBoundaries:
    """Tests file layout inference, boundary checks, and zero-indexed month handling."""

    def test_hourly_path_parsing_with_zero_indexed_month(self):
        """Dukascopy paths use 0-indexed months (09 = October)."""
        path = "datafeed/XAUUSD/2026/09/20/09h_ticks.bi5"
        sym, base_ts, layout = DukascopyBi5Decoder.parse_path_layout(path)
        assert sym == "XAUUSD"
        assert layout == Bi5FileLayout.HOURLY
        assert base_ts.year == 2026
        assert base_ts.month == 10  # 09 + 1 = October!
        assert base_ts.day == 20
        assert base_ts.hour == 9
        assert str(base_ts.tz) == "UTC"

    def test_daily_path_parsing_with_zero_indexed_month(self):
        """Daily path parsing should correctly convert month and anchor at 00:00:00."""
        path = "datafeed/XAUUSD/2026/00/15_ticks.bi5"  # 00 = January
        sym, base_ts, layout = DukascopyBi5Decoder.parse_path_layout(path)
        assert sym == "XAUUSD"
        assert layout == Bi5FileLayout.DAILY
        assert base_ts.month == 1  # January
        assert base_ts.day == 15
        assert base_ts.hour == 0

    def test_ambiguous_path_raises_ambiguous_layout_error(self):
        """Non-conforming path pattern must raise AmbiguousLayoutError."""
        with pytest.raises(AmbiguousLayoutError):
            DukascopyBi5Decoder.parse_path_layout("random_folder/some_ticks.bi5")

    def test_hourly_out_of_bounds_offset_rejection(self):
        """Offsets >= 3,600,000 ms in hourly files must be dropped by validation report."""
        fixture = generate_out_of_bounds_offset_fixture(offset_ms=4_000_000)
        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        batch = decoder.decode_bytes(
            raw_compressed_bytes=fixture,
            layout=Bi5FileLayout.HOURLY,
            base_timestamp_utc=pd.Timestamp("2026-10-20 09:00:00", tz="UTC"),
        )
        # 1 valid, 1 dropped out-of-bounds offset
        assert batch.record_count == 1
        assert batch.validation_report.dropped_count == 1
        assert batch.validation_report.rejections[0]["reason"] == "INVALID_TIMESTAMP_OFFSET"

    def test_daily_valid_offsets_within_24_hours(self):
        """Daily layout permits offsets across the full 24-hour day (< 86,400,000 ms)."""
        fixture = generate_valid_daily_fixture(num_ticks=5)
        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        batch = decoder.decode_bytes(
            raw_compressed_bytes=fixture,
            layout=Bi5FileLayout.DAILY,
            base_timestamp_utc=pd.Timestamp("2026-10-20 00:00:00", tz="UTC"),
        )
        assert batch.record_count == 5
        assert batch.validation_report.dropped_count == 0


class TestPriceScaleAndVerificationFailClosed:
    """Verifies fail-closed behavior for unverified instrument specifications."""

    def test_unverified_xauusd_fails_closed_by_default(self):
        """Attempting to decode real XAUUSD without allow_unverified_scale=True must raise UnverifiedPriceScaleError."""
        # DUKASCOPY_XAUUSD_SPEC is marked UNVERIFIED_PENDING_CONFIRMATION
        with pytest.raises(UnverifiedPriceScaleError) as exc_info:
            DukascopyBi5Decoder(
                instrument_spec=DUKASCOPY_XAUUSD_SPEC,
                allow_unverified_scale=False,  # Enforce strict fail-closed
            )
        assert "UNRESOLVED PREREQUISITE" in str(exc_info.value)
        assert "UNVERIFIED_PENDING_CONFIRMATION" in str(exc_info.value)

    def test_verified_eurusd_succeeds_without_allow_unverified_flag(self):
        """Verified spec (EURUSD) succeeds with default fail-closed setting."""
        decoder = DukascopyBi5Decoder(
            instrument_spec=DUKASCOPY_EURUSD_SPEC,
            allow_unverified_scale=False,
        )
        assert decoder.instrument_spec.verification_status == VerificationStatus.VERIFIED
        assert decoder.instrument_spec.price_scale == 100000.0

    def test_synthetic_scale_allowed_when_explicitly_declared(self):
        """Synthetic fixture specification succeeds when allow_unverified_scale=True."""
        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        assert decoder.instrument_spec.verification_status == VerificationStatus.SYNTHETIC_FIXTURE_ONLY


class TestDataQualityAndValidationAnomalyHandling:
    """Verifies handling of crossed quotes, duplicate ticks, and non-finite volumes."""

    def test_crossed_quotes_detected_and_filtered(self):
        """Crossed quotes (Bid > Ask) are recorded in validation report and dropped."""
        fixture = generate_crossed_quote_fixture()
        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        batch = decoder.decode_bytes(
            raw_compressed_bytes=fixture,
            layout=Bi5FileLayout.HOURLY,
            base_timestamp_utc=pd.Timestamp("2026-10-20 09:00:00", tz="UTC"),
        )
        assert batch.record_count == 2
        assert batch.validation_report.crossed_quotes == 1
        assert batch.validation_report.dropped_count == 1

    def test_duplicate_ticks_detected_and_dropped(self):
        """Identical consecutive tick observations are filtered out."""
        fixture = generate_duplicate_ticks_fixture()
        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        batch = decoder.decode_bytes(
            raw_compressed_bytes=fixture,
            layout=Bi5FileLayout.HOURLY,
            base_timestamp_utc=pd.Timestamp("2026-10-20 09:00:00", tz="UTC"),
        )
        assert batch.record_count == 2
        assert batch.validation_report.duplicates_dropped == 1

    def test_non_finite_volume_records_dropped(self):
        """Records with NaN or Inf volume values are filtered out."""
        fixture = generate_non_finite_volume_fixture()
        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        batch = decoder.decode_bytes(
            raw_compressed_bytes=fixture,
            layout=Bi5FileLayout.HOURLY,
            base_timestamp_utc=pd.Timestamp("2026-10-20 09:00:00", tz="UTC"),
        )
        assert batch.record_count == 1
        assert batch.validation_report.dropped_count == 2


class TestDukascopyProviderAndReconciliation:
    """Verifies DukascopyIngestionProvider offline behavior and feed reconciliation script."""

    def test_provider_offline_fetch_with_local_files(self):
        """Provider decodes local files matching symbol and date range."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # Create local folder structure: tmp/XAUUSD/2026/09/20/09h_ticks.bi5
            target_dir = tmp_path / "XAUUSD" / "2026" / "09" / "20"
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = target_dir / "09h_ticks.bi5"

            fixture = generate_valid_hourly_fixture(num_ticks=5)
            with open(file_path, "wb") as f:
                f.write(fixture)

            provider = DukascopyIngestionProvider(
                local_archive_root=tmp_path,
                allow_unverified_scale=True,
            )

            start = dt.datetime(2026, 10, 20, 9, 0, tzinfo=dt.timezone.utc)
            end = dt.datetime(2026, 10, 20, 9, 30, tzinfo=dt.timezone.utc)

            obs_list, meta = provider.fetch_historical_ticks("XAUUSD", start, end)
            assert len(obs_list) == 5
            assert meta["files_processed"] == 1
            assert meta["provider"] == "DUKASCOPY"

    def test_provider_raises_data_unavailable_when_local_archive_missing(self):
        """If local archive is missing for a verified instrument, raises DataUnavailableError without network call."""
        provider = DukascopyIngestionProvider(local_archive_root=Path("/non_existent_dir"))
        start = dt.datetime(2026, 10, 20, 9, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 10, 20, 10, 0, tzinfo=dt.timezone.utc)

        with pytest.raises(DataUnavailableError):
            provider.fetch_historical_ticks("EURUSD", start, end)

    def test_provider_raises_unverified_scale_for_xauusd_by_default(self):
        """Fetching XAUUSD without allow_unverified_scale=True fails closed with UnverifiedPriceScaleError."""
        provider = DukascopyIngestionProvider(local_archive_root=Path("/some_dir"), allow_unverified_scale=False)
        start = dt.datetime(2026, 10, 20, 9, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 10, 20, 10, 0, tzinfo=dt.timezone.utc)

        with pytest.raises(UnverifiedPriceScaleError):
            provider.fetch_historical_ticks("XAUUSD", start, end)

    def test_provider_streaming_is_disabled_in_phase6c(self):
        """Streaming incremental ticks in Phase 6C raises IngestionError."""
        provider = DukascopyIngestionProvider()
        with pytest.raises(IngestionError) as exc_info:
            list(provider.stream_incremental_ticks("XAUUSD"))
        assert "External network streaming is disabled" in str(exc_info.value)

    def test_cross_provider_reconciliation_logic(self):
        """Test reconciliation engine comparing two feeds with known price offsets."""
        dates = pd.date_range("2026-10-20 09:00:00", periods=10, freq="1min", tz="UTC")
        p_df = pd.DataFrame({
            "time_utc": dates,
            "open": [2735.0 + i for i in range(10)],
            "high": [2735.5 + i for i in range(10)],
            "low": [2734.5 + i for i in range(10)],
            "close": [2735.2 + i for i in range(10)],
            "spread": [0.25] * 10,
        })
        # Comparison feed with +0.10 price difference and +0.05 spread difference
        c_df = pd.DataFrame({
            "time_utc": dates,
            "open": [2735.10 + i for i in range(10)],
            "high": [2735.60 + i for i in range(10)],
            "low": [2734.60 + i for i in range(10)],
            "close": [2735.30 + i for i in range(10)],
            "spread": [0.30] * 10,
        })

        p_meta = {"file_name": "mt5_ref.parquet", "sha256": "aaa111", "row_count": 10}
        c_meta = {"file_name": "dukascopy_ref.parquet", "sha256": "bbb222", "row_count": 10}

        result = reconcile_market_feeds(
            primary_df=p_df,
            primary_meta=p_meta,
            comparison_df=c_df,
            comparison_meta=c_meta,
            tolerance_pts=0.50,
        )

        assert result["status"] == "RECONCILIATION_COMPLETED"
        assert result["coverage"]["aligned_bars"] == 10
        assert round(result["price_deviations"]["close"]["mean_diff"], 2) == 0.10
        assert round(result["price_deviations"]["close"]["mae"], 2) == 0.10
        assert result["price_deviations"]["close"]["exceeding_tolerance_count"] == 0
        assert result["spread_comparison"]["primary"]["mean"] == 0.25
        assert result["spread_comparison"]["comparison"]["mean"] == 0.30
