import hashlib
from pathlib import Path

files = {
    "configs/smc_v1_frozen.json": "1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a",
    "configs/candidate_specs/smc_confluence_v2.json": None,
    "data/research/phase3/processed/XAUUSD_M15_extended.csv": "fcd5aba9b5e62a20216d6701bc6f9f1b31bb5ad95e26f5cfa928e4c334521fb9",
    "data/raw/XAUUSD_M5_raw.csv": None,
}

for f, expected in files.items():
    p = Path(f)
    if not p.exists():
        print(f"MISSING: {f}")
        continue
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    if expected:
        status = "MATCH" if actual == expected else "MISMATCH"
        print(f"{f}\n  SHA256: {actual}\n  Expected: {expected}\n  Status: {status}\n")
    else:
        print(f"{f}\n  SHA256: {actual}\n")

# Also check MT5 guard
print("=== MetaTrader5 Guard Check ===")
import subprocess
import sys
result = subprocess.run([sys.executable, "-c", 
    "import src.execution.mt5_gateway as gw; print(dir(gw))"],
    capture_output=True, text=True, cwd=".")
print("stdout:", result.stdout[:300] if result.stdout else "(none)")
print("stderr:", result.stderr[:300] if result.stderr else "(none)")

