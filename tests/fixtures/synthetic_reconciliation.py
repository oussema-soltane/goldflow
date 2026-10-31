"""
Synthetic reconciliation fixtures for Phase 6D Stage F.

Generates two deterministic CSV tick files representing hypothetical provider A
and provider B feeds for XAUUSD over a 5-minute window.  Used only to
demonstrate that the reconciliation tool operates correctly on known data.

No real market data is represented here.
"""

import csv
import pathlib

SYNTHETIC_DIR = pathlib.Path(__file__).parent.parent.parent / "data" / "synthetic"


def write_provider_a() -> pathlib.Path:
    """Provider A: 6 ticks, 2024-10-01 08:00–08:04 UTC, prices near 2735."""
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    path = SYNTHETIC_DIR / "provider_a_xauusd.csv"
    rows = [
        ("2024-10-01T08:00:00.000Z", 2735.10, 2735.12, 0.5, 0.5),
        ("2024-10-01T08:01:00.000Z", 2735.20, 2735.22, 0.4, 0.6),
        ("2024-10-01T08:02:00.000Z", 2735.15, 2735.17, 0.3, 0.7),
        ("2024-10-01T08:03:00.000Z", 2735.30, 2735.32, 0.5, 0.5),
        ("2024-10-01T08:04:00.000Z", 2735.25, 2735.27, 0.6, 0.4),
        ("2024-10-01T08:04:30.000Z", 2735.28, 2735.30, 0.2, 0.3),
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_utc", "ask", "bid", "ask_vol", "bid_vol"])
        writer.writerows(rows)
    return path


def write_provider_b() -> pathlib.Path:
    """Provider B: matching ticks for the same window, minor price deviations (within 0.5 pip)."""
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    path = SYNTHETIC_DIR / "provider_b_xauusd.csv"
    rows = [
        # Slightly different ask/bid values — same timestamps
        ("2024-10-01T08:00:00.000Z", 2735.11, 2735.13, 0.5, 0.5),
        ("2024-10-01T08:01:00.000Z", 2735.20, 2735.22, 0.4, 0.6),
        ("2024-10-01T08:02:00.000Z", 2735.14, 2735.16, 0.3, 0.7),
        ("2024-10-01T08:03:00.000Z", 2735.31, 2735.33, 0.5, 0.5),
        # Missing tick at 08:04:00 — B has a gap
        ("2024-10-01T08:04:30.000Z", 2735.29, 2735.31, 0.2, 0.3),
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_utc", "ask", "bid", "ask_vol", "bid_vol"])
        writer.writerows(rows)
    return path


if __name__ == "__main__":
    a = write_provider_a()
    b = write_provider_b()
    print(f"Provider A fixture: {a}")
    print(f"Provider B fixture: {b}")

