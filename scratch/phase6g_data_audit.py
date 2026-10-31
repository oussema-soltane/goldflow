"""
Phase 6G — Comprehensive data inventory and provenance audit.
Examines all available datasets: date ranges, bar counts, UTC coverage,
SHA-256 hashes, completeness, and prior research use classification.
"""
import hashlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROCESSED_DIR = ROOT / "data" / "processed"
RAW_DIR = ROOT / "data" / "raw"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def audit_csv(path: Path, time_col: str = "time") -> dict:
    df = pd.read_csv(path)
    if time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
        df = df.dropna(subset=[time_col])
        df = df.sort_values(time_col)
        first = df[time_col].iloc[0]
        last = df[time_col].iloc[-1]
        n = len(df)
        # Check for gaps
        diffs = df[time_col].diff().dropna()
        mode_gap = diffs.mode().iloc[0] if not diffs.empty else None
        gaps = (diffs > mode_gap * 2).sum() if mode_gap else 0
        dup_times = df[time_col].duplicated().sum()
        nulls = df.isnull().sum().sum()
    else:
        first = last = n = mode_gap = gaps = dup_times = nulls = "N/A"
    return {
        "path": str(path.relative_to(ROOT)),
        "rows": n,
        "first_utc": str(first),
        "last_utc": str(last),
        "mode_interval": str(mode_gap),
        "gap_count": int(gaps) if isinstance(gaps, (int, float)) else gaps,
        "duplicate_timestamps": int(dup_times) if isinstance(dup_times, (int, float)) else dup_times,
        "null_values": int(nulls) if isinstance(nulls, (int, float)) else nulls,
        "sha256": sha256_file(path),
    }

print("=" * 90)
print("PHASE 6G — DATA INVENTORY AND PROVENANCE AUDIT")
print("=" * 90)

files_to_audit = sorted(list(PROCESSED_DIR.glob("*.csv")) + list(RAW_DIR.glob("*.csv")))

results = {}
for f in files_to_audit:
    print(f"\nAuditing: {f.name}")
    r = audit_csv(f)
    results[f.name] = r
    print(f"  Rows     : {r['rows']}")
    print(f"  First    : {r['first_utc']}")
    print(f"  Last     : {r['last_utc']}")
    print(f"  Interval : {r['mode_interval']}")
    print(f"  Gaps     : {r['gap_count']}")
    print(f"  Dupes    : {r['duplicate_timestamps']}")
    print(f"  Nulls    : {r['null_values']}")
    print(f"  SHA-256  : {r['sha256']}")

# Now specifically examine M15 data overlap
print("\n" + "=" * 90)
print("M15 DATASET OVERLAP ANALYSIS")
print("=" * 90)
m15_proc = PROCESSED_DIR / "XAUUSD_M15_clean.csv"
m15_raw = RAW_DIR / "XAUUSD_M15_raw.csv"

for p in [m15_proc, m15_raw]:
    if p.exists():
        df = pd.read_csv(p)
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df = df.dropna(subset=["time"]).sort_values("time")
        print(f"\n{p.name}:")
        print(f"  Total bars  : {len(df)}")
        print(f"  First UTC   : {df['time'].iloc[0]}")
        print(f"  Last UTC    : {df['time'].iloc[-1]}")
        print(f"  Date range  : {(df['time'].iloc[-1] - df['time'].iloc[0]).days} days")
        # Phase 6F used all 5000 bars of processed M15
        # Check if raw has more bars beyond processed
        if p.name.endswith("raw.csv"):
            proc = pd.read_csv(m15_proc)
            proc["time"] = pd.to_datetime(proc["time"], utc=True, errors="coerce")
            proc_last = proc["time"].max()
            raw_beyond = df[df["time"] > proc_last]
            print(f"  Bars beyond processed last ({proc_last}): {len(raw_beyond)}")
            if len(raw_beyond) > 0:
                print(f"  Raw 'unseen' first : {raw_beyond['time'].iloc[0]}")
                print(f"  Raw 'unseen' last  : {raw_beyond['time'].iloc[-1]}")

