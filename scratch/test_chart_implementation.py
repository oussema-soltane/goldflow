import sys
import pandas as pd
import plotly.graph_objects as go
from src.smc.engine import SMCConfig, analyze_smc

# Read H1 clean data
df = pd.read_csv('data/processed/XAUUSD_H1_clean.csv')
df['time'] = pd.to_datetime(df['time'], utc=True)
smc_res = analyze_smc(df=df, symbol='XAUUSD', timeframe='H1', config=SMCConfig())

print(f"Data loaded: {len(df)} bars. SMC analysis complete.")

