"""Audit processed datasets and write a Phase 3B readiness report.

Run from project root:
    py -3.13 scripts/research_readiness.py

Exit code 0 means the configured readiness gates passed; exit code 2 means
research remains blocked. No trades are simulated and no strategy is evaluated.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.research.data_readiness import audit_all_datasets, evaluate_research_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="GoldFlow Phase 3B data readiness audit")
    parser.add_argument("--data-dir", default="data/processed", help="Processed CSV directory")
    parser.add_argument("--reports-dir", default="reports", help="Output report directory")
    parser.add_argument("--min-h4", type=int, default=2000)
    parser.add_argument("--min-h1", type=int, default=5000)
    parser.add_argument("--min-m15", type=int, default=5000)
    parser.add_argument("--min-m5", type=int, default=5000)
    args = parser.parse_args()

    minimums = {"H4": args.min_h4, "H1": args.min_h1, "M15": args.min_m15, "M5": args.min_m5}
    audits = audit_all_datasets(args.data_dir)
    readiness = evaluate_research_readiness(audits, minimum_bars=minimums)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_status": readiness["overall_status"],
        "readiness": readiness,
        "dataset_audits": audits,
    }

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "research_readiness.json"
    md_path = reports_dir / "research_readiness.md"
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    lines = [
        "# GoldFlow — Phase 3B Research Data Readiness",
        "",
        f"**Generated (UTC):** {payload['generated_at_utc']}",
        f"**Overall status:** {readiness['overall_status']}",
        "",
        "This is a data eligibility audit for descriptive research only. It is not a strategy backtest or evidence of profitability.",
        "",
        "## Timeframe Summary",
        "",
        "| Timeframe | Status | Rows | Recommended minimum | Provenance | Date range |",
        "|---|---:|---:|---:|---|---|",
    ]
    for tf, item in readiness["timeframes"].items():
        dr = item.get("date_range") or {}
        date_range = f"{dr.get('start', 'N/A')} → {dr.get('end', 'N/A')}"
        lines.append(f"| {tf} | {item['status']} | {item['row_count']} | {item['minimum_bars']} | {item['provenance_status']} | {date_range} |")
    lines += ["", "## Blockers", ""]
    if readiness["blockers"]:
        lines += [f"- {blocker}" for blocker in readiness["blockers"]]
    else:
        lines.append("- None")
    lines += ["", "## Dataset Warnings", ""]
    for tf, item in readiness["timeframes"].items():
        lines.append(f"### {tf}")
        if item["warnings"]:
            lines += [f"- {warning}" for warning in item["warnings"]]
        else:
            lines.append("- None")
        if item["blockers"]:
            lines.append("**Blocking issues:**")
            lines += [f"- {blocker}" for blocker in item["blockers"]]
        lines.append("")
    lines += [
        "## Next Step",
        "",
        "If blocked, open MT5, log in to the demo account, verify the broker's exact Gold symbol, run `scripts/download_data.py` with real MT5 data, then rerun this audit. Do not present synthetic or unknown-provenance data as real-market findings.",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Overall status: {readiness['overall_status']}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    for blocker in readiness["blockers"]:
        print(f"BLOCKER: {blocker}")
    return 2 if readiness["overall_status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
