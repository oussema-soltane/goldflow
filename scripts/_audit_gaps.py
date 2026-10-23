"""
Phase 3B — Gap Analysis Script.
Classifies each timestamp gap in each timeframe as:
  - WEEKEND_CLOSURE: Friday 21:00 UTC to Sunday 22:00 UTC (standard FX/Gold)
  - BROKER_HOLIDAY: multi-day closure outside weekend pattern
  - UNEXPLAINED_INTRADAY: gap during expected trading hours (Mon-Fri, 22:00-20:59)
  - END_OF_WEEK: normal Friday-to-Monday roll
Documents all assumptions explicitly.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw"
REPORTS = ROOT / "reports"
TIMEFRAMES = ["M5", "M15", "H1", "H4"]

# ── Broker trading schedule assumptions ─────────────────────────────────────
# Gold (XAU/USD) on MetaQuotes-Demo server:
# Trading opens: Sunday 22:00 UTC
# Trading closes: Friday 21:00 UTC
# Weekend gap: Friday 21:00 UTC → Sunday 22:00 UTC = ~49 hours
# Nightly maintenance is only a hypothesis. If a verified IANA server timezone
# is present in the sidecar, gaps can be compared with a local 22:00-02:00 window.
# Otherwise such gaps remain unexplained; the script never assumes a fixed UTC+3.

FRIDAY_CLOSE_HOUR = 21   # UTC
SUNDAY_OPEN_HOUR = 22    # UTC
WEEKEND_GAP_HOURS_MIN = 46.0   # minimum normal weekend gap (hrs)
WEEKEND_GAP_HOURS_MAX = 52.0   # maximum normal weekend gap (hrs)

MAINT_START_LOCAL_HOUR = 22
MAINT_END_LOCAL_HOUR = 2
MAINT_MAX_DURATION_HOURS = 3.0

def main() -> None:
    now_utc = datetime.now(timezone.utc)

    all_gaps = {}

    print("=" * 70)
    print("  GOLDFLOW — PHASE 3B GAP ANALYSIS")
    print("=" * 70)
    print(f"\nAnalysis run at (UTC): {now_utc.isoformat()}")
    print(f"\nBroker schedule assumption: XAU/USD on MetaQuotes-Demo")
    print(f"  Market open  : Sunday  {SUNDAY_OPEN_HOUR:02d}:00 UTC")
    print(f"  Market close : Friday  {FRIDAY_CLOSE_HOUR:02d}:00 UTC")
    print(f"  Normal weekend gap assumption: {WEEKEND_GAP_HOURS_MIN:.0f}–{WEEKEND_GAP_HOURS_MAX:.0f} hours")
    print("  Nightly maintenance: only a suspected pattern when a server timezone is recorded")
    print()

    for tf in TIMEFRAMES:
        raw_path = RAW / f"XAUUSD_{tf}_raw.csv"
        if not raw_path.exists():
            print(f"[SKIP] {tf}: raw file not found")
            continue

        meta_path = ROOT / "data/processed" / f"XAUUSD_{tf}_clean.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        timestamp_status = meta.get("timestamp_integrity_status")
        timestamp_mode = meta.get("timestamp_mode")
        timestamp_mode_verified = meta.get("timestamp_mode_verified") is True
        server_timezone = meta.get("server_timezone")

        if timestamp_status != "verified" or not timestamp_mode_verified or timestamp_mode not in {"posix_utc", "server_wall_clock"}:
            all_gaps[tf] = {
                "status": "BLOCKED_UNTRUSTED_TIMESTAMPS",
                "timestamp_mode": timestamp_mode,
                "timestamp_integrity_status": timestamp_status,
                "gaps": [],
            }
            print(f"[BLOCKED] {tf}: timestamp integrity is {timestamp_status!r}; re-ingest before classifying gaps.")
            continue

        df = pd.read_csv(raw_path)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.sort_values("time").reset_index(drop=True)

        tf_minutes = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}[tf]
        expected_gap_minutes = tf_minutes
        # Tolerance: allow up to 1.5× bar duration before flagging
        gap_threshold_minutes = expected_gap_minutes * 1.5

        gaps = []
        for i in range(1, len(df)):
            t_prev = df["time"].iloc[i - 1]
            t_curr = df["time"].iloc[i]
            delta_minutes = (t_curr - t_prev).total_seconds() / 60.0

            if delta_minutes <= gap_threshold_minutes:
                continue  # normal sequential bar

            gap_hours = delta_minutes / 60.0
            prev_weekday = t_prev.dayofweek   # Mon=0, Fri=4, Sat=5, Sun=6
            curr_weekday = t_curr.dayofweek
            prev_hour = t_prev.hour
            curr_hour = t_curr.hour

            # Classify
            if (
                prev_weekday == 4 and prev_hour >= FRIDAY_CLOSE_HOUR - 1
                and curr_weekday == 6 and curr_hour >= SUNDAY_OPEN_HOUR - 1
                and WEEKEND_GAP_HOURS_MIN <= gap_hours <= WEEKEND_GAP_HOURS_MAX
            ):
                classification = "WEEKEND_CLOSURE"
            elif (
                prev_weekday == 4 and prev_hour >= FRIDAY_CLOSE_HOUR - 4
                and curr_weekday == 6
            ):
                # Wider window — still likely weekend
                classification = "WEEKEND_CLOSURE_EDGE"
            elif delta_minutes >= 48 * 60:
                classification = "BROKER_HOLIDAY_OR_EXTENDED_CLOSURE"
            elif server_timezone and gap_hours <= MAINT_MAX_DURATION_HOURS:
                # The local maintenance window is a hypothesis, not a confirmed broker schedule.
                local_prev = t_prev.tz_convert(server_timezone)
                local_curr = t_curr.tz_convert(server_timezone)
                if (
                    local_prev.weekday() < 5
                    and local_curr.weekday() < 5
                    and local_prev.hour >= MAINT_START_LOCAL_HOUR
                    and local_curr.hour <= MAINT_END_LOCAL_HOUR
                ):
                    classification = "SUSPECTED_NIGHTLY_MAINTENANCE"
                else:
                    classification = "UNEXPLAINED_INTRADAY_GAP"
            else:
                # Gap during expected trading window
                classification = "UNEXPLAINED_INTRADAY_GAP"

            gaps.append({
                "gap_start": t_prev.isoformat(),
                "gap_end": t_curr.isoformat(),
                "gap_duration_hours": round(gap_hours, 2),
                "gap_duration_minutes": round(delta_minutes, 1),
                "prev_weekday_name": t_prev.strftime("%A"),
                "curr_weekday_name": t_curr.strftime("%A"),
                "classification": classification,
                "bar_index_prev": int(i - 1),
                "bar_index_curr": int(i),
            })

        all_gaps[tf] = {
            "status": "ANALYZED",
            "timestamp_mode": timestamp_mode,
            "timestamp_integrity_status": timestamp_status,
            "server_timezone": server_timezone,
            "gaps": gaps,
        }

        # Summary
        counts = {}
        for g in gaps:
            c = g["classification"]
            counts[c] = counts.get(c, 0) + 1

        print(f"--- {tf} ({len(df)} bars, bar={tf_minutes}min, threshold={gap_threshold_minutes:.0f}min) ---")
        print(f"  Total gaps detected: {len(gaps)}")
        for cls, cnt in sorted(counts.items()):
            flag = " *** REQUIRES INVESTIGATION ***" if "UNEXPLAINED" in cls else ""
            print(f"  {cls}: {cnt}{flag}")
        if gaps:
            unexplained = [g for g in gaps if g["classification"] == "UNEXPLAINED_INTRADAY_GAP"]
            if unexplained:
                print(f"  UNEXPLAINED gaps detail:")
                for g in unexplained[:5]:
                    print(f"    {g['gap_start']} -> {g['gap_end']} ({g['gap_duration_hours']:.1f}h, {g['prev_weekday_name']}->{g['curr_weekday_name']})")
        print()

    # Save
    REPORTS.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS / "gap_analysis.json"
    out_path.write_text(json.dumps({
        "analysis_run_utc": now_utc.isoformat(),
        "broker_schedule_assumptions": {
            "instrument": "XAU/USD (Gold)",
            "server": "MetaQuotes-Demo (assumed)",
            "market_open_utc": f"Sunday {SUNDAY_OPEN_HOUR:02d}:00",
            "market_close_utc": f"Friday {FRIDAY_CLOSE_HOUR:02d}:00",
            "normal_weekend_gap_hours_range": [WEEKEND_GAP_HOURS_MIN, WEEKEND_GAP_HOURS_MAX],
            "nightly_maintenance_window_server_local": f"{MAINT_START_LOCAL_HOUR:02d}:00–{MAINT_END_LOCAL_HOUR:02d}:00",
            "nightly_maintenance_max_duration_hours": MAINT_MAX_DURATION_HOURS,
            "note": "Market-session times are assumptions, not verified broker specifications. "
                    "Nightly gaps are labelled SUSPECTED only when a server timezone is recorded; "
                    "untrusted legacy timestamp files are not classified."
        },
        "gaps_by_timeframe": all_gaps
    }, indent=2, default=str), encoding="utf-8")
    print(f"Gap analysis saved: {out_path}")


if __name__ == '__main__':
    main()
