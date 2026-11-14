import json
from pathlib import Path

path = Path("reports/smc_backtest_metrics_full_history.json")
if path.exists():
    data = json.loads(path.read_text(encoding="utf-8"))
    print("Baseline Metrics Summary:")
    for tf, v in data.get("metrics_by_timeframe", {}).items():
        print(f"  {tf}: Net=${v.get('net_profit', 0):,.2f} | PF={v.get('profit_factor')} | WR={v.get('win_rate_pct')}% | Trades={v.get('closed_trades')}")
else:
    print("File not found.")

