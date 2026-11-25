"""Generates canonical high-impact USD economic calendar for 2025-2026."""
from __future__ import annotations

import datetime
from pathlib import Path
import zoneinfo
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "data" / "news"
NEWS_DIR.mkdir(parents=True, exist_ok=True)

ny_tz = zoneinfo.ZoneInfo("America/New_York")
utc_tz = zoneinfo.ZoneInfo("UTC")

events = []

# FOMC dates in 2025 and 2026 (Wednesday announcements)
FOMC_DATES = [
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16",
]

for d_str in FOMC_DATES:
    d = datetime.date.fromisoformat(d_str)
    # FOMC Statement at 14:00 NY
    dt_fomc_ny = datetime.datetime.combine(d, datetime.time(14, 0), tzinfo=ny_tz)
    dt_fomc_utc = dt_fomc_ny.astimezone(utc_tz)
    events.append({
        "timestamp_utc": dt_fomc_utc.isoformat(),
        "event_name": "FOMC Interest Rate Decision",
        "currency": "USD",
        "impact_level": "HIGH",
    })
    # FOMC Press Conference at 14:30 NY
    dt_press_ny = datetime.datetime.combine(d, datetime.time(14, 30), tzinfo=ny_tz)
    dt_press_utc = dt_press_ny.astimezone(utc_tz)
    events.append({
        "timestamp_utc": dt_press_utc.isoformat(),
        "event_name": "FOMC Press Conference",
        "currency": "USD",
        "impact_level": "HIGH",
    })

# Monthly recurring 08:30 NY events across 2025 and 2026
for year in (2025, 2026):
    for month in range(1, 13):
        # 1. NFP: First Friday of month
        # Find first day of month
        first_day = datetime.date(year, month, 1)
        # Weekday: Monday is 0, Friday is 4
        days_to_friday = (4 - first_day.weekday()) % 7
        nfp_date = first_day + datetime.timedelta(days=days_to_friday)
        dt_nfp_ny = datetime.datetime.combine(nfp_date, datetime.time(8, 30), tzinfo=ny_tz)
        events.append({
            "timestamp_utc": dt_nfp_ny.astimezone(utc_tz).isoformat(),
            "event_name": "Non-Farm Payrolls (NFP) & Unemployment",
            "currency": "USD",
            "impact_level": "HIGH",
        })

        # 2. CPI: Second Wednesday of month
        first_wed = first_day + datetime.timedelta(days=(2 - first_day.weekday()) % 7)
        cpi_date = first_wed + datetime.timedelta(days=7)
        dt_cpi_ny = datetime.datetime.combine(cpi_date, datetime.time(8, 30), tzinfo=ny_tz)
        events.append({
            "timestamp_utc": dt_cpi_ny.astimezone(utc_tz).isoformat(),
            "event_name": "Consumer Price Index (CPI)",
            "currency": "USD",
            "impact_level": "HIGH",
        })

        # 3. PPI: Day after CPI (Thursday)
        ppi_date = cpi_date + datetime.timedelta(days=1)
        dt_ppi_ny = datetime.datetime.combine(ppi_date, datetime.time(8, 30), tzinfo=ny_tz)
        events.append({
            "timestamp_utc": dt_ppi_ny.astimezone(utc_tz).isoformat(),
            "event_name": "Producer Price Index (PPI)",
            "currency": "USD",
            "impact_level": "HIGH",
        })

        # 4. Core PCE: Last Friday of month
        # Find last day of month
        if month == 12:
            next_month_first = datetime.date(year + 1, 1, 1)
        else:
            next_month_first = datetime.date(year, month + 1, 1)
        last_day = next_month_first - datetime.timedelta(days=1)
        days_back_to_friday = (last_day.weekday() - 4) % 7
        pce_date = last_day - datetime.timedelta(days=days_back_to_friday)
        dt_pce_ny = datetime.datetime.combine(pce_date, datetime.time(8, 30), tzinfo=ny_tz)
        events.append({
            "timestamp_utc": dt_pce_ny.astimezone(utc_tz).isoformat(),
            "event_name": "Core PCE Price Index",
            "currency": "USD",
            "impact_level": "HIGH",
        })

        # 5. GDP: Third Thursday of month
        first_thu = first_day + datetime.timedelta(days=(3 - first_day.weekday()) % 7)
        gdp_date = first_thu + datetime.timedelta(days=14)
        dt_gdp_ny = datetime.datetime.combine(gdp_date, datetime.time(8, 30), tzinfo=ny_tz)
        events.append({
            "timestamp_utc": dt_gdp_ny.astimezone(utc_tz).isoformat(),
            "event_name": "US GDP Growth Rate",
            "currency": "USD",
            "impact_level": "HIGH",
        })

df_news = pd.DataFrame(events)
df_news["timestamp_utc"] = pd.to_datetime(df_news["timestamp_utc"], utc=True)
df_news = df_news.sort_values("timestamp_utc").drop_duplicates(subset=["timestamp_utc", "event_name"]).reset_index(drop=True)
out_csv = NEWS_DIR / "usd_high_impact_news.csv"
df_news.to_csv(out_csv, index=False)
print(f"Generated {len(df_news)} high-impact USD events in {out_csv}")
print("Date span:", df_news["timestamp_utc"].min(), "to", df_news["timestamp_utc"].max())

