"""
Data Ingestion Package for GoldFlow.

Provides provider-neutral data structures, abstract provider interfaces,
validation logic, mock feeds, instrument limit configurations, M1 bar synthesis,
and Dukascopy BI5 binary decoding.
"""

from src.data.ingestion.base import (
    AuthenticationError,
    DataIngestionProvider,
    DataUnavailableError,
    IngestionError,
    RateLimitError,
)
from src.data.ingestion.bar_builder import M1BarBuilder, synthesize_m1_bars
from src.data.ingestion.bi5_decoder import (
    BI5_DECODER_VERSION,
    AmbiguousLayoutError,
    Bi5DecodedBatch,
    Bi5DecoderError,
    Bi5FileLayout,
    CorruptedRecordError,
    DecompressionError,
    DukascopyBi5Decoder,
    InvalidPayloadLengthError,
)
from src.data.ingestion.dukascopy_provider import DukascopyIngestionProvider
from src.data.ingestion.instrument_spec import (
    DUKASCOPY_EURUSD_SPEC,
    DUKASCOPY_XAUUSD_SPEC,
    PriceScaleError,
    ProviderInstrumentSpec,
    SYNTHETIC_XAUUSD_FIXTURE_SPEC,
    UnverifiedPriceScaleError,
    VerificationStatus,
    get_provider_instrument_spec,
)
from src.data.ingestion.models import (
    AggregatedBar,
    IngestionBatchMetadata,
    IngestionStatus,
    RawTickObservation,
)
from src.data.ingestion.mock_provider import MockDataIngestionProvider
from src.data.ingestion.validator import (
    DEFAULT_FX_LIMITS,
    DEFAULT_GOLD_LIMITS,
    InstrumentPriceLimits,
    TickDataValidator,
    ValidationAuditReport,
    validate_and_canonicalize_ticks,
)

__all__ = [
    "AggregatedBar",
    "AmbiguousLayoutError",
    "AuthenticationError",
    "BI5_DECODER_VERSION",
    "Bi5DecodedBatch",
    "Bi5DecoderError",
    "Bi5FileLayout",
    "CorruptedRecordError",
    "DEFAULT_FX_LIMITS",
    "DEFAULT_GOLD_LIMITS",
    "DUKASCOPY_EURUSD_SPEC",
    "DUKASCOPY_XAUUSD_SPEC",
    "DataIngestionProvider",
    "DataUnavailableError",
    "DecompressionError",
    "DukascopyBi5Decoder",
    "DukascopyIngestionProvider",
    "IngestionBatchMetadata",
    "IngestionError",
    "IngestionStatus",
    "InstrumentPriceLimits",
    "InvalidPayloadLengthError",
    "M1BarBuilder",
    "MockDataIngestionProvider",
    "PriceScaleError",
    "ProviderInstrumentSpec",
    "RateLimitError",
    "RawTickObservation",
    "SYNTHETIC_XAUUSD_FIXTURE_SPEC",
    "TickDataValidator",
    "UnverifiedPriceScaleError",
    "ValidationAuditReport",
    "VerificationStatus",
    "get_provider_instrument_spec",
    "synthesize_m1_bars",
    "validate_and_canonicalize_ticks",
]
