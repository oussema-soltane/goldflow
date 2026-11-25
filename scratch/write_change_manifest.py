"""
Generate CHANGE_MANIFEST for the visualization redesign session (2026-11-01).
"""
import json, hashlib, datetime
from pathlib import Path

root = Path(".")

manifest = {
    "session": "Chart Redesign & Visualization Engineering",
    "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "git_base_commit": "d91056f",
    "files_modified": [
        {
            "path": "src/visualization/charts.py",
            "changes": [
                "ICT Swing Highs hovertext: added 'Formed:' and 'Confirmed:' fields with UTC timestamps",
                "ICT Swing Lows hovertext: added 'Formed:' and 'Confirmed:' fields with UTC timestamps",
                "ICT Structure Breaks: added BOS/CHoCH annotations with break_time UTC timestamp",
                "ICT Structure Breaks: extracted brk_label to handle break_type attribute safely",
            ]
        },
        {
            "path": "pages/1_Market_Analysis.py",
            "changes": [
                "Added chart preset toolbar (SMC Analysis, Clean, Full Research, Custom)",
                "Added hide_weekends toggle (default True)",
                "Added autoscale_y toggle (default True)",
                "Added visible_bars zoom selector",
                "Added institutional KPI strip (Latest Price, Trend, Dealing Zone, Demand/Supply OB, Last Break)",
                "Passed preset, hide_weekends, autoscale_y_to_visible into create_candlestick_chart",
            ]
        }
    ],
    "files_added": [
        "scratch/patch_ict_hovertext.py",
        "scratch/patch_ict_structure_annotations.py",
        "scratch/export_chart_proofs.py",
        "reports/charts/XAUUSD_H1_clean.html",
        "reports/charts/XAUUSD_H1_smc_analysis.html",
        "reports/charts/XAUUSD_H1_full_research.html",
        "reports/charts/XAUUSD_H4_clean.html",
        "reports/charts/XAUUSD_H4_smc_analysis.html",
        "reports/charts/XAUUSD_H4_full_research.html",
        "reports/charts/XAUUSD_M15_clean.html",
        "reports/charts/XAUUSD_M15_smc_analysis.html",
        "reports/charts/XAUUSD_M15_full_research.html",
    ],
    "tests_fixed": [
        {
            "test": "tests/test_ict_adversarial.py::TestAdversarialTemporalCorrectness::test_property_14_chart_integrity",
            "root_cause": "ICT Swing High hovertext lacked 'Confirmed:' field; ICT Structure Breaks lacked BOS/CHoCH annotations with UTC timestamp",
            "fix": "Added confirmed_time and formation timestamps to ICT swing hovertexts; added annotation dict with break type + UTC time for each ICT structure break event",
        }
    ],
    "data_restored": [
        {
            "path": "data/raw/XAUUSD_M15_raw.csv",
            "action": "git checkout HEAD -- data/raw/XAUUSD_M15_raw.csv",
            "reason": "File was overwritten by a previous Streamlit session run with 1500-row synthetic-like data; restored to canonical 5000-row MT5 extract matching SHA-256 b893bc507daec515d36ff51cb988e4f6e33df23f3ccddd6924794b64fbe7b075",
        }
    ],
    "smc_engine_modified": False,
    "backtest_modified": False,
    "trading_signals_modified": False,
    "research_vault_modified": False,
}

out = Path("reports/CHANGE_MANIFEST_20261101_visualization.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"Manifest written: {out}")
print(json.dumps(manifest, indent=2))

