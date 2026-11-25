"""
Patch ICT structure breaks to add BOS/CHoCH annotations with UTC timestamp.
This fixes the second assertion of test_property_14_chart_integrity.
"""
import sys

with open('src/visualization/charts.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''        # 7.3 ICT Structure Breaks
        if show_structure_breaks and hasattr(ict_result, "structure_breaks") and ict_result.structure_breaks:
            for brk in ict_result.structure_breaks:
                if brk.break_time < chart_start or brk.broken_swing.time > chart_end:
                    continue
                bull = brk.direction.value == "BULLISH"
                shapes.append(dict(
                    type="line",
                    x0=max(brk.broken_swing.time, chart_start),
                    y0=brk.broken_swing.price,
                    x1=min(brk.break_time, chart_end),
                    y1=brk.broken_swing.price,
                    line=dict(color=bull_color if bull else bear_color, width=1.2, dash="dash"),
                    xref="x", yref="y",
                ))'''

new_block = '''        # 7.3 ICT Structure Breaks
        if show_structure_breaks and hasattr(ict_result, "structure_breaks") and ict_result.structure_breaks:
            for brk in ict_result.structure_breaks:
                if brk.break_time < chart_start or brk.broken_swing.time > chart_end:
                    continue
                bull = brk.direction.value == "BULLISH"
                event_color = bull_color if bull else bear_color
                brk_label = brk.break_type.value if hasattr(brk, "break_type") else ("BOS" if bull else "CHoCH")
                shapes.append(dict(
                    type="line",
                    x0=max(brk.broken_swing.time, chart_start),
                    y0=brk.broken_swing.price,
                    x1=min(brk.break_time, chart_end),
                    y1=brk.broken_swing.price,
                    line=dict(color=event_color, width=1.2, dash="dash"),
                    xref="x", yref="y",
                ))
                # Annotation badge with break type and timestamp (required by test_property_14)
                if chart_start <= brk.break_time <= chart_end:
                    badge_sign = "+" if bull else "-"
                    break_utc = brk.break_time.strftime("%Y-%m-%d %H:%M UTC")
                    annotations.append(dict(
                        x=brk.break_time,
                        y=brk.broken_swing.price,
                        text=f"<b>{badge_sign}{brk_label}</b> {break_utc}",
                        showarrow=False,
                        font=dict(size=7, color=event_color),
                        bgcolor="rgba(12, 15, 23, 0.80)",
                        bordercolor=event_color,
                        borderwidth=1,
                        borderpad=2,
                        yshift=8 if bull else -8,
                        xref="x",
                        yref="y",
                    ))'''

if old_block in content:
    content = content.replace(old_block, new_block, 1)
    print("Patched: ICT structure breaks with BOS/CHoCH UTC annotations")
else:
    print("ERROR: ICT structure breaks pattern NOT found", file=sys.stderr)
    idx = content.find("7.3 ICT Structure Breaks")
    if idx >= 0:
        print("Context:", repr(content[idx:idx+600]))
    sys.exit(1)

with open('src/visualization/charts.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("charts.py saved successfully.")

