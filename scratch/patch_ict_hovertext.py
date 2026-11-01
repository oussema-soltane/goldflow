"""
Patch ICT Swing Highs/Lows hovertext to include Confirmed: timestamp.
This fixes test_property_14_chart_integrity.
"""
import sys

with open('src/visualization/charts.py', 'r', encoding='utf-8') as f:
    content = f.read()

# --- Patch Swing Highs ---
old_sh = (
    "                    hovertext=[f\"<b>ICT Swing High</b><br>Price: ${s.price:,.2f}<br>"
    "Time: {s.time.strftime('%Y-%m-%d %H:%M UTC')}\" for s in shs],"
)
new_sh = (
    "                    hovertext=[\n"
    "                        f\"<b>ICT Swing High</b><br>\"\n"
    "                        f\"Price: ${s.price:,.2f}<br>\"\n"
    "                        f\"Formed: {s.time.strftime('%Y-%m-%d %H:%M UTC')}<br>\"\n"
    "                        f\"Confirmed: {s.confirmed_time.strftime('%Y-%m-%d %H:%M UTC')}<br>\"\n"
    "                        f\"Classification: {s.classification}\"\n"
    "                        for s in shs\n"
    "                    ],"
)

if old_sh in content:
    content = content.replace(old_sh, new_sh, 1)
    print("Patched: ICT Swing Highs hovertext")
else:
    print("ERROR: Swing Highs pattern NOT found", file=sys.stderr)
    idx = content.find("ICT Swing High")
    if idx >= 0:
        print("Context around 'ICT Swing High':", repr(content[idx-20:idx+200]))
    sys.exit(1)

# --- Patch Swing Lows ---
old_sl = (
    "                    hovertext=[f\"<b>ICT Swing Low</b><br>Price: ${s.price:,.2f}<br>"
    "Time: {s.time.strftime('%Y-%m-%d %H:%M UTC')}\" for s in sls],"
)
new_sl = (
    "                    hovertext=[\n"
    "                        f\"<b>ICT Swing Low</b><br>\"\n"
    "                        f\"Price: ${s.price:,.2f}<br>\"\n"
    "                        f\"Formed: {s.time.strftime('%Y-%m-%d %H:%M UTC')}<br>\"\n"
    "                        f\"Confirmed: {s.confirmed_time.strftime('%Y-%m-%d %H:%M UTC')}<br>\"\n"
    "                        f\"Classification: {s.classification}\"\n"
    "                        for s in sls\n"
    "                    ],"
)

if old_sl in content:
    content = content.replace(old_sl, new_sl, 1)
    print("Patched: ICT Swing Lows hovertext")
else:
    print("ERROR: Swing Lows pattern NOT found", file=sys.stderr)
    sys.exit(1)

with open('src/visualization/charts.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("charts.py saved successfully.")

