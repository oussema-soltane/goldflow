"""
GoldFlow — Experimental SMC Strategy Candidates (Phase 6 Research).

ISOLATION POLICY:
This module contains experimental research candidates only.
It does NOT modify configs/smc_v1_frozen.json or src/smc/engine.py.
The frozen SMC v1 baseline remains 100% reproducible and isolated.
All candidate filtering is causal (evaluating only information known at decision time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
import numpy as np
import pandas as pd

from src.backtesting.engine import BacktestConfig, BacktestResult, run_event_backtest
from src.smc.engine import SMCConfig, analyze_smc
from src.strategy.smc_mtf import filter_candidates_by_mtf
from src.strategy.smc_setups import (
    SMCSetupCandidate,
    SMCSetupConfig,
    detect_smc_setup_candidates,
    detect_smc_setups_with_funnel,
)


@dataclass(frozen=True)
class ResearchCandidateSpec:
    name: str
    version: str
    description: str
    session_filter_enabled: bool = False
    allowed_session_start_hour: int = 7   # 07:00 UTC (London open)
    allowed_session_end_hour: int = 21    # 21:00 UTC (NY close)
    setup_config: SMCSetupConfig = SMCSetupConfig()
    require_htf_confirmation: bool = False


# Candidate Specifications
CANDIDATE_BASELINE_V1 = ResearchCandidateSpec(
    name="SMC_v1_frozen_baseline",
    version="1.0.0",
    description="Canonical frozen SMC v1 baseline (control benchmark)",
    session_filter_enabled=False,
    setup_config=SMCSetupConfig(
        use_opposing_liquidity_target=True,
        fixed_rr=2.0,
        minimum_reward_risk=1.0,
    ),
    require_htf_confirmation=False,
)

CANDIDATE_SESSION_FILTERED = ResearchCandidateSpec(
    name="SMC_v2_session_filtered",
    version="2.0.0-alpha.1",
    description="SMC baseline restricted to liquid London and New York trading sessions (07:00-21:00 UTC)",
    session_filter_enabled=True,
    allowed_session_start_hour=7,
    allowed_session_end_hour=21,
    setup_config=SMCSetupConfig(
        use_opposing_liquidity_target=True,
        fixed_rr=2.0,
        minimum_reward_risk=1.0,
    ),
    require_htf_confirmation=False,
)

CANDIDATE_TARGET_RATIONALIZED = ResearchCandidateSpec(
    name="SMC_v2_target_rationalized",
    version="2.0.0-alpha.2",
    description="SMC with rationalized fixed 2.0R target instead of runaway opposing liquidity",
    session_filter_enabled=False,
    setup_config=SMCSetupConfig(
        use_opposing_liquidity_target=False,
        fixed_rr=2.0,
        minimum_reward_risk=1.0,
    ),
    require_htf_confirmation=False,
)

CANDIDATE_COMPOSITE_LIQUID = ResearchCandidateSpec(
    name="SMC_v2_composite_liquid",
    version="2.0.0-alpha.3",
    description="Composite candidate: Liquid session filter (07:00-21:00 UTC) + Rationalized 2.0R target",
    session_filter_enabled=True,
    allowed_session_start_hour=7,
    allowed_session_end_hour=21,
    setup_config=SMCSetupConfig(
        use_opposing_liquidity_target=False,
        fixed_rr=2.0,
        minimum_reward_risk=1.0,
    ),
    require_htf_confirmation=False,
)

CANDIDATE_NY_SESSION = ResearchCandidateSpec(
    name="SMC_v2_ny_session",
    version="2.0.0-alpha.4",
    description="NY session focus (13:00-21:00 UTC) + Rationalized 2.0R target",
    session_filter_enabled=True,
    allowed_session_start_hour=13,
    allowed_session_end_hour=21,
    setup_config=SMCSetupConfig(
        use_opposing_liquidity_target=False,
        fixed_rr=2.0,
        minimum_reward_risk=1.0,
    ),
    require_htf_confirmation=False,
)

CANDIDATE_MTF_ALIGNED = ResearchCandidateSpec(
    name="SMC_v2_mtf_aligned",
    version="2.0.0-alpha.5",
    description="Multi-Timeframe aligned: H4 & H1 trend consensus + Liquid sessions + 2.0R target",
    session_filter_enabled=True,
    allowed_session_start_hour=7,
    allowed_session_end_hour=21,
    setup_config=SMCSetupConfig(
        use_opposing_liquidity_target=False,
        fixed_rr=2.0,
        minimum_reward_risk=1.0,
    ),
    require_htf_confirmation=True,
)


def filter_candidates_by_session(
    candidates: List[SMCSetupCandidate],
    start_hour: int = 7,
    end_hour: int = 21,
) -> List[SMCSetupCandidate]:
    """
    Causally filter candidates by signal hour of day (UTC).
    Preserves only candidates whose signal occurs between start_hour and end_hour UTC.
    """
    filtered = []
    for c in candidates:
        sig_time = pd.Timestamp(c.signal_time)
        hour = sig_time.hour
        if start_hour <= hour < end_hour:
            filtered.append(c)
    return filtered



def run_candidate_simulation(
    frame: pd.DataFrame,
    spec: ResearchCandidateSpec,
    timeframe: str = "M5",
    config: Optional[BacktestConfig] = None,
    h4_df: Optional[pd.DataFrame] = None,
    h1_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Execute a backtest simulation for an experimental research candidate.
    """
    backtest_cfg = config or BacktestConfig()
    
    # 1. Run SMC analysis
    analysis = analyze_smc(frame, symbol="XAUUSD", timeframe=timeframe, config=SMCConfig())
    
    # 2. Detect setups using candidate setup config
    raw_candidates, funnel = detect_smc_setups_with_funnel(frame, analysis, spec.setup_config)
    
    # 3. Apply session filter if enabled
    filtered_candidates = raw_candidates
    if spec.session_filter_enabled:
        filtered_candidates = filter_candidates_by_session(
            filtered_candidates,
            start_hour=spec.allowed_session_start_hour,
            end_hour=spec.allowed_session_end_hour,
        )

    # 4. Apply HTF filter if enabled
    if spec.require_htf_confirmation and h4_df is not None and h1_df is not None:
        h4_analysis = analyze_smc(h4_df, symbol="XAUUSD", timeframe="H4", config=SMCConfig())
        h1_analysis = analyze_smc(h1_df, symbol="XAUUSD", timeframe="H1", config=SMCConfig())
        h4_end = pd.Timestamp(h4_df["time"].iloc[-1]) + pd.Timedelta(hours=4)
        h1_end = pd.Timestamp(h1_df["time"].iloc[-1]) + pd.Timedelta(hours=1)
        accepted, _, _ = filter_candidates_by_mtf(
            candidates=filtered_candidates,
            lower_timeframe=timeframe,
            h4_analysis=h4_analysis,
            h1_analysis=h1_analysis,
            h4_data_end_time=h4_end,
            h1_data_end_time=h1_end,
        )
        filtered_candidates = accepted

    # Convert to backtest records
    records = []
    for n, cand in enumerate(filtered_candidates, start=1):
        rec = cand.to_dict()
        rec["setup_id"] = f"{spec.name}_{timeframe}_{n:04d}"
        rec["timeframe"] = timeframe
        rec["strategy_variant"] = spec.name
        records.append(rec)

    # 5. Run event-driven backtest
    result: BacktestResult = run_event_backtest(frame, records, backtest_cfg, timeframe=timeframe)

    # Calculate rich derived metrics
    trades_df = pd.DataFrame(result.trades)
    closed = trades_df[trades_df["status"] == "CLOSED"] if not trades_df.empty and "status" in trades_df.columns else pd.DataFrame()
    
    n_closed = len(closed)
    wins = closed[closed["net_pnl"] > 0] if not closed.empty else pd.DataFrame()
    losses = closed[closed["net_pnl"] <= 0] if not closed.empty else pd.DataFrame()
    
    n_wins = len(wins)
    n_losses = len(losses)
    wr = (n_wins / n_closed) * 100.0 if n_closed > 0 else 0.0
    
    gross_pnl = float(closed["gross_pnl"].sum()) if not closed.empty else 0.0
    net_pnl = float(closed["net_pnl"].sum()) if not closed.empty else 0.0
    costs = float(closed["total_transaction_costs"].sum()) if not closed.empty else 0.0
    spread_cost = float(closed["spread_cost"].sum()) if not closed.empty and "spread_cost" in closed.columns else 0.0
    slippage_cost = float(closed["slippage_cost"].sum()) if not closed.empty and "slippage_cost" in closed.columns else 0.0
    
    avg_win = float(wins["net_pnl"].mean()) if n_wins > 0 else 0.0
    avg_loss = abs(float(losses["net_pnl"].mean())) if n_losses > 0 else 0.0
    payoff_b = (avg_win / avg_loss) if avg_loss > 0 else np.nan
    expectancy = float(closed["net_pnl"].mean()) if n_closed > 0 else 0.0
    
    loss_sum = abs(float(losses["net_pnl"].sum())) if not losses.empty else 0.0
    pf = (float(wins["net_pnl"].sum()) / loss_sum) if loss_sum > 0 else (np.inf if n_wins > 0 else 0.0)
    
    max_dd = float(result.metrics.get("max_drawdown_cash", 0.0))
    ret_pct = (net_pnl / backtest_cfg.initial_capital) * 100.0

    return {
        "candidate_name": spec.name,
        "version": spec.version,
        "description": spec.description,
        "timeframe": timeframe,
        "initial_capital": backtest_cfg.initial_capital,
        "total_candidates": len(raw_candidates),
        "filtered_candidates": len(filtered_candidates),
        "closed_trades": n_closed,
        "wins": n_wins,
        "losses": n_losses,
        "win_rate_pct": round(wr, 2),
        "gross_pnl": round(gross_pnl, 2),
        "transaction_costs": round(costs, 2),
        "spread_costs": round(spread_cost, 2),
        "slippage_costs": round(slippage_cost, 2),
        "net_pnl": round(net_pnl, 2),
        "return_pct": round(ret_pct, 2),
        "profit_factor": round(pf, 3) if np.isfinite(pf) else None,
        "max_drawdown_cash": round(max_dd, 2),
        "max_drawdown_pct": round((max_dd / backtest_cfg.initial_capital) * 100.0, 2),
        "average_win": round(avg_win, 2),
        "average_loss": round(avg_loss, 2),
        "payoff_ratio": round(payoff_b, 2) if pd.notna(payoff_b) else None,
        "net_expectancy_per_trade": round(expectancy, 2),
        "trades": result.trades,
        "equity_curve": result.equity_curve,
    }
