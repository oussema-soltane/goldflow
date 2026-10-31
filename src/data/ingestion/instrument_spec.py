"""
Instrument Specification and Price Scaling Verification for GoldFlow.

Enforces explicit verification of instrument definitions, tick sizes, point scales,
and contract specifications. Prevents silent assumptions regarding provider price scaling
(such as unverified XAUUSD multipliers) by failing closed unless explicitly verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
from enum import Enum
from typing import Any, Dict, Optional


class VerificationStatus(str, Enum):
    """Status of an instrument specification's verified provenance."""
    VERIFIED = "VERIFIED"
    UNVERIFIED_PENDING_CONFIRMATION = "UNVERIFIED_PENDING_CONFIRMATION"
    SYNTHETIC_FIXTURE_ONLY = "SYNTHETIC_FIXTURE_ONLY"


class PriceScaleError(Exception):
    """Base exception for price scale specification errors."""
    pass


class UnverifiedPriceScaleError(PriceScaleError):
    """Raised when decoding real data with an unverified price scale."""
    pass


@dataclass(frozen=True)
class ProviderInstrumentSpec:
    """
    Explicit specification of an instrument's pricing, scaling, and contract structure.
    
    Attributes
    ----------
    provider: str
        Canonical identifier of the data provider (e.g. 'DUKASCOPY').
    provider_symbol: str
        Exact symbol used by the provider (e.g. 'XAU/USD', 'XAUUSD').
    canonical_symbol: str
        GoldFlow canonical symbol (e.g. 'XAUUSD').
    price_scale: float
        Divisor applied to raw integer prices to yield floating-point units.
    digits: int
        Number of decimal digits for display and round-off.
    tick_size: float
        Minimum price increment in price units.
    point_value: float
        Price increment representing one point (e.g. 0.01 for gold, 0.00001 for FX).
    contract_description: str
        Human-readable description of the instrument.
    documentation_reference: str
        Citation or URL to official documentation or source.
    verification_status: VerificationStatus
        Whether the scale and specifications have been verified against official SLA.
    verified_date: Optional[str]
        ISO-8601 date when the specification was verified.
    notes: str
        Technical or operational notes regarding this specification.
    """
    provider: str
    provider_symbol: str
    canonical_symbol: str
    price_scale: float
    digits: int
    tick_size: float
    point_value: float
    contract_description: str
    documentation_reference: str
    verification_status: VerificationStatus
    verified_date: Optional[str] = None
    notes: str = ""

    def validate_for_decoding(self, allow_unverified: bool = False) -> None:
        """
        Validate that this specification is legally and technically eligible for decoding.
        
        Parameters
        ----------
        allow_unverified : bool
            If True, permits unverified or synthetic specifications for local testing.
            If False, fails closed with UnverifiedPriceScaleError.

        NOTE: This method is for SYNTHETIC/LOCAL decoding only. For real network
        ingestion, use validate_for_real_network_ingestion() which is unconditionally
        fail-closed regardless of this flag.
        """
        if self.price_scale <= 0.0:
            raise PriceScaleError(f"Invalid non-positive price scale: {self.price_scale}")

        if not allow_unverified and self.verification_status != VerificationStatus.VERIFIED:
            raise UnverifiedPriceScaleError(
                f"UNRESOLVED PREREQUISITE: Price scale {self.price_scale} for {self.provider}:{self.provider_symbol} "
                f"is marked as '{self.verification_status.value}' (not VERIFIED). "
                f"Reference: {self.documentation_reference}. "
                f"To prevent silent scaling errors, decoding real provider data with an unverified "
                f"price scale is prohibited. Set allow_unverified=True explicitly for synthetic testing."
            )

    def validate_for_real_network_ingestion(self) -> None:
        """
        Unconditional fail-closed gate for REAL NETWORK data ingestion.

        Phase 6D.1: This method NEVER accepts an override flag. A synthetic fixture
        flag (allow_unverified_scale=True on the provider) MUST NOT reach this method.
        Real XAUUSD network ingestion cannot proceed until the instrument specification
        is promoted to VERIFIED through a documented calibration process.

        Unlike validate_for_decoding(), this method ignores any caller-side
        allow_unverified flag. The verification must be unconditional.
        """
        if self.price_scale <= 0.0:
            raise PriceScaleError(f"Invalid non-positive price scale: {self.price_scale}")

        if self.verification_status != VerificationStatus.VERIFIED:
            raise UnverifiedPriceScaleError(
                f"UNRESOLVED PREREQUISITE: REAL NETWORK INGESTION BLOCKED: Instrument {self.provider}:{self.provider_symbol} "
                f"has verification status '{self.verification_status.value}' (requires VERIFIED). "
                f"Reference: {self.documentation_reference}. "
                f"No override is accepted for real network ingestion. "
                f"Synthetic test overrides (allow_unverified_scale=True) are not valid here. "
                f"To unblock: produce documented calibration evidence and promote the spec to VERIFIED."
            )

        if self.verification_status == VerificationStatus.SYNTHETIC_FIXTURE_ONLY:
            raise UnverifiedPriceScaleError(
                f"SYNTHETIC FIXTURE SPEC CANNOT AUTHORIZE REAL INGESTION: "
                f"Spec {self.provider}:{self.provider_symbol} is SYNTHETIC_FIXTURE_ONLY. "
                f"Use a VERIFIED real-provider spec for network ingestion."
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert specification to dictionary."""
        return {
            "provider": self.provider,
            "provider_symbol": self.provider_symbol,
            "canonical_symbol": self.canonical_symbol,
            "price_scale": self.price_scale,
            "digits": self.digits,
            "tick_size": self.tick_size,
            "point_value": self.point_value,
            "contract_description": self.contract_description,
            "documentation_reference": self.documentation_reference,
            "verification_status": self.verification_status.value,
            "verified_date": self.verified_date,
            "notes": self.notes,
        }


# =====================================================================
# Canonical Instrument Specification Catalog
# =====================================================================

# 1. Dukascopy Standard FX (EURUSD) - Verified Official Pip Point Scale
DUKASCOPY_EURUSD_SPEC = ProviderInstrumentSpec(
    provider="DUKASCOPY",
    provider_symbol="EUR/USD",
    canonical_symbol="EURUSD",
    price_scale=100000.0,
    digits=5,
    tick_size=0.00001,
    point_value=0.00001,
    contract_description="Euro vs US Dollar SWFX Spot",
    documentation_reference="Dukascopy JForex API documentation: standard 5-digit FX scale 10^5",
    verification_status=VerificationStatus.VERIFIED,
    verified_date="2026-10-28",
    notes="Verified standard currency point scale.",
)

# 2. Dukascopy XAUUSD - UNVERIFIED PENDING OFFICIAL CONFIRMATION
# JForex community conventions frequently use 1000.0 (3 decimal places),
# but this is not yet corroborated by an official Dukascopy SLA or contract spec.
# Must remain UNVERIFIED and fail closed for real ingestion.
DUKASCOPY_XAUUSD_SPEC = ProviderInstrumentSpec(
    provider="DUKASCOPY",
    provider_symbol="XAU/USD",
    canonical_symbol="XAUUSD",
    price_scale=1000.0,
    digits=3,
    tick_size=0.001,
    point_value=0.01,
    contract_description="Gold Spot Bullion vs US Dollar (SWFX Marketplace)",
    documentation_reference="JForex community historical data parser conventions (unconfirmed by official bank SLA)",
    verification_status=VerificationStatus.UNVERIFIED_PENDING_CONFIRMATION,
    verified_date=None,
    notes="Requires controlled feed calibration against known reference quote before production ingestion.",
)

# 3. Explicit Synthetic Fixture Specification (For Offline Testing Only)
SYNTHETIC_XAUUSD_FIXTURE_SPEC = ProviderInstrumentSpec(
    provider="SYNTHETIC_MOCK",
    provider_symbol="XAU/USD_FIXTURE",
    canonical_symbol="XAUUSD",
    price_scale=1000.0,
    digits=3,
    tick_size=0.001,
    point_value=0.01,
    contract_description="Synthetic Gold Bullion Test Fixture",
    documentation_reference="GoldFlow Phase 6C internal test fixture specification",
    verification_status=VerificationStatus.SYNTHETIC_FIXTURE_ONLY,
    verified_date="2026-10-28",
    notes="Explicitly labeled test fixture specification. Does not represent verified live provider feed.",
)


def get_provider_instrument_spec(
    provider: str,
    symbol: str,
) -> ProviderInstrumentSpec:
    """
    Look up an instrument specification by provider and symbol.
    
    Raises KeyError if specification is not defined.
    """
    prov_upper = provider.upper()
    sym_clean = symbol.replace("/", "").replace("_", "").upper()

    if prov_upper == "DUKASCOPY":
        if sym_clean == "XAUUSD":
            return DUKASCOPY_XAUUSD_SPEC
        elif sym_clean == "EURUSD":
            return DUKASCOPY_EURUSD_SPEC
    elif prov_upper in ("SYNTHETIC_MOCK", "SYNTHETIC"):
        if sym_clean == "XAUUSD":
            return SYNTHETIC_XAUUSD_FIXTURE_SPEC

    raise KeyError(
        f"No instrument specification registered for provider '{provider}' and symbol '{symbol}'."
    )

