import sys

with open("src/visualization/charts.py", "r", encoding="utf-8") as f:
    text = f.read()

target = """    # 3. Preset Application
    # If preset is None, default to 'custom' to preserve full backward compatibility with explicit caller toggles.
    p_norm = preset.lower() if preset is not None else "custom"
    if p_norm == "clean":
        show_order_blocks = False
        show_breakers = False
        show_fvgs = False
        show_liquidity_pools = False
        show_swings = False
        show_structure_breaks = True
        show_sweeps = False
        show_dealing_range = False
        proximity_filter = True if proximity_filter is None else proximity_filter
        only_active_zones = True if only_active_zones is None else only_active_zones
    elif p_norm == "smc_analysis":
        # Institutional Default: focused on actionable active structure
        show_order_blocks = True
        show_breakers = True
        show_fvgs = True
        show_liquidity_pools = True
        show_swings = True
        show_structure_breaks = True
        show_sweeps = True
        proximity_filter = True if proximity_filter is None else proximity_filter
        only_active_zones = True if only_active_zones is None else only_active_zones
        max_zones_per_type = 5 if max_zones_per_type is None else max_zones_per_type
    elif p_norm == "full_research":
        # Full Academic Research: all historical zones, all states
        show_order_blocks = True
        show_breakers = True
        show_fvgs = True
        show_liquidity_pools = True
        show_swings = True
        show_structure_breaks = True
        show_sweeps = True
        proximity_filter = False if proximity_filter is None else proximity_filter
        only_active_zones = False if only_active_zones is None else only_active_zones
        max_zones_per_type = None if max_zones_per_type is None else max_zones_per_type
    else:  # Custom
        proximity_filter = False if proximity_filter is None else proximity_filter
        only_active_zones = False if only_active_zones is None else only_active_zones"""

replacement = """    # 3. Preset Application
    if preset is not None:
        p_norm = preset.lower()
        if p_norm == "clean":
            show_order_blocks = False
            show_breakers = False
            show_fvgs = False
            show_liquidity_pools = False
            show_swings = False
            show_structure_breaks = True
            show_sweeps = False
            show_dealing_range = False
            proximity_filter = True if proximity_filter is None else proximity_filter
            only_active_zones = True if only_active_zones is None else only_active_zones
        elif p_norm == "smc_analysis":
            # Institutional Default: focused on actionable nearby structure
            show_order_blocks = True
            show_breakers = True
            show_fvgs = True
            show_liquidity_pools = True
            show_swings = True
            show_structure_breaks = True
            show_sweeps = True
            proximity_filter = True if proximity_filter is None else proximity_filter
            only_active_zones = False if only_active_zones is None else only_active_zones
            max_zones_per_type = 8 if max_zones_per_type is None else max_zones_per_type
        elif p_norm == "full_research":
            # Full Academic Research: all historical zones, all states
            show_order_blocks = True
            show_breakers = True
            show_fvgs = True
            show_liquidity_pools = True
            show_swings = True
            show_structure_breaks = True
            show_sweeps = True
            proximity_filter = False if proximity_filter is None else proximity_filter
            only_active_zones = False if only_active_zones is None else only_active_zones
            max_zones_per_type = None if max_zones_per_type is None else max_zones_per_type
        else:  # Custom
            proximity_filter = False if proximity_filter is None else proximity_filter
            only_active_zones = False if only_active_zones is None else only_active_zones
    else:
        # Default when preset is None: preserve explicit caller toggles, while applying
        # proximity filtering to ensure institutional chart framing and sub-second rendering.
        proximity_filter = True if proximity_filter is None else proximity_filter
        only_active_zones = False if only_active_zones is None else only_active_zones
        max_zones_per_type = 8 if max_zones_per_type is None else max_zones_per_type"""

text_norm = text.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")
replacement_norm = replacement.replace("\r\n", "\n")

if target_norm in text_norm:
    text_norm = text_norm.replace(target_norm, replacement_norm, 1)
    with open("src/visualization/charts.py", "w", encoding="utf-8") as f:
        f.write(text_norm)
    print("SUCCESS: Updated preset logic in charts.py")
else:
    print("FAILED: Target block not found in charts.py", file=sys.stderr)
    sys.exit(1)
