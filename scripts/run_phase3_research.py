"""
Phase 3 Extended Quantitative Research Runner
==============================================
Runs extended ablation and 10-fold chronological walk-forward validation
on the 33,388-bar XAU/USD M15 extended dataset.

Outputs:
- reports/PHASE3_PERFORMANCE_COMPARISON.csv
- reports/PHASE3_TRADE_LEDGER.csv
- reports/PHASE3_WALK_FORWARD_VALIDATION.csv
"""
from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backtesting.engine import BacktestConfig
from src.smc.engine import analyze_smc, SMCConfig
from src.strategy.smc_confluence import (
    SMCConfluenceConfig,
    SMCConfluenceStrategy,
    run_confluence_backtest,
)

EXTENDED_M15_PATH = ROOT / "data" / "research" / "phase3" / "processed" / "XAUUSD_M15_extended.csv"
H4_PATH = ROOT / "data" / "processed" / "XAUUSD_H4_clean.csv"
NEWS_PATH = ROOT / "data" / "news" / "usd_high_impact_news.csv"

REPORTS_DIR = ROOT / "reports"
PERF_CSV_PATH = REPORTS_DIR / "PHASE3_PERFORMANCE_COMPARISON.csv"
LEDGER_CSV_PATH = REPORTS_DIR / "PHASE3_TRADE_LEDGER.csv"
WF_CSV_PATH = REPORTS_DIR / "PHASE3_WALK_FORWARD_VALIDATION.csv"

BASE_BCONFIG = BacktestConfig(
    initial_capital=10_000.0,
    risk_fraction=0.005,
    fallback_spread_usd=0.20,
    slippage_per_side_usd=0.05,
    commission_per_lot_per_side=0.0,
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
        "name": "HTF Bias Only (D1 + H4 alignment)",
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
        "name": "Session Filter Only (London & NY)",
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
        "name": "News Filter Only (USD High Impact Blackout)",
        "config": SMCConfluenceConfig(
            enable_htf_bias=False,
            enable_session_filter=False,
            enable_news_filter=True,
            enable_atr_stop=False,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_F_ATR",
        "name": "ATR Stops Only (Dynamic Stop Expansion)",
        "config": SMCConfluenceConfig(
            enable_htf_bias=False,
            enable_session_filter=False,
            enable_news_filter=False,
            enable_atr_stop=True,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_H_HTF_ATR",
        "name": "HTF Bias + ATR Stops (Primary Candidate)",
        "config": SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=False,
            enable_news_filter=False,
            enable_atr_stop=True,
            enable_breakeven=False,
        ),
    },
    {
        "id": "EXP_K_FULL",
        "name": "Full Confluence (HTF + Session + News + ATR + BE)",
        "config": SMCConfluenceConfig(
            enable_htf_bias=True,
            enable_session_filter=True,
            enable_news_filter=True,
            enable_atr_stop=True,
            enable_breakeven=True,
        ),
    },
]


def extract_metrics(bt_res, initial_capital: float = 10_000.0) -> dict:
    m = bt_res.metrics if bt_res.metrics else {}
    trades_raw = bt_res.trades if bt_res.trades else []

    # Rule trades exclude END_OF_DATA and skipped
    rule_trades = [
        t for t in trades_raw
        if t.get("exit_reason") not in ("END_OF_DATA", None) and t.get("entry_time") is not None
    ]
    n = len(rule_trades)
    pnls = [float(t.get("net_pnl", 0.0)) for t in rule_trades]

    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    win_rate = (wins / n * 100.0) if n > 0 else 0.0

    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    net_pnl = sum(pnls)

    if gross_loss == 0:
        pf_val = float("inf") if gross_profit > 0 else 0.0
    else:
        pf_val = round(gross_profit / gross_loss, 3)

    expectancy = (net_pnl / n) if n > 0 else 0.0
    max_dd = m.get("max_drawdown_pct", 0.0)

    # Consecutive losses
    max_consec = 0
    cur_consec = 0
    for p in pnls:
        if p <= 0:
            cur_consec += 1
            max_consec = max(max_consec, cur_consec)
        else:
            cur_consec = 0

    return {
        "trades": n,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_pnl": round(net_pnl, 2),
        "profit_factor": pf_val,
        "expectancy": round(expectancy, 2),
        "avg_winner": round(gross_profit / wins, 2) if wins > 0 else 0.0,
        "avg_loser": round(-gross_loss / losses, 2) if losses > 0 else 0.0,
        "max_dd_pct": round(float(max_dd), 2),
        "max_consec_losses": max_consec,
        "rule_trades": rule_trades,
    }


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    plus_di = 100 * plus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, min_periods=period).mean()


def run_phase3():
    print("=" * 80)
    print("PHASE 3 EXTENDED QUANTITATIVE RESEARCH EXECUTION")
    print("=" * 80)

    # 1. Load Data
    print(f"Loading extended M15 data: {EXTENDED_M15_PATH}")
    m15_df = pd.read_csv(EXTENDED_M15_PATH)
    m15_df["time"] = pd.to_datetime(m15_df["time"], utc=True)
    print(f"  Total M15 bars: {len(m15_df):,} | {m15_df['time'].iloc[0]} -> {m15_df['time'].iloc[-1]}")

    print(f"Loading H4 data: {H4_PATH}")
    h4_df = pd.read_csv(H4_PATH)
    h4_df["time"] = pd.to_datetime(h4_df["time"], utc=True)
    print(f"  Total H4 bars: {len(h4_df):,} | {h4_df['time'].iloc[0]} -> {h4_df['time'].iloc[-1]}")

    # Compute ADX on M15 for regime classification
    print("Computing ADX(14) series for market regime labeling...")
    m15_df["adx"] = compute_adx(m15_df, 14)
    m15_df["regime"] = np.where(m15_df["adx"] > 25.0, "TRENDING", "RANGING")

    # Pre-compute base SMC on full dataset
    print("Running base SMC detection on full 33,388 bars (this may take ~15-20s)...", flush=True)
    t0 = time.perf_counter()
    smc_result = analyze_smc(m15_df, symbol="XAUUSD", timeframe="M15", config=SMCConfig())
    t1 = time.perf_counter()
    print(f"  SMC analysis complete in {t1-t0:.2f}s: {len(smc_result.swings):,} swings, {len(smc_result.structure_breaks):,} breaks")

    # -------------------------------------------------------------------------
    # PART A: Full-History Ablation on Extended Dataset (33,388 bars)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("PART A: EXTENDED FULL-HISTORY ABLATION (33,388 BARS)")
    print("=" * 80)

    perf_rows = []
    trade_ledger_rows = []

    for exp in EXPERIMENTS:
        exp_id = exp["id"]
        exp_name = exp["name"]
        exp_cfg = exp["config"]
        print(f"  Running {exp_id}: {exp_name}...", end=" ", flush=True)
        t_start = time.perf_counter()

        strategy = SMCConfluenceStrategy(
            h4_df=h4_df,
            news_calendar_source=NEWS_PATH,
            config=exp_cfg,
        )

        accepted, funnel, audit_rows = strategy.generate_candidates(
            m15_df, timeframe="M15", smc_result=smc_result
        )
        bt_res = run_confluence_backtest(m15_df, accepted, config=BASE_BCONFIG)
        m = extract_metrics(bt_res)
        t_elapsed = time.perf_counter() - t_start

        pf_str = "inf" if math.isinf(m["profit_factor"]) else f"{m['profit_factor']:.3f}"
        print(f"Done in {t_elapsed:.1f}s | Trades: {m['trades']}, WR: {m['win_rate']}%, PF: {pf_str}, Net: ${m['net_pnl']:.2f}")

        perf_rows.append({
            "experiment_id": exp_id,
            "experiment_name": exp_name,
            "timeframe": "M15",
            "bars": len(m15_df),
            "trades": m["trades"],
            "wins": m["wins"],
            "losses": m["losses"],
            "win_rate": m["win_rate"],
            "gross_profit": m["gross_profit"],
            "gross_loss": m["gross_loss"],
            "net_pnl": m["net_pnl"],
            "profit_factor": m["profit_factor"],
            "expectancy": m["expectancy"],
            "avg_winner": m["avg_winner"],
            "avg_loser": m["avg_loser"],
            "max_dd_pct": m["max_dd_pct"],
            "max_consec_losses": m["max_consec_losses"],
            "enable_htf": exp_cfg.enable_htf_bias,
            "enable_session": exp_cfg.enable_session_filter,
            "enable_news": exp_cfg.enable_news_filter,
            "enable_atr": exp_cfg.enable_atr_stop,
            "enable_breakeven": exp_cfg.enable_breakeven,
        })

        # Record trades for trade ledger
        for t in m["rule_trades"]:
            entry_t = pd.to_datetime(t.get("entry_time"), utc=True)
            # Find regime at entry time
            regime = "UNKNOWN"
            adx_val = 0.0
            idx_match = m15_df[m15_df["time"] == entry_t]
            if len(idx_match) > 0:
                regime = idx_match["regime"].iloc[0]
                adx_val = round(float(idx_match["adx"].iloc[0]), 2)

            # Determine session
            hour = entry_t.hour
            if 7 <= hour < 13:
                session = "LONDON"
            elif 13 <= hour < 17:
                session = "OVERLAP_NY"
            elif 17 <= hour < 21:
                session = "LATE_NY"
            else:
                session = "ASIAN_OFFHOURS"

            trade_ledger_rows.append({
                "experiment_id": exp_id,
                "timeframe": "M15",
                "entry_time": t.get("entry_time"),
                "exit_time": t.get("exit_time"),
                "direction": t.get("direction"),
                "entry_price": round(float(t.get("entry_price", 0.0)), 2),
                "exit_price": round(float(t.get("exit_price", 0.0)), 2),
                "exit_reason": t.get("exit_reason"),
                "net_pnl": round(float(t.get("net_pnl", 0.0)), 2),
                "r_multiple": round(float(t.get("R_multiple", 0.0)), 2),
                "holding_bars": t.get("bars_held", 0),
                "regime": regime,
                "adx_at_entry": adx_val,
                "session": session,
            })

    # Save Performance Comparison CSV
    pd.DataFrame(perf_rows).to_csv(PERF_CSV_PATH, index=False)
    print(f"\nSaved Phase 3 performance comparison: {PERF_CSV_PATH}")

    # Save Trade Ledger CSV
    pd.DataFrame(trade_ledger_rows).to_csv(LEDGER_CSV_PATH, index=False)
    print(f"Saved Phase 3 trade ledger ({len(trade_ledger_rows):,} trades): {LEDGER_CSV_PATH}")

    # -------------------------------------------------------------------------
    # PART B: 10-Fold Chronological Walk-Forward Validation (EXP_H_HTF_ATR)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("PART B: 10-FOLD CHRONOLOGICAL WALK-FORWARD VALIDATION (EXP_H_HTF_ATR)")
    print("=" * 80)

    # Initial training window: first 13,388 bars (~40%, May 2025 – Dec 2025)
    # 10 evaluation folds: 2,000 bars each (~60% of data, Dec 2025 – Oct 2026)
    initial_is_bars = 13_388
    fold_oos_bars = 2_000
    n_folds = 10

    exp_h_cfg = SMCConfluenceConfig(
        enable_htf_bias=True,
        enable_session_filter=False,
        enable_news_filter=False,
        enable_atr_stop=True,
        enable_breakeven=False,
    )

    wf_rows = []

    for fold_i in range(1, n_folds + 1):
        is_end_idx = initial_is_bars + (fold_i - 1) * fold_oos_bars
        oos_start_idx = is_end_idx
        oos_end_idx = min(oos_start_idx + fold_oos_bars, len(m15_df))

        is_sub = m15_df.iloc[:is_end_idx].copy().reset_index(drop=True)
        oos_sub = m15_df.iloc[oos_start_idx:oos_end_idx].copy().reset_index(drop=True)

        is_start_t = is_sub["time"].iloc[0].strftime("%Y-%m-%d")
        is_end_t = is_sub["time"].iloc[-1].strftime("%Y-%m-%d")
        oos_start_t = oos_sub["time"].iloc[0].strftime("%Y-%m-%d")
        oos_end_t = oos_sub["time"].iloc[-1].strftime("%Y-%m-%d")

        print(f"\nFold {fold_i:2d}/10: IS [0:{is_end_idx}] ({is_start_t} -> {is_end_t}) | OOS [{oos_start_idx}:{oos_end_idx}] ({oos_start_t} -> {oos_end_t})")

        # Run IS
        smc_is = analyze_smc(is_sub, symbol="XAUUSD", timeframe="M15", config=SMCConfig())
        strat_is = SMCConfluenceStrategy(h4_df=h4_df, news_calendar_source=NEWS_PATH, config=exp_h_cfg)
        acc_is, _, _ = strat_is.generate_candidates(is_sub, timeframe="M15", smc_result=smc_is)
        bt_is = run_confluence_backtest(is_sub, acc_is, config=BASE_BCONFIG)
        m_is = extract_metrics(bt_is)

        # Run OOS
        smc_oos = analyze_smc(oos_sub, symbol="XAUUSD", timeframe="M15", config=SMCConfig())
        strat_oos = SMCConfluenceStrategy(h4_df=h4_df, news_calendar_source=NEWS_PATH, config=exp_h_cfg)
        acc_oos, _, _ = strat_oos.generate_candidates(oos_sub, timeframe="M15", smc_result=smc_oos)
        bt_oos = run_confluence_backtest(oos_sub, acc_oos, config=BASE_BCONFIG)
        m_oos = extract_metrics(bt_oos)

        # Detailed breakdown of OOS trades
        oos_trades = m_oos["rule_trades"]
        long_trades = sum(1 for t in oos_trades if t.get("direction") in ("BULLISH", "BUY"))
        short_trades = sum(1 for t in oos_trades if t.get("direction") in ("BEARISH", "SELL"))

        # Session breakdown
        london_trades = 0
        ny_trades = 0
        other_trades = 0
        for t in oos_trades:
            t_entry = pd.to_datetime(t.get("entry_time"), utc=True)
            hr = t_entry.hour
            if 7 <= hr < 13:
                london_trades += 1
            elif 13 <= hr < 21:
                ny_trades += 1
            else:
                other_trades += 1

        # Regime breakdown
        trending_trades = 0
        ranging_trades = 0
        for t in oos_trades:
            t_entry = pd.to_datetime(t.get("entry_time"), utc=True)
            match = oos_sub[oos_sub["time"] == t_entry]
            if len(match) > 0 and match["regime"].iloc[0] == "TRENDING":
                trending_trades += 1
            else:
                ranging_trades += 1

        # Holding bars
        holding_bars_list = [t.get("bars_held", 0) for t in oos_trades]
        avg_holding_bars = round(sum(holding_bars_list) / len(holding_bars_list), 1) if holding_bars_list else 0.0

        deg_ratio = round(m_oos["profit_factor"] / m_is["profit_factor"], 3) if m_is["profit_factor"] > 0 and not math.isinf(m_is["profit_factor"]) else 0.0
        is_pos = m_oos["net_pnl"] > 0

        print(f"  IS:  Trades={m_is['trades']}, WR={m_is['win_rate']}%, PF={m_is['profit_factor']:.3f}, Net=${m_is['net_pnl']:.2f}")
        print(f"  OOS: Trades={m_oos['trades']}, WR={m_oos['win_rate']}%, PF={m_oos['profit_factor']:.3f}, Net=${m_oos['net_pnl']:.2f} | Positive: {is_pos}")

        wf_rows.append({
            "fold": fold_i,
            "is_start": is_start_t,
            "is_end": is_end_t,
            "is_bars": len(is_sub),
            "is_trades": m_is["trades"],
            "is_wr": m_is["win_rate"],
            "is_pf": m_is["profit_factor"],
            "is_net": m_is["net_pnl"],
            "is_dd": m_is["max_dd_pct"],
            "oos_start": oos_start_t,
            "oos_end": oos_end_t,
            "oos_bars": len(oos_sub),
            "oos_trades": m_oos["trades"],
            "oos_wins": m_oos["wins"],
            "oos_losses": m_oos["losses"],
            "oos_wr": m_oos["win_rate"],
            "oos_pf": m_oos["profit_factor"],
            "oos_net": m_oos["net_pnl"],
            "oos_dd": m_oos["max_dd_pct"],
            "oos_expectancy": m_oos["expectancy"],
            "avg_holding_bars": avg_holding_bars,
            "long_trades": long_trades,
            "short_trades": short_trades,
            "london_trades": london_trades,
            "ny_trades": ny_trades,
            "other_session_trades": other_trades,
            "trending_regime_trades": trending_trades,
            "ranging_regime_trades": ranging_trades,
            "degradation_ratio": deg_ratio,
            "oos_positive": is_pos,
        })

    # Save Walk-Forward CSV
    pd.DataFrame(wf_rows).to_csv(WF_CSV_PATH, index=False)
    print(f"\nSaved Phase 3 walk-forward validation: {WF_CSV_PATH}")

    pos_folds = sum(1 for r in wf_rows if r["oos_positive"])
    total_oos_trades = sum(r["oos_trades"] for r in wf_rows)
    total_oos_net = sum(r["oos_net"] for r in wf_rows)
    print("\n" + "=" * 80)
    print("WALK-FORWARD SUMMARY:")
    print(f"  Positive Folds: {pos_folds}/{n_folds} ({pos_folds/n_folds*100:.1f}%)")
    print(f"  Total OOS Trades: {total_oos_trades}")
    print(f"  Total OOS Net P&L: ${total_oos_net:.2f}")
    print("=" * 80)


if __name__ == "__main__":
    run_phase3()
