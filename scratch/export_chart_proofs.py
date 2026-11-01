"""
Export GoldFlow chart HTML proofs for H1, H4, M15 across clean and smc_analysis presets.
Demonstrates the visualization redesign works correctly.
"""
import sys
sys.path.insert(0, '.')
import pandas as pd
from pathlib import Path
from src.data.loader import load_local_data
from src.smc.engine import SMCConfig, analyze_smc
from src.visualization.charts import create_candlestick_chart

output_dir = Path("reports/charts")
output_dir.mkdir(parents=True, exist_ok=True)

datasets = [
    ("data/processed/XAUUSD_H1_clean.csv", "H1"),
    ("data/processed/XAUUSD_H4_clean.csv", "H4"),
    ("data/processed/XAUUSD_M15_clean.csv", "M15"),
]

presets = ["clean", "smc_analysis", "full_research"]

for csv_path, tf in datasets:
    p = Path(csv_path)
    if not p.exists():
        print(f"SKIP {tf}: {csv_path} not found")
        continue
    print(f"\nLoading {tf}...")
    df = load_local_data(csv_path)
    df['time'] = pd.to_datetime(df['time'], utc=True)
    print(f"  {len(df)} bars, range: {df.low.min():.0f} to {df.high.max():.0f}")

    print(f"  Running SMC engine...")
    smc_res = analyze_smc(df=df, symbol='XAUUSD', timeframe=tf, config=SMCConfig())
    print(f"  OBs: {len(smc_res.order_blocks)}, Breaks: {len(smc_res.structure_breaks)}, FVGs: {len(smc_res.fair_value_gaps)}")

    for preset in presets:
        outfile = output_dir / f"XAUUSD_{tf}_{preset}.html"
        fig = create_candlestick_chart(
            df=df,
            symbol='XAUUSD',
            timeframe=tf,
            preset=preset,
            visible_bars=500,
            hide_weekends=True,
            autoscale_y_to_visible=True,
            smc_result=smc_res,
            height=720,
        )
        shapes_n = len(fig.layout.shapes)
        traces_n = len(fig.data)
        y_range = fig.layout.yaxis.range
        fig.write_html(str(outfile), include_plotlyjs='cdn')
        print(f"  [{preset}] shapes={shapes_n} traces={traces_n} y={y_range[0]:.0f}-{y_range[1]:.0f} -> {outfile.name}")

print("\nDone. HTML proof charts saved to reports/charts/")

