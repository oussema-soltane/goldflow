"""
Provider-Neutral Ingestion Base Interfaces for GoldFlow.

Defines the abstract base class and common exceptions for market data providers.
"""

from __future__ import annotations

import abc
import datetime as dt
from typing import Any, Dict, Iterator, List, Optional, Tuple

from src.data.ingestion.models import RawTickObservation


class IngestionError(Exception):
    """Base exception for all market data ingestion failures."""
    pass


class AuthenticationError(IngestionError):
    """Raised when authentication credentials are missing or invalid."""
    pass


class RateLimitError(IngestionError):
    """Raised when provider rate limits are exceeded."""
    pass


class DataUnavailableError(IngestionError):
    """Raised when requested instrument or date range is not available."""
    pass


class DataIngestionProvider(abc.ABC):
    """
    Abstract protocol for institutional and mock market data providers.
    
    All implementations must return strictly UTC-aware RawTickObservation objects
    and declare their instrument specifications without silently guessing values.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Return the unique canonical identifier for this provider."""
        raise NotImplementedError

    @abc.abstractmethod
    def is_authenticated(self) -> bool:
        """Check whether the provider is currently authenticated and ready."""
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_historical_ticks(
        self,
        symbol: str,
        start_time: dt.datetime,
        end_time: dt.datetime,
    ) -> Tuple[List[RawTickObservation], Dict[str, Any]]:
        """
        Fetch historical raw ticks for a specified symbol and UTC time window.
        
        Parameters
        ----------
        symbol : str
            Canonical instrument symbol (e.g. 'XAUUSD').
        start_time : dt.datetime
            UTC start datetime (inclusive).
        end_time : dt.datetime
            UTC end datetime (inclusive).
            
        Returns
        -------
        Tuple[List[RawTickObservation], Dict[str, Any]]
            A list of raw tick observations and a retrieval metadata dictionary.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def stream_incremental_ticks(
        self,
        symbol: str,
        max_ticks: Optional[int] = None,
    ) -> Iterator[RawTickObservation]:
        """
        Stream incremental real-time or simulated tick observations.
        
        Parameters
        ----------
        symbol : str
            Canonical instrument symbol.
        max_ticks : int, optional
            Maximum number of ticks to yield before terminating stream.
            
        Yields
        ------
        RawTickObservation
            Individual tick observations as they arrive.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_instrument_specification(self, symbol: str) -> Dict[str, Any]:
        """
        Query execution specifications for the specified instrument.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary containing digits, point, trade_contract_size, tick_size,
            tick_value, spread_typical, and currency attributes.
        """
        raise NotImplementedError

