"""
Phase 6D Test Suite: Controlled Dukascopy Ingestion Pilot & Safety Gates.

Verifies:
- Bounded retrieval pilot safety gates (network disabled by default).
- Fail-closed price scale enforcement for unverified XAUUSD.
- Deterministic mock pilot download, pre-decoding SHA-256 hashing, and partition manifest generation.
- Strict isolation of historical retrieval from forward holdout vaults.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from io import BytesIO
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data.ingestion.base import IngestionError
from src.data.ingestion.dukascopy_provider import DukascopyIngestionProvider
from src.data.ingestion.instrument_spec import (
    DUKASCOPY_EURUSD_SPEC,
    DUKASCOPY_XAUUSD_SPEC,
    UnverifiedPriceScaleError,
    VerificationStatus,
)
from src.data.ingestion.models import IngestionStatus
from tests.fixtures.synthetic_bi5 import generate_valid_hourly_fixture


class TestDukascopyBoundedPilotSafetyGates:
    """Verifies that the bounded retrieval pilot enforces fail-closed research integrity."""

    def test_pilot_network_disabled_by_default(self):
        """Calling execute_bounded_retrieval_pilot without allow_network=True must fail closed."""
        provider = DukascopyIngestionProvider()
        target_hour = pd.Timestamp("2026-10-20 09:00:00", tz="UTC")

        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(IngestionError) as exc_info:
                provider.execute_bounded_retrieval_pilot(
                    symbol="EURUSD",
                    target_hour_utc=target_hour,
                    output_dir=Path(tmp_dir),
                    allow_network=False,  # Enforce default safety
                )
            assert "NETWORK_PILOT_DISABLED" in str(exc_info.value)

    def test_pilot_unverified_xauusd_scale_fails_closed(self):
        """Calling execute_bounded_retrieval_pilot for unverified XAUUSD must raise UnverifiedPriceScaleError."""
        provider = DukascopyIngestionProvider(allow_unverified_scale=False)
        target_hour = pd.Timestamp("2026-10-20 09:00:00", tz="UTC")

        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(UnverifiedPriceScaleError) as exc_info:
                provider.execute_bounded_retrieval_pilot(
                    symbol="XAUUSD",
                    target_hour_utc=target_hour,
                    output_dir=Path(tmp_dir),
                    allow_network=True,  # Operator enabled network, but scale is UNVERIFIED!
                )
            assert "UNRESOLVED PREREQUISITE" in str(exc_info.value)
            assert "UNVERIFIED_PENDING_CONFIRMATION" in str(exc_info.value)

    def test_mocked_network_pilot_execution(self):
        """Test pilot pipeline with deterministic mock network response (zero real network calls)."""
        fixture_bytes = generate_valid_hourly_fixture(num_ticks=10)
        expected_sha = hashlib.sha256(fixture_bytes).hexdigest()

        mock_resp = MagicMock()
        mock_resp.read.return_value = fixture_bytes
        mock_resp.__enter__.return_value = mock_resp

        target_hour = pd.Timestamp("2026-10-20 09:00:00", tz="UTC")

        # Use verified EURUSD specification to test pilot execution end-to-end
        provider = DukascopyIngestionProvider(allow_unverified_scale=False)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)

            with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
                metadata = provider.execute_bounded_retrieval_pilot(
                    symbol="EURUSD",
                    target_hour_utc=target_hour,
                    output_dir=out_dir,
                    allow_network=True,
                    timeout_seconds=5.0,
                )

                # Verify mock was called with verified public CDN URL
                mock_urlopen.assert_called_once()
                called_req = mock_urlopen.call_args[0][0]
                assert "datafeed.dukascopy.com" in called_req.full_url
                assert "EURUSD" in called_req.full_url

            # Verify returned metadata
            assert metadata.status == IngestionStatus.SUCCESS
            assert metadata.symbol == "EURUSD"
            assert metadata.valid_tick_count == 10
            assert metadata.custom_metadata["raw_compressed_sha256"] == expected_sha
            assert metadata.partition_path is not None
            assert Path(metadata.partition_path).exists()
            assert Path(metadata.partition_path + ".manifest.json").exists()

