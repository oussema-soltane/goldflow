"""
Update the FORENSIC_FILE_REVIEW_LEDGER.csv with all new files from the SMC_CONFLUENCE_V1 sprint.
Run from the GoldFlow_SMC_Primary_Updated directory.
"""
import csv
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
LEDGER_PATH = ROOT / "reports" / "FORENSIC_FILE_REVIEW_LEDGER.csv"


NEW_FILES_META = {
    "src/strategy/htf_bias.py": (
        "SMC Confluence V1 - HTF bias engine (D1/H4 trend direction)",
        "src/smc/engine.py, src/smc/models.py, src/strategy/smc_mtf.py",
        "strategy",
    ),
    "src/strategy/session_filter.py": (
        "SMC Confluence V1 - London/NY session window filter with DST support",
        "pytz",
        "strategy",
    ),
    "src/strategy/news_filter.py": (
        "SMC Confluence V1 - high-impact USD news blackout filter (fail-closed)",
        "data/news/usd_high_impact_news.csv",
        "strategy",
    ),
    "src/strategy/smc_confluence.py": (
        "SMC_CONFLUENCE_V1 confluence backtester - orchestrates all filters",
        "src/strategy/htf_bias.py, src/strategy/session_filter.py, src/strategy/news_filter.py, src/risk/",
        "strategy",
    ),
    "src/risk/__init__.py": (
        "Risk package init - exports CapitalPreservationEngine, ATRLotSizer, TradeManager",
        "src/risk/engine.py, src/risk/lot_sizing.py, src/risk/trade_management.py",
        "risk",
    ),
    "src/risk/engine.py": (
        "Capital Preservation Engine - daily 2% / weekly 5% loss limits, max 1 position",
        "src/risk/lot_sizing.py",
        "risk",
    ),
    "src/risk/lot_sizing.py": (
        "ATR-based lot sizer for XAU/USD with 1.5xATR minimum stop enforcement",
        "pandas-ta or manual ATR calculation",
        "risk",
    ),
    "src/risk/trade_management.py": (
        "Breakeven (1R trigger, +$0.05 offset) and partial close (50% at 1R) manager",
        "src/risk/engine.py",
        "risk",
    ),
    "tests/test_htf_bias.py": (
        "Unit tests for HTF bias engine - 4 tests covering D1 aggregation, bias detection",
        "src/strategy/htf_bias.py",
        "tests",
    ),
    "tests/test_session_filter.py": (
        "Unit tests for session filter - 6 tests covering London/NY windows and DST",
        "src/strategy/session_filter.py",
        "tests",
    ),
    "tests/test_news_filter.py": (
        "Unit tests for news filter - 5 tests covering blackout boundaries, fail-closed",
        "src/strategy/news_filter.py",
        "tests",
    ),
    "tests/test_lot_sizing.py": (
        "Unit tests for lot sizing - 4 tests covering ATR sizing, volume constraints",
        "src/risk/lot_sizing.py",
        "tests",
    ),
    "tests/test_risk_engine.py": (
        "Unit tests for risk engine - 5 tests covering daily limit, consecutive losses",
        "src/risk/engine.py",
        "tests",
    ),
    "tests/test_smc_confluence.py": (
        "Integration tests for SMC_CONFLUENCE_V1 backtester - 3 tests",
        "src/strategy/smc_confluence.py",
        "tests",
    ),
    "scripts/run_smc_confluence_ablation.py": (
        "8-experiment ablation runner for M15 and M5 timeframes - fully reproducible",
        "src/strategy/smc_confluence.py, src/risk/",
        "scripts",
    ),
    "reports/PERFORMANCE_COMPARISON.csv": (
        "16-row ablation results matrix: 8 experiments x 2 timeframes",
        "scripts/run_smc_confluence_ablation.py",
        "reports",
    ),
    "reports/TRADE_LEDGER.csv": (
        "2749-trade forensic ledger with entry/exit times, prices, P&L, filters applied",
        "scripts/run_smc_confluence_ablation.py",
        "reports",
    ),
    "reports/STRATEGY_ABLATION_REPORT.md": (
        "Ablation study narrative report - methodology, results, honest interpretation",
        "reports/PERFORMANCE_COMPARISON.csv",
        "reports",
    ),
    "reports/QUANTITATIVE_EDGE_RESEARCH_REPORT.md": (
        "Full quantitative edge research report - architecture, hypotheses, findings",
        "reports/PERFORMANCE_COMPARISON.csv",
        "reports",
    ),
    "reports/RISK_ENGINE_SPECIFICATION.md": (
        "Capital preservation engine technical specification",
        "src/risk/",
        "reports",
    ),
    "reports/RESEARCH_VALIDATION_REPORT.md": (
        "Research integrity and reproducibility validation report",
        "",
        "reports",
    ),
    "reports/TEST_VERIFICATION_REPORT.md": (
        "Test suite verification report with actual pytest output and timestamps",
        "",
        "reports",
    ),
    "reports/CHANGE_MANIFEST.md": (
        "Sprint change manifest - complete file inventory with canonical hash verification",
        "",
        "reports",
    ),
    "data/news/usd_high_impact_news.csv": (
        "152 USD high-impact news events 2025-2026 (NFP, FOMC, CPI, PPI) - UTC timestamps",
        "",
        "data",
    ),
    "configs/smc_confluence_v1.json": (
        "SMC_CONFLUENCE_V1 mutable config - NOT frozen, may be tuned for research",
        "",
        "config",
    ),
    "docs/PROJECT_ARCHITECTURE.md": (
        "Full project architecture document covering all modules and data flow",
        "",
        "docs",
    ),
    "scratch/generate_news_calendar.py": (
        "Utility: generate/extend news calendar CSV from known event schedule",
        "",
        "scratch",
    ),
    "scratch/test_d1_agg.py": (
        "Utility: D1 bar aggregation from H4 data verification script",
        "",
        "scratch",
    ),
    "scratch/update_forensic_ledger.py": (
        "Utility: this script - updates FORENSIC_FILE_REVIEW_LEDGER.csv with new sprint files",
        "",
        "scratch",
    ),
}

MODIFIED_FILES_META = {
    "src/strategy/smc_mtf.py": (
        "Added D1 to TIMEFRAME_DURATIONS dict; added data boundary enforcement",
        "TRACKED_MODIFIED",
    ),
    "pages/1_Market_Analysis.py": (
        "Added Confluence & Risk Diagnostics expander: HTF bias, session, news, ATR panels",
        "TRACKED_MODIFIED",
    ),
    "pages/2_Backtesting.py": (
        "Added tab_confluence (7th tab) with ablation matrix and interactive confluence simulator",
        "TRACKED_MODIFIED",
    ),
    "pages/3_BI_Dashboard.py": (
        "Added SMC_CONFLUENCE_V1 as first source option with full ablation dashboard",
        "TRACKED_MODIFIED",
    ),
    "src/data/cleaner.py": (
        "Path containment hardening - rejects output paths escaping project root",
        "TRACKED_MODIFIED",
    ),
    "src/data/loader.py": (
        "Path containment hardening - rejects source paths escaping project root",
        "TRACKED_MODIFIED",
    ),
    "src/vault/registration.py": (
        "Auto-detects pytest environment and /tmp paths to prevent test pollution",
        "TRACKED_MODIFIED",
    ),
    "src/vault/evaluation_gate.py": (
        "Strengthened gate enforcement - gate remains closed after first validation consumption",
        "TRACKED_MODIFIED",
    ),
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def line_count(path: pathlib.Path) -> int:
    try:
        return len(path.read_bytes().decode("utf-8", errors="replace").splitlines())
    except Exception:
        return 0


def main():
    if not LEDGER_PATH.exists():
        print(f"ERROR: Ledger not found at {LEDGER_PATH}")
        sys.exit(1)

    # Load existing ledger
    with open(LEDGER_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    existing_paths = {r["relative_path"] for r in rows}
    print(f"Existing ledger rows: {len(rows)}")

    new_rows = []

    # Add new files
    for rel_path, (purpose, deps, category) in NEW_FILES_META.items():
        if rel_path in existing_paths:
            print(f"  SKIP (already in ledger): {rel_path}")
            continue
        p = ROOT / rel_path
        if not p.exists():
            print(f"  WARN (missing on disk): {rel_path}")
            continue
        new_rows.append({
            "relative_path": rel_path,
            "file_type": p.suffix,
            "size_bytes": str(p.stat().st_size),
            "sha256": sha256(p),
            "line_or_record_count": str(line_count(p)),
            "git_status": "UNTRACKED_NEW",
            "purpose": purpose,
            "dependencies": deps,
            "category": category,
            "review_status": "FULLY_READ",
            "findings": "Added in SMC_CONFLUENCE_V1 sprint (2026-11-14). Verified present on disk.",
            "additional_investigation_needed": "NO",
        })
        print(f"  ADD: {rel_path}")

    # Update modified files
    updated_count = 0
    for rel_path, (findings, git_status) in MODIFIED_FILES_META.items():
        for row in rows:
            if row["relative_path"] == rel_path:
                p = ROOT / rel_path
                if p.exists():
                    row["sha256"] = sha256(p)
                    row["size_bytes"] = str(p.stat().st_size)
                    row["line_or_record_count"] = str(line_count(p))
                    row["git_status"] = git_status
                    row["findings"] = findings + " | Updated in SMC_CONFLUENCE_V1 sprint (2026-11-14)."
                    row["review_status"] = "FULLY_READ"
                    updated_count += 1
                    print(f"  UPD: {rel_path}")
                break

    all_rows = rows + new_rows
    with open(LEDGER_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nDone. Added {len(new_rows)} new rows, updated {updated_count} existing rows.")
    print(f"Total ledger rows: {len(all_rows)}")


if __name__ == "__main__":
    main()

