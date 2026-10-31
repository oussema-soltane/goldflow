"""Tests for Stage 2 (P1): Frozen SMC Config Enforcement.

Ensures that:
1. configs/smc_v1_frozen.json is strictly validated against expected schema and required fields.
2. Missing or bad fields raise RuntimeError and prevent Phase 4 execution.
3. Frozen JSON values correctly map to SMCConfig, SMCSetupConfig, and BacktestConfig.
4. Altered JSON parameters change runtime behavior, not ignored in favor of defaults.
5. SHA-256 of frozen config bytes is stored in the validation payload.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_smc_phase4_validation import (
    FROZEN_CONFIG_PATH,
    _frozen_config_sha256,
    _frozen_to_backtest_config,
    _frozen_to_setup_config,
    _frozen_to_smc_config,
    _load_and_validate_frozen_config,
)
from src.backtesting.engine import BacktestConfig


class TestFrozenConfigSchema:
    def test_canonical_frozen_config_passes_validation(self):
        cfg = _load_and_validate_frozen_config(FROZEN_CONFIG_PATH)
        assert cfg["_schema"] == "smc_v1_frozen_strategy"
        assert cfg["_strategy_name"] == "SMC v1"
        assert "strategy_rules" in cfg

    def test_missing_file_raises_not_found(self, tmp_path):
        non_existent = tmp_path / "missing.json"
        with pytest.raises(FileNotFoundError):
            _load_and_validate_frozen_config(non_existent)

    def test_schema_mismatch_raises_runtime_error(self, tmp_path):
        bad_cfg = tmp_path / "bad_schema.json"
        bad_cfg.write_text(json.dumps({
            "_schema": "wrong_schema_v2",
            "strategy_rules": {},
        }), encoding="utf-8")
        with pytest.raises(RuntimeError, match="schema mismatch"):
            _load_and_validate_frozen_config(bad_cfg)

    def test_missing_required_field_raises_runtime_error(self, tmp_path):
        # Load valid config, remove swing_identification.swing_window_k
        valid = json.loads(FROZEN_CONFIG_PATH.read_text(encoding="utf-8"))
        del valid["strategy_rules"]["swing_identification"]["swing_window_k"]

        bad_cfg = tmp_path / "missing_field.json"
        bad_cfg.write_text(json.dumps(valid), encoding="utf-8")

        with pytest.raises(RuntimeError, match="missing required fields"):
            _load_and_validate_frozen_config(bad_cfg)


class TestFrozenConfigMapping:
    @pytest.fixture
    def canonical_cfg(self):
        return _load_and_validate_frozen_config(FROZEN_CONFIG_PATH)

    def test_smc_config_mapped_from_frozen(self, canonical_cfg):
        smc_cfg = _frozen_to_smc_config(canonical_cfg)
        rules = canonical_cfg["strategy_rules"]

        assert smc_cfg.swing_window == int(rules["swing_identification"]["swing_window_k"])
        assert smc_cfg.equal_level_tolerance == float(rules["liquidity_pool"]["equal_level_tolerance_price_units"])
        assert smc_cfg.min_sweep_penetration == float(rules["sweep_identification"]["min_penetration_price_units"])
        assert smc_cfg.order_block_lookback == int(rules["order_block"]["lookback_bars"])
        assert smc_cfg.order_block_zone_basis == str(rules["order_block"]["zone_basis"])
        assert smc_cfg.track_order_block_lifecycle is True

    def test_setup_config_mapped_from_frozen(self, canonical_cfg):
        setup_cfg = _frozen_to_setup_config(canonical_cfg)
        rules = canonical_cfg["strategy_rules"]

        assert setup_cfg.max_sweep_to_choch_bars == int(rules["sweep_identification"]["max_sweep_to_choch_bars"])
        assert setup_cfg.max_bars_choch_to_retest == int(rules["retest_conditions"]["max_bars_choch_to_retest"])
        assert setup_cfg.stop_buffer == float(rules["stop_loss"]["stop_buffer_price_units"])
        assert setup_cfg.fixed_rr == float(rules["take_profit"]["fixed_rr_fallback"])

    def test_backtest_config_mapped_from_frozen(self, canonical_cfg):
        bc = _frozen_to_backtest_config(canonical_cfg)
        rules = canonical_cfg["strategy_rules"]

        assert bc.initial_capital == float(rules["risk_management"]["initial_capital_usd"])
        assert bc.risk_fraction == float(rules["risk_management"]["risk_fraction"])
        assert bc.fallback_spread_usd == float(rules["execution_costs"]["fallback_spread_usd"])
        assert bc.slippage_per_side_usd == float(rules["execution_costs"]["slippage_per_side_usd"])
        assert bc.commission_per_lot_per_side == float(rules["execution_costs"]["commission_per_lot_per_side_usd"])

    def test_altered_frozen_json_changes_runtime_config(self, canonical_cfg):
        # Alter swing_window_k to 5 in copy
        altered = json.loads(json.dumps(canonical_cfg))
        altered["strategy_rules"]["swing_identification"]["swing_window_k"] = 5
        smc_cfg = _frozen_to_smc_config(altered)
        assert smc_cfg.swing_window == 5, "Runtime config must reflect altered frozen JSON"

    def test_frozen_config_sha256(self):
        sha = _frozen_config_sha256(FROZEN_CONFIG_PATH)
        assert len(sha) == 64
        assert sha == "1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a"
