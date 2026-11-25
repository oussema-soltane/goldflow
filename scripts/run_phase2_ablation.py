"""
Extended Ablation Phase 2 — Targeted experiments based on Phase 1 findings.

Phase 1 key insights:
- HTF bias alone is the strongest single filter (M15 WR 20.51% -> 40%)
- Session filter HURTS when applied without HTF (destroys trade frequency badly)
- ATR stop expansion helps M5 significantly
- Best combination NOT yet found: HTF + ATR has not been tested in isolation

This script tests:
EXP_H: SMC + HTF Bias + ATR Stops (without session/news) on M15 and H1
EXP_I: SMC + HTF Bias + ATR Stops + Session (London-only) on M15
EXP_J: HTF + ATR + Partial Exit (1.5R first target, 3.0R second) on M15
EXP_K: HTF only on H1 baseline

Also introduces walk-forward split:
- IN-SAMPLE: first 60% of bars
- OOS: remaining 40% (never used for optimization)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
import time
from typing import Any, Optional

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

RESULTS_PATH = ROOT / "reports" / "PHASE2_PERFORMANCE_COMPARISON.csv"
LEDGER_PATH = ROOT / "reports" / "PHASE2_TRADE_LEDGER.csv"

EXPERIMENTS = [
    {
        "id": "EXP_H_HTF_ATR",
        "name": "HTF Bias + ATR Stops only (no session/news)",
        "config": SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=False,
            enable_news_filter=False,
            enable_atr_stop=True,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_I_HTF_ATR_LONDON",
        "name": "HTF + ATR + London Session only",
        "config": SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=True,
            enable_news_filter=False,
            enable_atr_stop=True,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_J_HTF_ATR_BREAKEVEN",
        "name": "HTF + ATR + Breakeven (no session/news)",
        "config": SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=False,
            enable_news_filter=False,
            enable_atr_stop=True,
            enable_breakeven=True,
        ),
    },
    {
        "id": "EXP_K_FULL_CONFLUENCE",
        "name": "Full Confluence: HTF + Session + News + ATR + Breakeven",
        "config": SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=True,
            enable_news_filter=True,
            enable_atr_stop=True,
            enable_breakeven=True,
        ),
    },
    {
        "id": "BASELINE",
        "name": "Frozen SMC v1 (Raw Baseline - for reference)",
        "config": SMCConfluenceConfig(
            enable_htf_bias=False,
            enable_session_filter=False,
            enable_news_filter=False,
            enable_atr_stop=False,
            enable_breakeven=False,
        ),
    },
]


def metrics_from_bt_result(bt_res, initial_capital: float) -> dict:
    """Extract metrics directly from BacktestResult.metrics dict (already computed)."""
    m = bt_res.metrics if bt_res.metrics else {}
    trades_raw = bt_res.trades if bt_res.trades else []

    # Profit factor: engine may return float('inf'), 'infinite' string, or a number
    pf_raw = m.get("profit_factor", 0.0)
    if pf_raw in (float("inf"), "infinite", "inf") or str(pf_raw).lower() in ("infinite", "inf"):
        pf_val = float("inf")
    else:
        try:
            pf_val = round(float(pf_raw), 3)
        except (ValueError, TypeError):
            pf_val = 0.0

    n = m.get("rule_exit_trades", m.get("closed_trades", len(trades_raw)))
    wins = m.get("wins", 0)
    win_rate = m.get("win_rate_pct", 0.0)
    net_pnl = m.get("net_profit_from_rule_exits", m.get("net_profit", 0.0))
    expectancy = m.get("expectancy_per_rule_exit", 0.0)
    max_dd = m.get("max_drawdown_pct", 0.0)

    # Gross P&L from individual trades (they ARE dicts)
    pnls = [float(t.get("net_pnl", 0.0)) for t in trades_raw
            if t.get("exit_reason", "") not in ("END_OF_DATA",)]
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p <= 0))
    losses_list = [p for p in pnls if p <= 0]

    # Max consecutive losses
    max_consec = 0
    consec = 0
    for p in pnls:
        if p <= 0:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0

    return {
        "trades": int(n),
        "wins": int(wins),
        "win_rate": round(float(win_rate), 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_pnl": round(float(net_pnl), 2),
        "profit_factor": pf_val,
        "expectancy": round(float(expectancy), 2),
        "avg_winner": round(gross_profit / wins, 2) if wins > 0 else 0.0,
        "avg_loser": round(sum(losses_list) / len(losses_list), 2) if losses_list else 0.0,
        "max_dd_pct": round(float(max_dd), 2),
        "max_consec_losses": max_consec,
    }


def run_phase2():
    print("=" * 80)
    print(" GOLDFLOW ABLATION PHASE 2 — TARGETED HYPOTHESIS TESTING")
    print("=" * 80)
    print()
    print("Phase 1 insight: HTF+ATR combination not yet tested in isolation.")
    print("This run fills that gap and introduces In-Sample / OOS split reporting.")
    print()

    # Load data
    h4_path = ROOT / "data" / "processed" / "XAUUSD_H4_clean.csv"
    h1_path = ROOT / "data" / "processed" / "XAUUSD_H1_clean.csv"
    m15_path = ROOT / "data" / "processed" / "XAUUSD_M15_clean.csv"
    news_path = ROOT / "data" / "news" / "usd_high_impact_news.csv"

    h4_df = pd.read_csv(h4_path)
    h4_df["time"] = pd.to_datetime(h4_df["time"], utc=True)
    print(f"H4: {len(h4_df):,} bars ({h4_df['time'].iloc[0]} → {h4_df['time'].iloc[-1]})")

    h1_df = pd.read_csv(h1_path)
    h1_df["time"] = pd.to_datetime(h1_df["time"], utc=True)
    print(f"H1: {len(h1_df):,} bars ({h1_df['time'].iloc[0]} → {h1_df['time'].iloc[-1]})")

    m15_df = pd.read_csv(m15_path)
    m15_df["time"] = pd.to_datetime(m15_df["time"], utc=True)
    print(f"M15: {len(m15_df):,} bars ({m15_df['time'].iloc[0]} → {m15_df['time'].iloc[-1]})")

    base_bconfig = BacktestConfig(
        initial_capital=10_000.0,
        risk_fraction=0.005,
        fallback_spread_usd=0.20,
        slippage_per_side_usd=0.05,
        commission_per_lot_per_side=0.0,
    )

    # Walk-forward split (60% in-sample, 40% OOS)
    timeframe_datasets = [
        ("M15", m15_df),
        ("H1", h1_df),
    ]

    all_rows = []
    all_trades = []

    for tf_name, tf_df in timeframe_datasets:
        n_bars = len(tf_df)
        split_idx = int(n_bars * 0.6)
        is_df = tf_df.iloc[:split_idx].copy().reset_index(drop=True)
        oos_df = tf_df.iloc[split_idx:].copy().reset_index(drop=True)

        print(f"\n{'='*70}")
        print(f" Timeframe: {tf_name} | Total: {n_bars:,} bars")
        print(f" In-Sample:  bars 0–{split_idx-1} ({len(is_df):,}) | {is_df['time'].iloc[0].date()} → {is_df['time'].iloc[-1].date()}")
        print(f" OOS:        bars {split_idx}–{n_bars-1} ({len(oos_df):,}) | {oos_df['time'].iloc[0].date()} → {oos_df['time'].iloc[-1].date()}")

        # Pre-compute SMC on full dataset (walk-forward: use only completed bars)
        print(f" Running base SMC on full {tf_name} dataset...", flush=True)
        smc_full = analyze_smc(tf_df, symbol="XAUUSD", timeframe=tf_name, config=SMCConfig())
        smc_is = analyze_smc(is_df, symbol="XAUUSD", timeframe=tf_name, config=SMCConfig())
        smc_oos = analyze_smc(oos_df, symbol="XAUUSD", timeframe=tf_name, config=SMCConfig())
        print(f" SMC analysis done: {len(smc_full.swings)} swings, {len(smc_full.structure_breaks)} breaks (full)", flush=True)

        for exp in EXPERIMENTS:
            exp_id = exp["id"]
            exp_name = exp["name"]
            exp_cfg: SMCConfluenceConfig = exp["config"]

            for split_name, split_df, split_smc in [
                ("IS", is_df, smc_is),
                ("OOS", oos_df, smc_oos),
            ]:
                print(f"  [{split_name}] {exp_id}: {exp_name}...", end=" ", flush=True)
                t0 = time.perf_counter()

                strategy = SMCConfluenceStrategy(
                    h4_df=h4_df,
                    news_calendar_source=news_path,
                    config=exp_cfg,
                )

                try:
                    accepted, funnel, audit_rows = strategy.generate_candidates(
                        split_df, timeframe=tf_name, smc_result=split_smc
                    )
                    bt_res = run_confluence_backtest(
                        split_df, accepted, config=base_bconfig
                    )
                except Exception as e:
                    print(f"ERROR: {e}")
                    continue

                elapsed = time.perf_counter() - t0

                # Use bt.metrics (already computed correctly by engine)
                m = metrics_from_bt_result(bt_res, base_bconfig.initial_capital)

                # Accumulate trade ledger (trades are dicts)
                for t in (bt_res.trades or []):
                    all_trades.append({
                        "experiment": exp_id,
                        "timeframe": tf_name,
                        "split": split_name,
                        "net_pnl": float(t.get("net_pnl", 0.0)),
                        "exit_reason": t.get("exit_reason", ""),
                        "direction": t.get("direction", ""),
                        "entry_time": t.get("entry_time", ""),
                        "exit_time": t.get("exit_time", ""),
                        "R_multiple": t.get("R_multiple", 0.0),
                    })

                pf_display = f"{m['profit_factor']:.3f}" if m['profit_factor'] != float("inf") else "inf"
                print(f"trades={m['trades']}, WR={m['win_rate']}%, PF={pf_display}, net=${m['net_pnl']:+.2f}, DD={m['max_dd_pct']}% ({elapsed:.1f}s)")

                row = {
                    "experiment_id": exp_id,
                    "experiment_name": exp_name,
                    "timeframe": tf_name,
                    "split": split_name,
                    **m,
                    "htf_bias": exp_cfg.enable_htf_bias,
                    "session_filter": exp_cfg.enable_session_filter,
                    "news_filter": exp_cfg.enable_news_filter,
                    "atr_stop": exp_cfg.enable_atr_stop,
                    "breakeven": exp_cfg.enable_breakeven,
                }
                all_rows.append(row)

    # Save results
    results_df = pd.DataFrame(all_rows)
    results_df.to_csv(RESULTS_PATH, index=False)
    print(f"\nResults saved: {RESULTS_PATH}")

    trades_df = pd.DataFrame(all_trades)
    trades_df.to_csv(LEDGER_PATH, index=False)
    print(f"Trade ledger saved: {LEDGER_PATH}")

    # Print summary
    print("\n" + "=" * 80)
    print(" PHASE 2 RESULTS SUMMARY")
    print("=" * 80)
    for _, row in results_df.iterrows():
        pf = row["profit_factor"]
        pf_str = f"{pf:.3f}" if pf != float("inf") else " inf"
        mark = "✓" if pf >= 1.6 else ("~" if pf >= 1.0 else "✗")
        print(f" {mark} [{row['timeframe']}/{row['split']}] {row['experiment_id']:25s}: "
              f"T={row['trades']:3d} WR={row['win_rate']:5.1f}% PF={pf_str} "
              f"Net=${row['net_pnl']:+8.2f} DD={row['max_dd_pct']:5.1f}%")

    print("\n FILTER CONTRIBUTION ANALYSIS (M15 IS, sorted by PF):")
    m15_is = results_df[(results_df["timeframe"] == "M15") & (results_df["split"] == "IS")].sort_values("profit_factor", ascending=False)
    for _, row in m15_is.iterrows():
        filters = []
        if row["htf_bias"]: filters.append("HTF")
        if row["session_filter"]: filters.append("SESS")
        if row["news_filter"]: filters.append("NEWS")
        if row["atr_stop"]: filters.append("ATR")
        if row["breakeven"]: filters.append("BE")
        filter_str = "+".join(filters) if filters else "NONE"
        pf = row["profit_factor"]
        pf_str = f"{pf:.3f}" if pf != float("inf") else "  inf"
        print(f"   PF={pf_str} [{filter_str:30s}] T={row['trades']:3d} WR={row['win_rate']:.1f}%")


if __name__ == "__main__":
    run_phase2()
