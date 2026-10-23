"""Data management module: loader, validator, cleaner."""
from src.data.loader import (
    check_mt5_status,
    discover_gold_symbols,
    fetch_historical_bars,
    save_raw_data,
    load_local_data,
    generate_synthetic_gold_data,
    sanitize_symbol_for_filename,
    TIMEFRAME_MAP,
)
from src.data.validator import (
    validate_market_data,
    DataQualityReport,
)
from src.data.cleaner import (
    clean_market_data,
    save_processed_data,
)

__all__ = [
    "check_mt5_status",
    "discover_gold_symbols",
    "fetch_historical_bars",
    "save_raw_data",
    "load_local_data",
    "generate_synthetic_gold_data",
    "sanitize_symbol_for_filename",
    "TIMEFRAME_MAP",
    "validate_market_data",
    "DataQualityReport",
    "clean_market_data",
    "save_processed_data",
]
