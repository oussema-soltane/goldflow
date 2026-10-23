"""Read-only live MT5 timestamp diagnostic. Does not place or modify orders.

Run during active trading after confirming Windows time synchronization:
  py -3.13 scripts/diagnose_mt5_timestamps.py --symbol XAUUSD --server-timezone Europe/Athens

The result is evidence for choosing a mode, not an automatic approval.

Bug fixed (Phase 3B.1): mt5.initialize() is now wrapped in a threading timeout
so the script does not hang indefinitely when the MT5 terminal is not running.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import threading
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.loader import convert_mt5_epoch_times, is_terminal_running

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

DEFAULT_INIT_TIMEOUT_SEC = 8.0


def _iso(value: dt.datetime | pd.Timestamp) -> str:
    return pd.Timestamp(value).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only MT5 timestamp diagnostic")
    parser.add_argument("--symbol", default="XAUUSD", help="Exact broker symbol, e.g. XAUUSD or GOLD")
    parser.add_argument(
        "--server-timezone",
        default=None,
        help="Optional candidate IANA server timezone for testing wall-clock mode, e.g. Europe/Athens",
    )
    parser.add_argument("--tolerance-seconds", type=float, default=120.0)
    args = parser.parse_args()

    if mt5 is None:
        print("ERROR: MetaTrader5 Python package is not installed in this environment.")
        return 2

    if not is_terminal_running():
        print(
            "ERROR: MetaTrader 5 terminal process is not running. "
            "Please launch the MT5 desktop application and log in before running this diagnostic."
        )
        return 2

    # Use a threading timeout so the script does not hang when MT5 refuses IPC.
    before = dt.datetime.now(dt.timezone.utc)
    init_result: dict[str, Any] = {"ok": False, "err": None}

    def _init() -> None:
        try:
            init_result["ok"] = bool(mt5.initialize())
            if not init_result["ok"]:
                init_result["err"] = mt5.last_error()
        except Exception as exc:
            init_result["err"] = str(exc)

    t = threading.Thread(target=_init, daemon=True)
    t.start()
    t.join(timeout=DEFAULT_INIT_TIMEOUT_SEC)
    if t.is_alive():
        print(
            f"ERROR: mt5.initialize() did not respond within {DEFAULT_INIT_TIMEOUT_SEC}s. "
            "The MT5 terminal may be starting up or unresponsive. "
            "Ensure you are logged in and the terminal is fully loaded."
        )
        return 2
    if not init_result["ok"]:
        print(f"ERROR: mt5.initialize() failed: {init_result['err']}")
        return 2

    try:
        if not mt5.symbol_select(args.symbol, True):
            print(f"ERROR: Cannot select {args.symbol}: {mt5.last_error()}")
            return 2

        tick = mt5.symbol_info_tick(args.symbol)
        after = dt.datetime.now(dt.timezone.utc)
        if tick is None or not getattr(tick, "time", 0):
            print(f"ERROR: No usable tick returned for {args.symbol}: {mt5.last_error()}")
            return 2

        reference = before + (after - before) / 2
        raw_tick = int(tick.time)
        posix_tick = dt.datetime.fromtimestamp(raw_tick, tz=dt.timezone.utc)
        posix_age = (reference - posix_tick).total_seconds()

        report: dict[str, Any] = {
            "run_started_utc": before.isoformat(),
            "run_finished_utc": after.isoformat(),
            "reference_utc_midpoint": reference.isoformat(),
            "symbol": args.symbol,
            "tick_raw_epoch_seconds": raw_tick,
            "tick_raw_epoch_milliseconds": int(getattr(tick, "time_msc", raw_tick * 1000)),
            "tick_interpreted_as_posix_utc": posix_tick.isoformat(),
            "posix_candidate_age_seconds": round(posix_age, 3),
            "tolerance_seconds": args.tolerance_seconds,
            "server_timezone_candidate": args.server_timezone,
            "warning": (
                "Verify Windows time synchronization first. A stale tick, closed market, "
                "or incorrect machine clock makes this diagnostic inconclusive."
            ),
        }

        posix_near = abs(posix_age) <= args.tolerance_seconds
        wall_near = False
        if args.server_timezone:
            try:
                wall_series, corrections = convert_mt5_epoch_times(
                    [raw_tick],
                    timestamp_mode="server_wall_clock",
                    server_timezone=args.server_timezone,
                )
                wall_tick = wall_series.iloc[0].to_pydatetime()
                wall_age = (reference - wall_tick).total_seconds()
                wall_near = abs(wall_age) <= args.tolerance_seconds
                report["tick_interpreted_as_server_wall_clock_utc"] = wall_tick.isoformat()
                report["server_wall_clock_candidate_age_seconds"] = round(wall_age, 3)
                report["candidate_correction_seconds"] = int(corrections.iloc[0])
            except Exception as exc:
                report["server_wall_clock_candidate_error"] = str(exc)

        if posix_near and not wall_near:
            recommendation = "posix_utc"
            confidence = "candidate_matches_clock_within_tolerance"
        elif wall_near and not posix_near:
            recommendation = "server_wall_clock"
            confidence = "candidate_matches_clock_within_tolerance"
        else:
            recommendation = "INCONCLUSIVE"
            confidence = "neither_or_both_candidates_match"
        report["recommendation"] = recommendation
        report["recommendation_confidence"] = confidence

        rates = mt5.copy_rates_from_pos(args.symbol, mt5.TIMEFRAME_M5, 0, 3)
        bar_records = []
        if rates is not None:
            for row in rates:
                raw = int(row["time"])
                record = {
                    "raw_epoch_seconds": raw,
                    "posix_utc_candidate": dt.datetime.fromtimestamp(
                        raw, tz=dt.timezone.utc
                    ).isoformat(),
                }
                if args.server_timezone:
                    try:
                        converted, correction = convert_mt5_epoch_times(
                            [raw],
                            timestamp_mode="server_wall_clock",
                            server_timezone=args.server_timezone,
                        )
                        record["server_wall_clock_utc_candidate"] = converted.iloc[0].isoformat()
                        record["correction_seconds"] = int(correction.iloc[0])
                    except Exception as exc:
                        record["server_wall_clock_candidate_error"] = str(exc)
                bar_records.append(record)
        report["sample_m5_bars"] = bar_records

        output = ROOT / "reports" / "mt5_timestamp_diagnostic.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("GoldFlow — MT5 Timestamp Diagnostic (read-only)")
        print(f"Symbol: {args.symbol}")
        print(f"Machine UTC reference: {reference.isoformat()}")
        print(f"Raw tick epoch: {raw_tick}")
        print(f"POSIX UTC candidate: {posix_tick.isoformat()} (age {posix_age:.1f}s)")
        if args.server_timezone and "server_wall_clock_candidate_age_seconds" in report:
            print(
                "Server-wall-clock candidate: "
                f"{report['tick_interpreted_as_server_wall_clock_utc']} "
                f"(age {report['server_wall_clock_candidate_age_seconds']:.1f}s)"
            )
        print(f"Recommendation: {recommendation}")
        print("This is not approval if Windows time synchronization or the tick freshness is uncertain.")
        print(f"Report saved: {output}")
        return 0 if recommendation != "INCONCLUSIVE" else 3
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
