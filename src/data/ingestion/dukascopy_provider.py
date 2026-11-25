"""
Dukascopy Market Data Ingestion Provider for GoldFlow.

Implements the DataIngestionProvider protocol for Dukascopy Bank SA feeds.
Uses DukascopyBi5Decoder for decoding .bi5 archives, enforces strict price-scale
verification, operates offline by default with bounded, operator-guarded retrieval
pilots, and preserves complete audit traceability and raw file hashes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union
import urllib.error
import urllib.request

import pandas as pd

from src.data.ingestion.base import (
    AuthenticationError,
    DataIngestionProvider,
    DataUnavailableError,
    IngestionError,
)
from src.data.ingestion.bi5_decoder import (
    Bi5DecodedBatch,
    Bi5FileLayout,
    DukascopyBi5Decoder,
)
from src.data.ingestion.instrument_spec import (
    DUKASCOPY_EURUSD_SPEC,
    DUKASCOPY_XAUUSD_SPEC,
    ProviderInstrumentSpec,
    SYNTHETIC_XAUUSD_FIXTURE_SPEC,
    UnverifiedPriceScaleError,
    VerificationStatus,
    get_provider_instrument_spec,
)
from src.data.ingestion.models import (
    IngestionBatchMetadata,
    IngestionStatus,
    RawTickObservation,
)
from src.vault.raw_storage import PartitionStorageManager

logger = logging.getLogger(__name__)

# Verified Zero-Cost Public CDN Endpoint Base
DUKASCOPY_PUBLIC_CDN_BASE = "https://datafeed.dukascopy.com/datafeed"


class DukascopyIngestionProvider(DataIngestionProvider):
    """
    Provider-neutral adapter for Dukascopy market data feeds.
    
    Supports local offline archive decoding and guarded, bounded historical pilots.
    Network operations are strictly disabled by default and fail closed.
    """

    def __init__(
        self,
        local_archive_root: Optional[Union[str, Path]] = None,
        allow_unverified_scale: bool = False,
    ) -> None:
        """
        Initialize the Dukascopy provider adapter.
        
        Parameters
        ----------
        local_archive_root : Optional[Union[str, Path]]
            Root directory containing locally cached .bi5 files.
        allow_unverified_scale : bool
            Must be True to decode synthetic or unverified test feeds.
            If False, decoding unverified specs (like real XAUUSD) fails closed.
        """
        self.local_archive_root = Path(local_archive_root) if local_archive_root else None
        self.allow_unverified_scale = allow_unverified_scale

    @property
    def provider_name(self) -> str:
        """Unique canonical identifier for this provider."""
        return "DUKASCOPY"

    def is_authenticated(self) -> bool:
        """
        Check whether the provider is authenticated.
        
        The public Dukascopy historical datafeed requires no credentials.
        """
        return True

    def get_instrument_specification(self, symbol: str) -> Dict[str, Any]:
        """
        Query execution and scaling specifications for the specified instrument.
        """
        spec = get_provider_instrument_spec(self.provider_name, symbol)
        return spec.to_dict()

    def fetch_historical_ticks(
        self,
        symbol: str,
        start_time: dt.datetime,
        end_time: dt.datetime,
    ) -> Tuple[List[RawTickObservation], Dict[str, Any]]:
        """
        Fetch historical ticks for a symbol and UTC window from the local archive.
        
        Parameters
        ----------
        symbol : str
            Canonical instrument symbol (e.g. 'XAUUSD', 'EURUSD').
        start_time : dt.datetime
            UTC start time.
        end_time : dt.datetime
            UTC end time.
            
        Returns
        -------
        Tuple[List[RawTickObservation], Dict[str, Any]]
            Decoded canonical tick observations and audit metadata.
        """
        start_ts = pd.to_datetime(start_time, utc=True)
        end_ts = pd.to_datetime(end_time, utc=True)

        if start_ts > end_ts:
            raise IngestionError(f"Start time ({start_ts}) cannot be after end time ({end_ts}).")

        # 1. Resolve Instrument Specification & Verify Price Scale
        try:
            spec = get_provider_instrument_spec(self.provider_name, symbol)
        except KeyError:
            spec = get_provider_instrument_spec("SYNTHETIC_MOCK", symbol)

        decoder = DukascopyBi5Decoder(
            instrument_spec=spec,
            allow_unverified_scale=self.allow_unverified_scale,
        )

        # 2. Check Local Archive Availability
        if self.local_archive_root is None or not self.local_archive_root.exists():
            raise DataUnavailableError(
                f"OFFLINE POLICY ENFORCED: External network retrieval is disabled. "
                f"Local archive root '{self.local_archive_root}' is missing or not configured. "
                f"To fetch historical ticks, supply a valid local directory containing .bi5 files."
            )

        # 3. Discover Local Files Matching Time Range
        matching_files: List[Path] = []
        sym_dir = self.local_archive_root / symbol.replace("/", "")
        if not sym_dir.exists():
            sym_dir = self.local_archive_root

        for bi5_path in sorted(sym_dir.rglob("*.bi5")):
            try:
                _, base_ts, _ = DukascopyBi5Decoder.parse_path_layout(bi5_path)
                hour_end = base_ts + pd.Timedelta(hours=1)
                if hour_end >= start_ts and base_ts <= end_ts:
                    matching_files.append(bi5_path)
            except Exception:
                continue

        if not matching_files:
            raise DataUnavailableError(
                f"No local .bi5 partitions found in '{self.local_archive_root}' for {symbol} "
                f"between {start_ts} and {end_ts}."
            )

        # 4. Decode Files Sequentially
        all_observations: List[RawTickObservation] = []
        source_manifests: List[Dict[str, Any]] = []

        for f_path in matching_files:
            batch = decoder.decode_file(f_path)
            for obs in batch.observations:
                if start_ts <= obs.timestamp_utc <= end_ts:
                    all_observations.append(obs)

            source_manifests.append({
                "path": str(f_path.resolve()),
                "sha256": batch.source_file_sha256,
                "record_count": batch.record_count,
                "base_timestamp_utc": batch.base_timestamp_utc.isoformat(),
                "file_layout": batch.file_layout.value,
            })

        metadata = {
            "provider": self.provider_name,
            "symbol": symbol,
            "start_time_utc": start_ts.isoformat(),
            "end_time_utc": end_ts.isoformat(),
            "total_observations": len(all_observations),
            "files_processed": len(matching_files),
            "sources": source_manifests,
            "decoder_version": "1.0.0",
            "price_scale": spec.price_scale,
            "verification_status": spec.verification_status.value,
        }

        return all_observations, metadata

    def execute_bounded_retrieval_pilot(
        self,
        symbol: str,
        target_hour_utc: pd.Timestamp,
        output_dir: Union[str, Path],
        allow_network: bool = False,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
    ) -> IngestionBatchMetadata:
        """
        Execute a strictly guarded, bounded historical retrieval pilot for a single UTC hour.
        
        Security Controls:
        1. Fails closed if allow_network is False.
        2. Fails closed with UnverifiedPriceScaleError if instrument spec is not VERIFIED.
        3. Retrieves strictly from the verified zero-cost public CDN endpoint (never S3 Requester Pays).
        4. Hashes the raw response bytes before decoding.
        5. Preserves original bytes and creates Parquet partition with cryptographic manifest.
        6. Writes strictly into historical/cross-provider storage, never forward holdouts.
        """
        if not allow_network:
            raise IngestionError(
                "NETWORK_PILOT_DISABLED: Network retrieval requires explicit operator activation "
                "(allow_network=True). By default, external network operations are disabled."
            )

        # Ensure UTC hour anchor
        if not isinstance(target_hour_utc, pd.Timestamp):
            hour_ts = pd.to_datetime(target_hour_utc, utc=True)
        else:
            hour_ts = target_hour_utc.tz_convert("UTC") if target_hour_utc.tz else target_hour_utc.tz_localize("UTC")

        hour_ts = hour_ts.floor("h")

        # 1. Resolve Instrument Spec & Enforce UNCONDITIONAL Verification Check
        # Phase 6D.1 FIX: Use validate_for_real_network_ingestion() which ignores
        # allow_unverified_scale and is unconditionally fail-closed.
        # The previous call to validate_for_decoding(allow_unverified=self.allow_unverified_scale)
        # allowed synthetic fixture flags to bypass the real network gate.
        spec = get_provider_instrument_spec(self.provider_name, symbol)
        spec.validate_for_real_network_ingestion()  # NO override accepted

        decoder = DukascopyBi5Decoder(
            instrument_spec=spec,
            allow_unverified_scale=False,  # Real network path: never allow unverified
        )

        # 2. Construct Canonical Public CDN URL (Zero-cost HTTPS endpoint)
        # Note: Dukascopy month is 0-indexed: month - 1
        zero_month = hour_ts.month - 1
        prov_sym = spec.provider_symbol.replace("/", "")
        url = (
            f"{DUKASCOPY_PUBLIC_CDN_BASE}/{prov_sym}/"
            f"{hour_ts.year:04d}/{zero_month:02d}/{hour_ts.day:02d}/"
            f"{hour_ts.hour:02d}h_ticks.bi5"
        )

        # Verify output path does not escape or touch holdout
        storage_root = Path(output_dir).resolve()
        if "holdout" in str(storage_root).lower():
            raise IngestionError(
                f"STORAGE VIOLATION: Retrieval pilot cannot write into protected holdout vault '{storage_root}'."
            )

        logger.info(f"Initiating bounded Dukascopy pilot download from: {url}")

        # 3. Bounded HTTP Request with Timeout, Size Bounds, and Retry
        MAX_RESPONSE_BYTES = 50 * 1024 * 1024  # 50 MB bound
        raw_bytes: Optional[bytes] = None
        last_error: Optional[Exception] = None

        headers = {
            "User-Agent": "GoldFlow-Quantitative-Research-Pilot/1.0 (Research-Integrity-Audit)"
        }
        req = urllib.request.Request(url, headers=headers)

        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                    # Validate redirect host
                    if hasattr(response, "geturl") and callable(response.geturl):
                        final_url = response.geturl()
                        if isinstance(final_url, str) and not final_url.startswith("https://datafeed.dukascopy.com"):
                            raise IngestionError(
                                f"UNAUTHORIZED_REDIRECT: Bounded pilot redirected to unauthorized host: {final_url}"
                            )
                    raw_bytes = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw_bytes) > MAX_RESPONSE_BYTES:
                        raise IngestionError(
                            f"OVERSIZED_RESPONSE: Response size exceeded maximum limit of {MAX_RESPONSE_BYTES} bytes."
                        )
                    break
            except urllib.error.HTTPError as http_err:
                if http_err.code == 404:
                    raise DataUnavailableError(
                        f"HTTP_404_NOT_FOUND: Dukascopy partition not found for {url}."
                    )
                elif http_err.code == 403:
                    raise AuthenticationError(
                        f"HTTP_403_FORBIDDEN: Dukascopy feed access forbidden for {url}."
                    )
                elif http_err.code == 429:
                    raise IngestionError(
                        f"HTTP_429_RATE_LIMITED: Dukascopy feed rate limit encountered for {url}."
                    )
                elif 500 <= http_err.code < 600:
                    last_error = IngestionError(
                        f"HTTP_SERVER_ERROR: Dukascopy feed returned status {http_err.code} for {url}."
                    )
                    time.sleep(1.0 * (attempt + 1))
                else:
                    raise IngestionError(
                        f"HTTP error {http_err.code} for {url}: {http_err.reason}"
                    )
            except (DataUnavailableError, AuthenticationError, IngestionError):
                raise
            except Exception as exc:
                last_error = exc
                time.sleep(1.0 * (attempt + 1))

        if raw_bytes is None:
            raise IngestionError(
                f"Bounded pilot retrieval failed for {url} after {max_retries} attempts: {last_error}"
            )

        if len(raw_bytes) == 0:
            raise DataUnavailableError(
                f"EMPTY_RESPONSE: Dukascopy returned 0 bytes for {url}. No market data present."
            )

        # 4. Hash Raw Response Bytes Before Decoding
        raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        retrieval_time = dt.datetime.now(dt.timezone.utc).isoformat()

        # 5. Decode Bytes
        batch: Bi5DecodedBatch = decoder.decode_bytes(
            raw_compressed_bytes=raw_bytes,
            layout=Bi5FileLayout.HOURLY,
            base_timestamp_utc=hour_ts,
            preserve_compressed_bytes=True,
            source_path=url,
        )

        # 6. Save Partition, Source Object & Manifest via PartitionStorageManager
        storage_mgr = PartitionStorageManager(vault_root=storage_root)
        batch_id = f"PILOT_{prov_sym}_{hour_ts.strftime('%Y%m%d_%H%M%S')}"

        # Persist original compressed source object separately
        source_obj_path, _, _ = storage_mgr.write_source_object(
            raw_bytes=raw_bytes,
            symbol=spec.canonical_symbol,
            provider=self.provider_name,
            timestamp=hour_ts.to_pydatetime(),
            source_filename=f"{prov_sym}_{hour_ts.strftime('%Y%m%d_%H00')}.bi5",
            custom_metadata={"batch_id": batch_id, "source_url": url},
        )

        if batch.record_count > 0:
            df_rows = [obs.to_dict() for obs in batch.observations]
            ticks_df = pd.DataFrame(df_rows)
            partition_path, manifest_path, manifest_dict = storage_mgr.write_partition(
                df=ticks_df,
                symbol=spec.canonical_symbol,
                provider=self.provider_name,
                granularity="hourly",
                custom_metadata={
                    "batch_id": batch_id,
                    "source_url": url,
                    "source_object_path": str(source_obj_path.relative_to(storage_root)),
                },
            )
            partition_sha = manifest_dict.get("file_sha256") or manifest_dict.get("sha256")
        else:
            partition_path, partition_sha = None, None

        # 7. Construct and Return Metadata
        metadata = IngestionBatchMetadata(
            batch_id=batch_id,
            provider=self.provider_name,
            symbol=spec.canonical_symbol,
            retrieval_time_utc=retrieval_time,
            start_time=hour_ts.isoformat(),
            end_time=(hour_ts + pd.Timedelta(hours=1)).isoformat(),
            raw_tick_count=batch.validation_report.total_input,
            valid_tick_count=batch.validation_report.valid_count,
            rejected_tick_count=batch.validation_report.dropped_count,
            partition_path=str(partition_path) if partition_path else None,
            partition_sha256=partition_sha,
            status=IngestionStatus.SUCCESS,
            custom_metadata={
                "source_url": url,
                "raw_compressed_sha256": raw_sha256,
                "raw_compressed_size_bytes": len(raw_bytes),
                "decompressed_size_bytes": batch.decompressed_byte_length,
                "decoder_version": batch.decoder_version,
                "price_scale": spec.price_scale,
                "verification_status": spec.verification_status.value,
                "crossed_quotes": batch.validation_report.crossed_quotes,
                "duplicates_dropped": batch.validation_report.duplicates_dropped,
            },
        )

        return metadata

    def stream_incremental_ticks(
        self,
        symbol: str,
        max_ticks: Optional[int] = None,
    ) -> Iterator[RawTickObservation]:
        """
        Stream incremental tick observations.
        
        In Phase 6D, live network streaming remains disabled.
        """
        raise IngestionError(
            "External network streaming is disabled. "
            "To test streaming pipelines, use the deterministic MockDataIngestionProvider."
        )
