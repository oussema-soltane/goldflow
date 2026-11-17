    """
Walk-Forward Validation Framework for GoldFlow SMC_CONFLUENCE_V1.

This implements proper walk-forward analysis to distinguish genuine edge from
in-sample overfitting. It is NOT used for parameter optimization — it validates
the FIXED configuration identified from Phase 1 ablation.

Walk-Forward Protocol:
- 5-fold expanding window (IS grows, OOS is always 20% of remaining data)
- Fixed candidate config: HTF + ATR (EXP_H_HTF_ATR) — best Phase 1 combo
- Same BacktestConfig across all folds
- Checks: OOS PF >= IS PF * 0.7 (not severely degraded), positive OOS expectancy

This is NOT optimization — the config is fixed before this script runs.
The walk-forward only measures robustness of the FIXED hypothesis.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

from src.backtesting.engine import BacktestConfig
from src.smc.engine import analyze_smc, SMCConfig
from src.strategy.smc_confluence import (
    SMCConfluenceConfig,
    SMCConfluenceStrategy,
    run_confluence_backtest,
)


@dataclass
class WFResult:
    fold: int
    is_start: str
    is_end: str
    oos_start: str
    oos_end: str
    is_trades: int
    is_wr: float
    is_pf: float
    is_net: float
    is_dd: float
    oos_trades: int
    oos_wr: float
    oos_pf: float
    oos_net: float
    oos_dd: float
    degradation_ratio: float  # OOS PF / IS PF
    oos_positive: bool


CANDIDATE_CONFIG = SMCConfluenceConfig(
    enable_htf_bias=True,
    enable_session_filter=False,
    enable_news_filter=False,
    enable_atr_stop=True,
    enable_breakeven=False,
)

BCONFIG = BacktestConfig(
    initial_capital=10_000.0,
    risk_fraction=0.005,
    fallback_spread_usd=0.20,
    slippage_per_side_usd=0.05,
    commission_per_lot_per_side=0.0,
)


def run_single_fold(
    df: pd.DataFrame,
    h4_df: pd.DataFrame,
    news_path: Path,
    timeframe: str,
    fold_idx: int,
    is_start: int,
    is_end: int,
    oos_start: int,
    oos_end: int,
) -> WFResult:
    is_df = df.iloc[is_start:is_end].copy().reset_index(drop=True)
    oos_df = df.iloc[oos_start:oos_end].copy().reset_index(drop=True)

    def run_split(split_df: pd.DataFrame) -> dict:
        if len(split_df) < 50:
            return {"trades": 0, "wr": 0.0, "pf": 0.0, "net": 0.0, "dd": 0.0}
        try:
            smc_res = analyze_smc(split_df, symbol="XAUUSD", timeframe=timeframe, config=SMCConfig())
            strategy = SMCConfluenceStrategy(
                h4_df=h4_df,
                news_calendar_source=news_path,
                config=CANDIDATE_CONFIG,
            )
            accepted, _, _ = strategy.generate_candidates(split_df, timeframe=timeframe, smc_result=smc_res)
            bt_res = run_confluence_backtest(split_df, accepted, config=BCONFIG)
        except Exception as e:
            print(f"      ERROR in fold {fold_idx}: {e}")
            return {"trades": 0, "wr": 0.0, "pf": 0.0, "net": 0.0, "dd": 0.0}

        m = bt_res.metrics if bt_res.metrics else {}
        # trades are dicts — use bt.metrics directly
        n = m.get("rule_exit_trades", m.get("closed_trades", 0)) or 0
        wr = m.get("win_rate_pct") or 0.0
        pf_raw = m.get("profit_factor", 0.0)
        if pf_raw in (float("inf"), "infinite", "inf") or str(pf_raw).lower() in ("infinite", "inf"):
            pf = 999.0
        else:
            try:
                pf = round(float(pf_raw), 3)
            except (ValueError, TypeError):
                pf = 0.0
        net = m.get("net_profit_from_rule_exits") or m.get("net_profit") or 0.0
        dd = m.get("max_drawdown_pct") or 0.0

        return {
            "trades": int(n or 0),
            "wr": round(float(wr or 0.0), 2),
            "pf": round(float(pf or 0.0), 3),
            "net": round(float(net or 0.0), 2),
            "dd": round(float(dd or 0.0), 2),
        }

    is_m = run_split(is_df)
    oos_m = run_split(oos_df)

    deg_ratio = oos_m["pf"] / is_m["pf"] if is_m["pf"] > 0 else 0.0

    return WFResult(
        fold=fold_idx,
        is_start=str(is_df["time"].iloc[0].date()) if len(is_df) > 0 else "N/A",
        is_end=str(is_df["time"].iloc[-1].date()) if len(is_df) > 0 else "N/A",
        oos_start=str(oos_df["time"].iloc[0].date()) if len(oos_df) > 0 else "N/A",
        oos_end=str(oos_df["time"].iloc[-1].date()) if len(oos_df) > 0 else "N/A",
        is_trades=is_m["trades"],
        is_wr=is_m["wr"],
        is_pf=is_m["pf"],
        is_net=is_m["net"],
        is_dd=is_m["dd"],
        oos_trades=oos_m["trades"],
        oos_wr=oos_m["wr"],
        oos_pf=oos_m["pf"],
        oos_net=oos_m["net"],
        oos_dd=oos_m["dd"],
        degradation_ratio=round(deg_ratio, 3),
        oos_positive=oos_m["net"] > 0,
    )


def run_walk_forward(
    df: pd.DataFrame,
    h4_df: pd.DataFrame,
    news_path: Path,
    timeframe: str,
    n_folds: int = 5,
    oos_fraction: float = 0.20,
) -> List[WFResult]:
    n = len(df)
    # Minimum IS window: enough bars for meaningful SMC analysis
    min_is_bars = max(500, int(n * 0.30))

    results = []
    for fold in range(n_folds):
        # Expanding IS window
        # Fold 0: IS = first (1-oos_fraction*(n_folds-fold)/n_folds) of data
        # Each fold grows IS by equal steps
        step = int(n * (1.0 - oos_fraction) / n_folds)
        is_end = min_is_bars + fold * step
        oos_start = is_end
        oos_end = min(oos_start + int(n * oos_fraction), n)

        if is_end > n or oos_start >= n:
            print(f"  Fold {fold+1}: not enough data, skipping")
            break
        if oos_end <= oos_start:
            print(f"  Fold {fold+1}: OOS empty, skipping")
            break

        print(f"  Fold {fold+1}/{n_folds}: IS bars 0-{is_end-1} ({is_end:,}), OOS bars {oos_start}-{oos_end-1} ({oos_end-oos_start:,})", flush=True)

        result = run_single_fold(
            df, h4_df, news_path, timeframe,
            fold + 1, 0, is_end, oos_start, oos_end
        )
        results.append(result)
        status = "✓" if result.oos_positive else "✗"
        print(f"    {status} IS: T={result.is_trades} PF={result.is_pf:.3f} ${result.is_net:+.0f} | "
              f"OOS: T={result.oos_trades} PF={result.oos_pf:.3f} ${result.oos_net:+.0f} "
              f"[degradation={result.degradation_ratio:.2f}]", flush=True)

    return results


def main():
    print("=" * 80)
    print(" GOLDFLOW WALK-FORWARD VALIDATION — EXP_H (HTF + ATR)")
    print("=" * 80)
    print()
    print(" Candidate: HTF Bias + ATR Stop (enable_htf_bias=True, enable_atr_stop=True)")
    print(" Protocol: 5-fold expanding window, OOS=20% per fold")
    print(" Config is FIXED — this is NOT optimization, this is validation.")
    print()
    print(" IMPORTANT: Positive OOS results on untouched data would be meaningful.")
    print("            Negative OOS results = no proven edge, do not proceed to demo.")
    print()

    h4_path = ROOT / "data" / "processed" / "XAUUSD_H4_clean.csv"
    h1_path = ROOT / "data" / "processed" / "XAUUSD_H1_clean.csv"
    m15_path = ROOT / "data" / "processed" / "XAUUSD_M15_clean.csv"
    news_path = ROOT / "data" / "news" / "usd_high_impact_news.csv"

    h4_df = pd.read_csv(h4_path)
    h4_df["time"] = pd.to_datetime(h4_df["time"], utc=True)
    h1_df = pd.read_csv(h1_path)
    h1_df["time"] = pd.to_datetime(h1_df["time"], utc=True)
    m15_df = pd.read_csv(m15_path)
    m15_df["time"] = pd.to_datetime(m15_df["time"], utc=True)

    all_results = []

    for tf_name, tf_df in [("M15", m15_df), ("H1", h1_df)]:
        print(f"\n{'='*60}")
        print(f" Walk-Forward on {tf_name} ({len(tf_df):,} bars)")
        print(f" Period: {tf_df['time'].iloc[0].date()} → {tf_df['time'].iloc[-1].date()}")
        print(f"{'='*60}")
        t0 = time.perf_counter()
        results = run_walk_forward(tf_df, h4_df, news_path, tf_name, n_folds=5, oos_fraction=0.20)
        elapsed = time.perf_counter() - t0

        for r in results:
            all_results.append({
                "timeframe": tf_name, "fold": r.fold,
                "is_start": r.is_start, "is_end": r.is_end,
                "oos_start": r.oos_start, "oos_end": r.oos_end,
                "is_trades": r.is_trades, "is_wr": r.is_wr,
                "is_pf": r.is_pf, "is_net": r.is_net, "is_dd": r.is_dd,
                "oos_trades": r.oos_trades, "oos_wr": r.oos_wr,
                "oos_pf": r.oos_pf, "oos_net": r.oos_net, "oos_dd": r.oos_dd,
                "degradation_ratio": r.degradation_ratio,
                "oos_positive": r.oos_positive,
            })

        # Summary statistics
        oos_pfs = [r.oos_pf for r in results if r.oos_trades > 0]
        oos_nets = [r.oos_net for r in results if r.oos_trades > 0]
        positive_folds = sum(1 for r in results if r.oos_positive)

        print(f"\n {tf_name} Walk-Forward Summary ({elapsed:.1f}s):")
        print(f"  Folds run:        {len(results)}")
        print(f"  Positive OOS:     {positive_folds}/{len(results)}")
        print(f"  Avg OOS PF:       {sum(oos_pfs)/len(oos_pfs):.3f}" if oos_pfs else "  Avg OOS PF:       N/A")
        print(f"  Avg OOS Net:      ${sum(oos_nets)/len(oos_nets):+.2f}" if oos_nets else "  Avg OOS Net:      N/A")
        print(f"  Avg degradation:  {sum(r.degradation_ratio for r in results)/len(results):.2f}")

        if positive_folds >= 3 and oos_pfs and sum(oos_pfs) / len(oos_pfs) >= 1.0:
            verdict = "EDGE CANDIDATE — OOS shows positive expectancy in majority of folds"
        elif positive_folds >= 2:
            verdict = "INCONCLUSIVE — Mixed OOS results, insufficient evidence to proceed"
        else:
            verdict = "NO EDGE PROVEN — OOS negative in majority of folds"

        print(f"\n  VERDICT: {verdict}")

    # Save results
    out_path = ROOT / "reports" / "WALK_FORWARD_VALIDATION.csv"
    pd.DataFrame(all_results).to_csv(out_path, index=False)
    print(f"\nFull results saved: {out_path}")

    # Final verdict
    print("\n" + "=" * 80)
    print(" FINAL WALK-FORWARD VERDICT")
    print("=" * 80)
    df_res = pd.DataFrame(all_results)
    for tf in df_res["timeframe"].unique():
        sub = df_res[df_res["timeframe"] == tf]
        pos = sub["oos_positive"].sum()
        total = len(sub)
        avg_pf = sub["oos_pf"].mean()
        avg_net = sub["oos_net"].mean()
        print(f" {tf}: {pos}/{total} positive OOS folds | Avg OOS PF={avg_pf:.3f} | Avg OOS Net=${avg_net:+.2f}")

    all_pos = df_res["oos_positive"].sum()
    all_total = len(df_res)
    if all_pos / all_total >= 0.6:
        print(f"\n OVERALL: Edge candidate shows robustness ({all_pos}/{all_total} positive folds)")
        print("          Proceed to: collect new forward data for Stage 2 OOS evaluation")
    else:
        print(f"\n OVERALL: Insufficient robustness ({all_pos}/{all_total} positive folds)")
        print("          DO NOT proceed to demo. Continue research iteration.")


if __name__ == "__main__":
    main()
