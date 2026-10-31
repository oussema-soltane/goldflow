"""Phase 5 regression tests.

These tests guard:
  - Frozen config hash integrity.
  - Phase 5 runner's frozen-hash gate (blocks if hash mismatches).
  - Path separator normalization (the Stage B fix).
  - Cost scenario monotonicity (higher costs cannot improve P&L vs. baseline).
  - Missing-data and empty-candidate handling in the runner.
  - Dataset hash utility correctness.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
FROZEN_CONFIG_PATH = ROOT / "configs" / "smc_v1_frozen.json"
EXPECTED_SHA256 = "1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a"


# ---------------------------------------------------------------------------
# Frozen config integrity
# ---------------------------------------------------------------------------

def test_frozen_config_sha256_still_matches():
    """The frozen SMC v1 configuration must remain unmodified throughout Phase 5."""
    actual = hashlib.sha256(FROZEN_CONFIG_PATH.read_bytes()).hexdigest()
    assert actual == EXPECTED_SHA256, (
        f"Frozen config hash changed: expected {EXPECTED_SHA256}, got {actual}. "
        "Do not modify the frozen configuration."
    )


def test_frozen_config_is_valid_json_with_required_keys():
    """The frozen config must parse as JSON and contain the required schema keys."""
    data = json.loads(FROZEN_CONFIG_PATH.read_text(encoding="utf-8"))
    assert data.get("_schema") == "smc_v1_frozen_strategy"
    assert "strategy_rules" in data
    assert "execution_costs" in data["strategy_rules"]
    assert "risk_management" in data["strategy_rules"]


# ---------------------------------------------------------------------------
# Path separator normalization (Stage B fix)
# ---------------------------------------------------------------------------

def test_portable_uses_forward_slashes_on_windows():
    """_portable() must return POSIX-style paths regardless of OS."""
    from scripts.run_smc_mtf_backtest import ROOT as MTF_ROOT, _portable_execution_audit_paths

    audit = {
        "data_dir": str(MTF_ROOT / "data" / "processed"),
        "datasets": [
            {"sidecar_path": str(MTF_ROOT / "data" / "processed" / "XAUUSD_M5_clean.meta.json")},
            {"symbol": "XAUUSD"},
        ],
    }
    portable = _portable_execution_audit_paths(audit)
    assert "/" in portable["data_dir"] and "\\" not in portable["data_dir"], (
        "_portable must use forward slashes; got: " + portable["data_dir"]
    )
    assert "/" in portable["datasets"][0]["sidecar_path"] and "\\" not in portable["datasets"][0]["sidecar_path"]


# ---------------------------------------------------------------------------
# Phase 5 runner — frozen hash gate
# ---------------------------------------------------------------------------

def test_phase5_runner_blocks_on_frozen_hash_mismatch(tmp_path):
    """Runner must raise RuntimeError when frozen config hash does not match expected."""
    import scripts.run_phase5_validation as runner

    original_expected = runner.EXPECTED_FROZEN_SHA256
    try:
        # Temporarily override the expected hash with something wrong.
        runner.EXPECTED_FROZEN_SHA256 = "0" * 64
        with pytest.raises(RuntimeError, match="hash mismatch"):
            runner.run_phase5_pipeline(
                data_dir=ROOT / "data" / "processed",
                output_dir=tmp_path,
            )
    finally:
        runner.EXPECTED_FROZEN_SHA256 = original_expected


def test_phase5_runner_raises_on_missing_data_dir(tmp_path):
    """Runner must raise when the data directory does not exist."""
    import scripts.run_phase5_validation as runner

    nonexistent = tmp_path / "no_such_dir"
    with pytest.raises((RuntimeError, FileNotFoundError, Exception)):
        runner.run_phase5_pipeline(
            data_dir=nonexistent,
            output_dir=tmp_path,
        )


# ---------------------------------------------------------------------------
# Cost scenario monotonicity
# ---------------------------------------------------------------------------

def test_cost_replay_higher_costs_cannot_improve_net_profit():
    """Replay with higher spread or commission must not produce a higher net P&L."""
    from src.backtesting.engine import replay_trade_ledger_costs

    # Construct a minimal synthetic trade with known gross PnL.
    trade = {
        "status": "CLOSED",
        "side": "LONG",
        "lots": 0.1,
        "raw_gross_pnl": 100.0,          # $100 pre-cost gross
        "entry_spread_usd": 0.20,
        "exit_spread_usd": 0.20,
        "exit_reason": "TAKE_PROFIT",
        "estimated_stop_risk_cash": 50.0,
    }
    base = replay_trade_ledger_costs([trade], spread_multiplier=1.0, slippage_per_side_usd=0.05)
    costly = replay_trade_ledger_costs([trade], spread_multiplier=3.0, slippage_per_side_usd=0.15,
                                       commission_per_lot_per_side=3.0)
    assert base["net_profit"] >= costly["net_profit"], (
        "Higher costs must not produce a higher net P&L. "
        f"Base: {base['net_profit']}, Costly: {costly['net_profit']}"
    )


def test_cost_replay_zero_cost_equals_raw_gross():
    """At zero costs, replay net P&L should equal raw gross P&L."""
    from src.backtesting.engine import replay_trade_ledger_costs

    trade = {
        "status": "CLOSED",
        "side": "SHORT",
        "lots": 0.5,
        "raw_gross_pnl": 75.0,
        "entry_spread_usd": 0.0,
        "exit_spread_usd": 0.0,
        "exit_reason": "STOP_LOSS",
        "estimated_stop_risk_cash": 50.0,
    }
    result = replay_trade_ledger_costs(
        [trade],
        spread_multiplier=1.0,
        slippage_per_side_usd=0.0,
        commission_per_lot_per_side=0.0,
        override_spread_usd=0.0,
    )
    assert abs(result["net_profit"] - 75.0) < 1e-6, (
        f"Expected net profit = raw gross = 75.0, got {result['net_profit']}"
    )


# ---------------------------------------------------------------------------
# Dataset hash utility
# ---------------------------------------------------------------------------

def test_dataset_hashes_are_stable_and_match_raw_sha256(tmp_path):
    """_dataset_hashes must produce SHA-256 consistent with direct computation."""
    import scripts.run_phase5_validation as runner

    # Create a temporary CSV with known content.
    csv = tmp_path / "XAUUSD_M15_clean.csv"
    csv.write_bytes(b"time,open,high,low,close\n2026-01-01,2000,2010,1990,2005\n")
    expected = hashlib.sha256(csv.read_bytes()).hexdigest()

    hashes = runner._dataset_hashes(tmp_path)
    assert "XAUUSD_M15_clean.csv" in hashes
    assert hashes["XAUUSD_M15_clean.csv"] == expected


# ---------------------------------------------------------------------------
# Cost scenarios completeness
# ---------------------------------------------------------------------------

def test_phase5_cost_scenarios_include_required_variants():
    """The COST_SCENARIOS list must include baseline, spread, slippage, commission, and adverse."""
    from scripts.run_phase5_validation import COST_SCENARIOS

    labels = {s["label"] for s in COST_SCENARIOS}
    required = {"baseline", "spread_2x", "slippage_3x", "commission_3usd", "adverse_all"}
    missing = required - labels
    assert not missing, f"Missing cost scenario labels: {missing}"


# ---------------------------------------------------------------------------
# Finding A regression: M15 baseline cost replay filtering and exact reconciliation
# ---------------------------------------------------------------------------

def test_cost_replay_filters_m15_baseline_properly():
    """Replay of M15 baseline must evaluate strictly M15 baseline trades, not all trades."""
    from scripts.run_phase5_validation import _run_cost_scenarios

    trades_csv = ROOT / "reports" / "phase5" / "smc_mtf_trades.csv"
    if not trades_csv.exists():
        pytest.skip("Phase 5 trades CSV not found; skipping integration assertion")

    df = pd.read_csv(trades_csv)
    m15_baseline_trades = df[(df["timeframe"] == "M15") & (df["strategy_variant"] == "SMC_v1_baseline")].to_dict(orient="records")

    results = _run_cost_scenarios(m15_baseline_trades)
    baseline_scenario = next(r for r in results if r["scenario"] == "baseline")

    # M15 baseline on the valid evaluation window (time <= 2026-10-20 13:00 UTC) has 36 rule exits
    assert baseline_scenario["rule_exit_trades"] == 36
    # Net profit must be near -$884.02, NOT -$6,109.68 (which was all 1174 trades)
    assert abs(baseline_scenario["net_profit"] - (-884.02)) < 1.0
    assert baseline_scenario["net_profit"] > -1500.0, "Must not include M5 losses or full-corpus trades"


def test_cost_replay_exact_reconciliation_zero_cent_difference():
    """Backtest net P&L and baseline cost-replay net P&L must reconcile with $0.00 difference."""
    from scripts.run_phase5_validation import _run_cost_scenarios

    trades_csv = ROOT / "reports" / "phase5" / "smc_mtf_trades.csv"
    if not trades_csv.exists():
        pytest.skip("Phase 5 trades CSV not found; skipping integration assertion")

    df = pd.read_csv(trades_csv)
    # Phase 6D.1 BUG FIX: was incorrectly filtering by "M15" in both iterations of the loop,
    # meaning the M5 iteration never actually evaluated M5 trades. Fixed to use the `tf` variable.
    for tf in ("M15", "M5"):
        for variant in ("SMC_v1_baseline", "SMC_v1_H4_H1_confirmed"):
            variant_trades = df[(df["timeframe"] == tf) & (df["strategy_variant"] == variant)].to_dict(orient="records")
            if not variant_trades:
                continue
            backtest_net = sum(float(t["net_pnl"]) for t in variant_trades)
            replay_res = _run_cost_scenarios(variant_trades)
            baseline_replay = next(r for r in replay_res if r["scenario"] == "baseline")
            diff = abs(backtest_net - baseline_replay["net_profit"])
            assert diff < 0.01, (
                f"{tf} {variant} has non-zero discrepancy between backtest (${backtest_net:.4f}) "
                f"and cost replay (${baseline_replay['net_profit']:.4f}): diff = ${diff:.4f}"
            )


# ---------------------------------------------------------------------------
# Finding B regression: evaluation windows and intersections
# ---------------------------------------------------------------------------

def test_dataset_evaluation_windows_and_intersections():
    """Verify true chronological coverage: M15 starts 2026-08-04, M5 starts 2025-05-13, 4-way starts 2026-08-04."""
    data_dir = ROOT / "data" / "processed"
    m15_csv = data_dir / "XAUUSD_M15_clean.csv"
    m5_csv = data_dir / "XAUUSD_M5_clean.csv"
    h1_csv = data_dir / "XAUUSD_H1_clean.csv"
    h4_csv = data_dir / "XAUUSD_H4_clean.csv"

    if not all(p.exists() for p in (m15_csv, m5_csv, h1_csv, h4_csv)):
        pytest.skip("Processed datasets not found")

    m15_df = pd.read_csv(m15_csv)
    m5_df = pd.read_csv(m5_csv)
    h1_df = pd.read_csv(h1_csv)
    h4_df = pd.read_csv(h4_csv)

    for frame in (m15_df, m5_df, h1_df, h4_df):
        frame["time"] = pd.to_datetime(frame["time"], utc=True)

    # M15 starts in Aug 2026 (~2.5 months), NOT May 2025 (~17 months)
    assert m15_df["time"].iloc[0] == pd.Timestamp("2026-08-04 12:00:00+00:00")
    assert m5_df["time"].iloc[0] == pd.Timestamp("2025-05-13 22:15:00+00:00")

    # True 4-way intersection start is bounded by M15 start (2026-08-04 12:00:00 UTC)
    four_way_start = max(m15_df["time"].iloc[0], m5_df["time"].iloc[0], h1_df["time"].iloc[0], h4_df["time"].iloc[0])
    four_way_end = min(m15_df["time"].iloc[-1], m5_df["time"].iloc[-1], h1_df["time"].iloc[-1], h4_df["time"].iloc[-1])

    assert four_way_start == pd.Timestamp("2026-08-04 12:00:00+00:00")
    assert four_way_end == pd.Timestamp("2026-10-20 09:00:00+00:00")


# ---------------------------------------------------------------------------
# Finding C regression: empirical break-even win rate & denominator calculations
# ---------------------------------------------------------------------------

def test_empirical_breakeven_calculation_m15_mtf():
    """Verify empirical break-even win rate on the valid M15 MTF sample (8 trades)."""
    trades_csv = ROOT / "reports" / "phase5" / "smc_mtf_trades.csv"
    if not trades_csv.exists():
        pytest.skip("Phase 5 trades CSV not found")

    df = pd.read_csv(trades_csv)
    m15_mtf = df[(df["timeframe"] == "M15") & (df["strategy_variant"] == "SMC_v1_H4_H1_confirmed") & (df["status"] == "CLOSED")]

    assert len(m15_mtf) == 8
    wins = m15_mtf[m15_mtf["net_pnl"] > 0]
    losses = m15_mtf[m15_mtf["net_pnl"] < 0]

    # Cash-based break-even
    avg_win = wins["net_pnl"].mean()
    avg_loss = abs(losses["net_pnl"].mean())
    payoff_ratio = avg_win / avg_loss
    p_be_dollar = 1.0 / (1.0 + payoff_ratio)

    # R-multiple-based break-even
    avg_win_r = wins["R_multiple"].mean()
    avg_loss_r = abs(losses["R_multiple"].mean())
    payoff_ratio_r = avg_win_r / avg_loss_r
    p_be_r = 1.0 / (1.0 + payoff_ratio_r)

    # Dollar break-even is approx 37.21%
    assert abs(p_be_dollar - 0.3721) < 0.01
    # R-multiple break-even is approx 39.23%
    assert abs(p_be_r - 0.3923) < 0.01

    # Neither assumes 50%
    assert p_be_dollar < 0.45 and p_be_r < 0.45


def test_trade_outcome_denominators_consistency():
    """Verify that N_closed = N_rule + N_EOD across all reported variants."""
    trades_csv = ROOT / "reports" / "phase5" / "smc_mtf_trades.csv"
    if not trades_csv.exists():
        pytest.skip("Phase 5 trades CSV not found")

    df = pd.read_csv(trades_csv)
    for (tf, variant), group in df.groupby(["timeframe", "strategy_variant"]):
        closed = group[group["status"] == "CLOSED"]
        eod = closed[closed["exit_reason"] == "END_OF_DATA"]
        rules = closed[closed["exit_reason"] != "END_OF_DATA"]

        assert len(closed) == len(rules) + len(eod), (
            f"Denominator mismatch in {tf} {variant}: {len(closed)} != {len(rules)} + {len(eod)}"
        )


def test_valid_evaluation_ledger_excludes_smc_0053():
    """Verify that trade SMC_M15_0053 is excluded from the valid evaluation ledger."""
    trades_csv = ROOT / "reports" / "phase5" / "smc_mtf_trades.csv"
    if not trades_csv.exists():
        pytest.skip("Phase 5 trades CSV not found")

    df = pd.read_csv(trades_csv)
    m15_trades = df[df["timeframe"] == "M15"]
    assert "SMC_M15_0053" not in m15_trades["setup_id"].values, (
        "SMC_M15_0053 occurred after H4 data ended and must be excluded from valid evaluation."
    )
    # Check that all entry timestamps are <= 2026-10-20 13:00:00 UTC
    for entry_time in m15_trades["entry_time"].dropna():
        ts = pd.Timestamp(entry_time)
        assert ts <= pd.Timestamp("2026-10-20 13:00:00+00:00"), (
            f"Entry time {ts} exceeds H4 confirmed data boundary (2026-10-20 13:00:00 UTC)"
        )
