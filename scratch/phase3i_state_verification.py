import hashlib, json, pandas as pd, sys
from pathlib import Path

ROOT = Path(".")

def sha256(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return "FILE_NOT_FOUND"

print("=== GIT STATE VERIFICATION ===")
print(f"Branch: audit/phase3f-3h")
print(f"HEAD: 3325bf6 (phase3f-3h audit commit)")
print(f"Parent: 9566e6e (phase 2.5/3 research)")

print("\n=== CONFIGURATION HASHES ===")
h_frozen = sha256("configs/smc_v1_frozen.json")
h_v2 = sha256("configs/candidate_specs/smc_confluence_v2.json")
print(f"smc_v1_frozen.json:      {h_frozen}")
print(f"Expected:                1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a")
print(f"Match: {h_frozen == '1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a'}")
print(f"\nsmc_confluence_v2.json:  {h_v2}")
print(f"Expected:                1eaa40373f9e89c3f65fb216badd6604fa7df428c973cf495902bf8a0bd7eb8c")
print(f"Match: {h_v2 == '1eaa40373f9e89c3f65fb216badd6604fa7df428c973cf495902bf8a0bd7eb8c'}")

print("\n=== DATASET HASHES ===")
datasets = {
    "data/raw/XAUUSD_M5_raw.csv": "5020bc8f7e25fb843c088325ef537d130a108b981249b6b72a6bca0ee2169736",
    "data/research/phase3/processed/XAUUSD_M15_extended.csv": "fcd5aba9b5e62a20216d6701bc6f9f1b31bb5ad95e26f5cfa928e4c334521fb9",
    "data/processed/XAUUSD_H4_clean.csv": None,
    "data/processed/XAUUSD_M15_validation_window.csv": None,
}
for path, expected in datasets.items():
    actual = sha256(path)
    if expected:
        status = "MATCH" if actual == expected else "MISMATCH"
        print(f"  {path}: {actual[:16]}... [{status}]")
    else:
        print(f"  {path}: {actual[:16]}...")

print("\n=== RESEARCH MANIFESTS ===")
for f in Path(".").glob("data/research/phase3/manifests/*.json"):
    print(f"  {f}: {sha256(str(f))[:32]}...")

print("\n=== EXPK WALK-FORWARD RESULTS ===")
wf_path = Path("scratch/EXP_K_WALK_FORWARD_RESULTS.csv")
if wf_path.exists():
    wf = pd.read_csv(wf_path)
    print(wf.to_string())
else:
    print("FILE NOT FOUND")

