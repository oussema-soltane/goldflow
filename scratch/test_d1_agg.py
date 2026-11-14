import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

import pandas as pd
from src.smc.engine import analyze_smc, SMCConfig

h4_path = root / "data" / "processed" / "XAUUSD_H4_clean.csv"
df = pd.read_csv(h4_path)
df["time"] = pd.to_datetime(df["time"], utc=True)
print("H4 shape:", df.shape)
print("H4 start:", df["time"].min(), "end:", df["time"].max())

df["date"] = df["time"].dt.floor("1D")
daily = df.groupby("date").agg({
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "tick_volume": "sum",
    "spread": "mean",
    "real_volume": "sum",
}).reset_index().rename(columns={"date": "time"})
print("Daily bars:", len(daily))
print("Daily start:", daily["time"].min(), "end:", daily["time"].max())

res = analyze_smc(daily, symbol="XAUUSD", timeframe="D1", config=SMCConfig(swing_window=3))
print("D1 swings:", len(res.swings), "breaks:", len(res.structure_breaks))
for sb in res.structure_breaks[:5]:
    print(" ", sb.break_time, sb.break_type, sb.resulting_trend)
