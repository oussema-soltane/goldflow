"""Controlled Ablation Study Suite for GoldFlow SMC_CONFLUENCE_V1.

Executes all 8 ablation experiments across M15 and M5:
1. BASELINE: Raw SMC v1 (all confluence filters OFF)
2. EXP_A_HTF: SMC + Higher-Timeframe Bias (D1 + H4)
3. EXP_B_SESSION: SMC + Session Liquidity Filter (London/NY only)
4. EXP_C_NEWS: SMC + High-Impact USD News Filter
5. EXP_D_HTF_SESSION: SMC + HTF Bias + Session Filter
6. EXP_E_TRIPLE: SMC + HTF Bias + Session Filter + News Filter (Triple Confluence)
7. EXP_F_ATR: Triple Confluence + Volatility-Adjusted ATR Stops
8. EXP_G_BREAKEVEN: Candidate F + Breakeven (+1.5R) Capital Protection

Outputs:
- reports/PERFORMANCE_COMPARISON.csv
- reports/TRADE_LEDGER.csv
- Console progress and statistical summaries
"""
from __future__ import annotations

import math
from pathlib import Path
import sys
import time

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from src.backtesting.engine import BacktestConfig
from src.smc.engine import analyze_smc, SMCConfig
from src.strategy.smc_confluence import (
    SMCConfluenceConfig,
    SMCConfluenceStrategy,
    run_confluence_backtest,
)


EXPERIMENTS = [
    {
        "id": "BASELINE",
        "name": "Frozen SMC v1 (Raw Baseline)",
        "config": SMCConfluenceConfig(
            enable_htf_bias=False,
            enable_session_filter=False,
            enable_news_filter=False,
            enable_atr_stop=False,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_A_HTF",
        "name": "SMC + HTF Bias (D1 + H4)",
        "config": SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=False,
            enable_news_filter=False,
            enable_atr_stop=False,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_B_SESSION",
        "name": "SMC + Session Liquidity Filter",
        "config": SMCConfluenceConfig(
            enable_htf_bias=False,
            enable_session_filter=True,
            enable_news_filter=False,
            enable_atr_stop=False,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_C_NEWS",
        "name": "SMC + High-Impact News Filter",
        "config": SMCConfluenceConfig(
            enable_htf_bias=False,
            enable_session_filter=False,
            enable_news_filter=True,
            enable_atr_stop=False,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_D_HTF_SESSION",
        "name": "SMC + HTF Bias + Session Filter",
        "config": SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=True,
            enable_news_filter=False,
            enable_atr_stop=False,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_E_TRIPLE",
        "name": "SMC + HTF + Session + News (Triple Confluence)",
        "config": SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=True,
            enable_news_filter=True,
            enable_atr_stop=False,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_F_ATR",
        "name": "Candidate E + ATR Stops (1.5x ATR)",
        "config": SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=True,
            enable_news_filter=True,
            enable_atr_stop=True,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_G_BREAKEVEN",
        "name": "Candidate F + 1.5R Breakeven Trade Mgmt",
        "config": SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=True,
            enable_news_filter=True,
            enable_atr_stop=True,
            enable_breakeven=True,
        ),
    },
]


def calculate_annualized_sharpe(equity_curve: list[dict[str, Any]]) -> Optional[float]:
    """Calculate annualized Sharpe ratio from daily equity samples."""
    if not equity_curve or len(equity_curve) < 5:
        return None
    eq_df = pd.DataFrame(equity_curve)
    eq_df["time"] = pd.to_datetime(eq_df["time"], utc=True)
    eq_df["date"] = eq_df["time"].dt.floor("1D")
    daily_eq = eq_df.groupby("date")["equity"].last().pct_change().dropna()
    if len(daily_eq) < 3 or daily_eq.std() <= 1e-12:
        return 0.0
    daily_mean = daily_eq.mean()
    daily_std = daily_eq.std()
    sharpe = float((daily_mean / daily_std) * math.sqrt(252))
    return round(sharpe, 3)


def run_ablation_studies():
    print("================================================================================")
    print(" GOLDFLOW ABLATION STUDY SUITE — SYSTEMATIC CONFLUENCE EDGE EVALUATION")
    print("================================================================================")

    # Load canonical datasets
    h4_path = ROOT / "data" / "processed" / "XAUUSD_H4_clean.csv"
    m15_path = ROOT / "data" / "processed" / "XAUUSD_M15_clean.csv"
    m5_path = ROOT / "data" / "processed" / "XAUUSD_M5_clean.csv"
    news_path = ROOT / "data" / "news" / "usd_high_impact_news.csv"

    print(f"Loading H4 data from {h4_path.name}...")
    h4_df = pd.read_csv(h4_path)
    h4_df["time"] = pd.to_datetime(h4_df["time"], utc=True)

    print(f"Loading M15 data from {m15_path.name}...")
    m15_df = pd.read_csv(m15_path)
    m15_df["time"] = pd.to_datetime(m15_df["time"], utc=True)

    print(f"Loading M5 data from {m5_path.name}...")
    m5_df = pd.read_csv(m5_path)
    m5_df["time"] = pd.to_datetime(m5_df["time"], utc=True)

    # Base Backtest Config: $10,000, 0.5% risk, realistic costs
    base_bconfig = BacktestConfig(
        initial_capital=10_000.0,
        risk_fraction=0.005,  # 0.5% risk
        fallback_spread_usd=0.20,
        slippage_per_side_usd=0.05,
        commission_per_lot_per_side=0.0,
    )

    all_performance_rows = []
    all_trades_rows = []

    # Process timeframes: M15 and M5
    timeframe_datasets = [
        ("M15", m15_df),
        ("M5", m5_df),
    ]

    for tf_name, tf_df in timeframe_datasets:
        print(f"\n>>> Analyzing Timeframe: {tf_name} ({len(tf_df):,} bars) <<<", flush=True)
        t0_tf = time.perf_counter()

        # Precompute base SMC analysis once per timeframe to ensure exact repeatability
        print(f"  Running base SMC detector on {tf_name}...", flush=True)
        smc_res = analyze_smc(tf_df, symbol="XAUUSD", timeframe=tf_name, config=SMCConfig())
        print(f"  Base SMC detection complete: {len(smc_res.swings)} swings, {len(smc_res.structure_breaks)} breaks", flush=True)

        for exp in EXPERIMENTS:
            exp_id = exp["id"]
            exp_name = exp["name"]
            exp_cfg: SMCConfluenceConfig = exp["config"]
            print(f"    Running {exp_id}: {exp_name}...", flush=True)

            strategy = SMCConfluenceStrategy(
                h4_df=h4_df,
                news_calendar_source=news_path,
                config=exp_cfg,
            )

            # Generate confluence candidates
            accepted, funnel, audit_rows = strategy.generate_candidates(
                tf_df, timeframe=tf_name, smc_result=smc_res
            )

            # Run backtest
            bt_res = run_confluence_backtest(
                tf_df,
                accepted,
                config=base_bconfig,
                timeframe=tf_name,
                enable_breakeven=exp_cfg.enable_breakeven,
                breakeven_r_trigger=exp_cfg.breakeven_r_trigger,
                breakeven_buffer_usd=exp_cfg.breakeven_buffer_usd,
                max_daily_drawdown_pct=exp_cfg.max_daily_drawdown_pct,
                max_spread_dollars=exp_cfg.max_spread_dollars,
            )

            metrics = bt_res.metrics
            closed_trades = [t for t in bt_res.trades if t.get("status") == "CLOSED"]
            rule_trades = [t for t in closed_trades if t.get("exit_reason") != "END_OF_DATA"]
            wins = [t for t in rule_trades if float(t.get("net_pnl", 0.0)) > 0]
            losses = [t for t in rule_trades if float(t.get("net_pnl", 0.0)) < 0]

            tot_closed = len(closed_trades)
            wr = round((len(wins) / len(rule_trades) * 100.0), 2) if rule_trades else 0.0
            net_pnl = round(float(metrics.get("net_profit", 0.0)), 2)
            pf_val = metrics.get("profit_factor")
            pf_str = f"{pf_val:.3f}" if isinstance(pf_val, (int, float)) else str(pf_val)
            max_dd = round(float(metrics.get("max_drawdown_cash", 0.0)), 2)
            max_dd_pct = round(float(metrics.get("max_drawdown_pct", 0.0)), 2)
            exp_usd = round(float(metrics.get("expectancy_per_rule_exit", 0.0)), 2) if metrics.get("expectancy_per_rule_exit") is not None else 0.0
            avg_r = round(float(metrics.get("average_R_multiple", 0.0)), 3) if metrics.get("average_R_multiple") is not None else 0.0
            sharpe = calculate_annualized_sharpe(bt_res.equity_curve)

            perf_record = {
                "experiment_id": exp_id,
                "description": exp_name,
                "timeframe": tf_name,
                "total_bars": len(tf_df),
                "raw_candidates": funnel["raw_candidates_input"],
                "accepted_candidates": funnel["confluence_accepted"],
                "closed_trades": tot_closed,
                "rule_trades": len(rule_trades),
                "win_rate_pct": wr,
                "profit_factor": pf_str,
                "net_pnl_usd": net_pnl,
                "return_pct": round((net_pnl / 10_000.0) * 100.0, 2),
                "max_drawdown_usd": max_dd,
                "max_drawdown_pct": max_dd_pct,
                "expectancy_per_trade_usd": exp_usd,
                "average_r_multiple": avg_r,
                "annualized_sharpe": sharpe,
            }
            all_performance_rows.append(perf_record)

            print(f"      -> Trades: {tot_closed} | WR: {wr}% | PF: {pf_str} | Net: ${net_pnl:+.2f} | MaxDD: {max_dd_pct}%")

            # Collect trades for master ledger
            for t in bt_res.trades:
                if t.get("status") == "CLOSED":
                    all_trades_rows.append({
                        "experiment_id": exp_id,
                        "timeframe": tf_name,
                        "setup_id": t.get("setup_id"),
                        "direction": t.get("side"),
                        "signal_time": t.get("signal_time"),
                        "entry_time": t.get("time_iso") or t.get("entry_time"),
                        "entry_price": t.get("entry_price"),
                        "stop_loss": t.get("stop_loss"),
                        "take_profit": t.get("take_profit"),
                        "lots": t.get("lots"),
                        "exit_time": t.get("exit_time"),
                        "exit_price": t.get("exit_price"),
                        "exit_reason": t.get("exit_reason"),
                        "raw_gross_pnl": t.get("raw_gross_pnl"),
                        "spread_cost": t.get("spread_cost"),
                        "slippage_cost": t.get("slippage_cost"),
                        "total_transaction_costs": t.get("total_transaction_costs"),
                        "net_pnl": t.get("net_pnl"),
                        "R_multiple": t.get("R_multiple"),
                        "equity_after": t.get("equity_after"),
                        "breakeven_active": t.get("breakeven_active", False),
                    })

        elapsed_tf = time.perf_counter() - t0_tf
        print(f"Timeframe {tf_name} completed in {elapsed_tf:.2f}s")

    # Save reports
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    perf_df = pd.DataFrame(all_performance_rows)
    perf_path = reports_dir / "PERFORMANCE_COMPARISON.csv"
    perf_df.to_csv(perf_path, index=False)
    print(f"\n[DONE] Saved performance comparison table to {perf_path}")

    ledger_df = pd.DataFrame(all_trades_rows)
    ledger_path = reports_dir / "TRADE_LEDGER.csv"
    ledger_df.to_csv(ledger_path, index=False)
    print(f"[DONE] Saved trade ledger ({len(ledger_df):,} trades) to {ledger_path}")

    return perf_df, ledger_df


if __name__ == "__main__":
    run_ablation_studies()
