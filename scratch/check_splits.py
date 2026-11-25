import pandas as pd
from pathlib import Path

data_dir = Path("data/processed")
for tf in ["H4", "H1", "M15", "M5"]:
    path = data_dir / f"XAUUSD_{tf}_clean.csv"
    if path.exists():
        df = pd.read_csv(path)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        n = len(df)
        n_dev = int(n * 0.6)
        print(f"{tf}: total={n}, dev={n_dev}, dev_start={df['time'].iloc[0]}, dev_end={df['time'].iloc[n_dev-1]}, val_start={df['time'].iloc[n_dev]}, val_end={df['time'].iloc[-1]}")

