"""Complete dataset provenance audit — Task 4."""
import hashlib, pandas as pd, json
from pathlib import Path
import sys
sys.path.insert(0, '.')

print("=== TASK 4: COMPLETE PROVENANCE AUDIT ===\n")

EXPECTED = {
    "M15_raw": "b893bc507daec515d36ff51cb988e4f6e33df23f3ccddd6924794b64fbe7b075",
}

datasets = [
    ("data/raw/XAUUSD_H4_raw.csv", "H4_raw", None),
    ("data/raw/XAUUSD_H1_raw.csv", "H1_raw", None),
    ("data/raw/XAUUSD_M15_raw.csv", "M15_raw", EXPECTED["M15_raw"]),
    ("data/raw/XAUUSD_M5_raw.csv", "M5_raw", None),
    ("data/processed/XAUUSD_H4_clean.csv", "H4_clean", None),
    ("data/processed/XAUUSD_H1_clean.csv", "H1_clean", None),
    ("data/processed/XAUUSD_M15_clean.csv", "M15_clean", None),
    ("data/processed/XAUUSD_M5_clean.csv", "M5_clean", None),
]

for path, label, expected_hash in datasets:
    p = Path(path)
    if not p.exists():
        print(f"  {label}: MISSING")
        continue
    data = p.read_bytes()
    h = hashlib.sha256(data).hexdigest()
    df = pd.read_csv(p)
    t_min = pd.to_datetime(df["time"]).min()
    t_max = pd.to_datetime(df["time"]).max()
    if expected_hash:
        match_str = " HASH_MATCH" if h == expected_hash else f" HASH_MISMATCH (expected {expected_hash[:20]}...)"
    else:
        match_str = ""
    print(f"  {label}: {len(df)} rows | {t_min.date()} to {t_max.date()} | sha256={h[:20]}...{match_str}")

print()
print("Meta sidecar files:")
for mpath in ["data/processed/XAUUSD_M15_clean.meta.json", "data/processed/XAUUSD_H1_clean.meta.json", "data/processed/XAUUSD_H4_clean.meta.json"]:
    p = Path(mpath)
    if p.exists():
        m = json.loads(p.read_text())
        src = str(m.get("source", "N/A"))
        rows = str(m.get("rows_raw", "N/A"))
        sha = str(m.get("sha256_raw", "N/A"))[:20]
        print(f"  {p.name}: source={src} rows_raw={rows} sha256_raw={sha}...")
    else:
        print(f"  {mpath}: MISSING")

print()
# Reproduce research readiness check
from src.research.data_readiness import audit_all_datasets, evaluate_research_readiness
audit = audit_all_datasets("data/processed")
readiness = evaluate_research_readiness(audit)
print("Research readiness:", readiness["overall_status"])
if readiness.get("blockers"):
    print("  Blockers:", readiness["blockers"])
if readiness.get("warnings"):
    print("  Warnings:", readiness["warnings"][:3])

