"""Audit captured MT5 instrument specifications against simulator assumptions.

Run from the project root:
    python scripts/audit_execution_specs.py
Exit code 0 means captured required fields match the default BacktestConfig. Exit
code 2 means required specifications are missing, a mismatch exists, or the audit
could not be completed. This audit does not authenticate the historical feed.
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

from src.research.execution_spec_audit import audit_processed_execution_specs


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit MT5 symbol specifications for GoldFlow")
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--reports-dir", default="reports")
    args = parser.parse_args()

    report = audit_processed_execution_specs(args.data_dir)
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "execution_spec_audit.json"
    md_path = reports_dir / "execution_spec_audit.md"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    lines = [
        "# GoldFlow — Broker Execution Specification Audit",
        "",
        f"**Generated (UTC):** {report['generated_at_utc']}",
        f"**Overall status:** {report['overall_status']}",
        "",
        "This preflight compares current BacktestConfig defaults with instrument metadata captured from `MT5.symbol_info`. It does not verify that the historical price data is authentic, and it does not certify execution quality.",
        "",
        "## Assumptions Under Audit",
        "",
        "| Engine setting | Current default | MT5 metadata field |",
        "|---|---:|---|",
    ]
    mapping = {
        "point_size": "point",
        "contract_size_oz": "trade_contract_size",
        "min_lot": "volume_min",
        "lot_step": "volume_step",
        "max_lots": "volume_max",
    }
    for name, mt5_field in mapping.items():
        lines.append(f"| `{name}` | {report['default_config_assumptions'][name]} | `{mt5_field}` |")
    lines.append("| `trade_calc_mode` | documented linear contract-size profit formula required | `trade_calc_mode` |")
    lines += [
        "", "## Dataset Results", "",
        "| Symbol | Timeframe | Spec capture status | Calculation mode | Formula compatibility | Audit result | Missing required fields | Wrong-type fields | Mismatches |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for item in report["datasets"]:
        mismatches = [m["config_field"] for m in item.get("mismatches", [])]
        mismatches.extend(f"missing {name}" for name in item.get("missing_currency_fields", []))
        mismatches.extend(f"unsupported {name}={value}" for name, value in item.get("unsupported_currencies", {}).items())
        if item.get("status") == "SYMBOL_MISMATCH":
            mismatches.append(f"symbol: {item.get('symbol')} vs {item.get('captured_symbol')}")
        if item.get("status") == "SYMBOL_UNVERIFIED":
            mismatches.append("symbol identity not verifiable")
        if item.get("status") == "BROKER_MISMATCH":
            mismatches.append(f"broker: {item.get('metadata_broker_server')} vs {item.get('captured_broker_server')}")
        if item.get("status") == "BROKER_UNVERIFIED":
            mismatches.append("broker server match not verifiable")
        if item.get("status") == "TICK_VALUE_MISMATCH":
            check = item.get("tick_value_check", {})
            mismatches.append(
                f"tick value {check.get('captured_tick_value')} vs expected {check.get('expected_contract_times_tick_size')}"
            )
        if item.get("status") == "CALC_MODE_UNSUPPORTED":
            mismatches.append(
                f"unsupported trade_calc_mode={item.get('trade_calc_mode')} ({item.get('trade_calc_mode_name')})"
            )
        if item.get("status") == "CALC_MODE_MISMATCH":
            mismatches.append(
                f"trade_calc_mode code/name disagreement: code={item.get('trade_calc_mode')}, "
                f"name={item.get('trade_calc_mode_name')}, "
                f"captured map value={item.get('trade_calc_mode_constant_values', {}).get(item.get('trade_calc_mode_name')) if isinstance(item.get('trade_calc_mode_constant_values'), dict) else None}"
            )
        if item.get("status") == "CALC_MODE_UNVERIFIED":
            mismatches.append("trade_calc_mode or its MT5 symbolic-constant mapping is missing, malformed, or fractional")
        if item.get("tick_value_status") == "reconciled_via_order_calc_profit":
            mismatches.append("tick value 0.1 reconciled to 1.0 via order_calc_profit")
        lines.append(
            f"| {item.get('symbol') or 'N/A'} | {item.get('timeframe') or 'N/A'} | "
            f"{item.get('execution_specification_status')} | "
            f"{item.get('trade_calc_mode_name') or 'Unknown'} ({item.get('trade_calc_mode')}) | "
            f"{item.get('trade_calc_mode_status')} | {item.get('status')} | "
            f"{', '.join(item.get('missing_required_fields', [])) or 'None'} | "
            f"{', '.join(item.get('wrong_type_fields', [])) or 'None'} | "
            f"{', '.join(mismatches) or 'None'} |"
        )
    cross_check = report.get("cross_dataset_matching", {})
    lines += [
        "", "## Cross-Dataset Specification Matching", "",
        f"- **Status:** {cross_check.get('status', 'unknown')}",
        f"- **Datasets checked:** {cross_check.get('dataset_count', 0)}",
        f"- **Essential fields verified identical:** {', '.join(f'`{f}`' for f in cross_check.get('essential_fields_checked', []))}",
        f"- **Permitted varying observational fields:** {', '.join(f'`{f}`' for f in cross_check.get('permitted_varying_observational_fields', []))}",
    ]
    if cross_check.get("mismatches"):
        lines.append("- **Mismatches detected:**")
        lines.extend([f"  - {m}" for m in cross_check["mismatches"]])
    else:
        lines.append("- **Result:** All active datasets share identical essential calculation specifications.")

    reconciled = report.get("reconciled_discrepancies", [])
    warnings = report.get("warnings", [])
    if reconciled or warnings:
        lines += ["", "## Reconciled Discrepancies and Empirical Inquiries", ""]
        for r in reconciled:
            lines.append(f"- **Reconciled field:** {r}")
        for w in warnings:
            lines.append(f"- **Warning note:** {w}")

    lines += [
        "", "## Interpretation", "",
        "- `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE` means the captured required fields equal current defaults; it is not broker or data-source authentication.",
        "- `ASSUMPTIONS_ONLY` means at least one dataset has no complete instrument-specification record. Do not infer point size or contract size from OHLC decimals; refresh data from the intended MT5 terminal to capture the actual fields.",
        "- `CONFIG_MISMATCH` means at least one configured default differs from the captured broker field. Update the research config deliberately and rerun the audit; do not silently overwrite either value.",
        "- `SYMBOL_MISMATCH`, `SYMBOL_UNVERIFIED`, `BROKER_MISMATCH`, and `BROKER_UNVERIFIED` fail strict execution-spec validation. Re-ingest from the intended terminal rather than attach an unrelated symbol/server specification.",
        "- `CURRENCY_UNSUPPORTED` / `CURRENCY_UNVERIFIED` means the USD-valued position and P&L assumptions cannot be reconciled to the captured base/profit/account currencies.",
        "- `TICK_VALUE_MISMATCH` means MT5's captured tick value differs by more than 5% from `trade_contract_size × trade_tick_size` under XAU/USD assumptions without verified empirical order_calc_profit reconciliation.",
        "- `CROSS_DATASET_SPEC_MISMATCH` means different timeframe datasets have conflicting essential calculation specifications (e.g. different contract sizes or calculation modes).",
        "- `CALC_MODE_UNSUPPORTED` means the captured mode is not allowlisted for this simulator's contract-size P&L formula. `CALC_MODE_UNVERIFIED` means the mode or the active MT5 symbolic-constant map is missing/malformed. `CALC_MODE_MISMATCH` means the captured numeric enum code disagrees with the name/code mapping captured from the active MT5 package. All three block strict runs.",
        "- The allowlist includes the documented linear profit formula modes FOREX, FOREX_NO_LEVERAGE, CFD, CFDINDEX, CFDLEVERAGE, EXCH_STOCKS, and EXCH_STOCKS_MOEX. Futures/tick-price, bonds, collateral, and unknown modes are not accepted by this engine formula. Official formula reference: https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants.",
        "- `wrong_type_fields` identifies required numeric values that are present but unusable (for example boolean, NaN, infinity, or malformed values). These also remain in `missing_required_fields` for strict-gate compatibility.",
        "", "## Required fields", "", ", ".join(f"`{name}`" for name in report["required_spec_fields"]), "",
        "## Required currency fields", "", "`currency_base=XAU`, `currency_profit=USD`, `account_currency=USD`", "",
        "## Errors", "",
    ]
    lines.extend([f"- {error}" for error in report["errors"]] or ["- None"])
    lines += ["", f"**Caveat:** {report['provenance_caveat']}", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Overall status: {report['overall_status']}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    return 0 if report["overall_status"] == "MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
