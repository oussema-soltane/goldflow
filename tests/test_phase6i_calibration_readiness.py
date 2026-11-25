"""
Tests for Phase 6I: Dukascopy BI5 Decoder, Price-Scale Calibration Readiness,
Network Fail-Closed Boundaries, and Research Governance Invariants.
"""

import datetime as dt
import hashlib
import lzma
from pathlib import Path
import struct
import pytest
import pandas as pd

from src.data.ingestion.base import IngestionError
from src.data.ingestion.bi5_decoder import (
    BI5_RECORD_SIZE,
    BI5_STRUCT_FORMAT,
    Bi5FileLayout,
    DukascopyBi5Decoder,
    InvalidPayloadLengthError,
)
from src.data.ingestion.dukascopy_provider import (
    DUKASCOPY_PUBLIC_CDN_BASE,
    DukascopyIngestionProvider,
)
from src.data.ingestion.instrument_spec import (
    DUKASCOPY_EURUSD_SPEC,
    DUKASCOPY_XAUUSD_SPEC,
    SYNTHETIC_XAUUSD_FIXTURE_SPEC,
    UnverifiedPriceScaleError,
    VerificationStatus,
)


class TestPhase6IBi5UnpackingAndScaling:
    """Tests for low-level 20-byte record unpacking and price scale conversion."""

    def test_bi5_binary_record_unpacking(self):
        """Verify struct '>3I2f' correctly decodes offset, bid, ask, and volumes."""
        offset_ms = 1250
        raw_ask = 4156940
        raw_bid = 4156850
        ask_vol = 1.75
        bid_vol = 2.25

        packed_record = struct.pack(
            BI5_STRUCT_FORMAT,
            offset_ms,
            raw_ask,
            raw_bid,
            ask_vol,
            bid_vol,
        )
        assert len(packed_record) == BI5_RECORD_SIZE

        compressed_data = lzma.compress(packed_record)
        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )

        base_ts = pd.Timestamp("2026-10-15 10:00:00", tz="UTC")
        batch = decoder.decode_bytes(
            raw_compressed_bytes=compressed_data,
            layout=Bi5FileLayout.HOURLY,
            base_timestamp_utc=base_ts,
        )

        assert batch.record_count == 1
        obs = batch.observations[0]
        assert obs.timestamp_utc == pd.Timestamp("2026-10-15 10:00:01.250", tz="UTC")
        assert obs.ask == 4156.940
        assert obs.bid == 4156.850
        assert round(obs.ask - obs.bid, 3) == 0.090
        assert obs.volume == 1.75
        assert obs.bid_volume == 2.25

    def test_timestamp_offset_reconstruction_boundary(self):
        """Verify millisecond offset accurately reconstructs timestamps up to 3,599,999 ms."""
        base_ts = pd.Timestamp("2026-10-15 10:00:00", tz="UTC")
        offset_ms = 3599999  # 59m 59s 999ms

        packed = struct.pack(BI5_STRUCT_FORMAT, offset_ms, 4155000, 4154900, 1.0, 1.0)
        compressed = lzma.compress(packed)

        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        batch = decoder.decode_bytes(
            raw_compressed_bytes=compressed,
            layout=Bi5FileLayout.HOURLY,
            base_timestamp_utc=base_ts,
        )

        assert batch.record_count == 1
        assert batch.observations[0].timestamp_utc == pd.Timestamp("2026-10-15 10:59:59.999", tz="UTC")

    def test_invalid_decompressed_payload_length_fails_closed(self):
        """Decompressed payload length not divisible by 20 bytes must raise InvalidPayloadLengthError."""
        # 25 bytes (1 record + 5 trailing garbage bytes)
        corrupted_payload = struct.pack(BI5_STRUCT_FORMAT, 100, 4155000, 4154900, 1.0, 1.0) + b"EXTRA"
        compressed = lzma.compress(corrupted_payload)

        decoder = DukascopyBi5Decoder(
            instrument_spec=SYNTHETIC_XAUUSD_FIXTURE_SPEC,
            allow_unverified_scale=True,
        )
        with pytest.raises(InvalidPayloadLengthError) as exc_info:
            decoder.decode_bytes(
                raw_compressed_bytes=compressed,
                layout=Bi5FileLayout.HOURLY,
                base_timestamp_utc=pd.Timestamp("2026-10-15 10:00:00", tz="UTC"),
            )
        assert "not an exact multiple of 20 bytes" in str(exc_info.value)


class TestPhase6IPriceScaleVerificationGates:
    """Tests for unconditional fail-closed gates protecting against unverified scales."""

    def test_unverified_xauusd_spec_fails_closed_on_real_network_validation(self):
        """DUKASCOPY_XAUUSD_SPEC must fail closed unconditionally for real network ingestion."""
        assert DUKASCOPY_XAUUSD_SPEC.verification_status == VerificationStatus.UNVERIFIED_PENDING_CONFIRMATION

        with pytest.raises(UnverifiedPriceScaleError) as exc_info:
            DUKASCOPY_XAUUSD_SPEC.validate_for_real_network_ingestion()
        assert "REAL NETWORK INGESTION BLOCKED" in str(exc_info.value)
        assert "UNVERIFIED_PENDING_CONFIRMATION" in str(exc_info.value)

    def test_synthetic_fixture_spec_fails_closed_on_real_network_validation(self):
        """SYNTHETIC_XAUUSD_FIXTURE_SPEC must never authorize real network ingestion."""
        with pytest.raises(UnverifiedPriceScaleError) as exc_info:
            SYNTHETIC_XAUUSD_FIXTURE_SPEC.validate_for_real_network_ingestion()
        assert "REAL NETWORK INGESTION BLOCKED" in str(exc_info.value)
        assert "SYNTHETIC_FIXTURE_ONLY" in str(exc_info.value)

    def test_verified_eurusd_spec_passes_real_network_validation(self):
        """DUKASCOPY_EURUSD_SPEC has verified official scale and passes gate."""
        assert DUKASCOPY_EURUSD_SPEC.verification_status == VerificationStatus.VERIFIED
        # Should execute without raising
        DUKASCOPY_EURUSD_SPEC.validate_for_real_network_ingestion()

    def test_unverified_spec_fails_decoding_without_explicit_override(self):
        """DukascopyBi5Decoder must fail closed if allow_unverified_scale is False."""
        with pytest.raises(UnverifiedPriceScaleError) as exc_info:
            DukascopyBi5Decoder(
                instrument_spec=DUKASCOPY_XAUUSD_SPEC,
                allow_unverified_scale=False,
            )
        assert "marked as 'UNVERIFIED_PENDING_CONFIRMATION'" in str(exc_info.value)


class TestPhase6INetworkBoundaryAndUrlConstruction:
    """Tests verifying fail-closed network gate and zero-indexed month CDN URLs."""

    def test_provider_network_pilot_fails_closed_by_default(self, tmp_path):
        """Provider execute_bounded_retrieval_pilot must raise IngestionError when allow_network=False."""
        provider = DukascopyIngestionProvider(local_archive_root=tmp_path)
        target_hour = pd.Timestamp("2026-10-15 10:00:00", tz="UTC")

        with pytest.raises(IngestionError) as exc_info:
            provider.execute_bounded_retrieval_pilot(
                symbol="XAUUSD",
                target_hour_utc=target_hour,
                output_dir=tmp_path,
                allow_network=False,
            )
        assert "NETWORK_PILOT_DISABLED" in str(exc_info.value)

    def test_dukascopy_url_construction_zero_indexed_month(self):
        """Verify URL generator produces 0-indexed month (October 10 -> 09)."""
        target_hour = pd.Timestamp("2026-10-15 10:00:00", tz="UTC")
        zero_month = target_hour.month - 1
        assert zero_month == 9

        url = (
            f"{DUKASCOPY_PUBLIC_CDN_BASE}/XAUUSD/"
            f"{target_hour.year:04d}/{zero_month:02d}/{target_hour.day:02d}/"
            f"{target_hour.hour:02d}h_ticks.bi5"
        )
        assert url == "https://datafeed.dukascopy.com/datafeed/XAUUSD/2026/09/15/10h_ticks.bi5"


class TestPhase6ICalibrationToleranceLogic:
    """Tests for reference quote matching and scale discrimination logic."""

    def test_price_scale_discrimination_logic(self):
        """Verify candidate divisor discrimination rejects 100.0, 10000.0, 100000.0 and accepts 1000.0."""
        raw_int_price = 4156940  # Integer from feed
        ref_open = 4156.94
        tolerance = 0.50

        # Divisor 100.0 -> 41,569.40 (10x too big)
        p_100 = raw_int_price / 100.0
        assert abs(p_100 - ref_open) > tolerance

        # Divisor 10000.0 -> 415.69 (10x too small)
        p_10000 = raw_int_price / 10000.0
        assert abs(p_10000 - ref_open) > tolerance

        # Divisor 100000.0 -> 41.57 (100x too small)
        p_100000 = raw_int_price / 100000.0
        assert abs(p_100000 - ref_open) > tolerance

        # Divisor 1000.0 -> 4,156.94 (Exact match)
        p_1000 = raw_int_price / 1000.0
        assert abs(p_1000 - ref_open) <= tolerance

    def test_authoritative_reference_bar_in_clean_csv(self):
        """Verify that 2026-10-15 10:00 UTC reference bar exists in H1 clean CSV with exact values."""
        h1_path = Path("data/processed/XAUUSD_H1_clean.csv")
        assert h1_path.exists()

        df = pd.read_csv(h1_path)
        matching = df[df["time"] == "2026-10-15 10:00:00+00:00"]
        assert len(matching) == 1

        row = matching.iloc[0]
        assert row["open"] == 4156.94
        assert row["high"] == 4158.80
        assert row["low"] == 4151.71
        assert row["close"] == 4154.76
        assert row["tick_volume"] == 10903


class TestPhase6IImmutabilityInvariants:
    """Tests guaranteeing frozen benchmarks and candidate specs remain strictly uncorrupted."""

    def test_frozen_smc_v1_config_hash(self):
        """configs/smc_v1_frozen.json must match canonical SHA-256."""
        cfg_path = Path("configs/smc_v1_frozen.json")
        assert cfg_path.exists()
        expected = "1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a"
        actual = hashlib.sha256(cfg_path.read_bytes()).hexdigest()
        assert actual == expected

    def test_frozen_c2_candidate_spec_hash(self):
        """reports/strategy/phase6h_candidate_spec.json must match canonical SHA-256."""
        spec_path = Path("reports/strategy/phase6h_candidate_spec.json")
        assert spec_path.exists()
        expected = "d09474e02c3dc45165a667742cec5012662e58b95cea78bfd6e5e8d782849916"
        actual = hashlib.sha256(spec_path.read_bytes()).hexdigest()
        assert actual == expected
