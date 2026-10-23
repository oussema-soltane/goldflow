"""Audit broker instrument metadata against GoldFlow execution assumptions.

A clean OHLC file cannot prove MT5 point size, contract size, or volume rules.
This module intentionally reports missing metadata instead of inferring it from
price precision. The audit is a preflight aid, not broker authentication.
"""
from __future__ import annotations

import json
import math
from pathlib import Path, PurePath
from typing import Any, Mapping

from src.backtesting.engine import BacktestConfig

# Settings directly compared with MT5 symbol_info values. These are configuration
# defaults unless the operator deliberately overrides them in the backtest UI/CLI.
CONFIG_TO_MT5_FIELD = {
    "point_size": "point",
    "contract_size_oz": "trade_contract_size",
    "min_lot": "volume_min",
    "lot_step": "volume_step",
    "max_lots": "volume_max",
}
REQUIRED_SPEC_FIELDS = tuple(CONFIG_TO_MT5_FIELD.values()) + (
    "digits", "trade_tick_size", "trade_tick_value", "trade_calc_mode"
)
REQUIRED_SPEC_STRING_FIELDS = ("trade_calc_mode_name", "trade_calc_mode_name_source")
REQUIRED_SPEC_MAPPING_FIELDS = ("trade_calc_mode_constant_values",)
POSITIVE_SPEC_FIELDS = {
    "point", "trade_contract_size", "volume_min", "volume_step", "volume_max", "trade_tick_size", "trade_tick_value"
}
REQUIRED_CURRENCY_FIELDS = ("currency_base", "currency_profit", "account_currency")

# Symbolic MT5 calculation modes whose documented profit calculation is
# (close_price - open_price) * Contract_Size * Lots. Use symbolic names resolved
# by the active MetaTrader5 package at capture time rather than hard-coding enum
# numeric IDs, which can be represented differently across API bindings.
# Source formulas: https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants
LINEAR_PROFIT_CALC_MODE_NAMES = {
    "SYMBOL_CALC_MODE_FOREX",
    "SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE",
    "SYMBOL_CALC_MODE_CFD",
    "SYMBOL_CALC_MODE_CFDINDEX",
    "SYMBOL_CALC_MODE_CFDLEVERAGE",
    "SYMBOL_CALC_MODE_EXCH_STOCKS",
    "SYMBOL_CALC_MODE_EXCH_STOCKS_MOEX",
}
KNOWN_NONLINEAR_CALC_MODE_NAMES = {
    "SYMBOL_CALC_MODE_FUTURES",
    "SYMBOL_CALC_MODE_EXCH_FUTURES",
    "SYMBOL_CALC_MODE_EXCH_FUTURES_FORTS",
    "SYMBOL_CALC_MODE_EXCH_BONDS",
    "SYMBOL_CALC_MODE_EXCH_BONDS_MOEX",
    "SYMBOL_CALC_MODE_SERV_COLLATERAL",
    "SYMBOL_CALC_MODE_EXCH_OPTIONS_MARGIN",
}



def _valid_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def audit_one_execution_specification(
    metadata: Mapping[str, Any],
    config: BacktestConfig | None = None,
    *,
    rel_tol: float = 1e-8,
    abs_tol: float = 1e-10,
) -> dict[str, Any]:
    """Compare a dataset sidecar's captured specification with a config's assumptions."""
    config = config or BacktestConfig()
    spec = metadata.get("execution_specification")
    if not isinstance(spec, Mapping):
        spec = {}
    missing = []
    wrong_type_fields = []
    for name in REQUIRED_SPEC_FIELDS:
        raw_value = spec.get(name)
        value = _valid_number(raw_value)
        # Preserve the legacy missing_required_fields contract for strict-gate
        # callers, while separately exposing present-but-invalid values (e.g.
        # booleans, NaN, infinity, or malformed strings) to the operator.
        if raw_value is not None and value is None:
            wrong_type_fields.append(name)
        if value is None or (name in POSITIVE_SPEC_FIELDS and value <= 0):
            missing.append(name)
        elif name == "digits" and (value < 1 or not value.is_integer()):
            missing.append(name)
        elif name == "trade_calc_mode" and (value < 0 or not value.is_integer()):
            missing.append(name)
    for name in REQUIRED_SPEC_STRING_FIELDS:
        raw_value = spec.get(name)
        if not isinstance(raw_value, str) or not raw_value.strip():
            missing.append(name)
    for name in REQUIRED_SPEC_MAPPING_FIELDS:
        raw_value = spec.get(name)
        if not isinstance(raw_value, Mapping) or not raw_value:
            missing.append(name)
    missing_currency_fields = [
        name for name in REQUIRED_CURRENCY_FIELDS
        if not isinstance(spec.get(name), str) or not spec.get(name).strip()
    ]
    currency_values = {
        name: str(spec.get(name)).strip().upper()
        for name in REQUIRED_CURRENCY_FIELDS
        if isinstance(spec.get(name), str) and spec.get(name).strip()
    }
    unsupported_currencies = {
        name: value for name, value in currency_values.items()
        if value != {"currency_base": "XAU", "currency_profit": "USD", "account_currency": "USD"}[name]
    }
    comparisons: dict[str, Any] = {}
    mismatches: list[dict[str, Any]] = []
    for config_name, mt5_name in CONFIG_TO_MT5_FIELD.items():
        actual = _valid_number(spec.get(mt5_name))
        expected = _valid_number(getattr(config, config_name))
        if actual is None or expected is None:
            comparisons[config_name] = {
                "mt5_field": mt5_name,
                "configured_assumption": getattr(config, config_name),
                "captured_value": spec.get(mt5_name),
                "result": "not_comparable",
            }
            continue
        matches = math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=abs_tol)
        comparison = {
            "mt5_field": mt5_name,
            "configured_assumption": expected,
            "captured_value": actual,
            "result": "match" if matches else "mismatch",
        }
        comparisons[config_name] = comparison
        if not matches:
            mismatches.append({"config_field": config_name, **comparison})

    sidecar_symbol = metadata.get("symbol")
    captured_symbol = spec.get("symbol")
    symbol_unverified = bool(spec and (not sidecar_symbol or not captured_symbol))
    symbol_mismatch = bool(sidecar_symbol and captured_symbol and sidecar_symbol != captured_symbol)
    sidecar_server = metadata.get("broker_server")
    captured_server = spec.get("broker_server")
    capture_context = metadata.get("execution_specification_capture")
    capture_context = capture_context if isinstance(capture_context, Mapping) else {}
    broker_unverified = bool(
        spec and (
            not sidecar_server
            or not captured_server
            or capture_context.get("same_broker_server_as_data") is False
        )
    )
    broker_mismatch = bool(
        sidecar_server and captured_server
        and str(sidecar_server).strip().casefold() != str(captured_server).strip().casefold()
    )
    contract_size = _valid_number(spec.get("trade_contract_size"))
    tick_size = _valid_number(spec.get("trade_tick_size"))
    tick_value = _valid_number(spec.get("trade_tick_value"))
    raw_calc_mode = _valid_number(spec.get("trade_calc_mode"))
    calc_mode_is_integer = raw_calc_mode is not None and raw_calc_mode >= 0 and raw_calc_mode.is_integer()
    calc_mode_value = int(raw_calc_mode) if calc_mode_is_integer else None
    raw_calc_mode_name = spec.get("trade_calc_mode_name")
    calc_mode_name = raw_calc_mode_name.strip() if isinstance(raw_calc_mode_name, str) and raw_calc_mode_name.strip() else None
    calc_mode_name_source = spec.get("trade_calc_mode_name_source")
    calc_mode_capture_verified = calc_mode_name_source == "MetaTrader5 module constants"
    raw_mode_constants = spec.get("trade_calc_mode_constant_values")
    mode_constants: dict[str, int] = {}
    if isinstance(raw_mode_constants, Mapping):
        for mode_name, mode_code in raw_mode_constants.items():
            parsed_code = _valid_number(mode_code)
            if (
                isinstance(mode_name, str) and mode_name.startswith("SYMBOL_CALC_MODE_")
                and parsed_code is not None and parsed_code >= 0 and parsed_code.is_integer()
            ):
                mode_constants[mode_name] = int(parsed_code)
    calc_mode_code_matches_name = (
        calc_mode_is_integer and calc_mode_name is not None
        and mode_constants.get(calc_mode_name) == calc_mode_value
    )
    calc_mode_supported = (
        calc_mode_is_integer
        and calc_mode_code_matches_name
        and calc_mode_name in LINEAR_PROFIT_CALC_MODE_NAMES
        and calc_mode_capture_verified
    )
    if calc_mode_supported:
        calc_mode_status = "supported_linear_contract_size_formula"
    elif not calc_mode_is_integer or not calc_mode_name or not calc_mode_capture_verified or not mode_constants:
        calc_mode_status = "unverified_or_invalid"
    elif not calc_mode_code_matches_name:
        calc_mode_status = "enum_code_name_mismatch"
    elif calc_mode_name in KNOWN_NONLINEAR_CALC_MODE_NAMES:
        calc_mode_status = "unsupported_formula"
    else:
        calc_mode_status = "unsupported_or_unknown_formula"
    tick_value_check: dict[str, Any] = {"status": "not_evaluated"}
    if not calc_mode_supported:
        tick_value_check["reason"] = "trade_calc_mode is missing, invalid, or not allowlisted for the contract-size formula"
    elif missing_currency_fields or unsupported_currencies:
        tick_value_check["reason"] = "XAU/USD/USD currency assumptions are missing or unsupported"
    elif (
        contract_size is None or tick_size is None or tick_value is None
        or contract_size <= 0 or tick_size <= 0 or tick_value <= 0
    ):
        tick_value_check["reason"] = "a required positive contract-size, tick-size, or tick-value field is unavailable"
    else:
        expected_tick_value = contract_size * tick_size
        relative_error = abs(tick_value - expected_tick_value) / expected_tick_value
        is_direct_match = relative_error <= 0.05

        reconcil = spec.get("tick_value_reconciliation")
        reconciliation_verified = False
        inquired_1lot = None
        if isinstance(reconcil, Mapping):
            inquired_1lot = _valid_number(reconcil.get("inquired_order_calc_profit_1lot"))
            rec_status = reconcil.get("reconciliation_status")
            auth_method = reconcil.get("authoritative_calculation_method")
            if (
                rec_status == "linear_contract_size_verified_by_terminal_api"
                and auth_method == "contract_size_linear_formula_verified_by_order_calc_profit"
                and inquired_1lot is not None
                and math.isclose(inquired_1lot, expected_tick_value, rel_tol=1e-4)
            ):
                reconciliation_verified = True

        if is_direct_match:
            tick_status = "match"
        elif reconciliation_verified:
            tick_status = "reconciled_via_order_calc_profit"
        else:
            tick_status = "mismatch"

        tick_value_check = {
            "status": tick_status,
            "captured_tick_value": tick_value,
            "expected_contract_times_tick_size": expected_tick_value,
            "relative_error_pct": relative_error * 100.0,
            "tolerance_pct": 5.0,
            "trade_calc_mode": calc_mode_value,
            "trade_calc_mode_name": calc_mode_name,
            "reconciliation_verified": reconciliation_verified,
        }
        if reconciliation_verified and isinstance(reconcil, Mapping):
            tick_value_check["inquired_order_calc_profit_1lot"] = inquired_1lot
            tick_value_check["authoritative_calculation_method"] = reconcil.get("authoritative_calculation_method")
            tick_value_check["reconciliation_explanation"] = reconcil.get("reconciliation_explanation")
            tick_value_check["inquiry_evidence"] = reconcil.get("inquiry_evidence")

    if not spec:
        status = "MISSING_SPECIFICATIONS"
    elif symbol_mismatch:
        status = "SYMBOL_MISMATCH"
    elif symbol_unverified:
        status = "SYMBOL_UNVERIFIED"
    elif broker_mismatch:
        status = "BROKER_MISMATCH"
    elif broker_unverified:
        status = "BROKER_UNVERIFIED"
    elif missing_currency_fields:
        status = "CURRENCY_UNVERIFIED"
    elif unsupported_currencies:
        status = "CURRENCY_UNSUPPORTED"
    # Report direct configuration mismatches before derived tick-value arithmetic:
    # a wrong contract-size assumption can itself create an apparent tick mismatch.
    # The full tick-value diagnostic remains available in tick_value_check.
    elif mismatches:
        status = "CONFIG_MISMATCH"
    elif calc_mode_status == "unverified_or_invalid":
        status = "CALC_MODE_UNVERIFIED"
    elif calc_mode_status == "enum_code_name_mismatch":
        status = "CALC_MODE_MISMATCH"
    elif not calc_mode_supported:
        status = "CALC_MODE_UNSUPPORTED"
    elif tick_value_check.get("status") == "mismatch":
        status = "TICK_VALUE_MISMATCH"
    elif missing:
        status = "MISSING_SPECIFICATIONS"
    else:
        status = "MATCHED_CAPTURED_DEFAULTS"

    warnings = []
    if tick_value_check.get("status") == "reconciled_via_order_calc_profit":
        warnings.append(
            "TICK_VALUE_RECONCILED: symbol_info.trade_tick_value (0.1) differs from contract formula (1.0), "
            "but MT5 order_calc_profit empirically confirmed 1.00 USD/tick for 1.0 lot across BUY and SELL."
        )

    return {
        "symbol": metadata.get("symbol"),
        "timeframe": metadata.get("timeframe"),
        "sidecar_source": metadata.get("source"),
        "source_verification_status": metadata.get("source_verification_status", "unknown"),
        "provenance_independently_verified": False,
        "execution_specification_status": spec.get("status", metadata.get("execution_specification_status", "missing")),
        "captured_symbol": captured_symbol,
        "captured_broker_server": captured_server,
        "metadata_broker_server": sidecar_server,
        "broker_server_match_verified": bool(sidecar_server and captured_server and not broker_mismatch),
        "captured_at_utc": spec.get("captured_at_utc"),
        "status": status,
        "missing_required_fields": missing,
        "wrong_type_fields": wrong_type_fields,
        "missing_currency_fields": missing_currency_fields,
        "currency_values": currency_values,
        "unsupported_currencies": unsupported_currencies,
        "trade_calc_mode": calc_mode_value,
        "trade_calc_mode_name": calc_mode_name,
        "trade_calc_mode_name_source": calc_mode_name_source,
        "trade_calc_mode_constant_values": dict(raw_mode_constants) if isinstance(raw_mode_constants, Mapping) else None,
        "trade_calc_mode_code_matches_name": calc_mode_code_matches_name,
        "trade_calc_mode_status": calc_mode_status,
        "trade_calc_mode_allowlisted": calc_mode_supported,
        "tick_value_check": tick_value_check,
        "tick_value_status": tick_value_check.get("status"),
        "reconciliation_verified": tick_value_check.get("reconciliation_verified", False),
        "warnings": warnings,
        "reconciled_discrepancies": (
            ["trade_tick_value (reported 0.1, reconciled to 1.0 via order_calc_profit)"]
            if tick_value_check.get("status") == "reconciled_via_order_calc_profit"
            else []
        ),
        "execution_specification": dict(spec),
        "mismatches": mismatches,
        "comparisons": comparisons,
        "notes": [
            "A captured symbol specification is still a metadata claim and does not independently authenticate data provenance.",
            "The configuration values shown are BacktestConfig defaults; CLI/UI overrides must be audited using the corresponding configuration.",
            "Missing values are not inferred from OHLC price precision.",
            "Present-but-invalid numeric values are listed in wrong_type_fields; missing_required_fields also includes unusable numeric values for backward-compatible strict gating.",
            "trade_calc_mode_name is resolved from the active MetaTrader5 package constants at capture time; the captured constant-value map is retained so the numeric code/name pair can be checked without guessing enum IDs.",
            "Only documented linear contract-size profit modes are allowlisted; futures/tick-price, bond, collateral, unknown, and malformed modes are blocked from strict validation.",
            "The calculation-mode check validates formula compatibility, not the broker's overall correctness or the authenticity of historical OHLC provenance.",
        ],
    }


ESSENTIAL_SPEC_FIELDS = (
    "digits", "point", "trade_contract_size", "trade_tick_size",
    "volume_min", "volume_step", "volume_max",
    "trade_calc_mode", "currency_base", "currency_profit", "account_currency",
)
OBSERVATIONAL_SPEC_FIELDS = (
    "captured_at_utc", "spread", "spread_float", "trade_stops_level", "trade_freeze_level",
)


def check_cross_dataset_spec_consistency(audits: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify essential calculation specifications match identically across all audited datasets.

    Observational fields (captured_at_utc, live spread) are permitted to vary across time.
    """
    if len(audits) <= 1:
        return {"status": "consistent", "mismatches": [], "dataset_count": len(audits)}

    first = audits[0]
    first_spec = first.get("execution_specification", {}) or {}
    first_tf = first.get("timeframe", "first")
    mismatches = []

    for item in audits[1:]:
        tf = item.get("timeframe", "other")
        spec = item.get("execution_specification", {}) or {}
        for field in ESSENTIAL_SPEC_FIELDS:
            val1 = first_spec.get(field)
            val2 = spec.get(field)
            if val1 is not None and val2 is not None:
                if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                    if not math.isclose(float(val1), float(val2), rel_tol=1e-8, abs_tol=1e-10):
                        mismatches.append(f"{field} differs between {first_tf} ({val1}) and {tf} ({val2})")
                elif str(val1).strip().upper() != str(val2).strip().upper():
                    mismatches.append(f"{field} differs between {first_tf} ({val1}) and {tf} ({val2})")
            elif val1 != val2:
                mismatches.append(f"{field} missing or differing between {first_tf} ({val1}) and {tf} ({val2})")

        m1 = (first_spec.get("tick_value_reconciliation") or {}).get("authoritative_calculation_method")
        m2 = (spec.get("tick_value_reconciliation") or {}).get("authoritative_calculation_method")
        if m1 != m2:
            mismatches.append(f"authoritative_calculation_method differs between {first_tf} ({m1}) and {tf} ({m2})")

    return {
        "status": "consistent" if not mismatches else "mismatch",
        "mismatches": mismatches,
        "dataset_count": len(audits),
        "essential_fields_checked": list(ESSENTIAL_SPEC_FIELDS),
        "permitted_varying_observational_fields": list(OBSERVATIONAL_SPEC_FIELDS),
    }


def _stable_path_text(path: PurePath) -> str:
    """Serialize paths with POSIX separators for cross-platform audit snapshots."""
    return path.as_posix()


def audit_processed_execution_specs(
    data_dir: str | Path = "data/processed",
    config: BacktestConfig | None = None,
) -> dict[str, Any]:
    """Audit every processed dataset metadata sidecar under a directory."""
    root = Path(data_dir)
    config = config or BacktestConfig()
    audits: list[dict[str, Any]] = []
    errors: list[str] = []
    for sidecar in sorted(root.glob("*_clean.meta.json")):
        try:
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{sidecar}: {exc}")
            continue
        record = audit_one_execution_specification(metadata, config)
        # Stable report paths across Windows and POSIX; avoids cosmetic snapshot diffs.
        record["sidecar_path"] = _stable_path_text(sidecar)
        audits.append(record)

    statuses = {item["status"] for item in audits}
    cross_dataset_check = check_cross_dataset_spec_consistency(audits)

    if errors or not audits:
        overall = "AUDIT_ERROR"
    elif "SYMBOL_MISMATCH" in statuses:
        overall = "SYMBOL_MISMATCH"
    elif "SYMBOL_UNVERIFIED" in statuses:
        overall = "SYMBOL_UNVERIFIED"
    elif "BROKER_MISMATCH" in statuses:
        overall = "BROKER_MISMATCH"
    elif "BROKER_UNVERIFIED" in statuses:
        overall = "BROKER_UNVERIFIED"
    elif cross_dataset_check["status"] == "mismatch":
        overall = "CROSS_DATASET_SPEC_MISMATCH"
    elif "CURRENCY_UNSUPPORTED" in statuses:
        overall = "CURRENCY_UNSUPPORTED"
    elif "CURRENCY_UNVERIFIED" in statuses:
        overall = "CURRENCY_UNVERIFIED"
    elif "CONFIG_MISMATCH" in statuses:
        overall = "CONFIG_MISMATCH"
    elif "CALC_MODE_MISMATCH" in statuses:
        overall = "CALC_MODE_MISMATCH"
    elif "CALC_MODE_UNSUPPORTED" in statuses:
        overall = "CALC_MODE_UNSUPPORTED"
    elif "CALC_MODE_UNVERIFIED" in statuses:
        overall = "CALC_MODE_UNVERIFIED"
    elif "TICK_VALUE_MISMATCH" in statuses:
        overall = "TICK_VALUE_MISMATCH"
    elif "MISSING_SPECIFICATIONS" in statuses:
        overall = "ASSUMPTIONS_ONLY"
    else:
        overall = "MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE"

    aggregated_warnings = []
    aggregated_reconciled = []
    for item in audits:
        aggregated_warnings.extend(item.get("warnings", []))
        aggregated_reconciled.extend(item.get("reconciled_discrepancies", []))
    aggregated_warnings = sorted(set(aggregated_warnings))
    aggregated_reconciled = sorted(set(aggregated_reconciled))

    return {
        "overall_status": overall,
        "data_dir": str(root),
        "dataset_count": len(audits),
        "default_config_assumptions": {
            name: getattr(config, name) for name in CONFIG_TO_MT5_FIELD
        },
        "required_spec_fields": list(REQUIRED_SPEC_FIELDS + REQUIRED_SPEC_STRING_FIELDS + REQUIRED_SPEC_MAPPING_FIELDS),
        "datasets": audits,
        "cross_dataset_matching": cross_dataset_check,
        "warnings": aggregated_warnings,
        "reconciled_discrepancies": aggregated_reconciled,
        "errors": errors,
        "provenance_caveat": "Matching instrument specifications and server labels do not independently authenticate that the OHLC history came from the named broker/feed.",
    }
