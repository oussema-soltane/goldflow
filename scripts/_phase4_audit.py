"""Phase 4 audit: reproduce backtest metrics, investigate common-window M5/M15 anomalies."""
from __future__ import annotations
import json
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    # --- Timeframe date ranges ---
    print("=== Timeframe date ranges ===")
    frames = {}
    for tf in ["H4", "H1", "M15", "M5"]:
        df = pd.read_csv(ROOT / "data" / "processed" / f"XAUUSD_{tf}_clean.csv")
        df["time"] = pd.to_datetime(df["time"], utc=True)
        frames[tf] = df
        print(f"{tf}: {len(df)} rows  start={df.time.min()}  end={df.time.max()}")

    starts = [frames[tf].time.min() for tf in ["H4", "H1", "M15", "M5"]]
    ends   = [frames[tf].time.max() for tf in ["H4", "H1", "M15", "M5"]]
    common_start = max(starts)
    common_end   = min(ends)
    print(f"\nCommon window: {common_start}  to  {common_end}")
    for tf in ["H4", "H1", "M15", "M5"]:
        df_win = frames[tf][frames[tf].time <= common_end]
        print(f"  {tf} bars in common window (<=end): {len(df_win)}")

    # --- M5 identity check ---
    print("\n=== M5 common-window vs full-history identity ===")
    m5_start = frames["M5"].time.min()
    print(f"M5 data start: {m5_start}")
    print(f"Common window start: {common_start}")
    print(f"M5 starts AT common_start: {m5_start == common_start}")
    print("=> M5 common-window and full-history are EXPECTED to be identical because M5 data")
    print("  begins exactly at the common window start. No signals exist before the window.")

    # --- M15 EOD investigation ---
    print("\n=== M15 common-window END_OF_DATA analysis ===")
    trades_cw = pd.read_csv(ROOT / "reports" / "smc_backtest_trades_common_window.csv")
    m15_trades = trades_cw[trades_cw.timeframe == "M15"]
    closed = m15_trades[m15_trades.status == "CLOSED"]
    print(f"M15 closed trades: {len(closed)}")
    for _, row in closed.iterrows():
        print(f"  {row.setup_id}: {row.exit_reason}  net_pnl={row.net_pnl:.2f}  signal={row.signal_time}")
    eod = closed[closed.exit_reason == "END_OF_DATA"]
    rule = closed[closed.exit_reason != "END_OF_DATA"]
    print(f"\nRule exits: {len(rule)}, rule-exit net P&L: {rule.net_pnl.sum():.2f}")
    print(f"EOD exits:  {len(eod)}, EOD net P&L:       {eod.net_pnl.sum():.2f}")
    print(f"Total net P&L (incl EOD): {closed.net_pnl.sum():.2f}")

    # --- Load stored metrics ---
    print("\n=== Stored metrics cross-check ===")
    for mode in ["full_history", "common_window"]:
        with open(ROOT / "reports" / f"smc_backtest_metrics_{mode}.json") as f:
            payload = json.load(f)
        print(f"\n[{mode}]")
        for tf in ["H4", "H1", "M15", "M5"]:
            m = payload["metrics_by_timeframe"][tf]
            print(
                f"  {tf}: candidates={m['candidate_count']} rule_exits={m['rule_exit_trades']} "
                f"eod={m['end_of_data_exits']} skipped={m['skipped_candidates']} "
                f"win_rate={m.get('win_rate_pct')}% net_profit={m['net_profit']:.2f} "
                f"eod_pnl={m.get('end_of_data_pnl', 0):.2f}"
            )

    # --- Independent metric reproduction ---
    print("\n=== Independent metric reproduction from trade ledger ===")
    for fname, label in [
        ("smc_backtest_trades_full_history.csv", "full_history"),
        ("smc_backtest_trades_common_window.csv", "common_window"),
    ]:
        trades = pd.read_csv(ROOT / "reports" / fname)
        print(f"\n[{label}]")
        for tf in ["H4", "H1", "M15", "M5"]:
            sub = trades[trades.timeframe == tf]
            closed_t = sub[sub.status == "CLOSED"]
            skipped_t = sub[sub.status == "SKIPPED"]
            rule_t = closed_t[closed_t.exit_reason != "END_OF_DATA"]
            eod_t  = closed_t[closed_t.exit_reason == "END_OF_DATA"]
            wins   = rule_t[rule_t.net_pnl > 0]
            losses = rule_t[rule_t.net_pnl < 0]
            win_rate = len(wins) / len(rule_t) * 100 if len(rule_t) else None
            total_net = closed_t.net_pnl.sum()
            eod_net = eod_t.net_pnl.sum()
            gp = wins.net_pnl.sum()
            gl = abs(losses.net_pnl.sum())
            pf = gp / gl if gl > 0 else ("∞" if gp > 0 else "N/A")
            print(
                f"  {tf}: cands={len(sub)} rule={len(rule_t)} eod={len(eod_t)} skip={len(skipped_t)} "
                f"wins={len(wins)} wr={win_rate:.1f}% net={total_net:.2f} eod_pnl={eod_net:.2f} PF={pf}"
            )


if __name__ == "__main__":
    main()
