from __future__ import annotations

import json
from pathlib import PureWindowsPath

import pytest

from src.backtesting.engine import BacktestConfig
from src.research.execution_spec_audit import (
    audit_one_execution_specification,
    audit_processed_execution_specs,
    _stable_path_text,
)
from scripts.run_smc_backtest import run_backtest_pipeline
from scripts.run_smc_lifecycle_stress import run_lifecycle_stress
from scripts.run_smc_validation import run_validation_pipeline


def _complete_metadata():
    config = BacktestConfig()
    return {
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "broker_server": "MetaQuotes-Demo",
        "source": "MetaTrader 5 API",
        "source_verification_status": "declared_not_independently_verified",
        "execution_specification": {
            "status": "captured_complete",
            "symbol": "XAUUSD",
            "broker_server": "MetaQuotes-Demo",
            "captured_at_utc": "2026-10-20T00:00:00+00:00",
            "digits": 2,
            "point": config.point_size,
            "trade_contract_size": config.contract_size_oz,
            "currency_base": "XAU",
            "currency_profit": "USD",
            "account_currency": "USD",
            "volume_min": config.min_lot,
            "volume_step": config.lot_step,
            "volume_max": config.max_lots,
            "trade_tick_size": 0.01,
            "trade_tick_value": 1.0,
            "trade_calc_mode": 3,
            "trade_calc_mode_name": "SYMBOL_CALC_MODE_CFD",
            "trade_calc_mode_name_source": "MetaTrader5 module constants",
            "trade_calc_mode_constant_values": {"SYMBOL_CALC_MODE_CFD": 3},
        },
    }


def test_audit_missing_symbol_specs_is_assumptions_only():
    result = audit_one_execution_specification({"symbol": "XAUUSD", "timeframe": "M5"})
    assert result["status"] == "MISSING_SPECIFICATIONS"
    assert "point" in result["missing_required_fields"]
    assert result["provenance_independently_verified"] is False


def test_audit_rejects_nonpositive_tick_size_and_symbol_mismatch():
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_tick_size"] = 0
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "MISSING_SPECIFICATIONS"
    assert "trade_tick_size" in result["missing_required_fields"]

    metadata = _complete_metadata()
    metadata["execution_specification"]["symbol"] = "XAUUSD.a"
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "SYMBOL_MISMATCH"


def test_audit_rejects_broker_server_mismatch():
    metadata = _complete_metadata()
    metadata["execution_specification"]["broker_server"] = "Different-Demo-Server"
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "BROKER_MISMATCH"


def test_audit_does_not_strictly_accept_missing_sidecar_broker_identity():
    metadata = _complete_metadata()
    metadata.pop("broker_server")
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "BROKER_UNVERIFIED"


def test_audit_does_not_strictly_accept_missing_symbol_identity():
    metadata = _complete_metadata()
    metadata["execution_specification"].pop("symbol")
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "SYMBOL_UNVERIFIED"


def test_audit_rejects_non_usd_account_currency():
    metadata = _complete_metadata()
    metadata["execution_specification"]["account_currency"] = "EUR"
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "CURRENCY_UNSUPPORTED"


def test_audit_cross_checks_tick_value_against_contract_and_tick_size():
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_tick_value"] = 5.0
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "TICK_VALUE_MISMATCH"
    assert result["tick_value_check"]["status"] == "mismatch"


def test_audit_matching_captured_specs_and_preserves_provenance_warning():
    result = audit_one_execution_specification(_complete_metadata())
    assert result["status"] == "MATCHED_CAPTURED_DEFAULTS"
    assert result["mismatches"] == []
    assert result["provenance_independently_verified"] is False
    assert result["source_verification_status"] == "declared_not_independently_verified"


def test_audit_detects_contract_and_point_mismatch():
    metadata = _complete_metadata()
    metadata["execution_specification"]["point"] = 0.001
    metadata["execution_specification"]["trade_contract_size"] = 1.0
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "CONFIG_MISMATCH"
    assert {item["config_field"] for item in result["mismatches"]} == {"point_size", "contract_size_oz"}


def test_stable_sidecar_path_serialization_normalizes_windows_separators():
    windows_path = PureWindowsPath(r"data\processed\XAUUSD_M5_clean.meta.json")
    assert _stable_path_text(windows_path) == "data/processed/XAUUSD_M5_clean.meta.json"


def test_directory_audit_writes_assumptions_only_for_legacy_sidecars(tmp_path):
    meta = {
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "source": "MetaTrader 5 API",
        "source_verification_status": "declared_not_independently_verified",
    }
    (tmp_path / "XAUUSD_M5_clean.meta.json").write_text(json.dumps(meta))
    result = audit_processed_execution_specs(tmp_path)
    assert result["overall_status"] == "ASSUMPTIONS_ONLY"
    assert result["dataset_count"] == 1
    assert result["datasets"][0]["status"] == "MISSING_SPECIFICATIONS"
    # Audit snapshots should serialize path separators identically on Windows/POSIX.
    sidecar_path = result["datasets"][0]["sidecar_path"]
    assert sidecar_path.endswith("XAUUSD_M5_clean.meta.json")
    assert "\\" not in sidecar_path


def test_strict_backtest_gate_blocks_before_run_when_specs_missing(tmp_path):
    with pytest.raises(RuntimeError, match="Execution specification gate blocked"):
        run_backtest_pipeline(
            data_dir=tmp_path,
            output_dir=tmp_path / "reports",
            timeframes=["M5"],
            require_matched_execution_spec=True,
        )


def test_strict_lifecycle_gate_blocks_when_specs_missing(tmp_path):
    with pytest.raises(RuntimeError, match="Execution specification gate blocked lifecycle stress"):
        run_lifecycle_stress(
            data_dir=tmp_path,
            output_dir=tmp_path / "reports",
            timeframes=["M5"],
            horizons_hours=[4],
            require_matched_execution_spec=True,
        )


def test_strict_holdout_gate_blocks_when_specs_missing(tmp_path):
    with pytest.raises(RuntimeError, match="Execution specification gate blocked holdout validation"):
        run_validation_pipeline(
            data_dir=tmp_path,
            output_dir=tmp_path / "reports",
            timeframes=["M5"],
            require_matched_execution_spec=True,
        )


def test_audit_rejects_nan_in_required_numeric_field():
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_contract_size"] = float("nan")
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "MISSING_SPECIFICATIONS"
    assert "trade_contract_size" in result["missing_required_fields"]
    assert "trade_contract_size" in result["wrong_type_fields"]


def test_audit_rejects_infinity_in_required_numeric_field():
    metadata = _complete_metadata()
    metadata["execution_specification"]["point"] = float("inf")
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "MISSING_SPECIFICATIONS"
    assert "point" in result["missing_required_fields"]
    assert "point" in result["wrong_type_fields"]


def test_audit_rejects_boolean_in_required_numeric_field_and_explains_type():
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_tick_size"] = True
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "MISSING_SPECIFICATIONS"
    assert "trade_tick_size" in result["missing_required_fields"]
    assert "trade_tick_size" in result["wrong_type_fields"]


def test_audit_rejects_digits_zero():
    metadata = _complete_metadata()
    metadata["execution_specification"]["digits"] = 0
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "MISSING_SPECIFICATIONS"
    assert "digits" in result["missing_required_fields"]


def test_audit_rejects_missing_account_currency_as_unverified():
    metadata = _complete_metadata()
    metadata["execution_specification"]["account_currency"] = None
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "CURRENCY_UNVERIFIED"
    assert "account_currency" in result["missing_currency_fields"]


def test_audit_rejects_malformed_numeric_string_as_wrong_type():
    metadata = _complete_metadata()
    metadata["execution_specification"]["point"] = "not-a-number"
    result = audit_one_execution_specification(metadata)
    assert "point" in result["missing_required_fields"]
    assert "point" in result["wrong_type_fields"]


def test_audit_rejects_negative_and_fractional_digits():
    for invalid_digits in (-1, 1.5):
        metadata = _complete_metadata()
        metadata["execution_specification"]["digits"] = invalid_digits
        result = audit_one_execution_specification(metadata)
        assert result["status"] == "MISSING_SPECIFICATIONS"
        assert "digits" in result["missing_required_fields"]


@pytest.mark.parametrize("calc_mode_name", [
    "SYMBOL_CALC_MODE_FOREX",
    "SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE",
    "SYMBOL_CALC_MODE_CFD",
    "SYMBOL_CALC_MODE_CFDINDEX",
    "SYMBOL_CALC_MODE_CFDLEVERAGE",
    "SYMBOL_CALC_MODE_EXCH_STOCKS",
    "SYMBOL_CALC_MODE_EXCH_STOCKS_MOEX",
])
def test_audit_accepts_only_documented_linear_contract_size_profit_modes(calc_mode_name):
    metadata = _complete_metadata()
    # The numeric enum is captured for traceability but never decoded via a guessed ID.
    metadata["execution_specification"]["trade_calc_mode"] = 987
    metadata["execution_specification"]["trade_calc_mode_name"] = calc_mode_name
    metadata["execution_specification"]["trade_calc_mode_constant_values"] = {calc_mode_name: 987}
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "MATCHED_CAPTURED_DEFAULTS"
    assert result["trade_calc_mode"] == 987
    assert result["trade_calc_mode_name"] == calc_mode_name
    assert result["trade_calc_mode_allowlisted"] is True
    assert result["trade_calc_mode_status"] == "supported_linear_contract_size_formula"
    assert result["tick_value_check"]["status"] == "match"


@pytest.mark.parametrize("calc_mode_name", [
    "SYMBOL_CALC_MODE_FUTURES",
    "SYMBOL_CALC_MODE_EXCH_FUTURES",
    "SYMBOL_CALC_MODE_EXCH_FUTURES_FORTS",
    "SYMBOL_CALC_MODE_EXCH_BONDS",
    "SYMBOL_CALC_MODE_EXCH_BONDS_MOEX",
    "SYMBOL_CALC_MODE_SERV_COLLATERAL",
    "SYMBOL_CALC_MODE_EXCH_OPTIONS_MARGIN",
    "SYMBOL_CALC_MODE_UNKNOWN_NEW_VALUE",
])
def test_audit_blocks_unsupported_or_unknown_calculation_modes(calc_mode_name):
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_calc_mode"] = 987
    metadata["execution_specification"]["trade_calc_mode_name"] = calc_mode_name
    metadata["execution_specification"]["trade_calc_mode_constant_values"] = {calc_mode_name: 987}
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "CALC_MODE_UNSUPPORTED"
    assert result["trade_calc_mode_allowlisted"] is False
    assert result["tick_value_check"]["status"] == "not_evaluated"
    assert result["trade_calc_mode_name"] == calc_mode_name


def test_audit_blocks_missing_or_malformed_calculation_mode():
    for value in (None, True, -1, 3.5, "unknown"):
        metadata = _complete_metadata()
        metadata["execution_specification"]["trade_calc_mode"] = value
        result = audit_one_execution_specification(metadata)
        assert result["status"] == "CALC_MODE_UNVERIFIED", value
        assert result["trade_calc_mode_allowlisted"] is False
        assert result["tick_value_check"]["status"] == "not_evaluated"
        if value is None:
            assert "trade_calc_mode" in result["missing_required_fields"]


def test_audit_requires_capture_resolved_calc_mode_name_and_source():
    for field in ("trade_calc_mode_name", "trade_calc_mode_name_source"):
        metadata = _complete_metadata()
        metadata["execution_specification"].pop(field)
        result = audit_one_execution_specification(metadata)
        assert result["status"] == "CALC_MODE_UNVERIFIED"
        assert field in result["missing_required_fields"]


def test_audit_reports_calc_mode_code_name_mismatch():
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_calc_mode"] = 3
    metadata["execution_specification"]["trade_calc_mode_name"] = "SYMBOL_CALC_MODE_CFD"
    metadata["execution_specification"]["trade_calc_mode_constant_values"] = {"SYMBOL_CALC_MODE_CFD": 4}
    result = audit_one_execution_specification(metadata)
    assert result["status"] == "CALC_MODE_MISMATCH"
    assert result["trade_calc_mode_code_matches_name"] is False
    assert result["trade_calc_mode_allowlisted"] is False
    assert result["tick_value_check"]["status"] == "not_evaluated"


def test_audit_directory_overall_status_blocks_unsupported_calc_mode(tmp_path):
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_calc_mode"] = 987
    metadata["execution_specification"]["trade_calc_mode_name"] = "SYMBOL_CALC_MODE_FUTURES"
    metadata["execution_specification"]["trade_calc_mode_constant_values"] = {"SYMBOL_CALC_MODE_FUTURES": 987}
    (tmp_path / "XAUUSD_M15_clean.meta.json").write_text(json.dumps(metadata), encoding="utf-8")
    result = audit_processed_execution_specs(tmp_path)
    assert result["overall_status"] == "CALC_MODE_UNSUPPORTED"


def test_strict_backtest_gate_blocks_unsupported_calc_mode_before_csv_load(tmp_path):
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_calc_mode"] = 987
    metadata["execution_specification"]["trade_calc_mode_name"] = "SYMBOL_CALC_MODE_FUTURES"  # tick-price formula
    metadata["execution_specification"]["trade_calc_mode_constant_values"] = {"SYMBOL_CALC_MODE_FUTURES": 987}
    (tmp_path / "XAUUSD_M5_clean.meta.json").write_text(json.dumps(metadata), encoding="utf-8")
    # No OHLC CSV is present: strict preflight must reject the mode before data loading.
    with pytest.raises(RuntimeError, match="CALC_MODE_UNSUPPORTED"):
        run_backtest_pipeline(
            data_dir=tmp_path,
            output_dir=tmp_path / "reports",
            timeframes=["M5"],
            require_matched_execution_spec=True,
        )


def test_tick_value_discrepancy_blocks_execution_spec_audit_and_backtest(tmp_path):
    """
    Demonstrates the broker configuration observed on MetaQuotes-Demo:
    trade_contract_size=100.0 and trade_tick_size=0.01 implies $1.00/tick for 1.0 lot,
    but trade_tick_value=0.1 (likely calibrated to 0.1 lot).
    The audit MUST remain blocked on TICK_VALUE_MISMATCH and refuse backtest execution.
    """
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_calc_mode"] = 4
    metadata["execution_specification"]["trade_calc_mode_name"] = "SYMBOL_CALC_MODE_CFDLEVERAGE"
    metadata["execution_specification"]["trade_calc_mode_constant_values"] = {"SYMBOL_CALC_MODE_CFDLEVERAGE": 4}
    metadata["execution_specification"]["trade_contract_size"] = 100.0
    metadata["execution_specification"]["trade_tick_size"] = 0.01
    metadata["execution_specification"]["trade_tick_value"] = 0.1
    metadata["execution_specification"]["trade_tick_value_profit"] = 0.1

    res = audit_one_execution_specification(metadata)
    assert res["status"] == "TICK_VALUE_MISMATCH"
    assert res["tick_value_check"]["captured_tick_value"] == 0.1
    assert res["tick_value_check"]["expected_contract_times_tick_size"] == 1.0

    (tmp_path / "XAUUSD_M5_clean.meta.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(RuntimeError, match="TICK_VALUE_MISMATCH"):
        run_backtest_pipeline(
            data_dir=tmp_path,
            output_dir=tmp_path / "reports",
            timeframes=["M5"],
            require_matched_execution_spec=True,
        )


def test_tick_value_reconciliation_accepts_verified_empirical_inquiry():
    """
    When MT5 symbol_info.trade_tick_value=0.1 disagrees with contract formula,
    but a valid empirical order_calc_profit reconciliation is attached confirming
    exact 1.00 USD/tick for 1.0 lot, the audit must reconcile and match defaults.
    """
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_calc_mode"] = 4
    metadata["execution_specification"]["trade_calc_mode_name"] = "SYMBOL_CALC_MODE_CFDLEVERAGE"
    metadata["execution_specification"]["trade_calc_mode_constant_values"] = {"SYMBOL_CALC_MODE_CFDLEVERAGE": 4}
    metadata["execution_specification"]["trade_contract_size"] = 100.0
    metadata["execution_specification"]["trade_tick_size"] = 0.01
    metadata["execution_specification"]["trade_tick_value"] = 0.1
    metadata["execution_specification"]["trade_tick_value_profit"] = 0.1
    metadata["execution_specification"]["trade_tick_value_loss"] = 0.1
    metadata["execution_specification"]["tick_value_reconciliation"] = {
        "reconciliation_status": "linear_contract_size_verified_by_terminal_api",
        "authoritative_calculation_method": "contract_size_linear_formula_verified_by_order_calc_profit",
        "contract_size": 100.0,
        "tick_size": 0.01,
        "reported_property_tick_value": 0.1,
        "formula_expected_tick_value": 1.0,
        "inquired_order_calc_profit_1lot": 1.0,
        "discrepancy_detected": True,
        "discrepancy_fields": ["symbol_info.trade_tick_value"],
        "inquiry_evidence": [
            {"volume": 1.0, "buy_favorable_1tick": 1.0, "buy_adverse_1tick": -1.0, "sell_favorable_1tick": 1.0, "sell_adverse_1tick": -1.0, "expected_linear_profit": 1.0},
            {"volume": 0.1, "buy_favorable_1tick": 0.1, "buy_adverse_1tick": -0.1, "sell_favorable_1tick": 0.1, "sell_adverse_1tick": -0.1, "expected_linear_profit": 0.1},
        ],
    }

    res = audit_one_execution_specification(metadata)
    assert res["status"] == "MATCHED_CAPTURED_DEFAULTS"
    assert res["tick_value_status"] == "reconciled_via_order_calc_profit"
    assert res["reconciliation_verified"] is True
    assert len(res["warnings"]) > 0
    assert "TICK_VALUE_RECONCILED" in res["warnings"][0]
    assert len(res["reconciled_discrepancies"]) == 1


def test_tick_value_reconciliation_rejects_failed_or_disagreeing_inquiry():
    """
    If the inquiry status failed or the inquired 1-lot profit does not match
    the expected linear contract calculation, reconciliation must fail closed.
    """
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_contract_size"] = 100.0
    metadata["execution_specification"]["trade_tick_size"] = 0.01
    metadata["execution_specification"]["trade_tick_value"] = 0.1
    metadata["execution_specification"]["tick_value_reconciliation"] = {
        "reconciliation_status": "verification_failed",
        "authoritative_calculation_method": "contract_size_linear_formula_verified_by_order_calc_profit",
        "inquired_order_calc_profit_1lot": 0.5,  # disagrees with expected 1.0
    }

    res = audit_one_execution_specification(metadata)
    assert res["status"] == "TICK_VALUE_MISMATCH"
    assert res["reconciliation_verified"] is False
    assert res["tick_value_check"]["status"] == "mismatch"


def test_cross_dataset_spec_matching_across_timeframes(tmp_path):
    """
    Audits 4 timeframes (H4, H1, M15, M5) sharing identical specifications.
    Verifies cross-dataset check reports consistent and overall status passes.
    """
    from src.research.execution_spec_audit import check_cross_dataset_spec_consistency

    timeframes = ["H4", "H1", "M15", "M5"]
    audits = []
    for tf in timeframes:
        meta = _complete_metadata()
        meta["timeframe"] = tf
        audits.append(audit_one_execution_specification(meta))

    cross_check = check_cross_dataset_spec_consistency(audits)
    assert cross_check["status"] == "consistent"
    assert cross_check["mismatches"] == []
    assert cross_check["dataset_count"] == 4


def test_cross_dataset_spec_mismatch_detected(tmp_path):
    """
    If one dataset has a conflicting contract size or tick size,
    cross-dataset consistency must flag the mismatch and block overall status.
    """
    from src.research.execution_spec_audit import check_cross_dataset_spec_consistency

    meta_h1 = _complete_metadata()
    meta_h1["timeframe"] = "H1"
    meta_h1["execution_specification"]["trade_contract_size"] = 100.0

    meta_m5 = _complete_metadata()
    meta_m5["timeframe"] = "M5"
    meta_m5["execution_specification"]["trade_contract_size"] = 10.0  # conflicting contract size!

    audits = [
        audit_one_execution_specification(meta_h1),
        audit_one_execution_specification(meta_m5),
    ]
    cross_check = check_cross_dataset_spec_consistency(audits)
    assert cross_check["status"] == "mismatch"
    assert any("trade_contract_size differs" in m for m in cross_check["mismatches"])

    # Write sidecars and verify audit_processed_execution_specs sets CROSS_DATASET_SPEC_MISMATCH
    (tmp_path / "XAUUSD_H1_clean.meta.json").write_text(json.dumps(meta_h1), encoding="utf-8")
    (tmp_path / "XAUUSD_M5_clean.meta.json").write_text(json.dumps(meta_m5), encoding="utf-8")

    processed_audit = audit_processed_execution_specs(tmp_path)
    assert processed_audit["overall_status"] == "CROSS_DATASET_SPEC_MISMATCH"


def test_fail_closed_when_mt5_unavailable_or_uninitialized(monkeypatch):
    """
    When MT5 is unavailable, capture must fail-closed with status 'unavailable'
    and refuse to fabricate specification fields.
    """
    from src.data import loader
    monkeypatch.setattr(loader, "mt5", None)
    spec = loader.capture_symbol_execution_specification("XAUUSD")
    assert spec["status"] == "unavailable"
    assert spec["point"] is None
    assert spec["trade_contract_size"] is None
    assert spec["tick_value_reconciliation"] is None


def test_protection_against_bypassing_gate_through_direct_calls(tmp_path):
    """
    Directly calling run_backtest_pipeline without passing flags must still
    refuse to execute on fatal spec mismatches (e.g. TICK_VALUE_MISMATCH).
    """
    metadata = _complete_metadata()
    metadata["execution_specification"]["trade_tick_value"] = 999.0
    (tmp_path / "XAUUSD_M5_clean.meta.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Execution specification gate blocked the backtest due to spec mismatch"):
        run_backtest_pipeline(
            data_dir=tmp_path,
            output_dir=tmp_path / "reports",
            timeframes=["M5"],
            require_matched_execution_spec=False,  # direct call attempting bypass
        )


