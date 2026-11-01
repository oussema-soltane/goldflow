"""
Interactive Financial Visualization Engine for GoldFlow.

Builds high-performance, academic-grade Plotly candlestick charts with:
- Synchronized multi-pane subplots (Price action + Volume).
- Institutional dark styling with explicit UTC timestamp axis.
- Independent SMC (Smart Money Concepts) overlays — PRIMARY framework:
  * Confirmed Swing Highs & Lows (HH, LH, HL, LL) with availability timestamps.
  * Break of Structure (BOS), Change of Character (CHoCH), Initial Break lines.
  * SMC Fair Value Gaps (Bullish & Bearish, with 50% CE midpoint line).
  * Equal-High/Low Liquidity Pool zones (BSL amber / SSL blue) with sweep state.
  * Liquidity Sweeps (wick-and-reclaim events).
  * SMC Order Block zones (BULLISH / BEARISH, ACTIVE / MITIGATED / INVALIDATED).
  * Dealing Range (High, Low, 50% Equilibrium) context lines.
- Independent ICT (Inner Circle Trader) overlays — SECONDARY framework:
  * Fractal Swing Highs & Lows (HH, LH, HL, LL).
  * Break of Structure (BOS) & Change of Character (CHoCH).
  * Fair Value Gaps (ICT, 3-candle, with displacement filter + 50% CE line).
  * ICT Liquidity Sweeps (Buy-side & Sell-side stop runs).
  * ICT Institutional Order Blocks.
  * Displacement candles (ATR multiplier + body ratio filter).
- Trade execution overlay (entry/exit markers, SL/TP lines).

The two analytical frameworks share chart infrastructure but render completely
independent analytical events. SMC and ICT overlays are never mixed in a
single chart view — the caller passes either ``smc_result`` or ``ict_result``.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_candlestick_chart(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    show_volume: bool = True,
    dark_theme: bool = True,
    height: int = 700,
    ict_result: Optional[Any] = None,
    smc_result: Optional[Any] = None,
    show_swings: bool = True,
    show_structure_breaks: bool = True,
    show_fvgs: bool = True,
    show_sweeps: bool = True,
    show_order_blocks: bool = True,
    show_breakers: bool = True,
    show_displacements: bool = True,
    show_liquidity_pools: bool = True,
    show_dealing_range: bool = True,
    trades: Optional[Any] = None,
    show_trades: bool = True,
    visible_bars: Optional[int] = None,
    preset: Optional[str] = None,
    hide_weekends: bool = True,
    proximity_filter: Optional[bool] = None,
    only_active_zones: Optional[bool] = None,
    max_zones_per_type: Optional[int] = None,
    autoscale_y_to_visible: bool = True,
) -> go.Figure:
    """
    Construct an institutional-quality Plotly financial chart with volume and SMC/ICT overlays.

    Features & Architectural Fixes:
    - Dedicated visual presets: 'clean', 'smc_analysis' (default), 'full_research', 'custom'.
    - Intelligent dynamic Y-axis framing: locks price axis to visible OHLC (+8% padding),
      preventing distant historical zones from compressing candles into flat lines.
    - Overlay relevance & proximity filtering: filters out distant/mitigated zones in tactical view.
    - Non-overlapping structure badges (+BOS, -CHoCH) with rich hovercard diagnostics.
    - Removal of stacked left-edge labels; active unmitigated zones feature subtle right badges.
    - Weekend gap suppression via Plotly rangebreaks for smooth continuous candle/volume flows.
    - Ultra-fast bulk layout assignment (<0.5s render latency).
    """
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No market data available to display",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=16, color="#888888"),
        )
        return fig

    # 1. Slice visible window if specified
    if visible_bars is not None and visible_bars > 0 and len(df) > visible_bars:
        df = df.iloc[-visible_bars:].copy().reset_index(drop=True)
    else:
        df = df.copy()

    if not pd.api.types.is_datetime64_any_dtype(df["time"]):
        df["time"] = pd.to_datetime(df["time"], utc=True)

    chart_start = df["time"].iloc[0]
    chart_end = df["time"].iloc[-1]
    shapes: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []

    # 2. Dynamic Price Framing & Proximity Bounds
    vis_high = float(df["high"].max())
    vis_low = float(df["low"].min())
    vis_span = max(vis_high - vis_low, 1.0)
    current_price = float(df["close"].iloc[-1])

    pad = vis_span * 0.08
    y_min_target = vis_low - pad
    y_max_target = vis_high + pad

    # Proximity filter vertical limits
    price_margin = vis_span * 0.35
    min_zone_y = vis_low - price_margin
    max_zone_y = vis_high + price_margin

    # 3. Preset Application
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
        max_zones_per_type = 8 if max_zones_per_type is None else max_zones_per_type

    # Palette
    bg_color = "#0c0f17" if dark_theme else "#ffffff"
    paper_bg = "#121520" if dark_theme else "#f8f9fa"
    grid_color = "#1a1f2c" if dark_theme else "#e9ecef"
    text_color = "#d1d4dc" if dark_theme else "#1f2937"
    bull_color = "#00c087"  # Institutional Emerald Teal
    bear_color = "#ff3b57"  # Institutional Crimson Red
    gold_color = "#f0b90b"  # Gold Accent

    has_vol = show_volume and "tick_volume" in df.columns and df["tick_volume"].sum() > 0

    if has_vol:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.80, 0.20],
            specs=[[{"secondary_y": False}], [{"secondary_y": False}]],
        )
    else:
        fig = make_subplots(
            rows=1,
            cols=1,
            specs=[[{"secondary_y": False}]],
        )

    # 4. Candlestick Trace (The Hero Element)
    candlestick = go.Candlestick(
        x=df["time"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price",
        increasing=dict(line=dict(color=bull_color, width=1.2), fillcolor=bull_color),
        decreasing=dict(line=dict(color=bear_color, width=1.2), fillcolor=bear_color),
        showlegend=False,
    )
    fig.add_trace(candlestick, row=1, col=1)

    # 5. Volume Trace (Aligned candle-by-candle)
    if has_vol:
        is_bullish = df["close"] >= df["open"]
        vol_colors = [bull_color if b else bear_color for b in is_bullish]
        volume_bars = go.Bar(
            x=df["time"],
            y=df["tick_volume"],
            name="Tick Volume",
            marker=dict(color=vol_colors, opacity=0.65),
            showlegend=False,
        )
        fig.add_trace(volume_bars, row=2, col=1)

    # 6. SMC Primary Engine Overlays
    if smc_result is not None:
        # 6.1 Order Blocks
        if show_order_blocks and getattr(smc_result, "order_blocks", None):
            candidate_obs = []
            for ob in smc_result.order_blocks:
                end_x = ob.invalidation_time or ob.mitigation_time or chart_end
                if end_x < chart_start or ob.created_time > chart_end:
                    continue
                if only_active_zones and ob.status.value != "ACTIVE":
                    continue
                if proximity_filter and (ob.high < min_zone_y or ob.low > max_zone_y):
                    continue
                candidate_obs.append((ob, end_x))

            # Prioritize closest to current price if capped
            if max_zones_per_type is not None and max_zones_per_type > 0:
                bull_obs = [item for item in candidate_obs if item[0].direction.value == "BULLISH"]
                bear_obs = [item for item in candidate_obs if item[0].direction.value == "BEARISH"]
                bull_obs.sort(key=lambda item: abs(current_price - item[0].high))
                bear_obs.sort(key=lambda item: abs(item[0].low - current_price))
                candidate_obs = bull_obs[:max_zones_per_type] + bear_obs[:max_zones_per_type]

            ob_marker_x, ob_marker_y, ob_hovers = [], [], []
            for ob, end_x in candidate_obs:
                bullish = ob.direction.value == "BULLISH"
                is_active = ob.status.value == "ACTIVE"
                is_invalidated = ob.status.value == "INVALIDATED"

                if is_invalidated:
                    fill = "rgba(45, 55, 72, 0.04)"
                    edge = "rgba(100, 116, 139, 0.25)"
                    dash_style = "dot"
                elif is_active:
                    fill = "rgba(0, 192, 135, 0.12)" if bullish else "rgba(255, 59, 87, 0.12)"
                    edge = "rgba(0, 192, 135, 0.70)" if bullish else "rgba(255, 59, 87, 0.70)"
                    dash_style = "solid"
                else:  # MITIGATED
                    fill = "rgba(0, 192, 135, 0.05)" if bullish else "rgba(255, 59, 87, 0.05)"
                    edge = "rgba(0, 192, 135, 0.35)" if bullish else "rgba(255, 59, 87, 0.35)"
                    dash_style = "dash"

                # Shaded zone rectangle
                shapes.append(dict(
                    type="rect",
                    x0=max(ob.created_time, chart_start),
                    y0=ob.low,
                    x1=min(end_x, chart_end),
                    y1=ob.high,
                    fillcolor=fill,
                    line=dict(color=edge, width=1, dash=dash_style),
                    layer="below",
                    xref="x",
                    yref="y",
                ))

                # Hover diagnostic point inside visible window
                if chart_start <= ob.created_time <= chart_end:
                    ob_marker_x.append(ob.created_time)
                    ob_marker_y.append((ob.high + ob.low) / 2.0)
                    ob_hovers.append(
                        f"<b>SMC {ob.direction.value} ORDER BLOCK</b><br>"
                        f"Zone: ${ob.low:.2f} — ${ob.high:.2f}<br>"
                        f"Origin: {ob.origin_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Confirmed: {ob.created_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Status: {ob.status.value}"
                        + (f"<br>Mitigated: {ob.mitigation_time.strftime('%Y-%m-%d %H:%M UTC')}" if ob.mitigation_time else "")
                        + (f"<br>Invalidated: {ob.invalidation_time.strftime('%Y-%m-%d %H:%M UTC')}" if ob.invalidation_time else "")
                    )

                # Right-edge badge for active zones extending to current candle
                if is_active and end_x >= chart_end:
                    tag = "Demand OB" if bullish else "Supply OB"
                    tag_col = bull_color if bullish else bear_color
                    annotations.append(dict(
                        x=chart_end,
                        y=(ob.high + ob.low) / 2.0,
                        text=f"<b>{tag}</b>",
                        showarrow=False,
                        font=dict(size=8, color=tag_col),
                        bgcolor="rgba(12, 15, 23, 0.80)",
                        bordercolor=tag_col,
                        borderwidth=1,
                        borderpad=2,
                        xanchor="left",
                        xref="x",
                        yref="y",
                    ))

            if ob_marker_x:
                fig.add_trace(go.Scatter(
                    x=ob_marker_x, y=ob_marker_y, mode="markers",
                    name="SMC Order Blocks",
                    marker=dict(symbol="square", size=5, color="#22c55e", opacity=0.7),
                    hovertext=ob_hovers, hoverinfo="text", showlegend=False,
                ), row=1, col=1)

        # 6.2 Breaker Blocks
        if show_breakers and getattr(smc_result, "breaker_blocks", None):
            candidate_bbs = []
            for bb in smc_result.breaker_blocks:
                end_x = bb.invalidation_time or chart_end
                if end_x < chart_start or bb.created_time > chart_end:
                    continue
                if only_active_zones and bb.status.value == "INVALIDATED":
                    continue
                if proximity_filter and (bb.high < min_zone_y or bb.low > max_zone_y):
                    continue
                candidate_bbs.append((bb, end_x))

            bb_marker_x, bb_marker_y, bb_hovers = [], [], []
            for bb, end_x in candidate_bbs:
                bullish = bb.breaker_type.value == "BULLISH"
                is_inv = bb.status.value == "INVALIDATED"
                # Bullish Breaker: cyan | Bearish Breaker: magenta
                if is_inv:
                    fill = "rgba(45, 55, 72, 0.03)"
                    edge = "rgba(100, 116, 139, 0.20)"
                elif bullish:
                    fill = "rgba(6, 182, 212, 0.10)"
                    edge = "rgba(6, 182, 212, 0.65)"
                else:
                    fill = "rgba(217, 70, 239, 0.10)"
                    edge = "rgba(217, 70, 239, 0.65)"

                shapes.append(dict(
                    type="rect",
                    x0=max(bb.created_time, chart_start),
                    y0=bb.low,
                    x1=min(end_x, chart_end),
                    y1=bb.high,
                    fillcolor=fill,
                    line=dict(color=edge, width=1, dash="dashdot"),
                    layer="below",
                    xref="x",
                    yref="y",
                ))

                if chart_start <= bb.created_time <= chart_end:
                    bb_marker_x.append(bb.created_time)
                    bb_marker_y.append((bb.high + bb.low) / 2.0)
                    bb_hovers.append(
                        f"<b>SMC {bb.breaker_type.value} BREAKER BLOCK</b><br>"
                        f"Zone: ${bb.low:.2f} — ${bb.high:.2f}<br>"
                        f"Inverted: {bb.created_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Status: {bb.status.value}"
                        + (f"<br>Retested: {bb.retest_time.strftime('%Y-%m-%d %H:%M UTC')}" if bb.retest_time else "")
                        + (f"<br>Invalidated: {bb.invalidation_time.strftime('%Y-%m-%d %H:%M UTC')}" if bb.invalidation_time else "")
                    )

            if bb_marker_x:
                fig.add_trace(go.Scatter(
                    x=bb_marker_x, y=bb_marker_y, mode="markers",
                    name="SMC Breaker Blocks",
                    marker=dict(symbol="diamond", size=5, color="#f472b6", opacity=0.7),
                    hovertext=bb_hovers, hoverinfo="text", showlegend=False,
                ), row=1, col=1)

        # 6.3 Fair Value Gaps (FVG)
        if show_fvgs and getattr(smc_result, "fair_value_gaps", None):
            candidate_fvgs = []
            for fvg in smc_result.fair_value_gaps:
                end_x = fvg.closed_time or chart_end
                if end_x < chart_start or fvg.creation_time > chart_end:
                    continue
                if only_active_zones and fvg.status.value == "CLOSED":
                    continue
                if proximity_filter and (fvg.top < min_zone_y or fvg.bottom > max_zone_y):
                    continue
                candidate_fvgs.append((fvg, end_x))

            if max_zones_per_type is not None and max_zones_per_type > 0:
                bull_f = [item for item in candidate_fvgs if item[0].fvg_type.value == "BULLISH"]
                bear_f = [item for item in candidate_fvgs if item[0].fvg_type.value == "BEARISH"]
                bull_f.sort(key=lambda item: abs(current_price - item[0].top))
                bear_f.sort(key=lambda item: abs(item[0].bottom - current_price))
                candidate_fvgs = bull_f[:max_zones_per_type] + bear_f[:max_zones_per_type]

            fvg_marker_x, fvg_marker_y, fvg_hovers = [], [], []
            for fvg, end_x in candidate_fvgs:
                bullish = fvg.fvg_type.value == "BULLISH"
                is_closed = fvg.status.value == "CLOSED"

                if is_closed:
                    zone_fill = "rgba(45, 55, 72, 0.03)"
                    zone_edge = "rgba(100, 116, 139, 0.20)"
                    ce_color = "rgba(100, 116, 139, 0.25)"
                elif bullish:
                    zone_fill = "rgba(0, 208, 156, 0.08)"
                    zone_edge = "rgba(0, 208, 156, 0.50)"
                    ce_color = "rgba(0, 208, 156, 0.65)"
                else:
                    zone_fill = "rgba(255, 59, 87, 0.08)"
                    zone_edge = "rgba(255, 59, 87, 0.50)"
                    ce_color = "rgba(255, 59, 87, 0.65)"

                shapes.append(dict(
                    type="rect",
                    x0=max(fvg.creation_time, chart_start),
                    y0=fvg.bottom,
                    x1=min(end_x, chart_end),
                    y1=fvg.top,
                    fillcolor=zone_fill,
                    line=dict(color=zone_edge, width=1, dash="solid" if not is_closed else "dot"),
                    layer="below",
                    xref="x",
                    yref="y",
                ))
                # 50% Consequent Encroachment (CE) Line
                shapes.append(dict(
                    type="line",
                    x0=max(fvg.creation_time, chart_start),
                    y0=fvg.midpoint,
                    x1=min(end_x, chart_end),
                    y1=fvg.midpoint,
                    line=dict(color=ce_color, width=1, dash="dot"),
                    layer="below",
                    xref="x",
                    yref="y",
                ))

                if chart_start <= fvg.creation_time <= chart_end:
                    fvg_marker_x.append(fvg.creation_time)
                    fvg_marker_y.append(fvg.midpoint)
                    fvg_hovers.append(
                        f"<b>SMC {'BULLISH' if bullish else 'BEARISH'} FVG</b><br>"
                        f"Zone: ${fvg.bottom:.2f} — ${fvg.top:.2f}<br>"
                        f"CE (50%): ${fvg.midpoint:.2f}<br>"
                        f"Gap Size: ${fvg.size:.2f}<br>"
                        f"Created: {fvg.creation_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Status: {fvg.status.value}"
                        + (f"<br>First touch: {fvg.first_touch_time.strftime('%Y-%m-%d %H:%M UTC')}" if fvg.first_touch_time else "")
                        + (f"<br>Closed: {fvg.closed_time.strftime('%Y-%m-%d %H:%M UTC')}" if fvg.closed_time else "")
                    )

            if fvg_marker_x:
                fig.add_trace(go.Scatter(
                    x=fvg_marker_x, y=fvg_marker_y, mode="markers",
                    name="SMC FVGs",
                    marker=dict(symbol="circle", size=4, color="#a78bfa", opacity=0.6),
                    hovertext=fvg_hovers, hoverinfo="text", showlegend=False,
                ), row=1, col=1)

        # 6.4 Liquidity Pools
        if show_liquidity_pools and getattr(smc_result, "liquidity_pools", None):
            sweep_by_pool = {id(event.liquidity_pool): event for event in smc_result.liquidity_sweeps}
            candidate_pools = []
            for pool in smc_result.liquidity_pools:
                sweep = sweep_by_pool.get(id(pool))
                is_swept = sweep is not None
                end_x = sweep.sweep_time if is_swept else chart_end
                if end_x < chart_start or pool.created_time > chart_end:
                    continue
                if only_active_zones and is_swept and sweep.sweep_time < chart_start:
                    continue
                tol = float(pool.tolerance)
                if proximity_filter and ((pool.level + tol) < min_zone_y or (pool.level - tol) > max_zone_y):
                    continue
                candidate_pools.append((pool, sweep, is_swept, end_x))

            pool_marker_x, pool_marker_y, pool_hovers = [], [], []
            for pool, sweep, is_swept, end_x in candidate_pools:
                buy_side = pool.liquidity_type.value == "BUY_SIDE"
                tol = float(pool.tolerance)
                zone_top = pool.level + tol
                zone_bot = pool.level - tol

                if buy_side:
                    fill = "rgba(245, 158, 11, 0.04)" if is_swept else "rgba(245, 158, 11, 0.12)"
                    edge = "rgba(245, 158, 11, 0.30)" if is_swept else "rgba(245, 158, 11, 0.65)"
                    line_color = "rgba(245, 158, 11, 0.50)" if is_swept else "#f59e0b"
                else:
                    fill = "rgba(56, 189, 248, 0.04)" if is_swept else "rgba(56, 189, 248, 0.12)"
                    edge = "rgba(56, 189, 248, 0.30)" if is_swept else "rgba(56, 189, 248, 0.65)"
                    line_color = "rgba(56, 189, 248, 0.50)" if is_swept else "#38bdf8"

                # Tolerance rectangle
                shapes.append(dict(
                    type="rect",
                    x0=max(pool.created_time, chart_start),
                    y0=zone_bot,
                    x1=min(end_x, chart_end),
                    y1=zone_top,
                    fillcolor=fill,
                    line=dict(color=edge, width=0.8, dash="dot"),
                    layer="below",
                    xref="x",
                    yref="y",
                ))
                # Midline
                shapes.append(dict(
                    type="line",
                    x0=max(pool.created_time, chart_start),
                    y0=pool.level,
                    x1=min(end_x, chart_end),
                    y1=pool.level,
                    line=dict(color=line_color, width=1.2, dash="dash" if not is_swept else "dot"),
                    layer="below",
                    xref="x",
                    yref="y",
                ))

                if chart_start <= pool.created_time <= chart_end:
                    pool_marker_x.append(pool.created_time)
                    pool_marker_y.append(pool.level)
                    pool_hovers.append(
                        f"<b>SMC {pool.liquidity_type.value.replace('_', ' ')} POOL</b><br>"
                        f"Level: ${pool.level:.2f} ± {tol:.2f}<br>"
                        f"Formed: {pool.created_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Swept: {'Yes — ' + sweep.sweep_time.strftime('%Y-%m-%d %H:%M UTC') if is_swept else 'No (Active)'}"
                    )

                if not is_swept and end_x >= chart_end:
                    badge_lbl = "BSL" if buy_side else "SSL"
                    b_col = "#f59e0b" if buy_side else "#38bdf8"
                    annotations.append(dict(
                        x=chart_end,
                        y=pool.level,
                        text=f"<b>{badge_lbl}</b>",
                        showarrow=False,
                        font=dict(size=8, color=b_col),
                        bgcolor="rgba(12, 15, 23, 0.80)",
                        bordercolor=b_col,
                        borderwidth=1,
                        borderpad=2,
                        xanchor="left",
                        xref="x",
                        yref="y",
                    ))

            if pool_marker_x:
                fig.add_trace(go.Scatter(
                    x=pool_marker_x, y=pool_marker_y, mode="markers",
                    name="SMC Liquidity Pools",
                    marker=dict(symbol="line-ew", size=8, color="#f59e0b", opacity=0.8),
                    hovertext=pool_hovers, hoverinfo="text", showlegend=False,
                ), row=1, col=1)

        # 6.5 Structure Breaks (BOS / CHoCH)
        if show_structure_breaks and getattr(smc_result, "structure_breaks", None):
            brk_x, brk_y, brk_hovers = [], [], []
            for event in smc_result.structure_breaks:
                if event.break_time < chart_start or event.broken_swing.confirmed_time > chart_end:
                    continue
                bullish = event.direction.value == "BULLISH"
                event_color = bull_color if bullish else bear_color
                is_choch = event.break_type.value == "CHOCH"
                is_bos = event.break_type.value == "BOS"
                dash = "longdash" if is_choch else ("dash" if is_bos else "dot")
                width = 1.5 if is_choch else 1.2

                # Horizontal break line
                shapes.append(dict(
                    type="line",
                    x0=max(event.broken_swing.confirmed_time, chart_start),
                    y0=event.broken_swing.price,
                    x1=min(event.break_time, chart_end),
                    y1=event.broken_swing.price,
                    line=dict(color=event_color, width=width, dash=dash),
                    xref="x",
                    yref="y",
                ))

                # Sleek non-overlapping badge
                if chart_start <= event.break_time <= chart_end:
                    badge_lbl = f"+{event.break_type.value}" if bullish else f"-{event.break_type.value}"
                    yshift = 9 if bullish else -9
                    annotations.append(dict(
                        x=event.break_time,
                        y=event.broken_swing.price,
                        text=f"<b>{badge_lbl}</b>",
                        showarrow=False,
                        font=dict(size=8, color=event_color),
                        bgcolor="rgba(12, 15, 23, 0.85)",
                        bordercolor=event_color,
                        borderwidth=1,
                        borderpad=2,
                        yshift=yshift,
                        xref="x",
                        yref="y",
                    ))
                    brk_x.append(event.break_time)
                    brk_y.append(event.broken_swing.price)
                    brk_hovers.append(
                        f"<b>SMC {event.break_type.value} ({event.direction.value})</b><br>"
                        f"Broken Level: ${event.broken_swing.price:.2f}<br>"
                        f"Break Close: ${event.break_price:.2f}<br>"
                        f"Break Time: {event.break_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Prior: {event.prior_trend.value} → Resulting: {event.resulting_trend.value}"
                    )

            if brk_x:
                fig.add_trace(go.Scatter(
                    x=brk_x, y=brk_y, mode="markers",
                    name="Structure Breaks",
                    marker=dict(symbol="circle-open", size=6, color="#ffffff", line=dict(width=1.5)),
                    hovertext=brk_hovers, hoverinfo="text", showlegend=False,
                ), row=1, col=1)

        # 6.6 Confirmed Swings
        if show_swings and getattr(smc_result, "swings", None):
            for swing_type, trace_name, sym, col in (
                ("SWING_HIGH", "SMC Confirmed Swing Highs", "triangle-down", "#f59e0b"),
                ("SWING_LOW", "SMC Confirmed Swing Lows", "triangle-up", "#60a5fa"),
            ):
                pivots = [
                    s for s in smc_result.swings
                    if s.swing_type.value == swing_type and chart_start <= s.confirmed_time <= chart_end
                ]
                if pivots:
                    fig.add_trace(go.Scatter(
                        x=[s.time for s in pivots],
                        y=[s.price for s in pivots],
                        mode="markers",
                        name=trace_name,
                        marker=dict(symbol=sym, size=6, color=col),
                        hovertext=[
                            f"<b>SMC {swing_type.replace('_', ' ')}</b><br>"
                            f"Price: ${s.price:.2f}<br>"
                            f"Formed: {s.time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                            f"Confirmed: {s.confirmed_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                            f"Classification: {s.classification}"
                            for s in pivots
                        ],
                        hoverinfo="text",
                        showlegend=False,
                    ), row=1, col=1)

        # 6.7 Liquidity Sweeps
        if show_sweeps and getattr(smc_result, "liquidity_sweeps", None):
            sweeps = [
                ev for ev in smc_result.liquidity_sweeps
                if chart_start <= ev.sweep_time <= chart_end
            ]
            if sweeps:
                fig.add_trace(go.Scatter(
                    x=[ev.sweep_time for ev in sweeps],
                    y=[ev.sweep_price for ev in sweeps],
                    mode="markers",
                    name="SMC Liquidity Sweeps",
                    marker=dict(symbol="diamond", size=8, color="#ec4899", line=dict(color="#ffffff", width=1)),
                    hovertext=[
                        f"<b>SMC {ev.liquidity_type.value.replace('_', ' ')} SWEEP</b><br>"
                        f"Pool Level: ${ev.liquidity_pool.level:.2f}<br>"
                        f"Sweep Extreme: ${ev.sweep_price:.2f}<br>"
                        f"Candle Close: ${ev.close_price:.2f}<br>"
                        f"Penetration: ${ev.penetration:.2f}<br>"
                        f"Confirmed: {ev.sweep_time.strftime('%Y-%m-%d %H:%M UTC')}"
                        for ev in sweeps
                    ],
                    hoverinfo="text",
                    showlegend=False,
                ), row=1, col=1)

        # 6.8 Dealing Range
        if show_dealing_range and smc_result is not None:
            eq = getattr(smc_result, "equilibrium", None)
            dr_high = getattr(smc_result, "dealing_range_high", None)
            dr_low = getattr(smc_result, "dealing_range_low", None)
            if eq is not None and dr_high is not None and dr_low is not None:
                shapes.append(dict(
                    type="line", x0=chart_start, y0=dr_high, x1=chart_end, y1=dr_high,
                    line=dict(color="rgba(245, 158, 11, 0.50)", width=1.0, dash="dash"),
                    xref="x", yref="y",
                ))
                shapes.append(dict(
                    type="line", x0=chart_start, y0=dr_low, x1=chart_end, y1=dr_low,
                    line=dict(color="rgba(96, 165, 250, 0.50)", width=1.0, dash="dash"),
                    xref="x", yref="y",
                ))
                shapes.append(dict(
                    type="line", x0=chart_start, y0=eq, x1=chart_end, y1=eq,
                    line=dict(color="rgba(220, 225, 235, 0.65)", width=1.0, dash="dot"),
                    xref="x", yref="y",
                ))

    # 7. ICT Secondary Engine Overlays (Preserved & Cleaned)
    elif ict_result is not None:
        # 7.0 Displacements
        disp_indices = getattr(ict_result, "displacement_indices", [])
        if show_displacements and disp_indices:
            valid_idx = [i for i in disp_indices if 0 <= i < len(df)]
            if valid_idx:
                fig.add_trace(go.Scatter(
                    x=[df["time"].iloc[i] for i in valid_idx],
                    y=[float(df["close"].iloc[i]) for i in valid_idx],
                    mode="markers",
                    name="Displacement",
                    marker=dict(symbol="star", size=8, color="#f59e0b"),
                    hovertext=[
                        f"<b>ICT DISPLACEMENT</b><br>Time: {df['time'].iloc[i].strftime('%Y-%m-%d %H:%M UTC')}<br>Body: {abs(float(df['close'].iloc[i]) - float(df['open'].iloc[i])):.2f}"
                        for i in valid_idx
                    ],
                    hoverinfo="text",
                    showlegend=False,
                ), row=1, col=1)

        # 7.1 ICT Order Blocks
        if show_order_blocks and hasattr(ict_result, "order_blocks") and ict_result.order_blocks:
            ob_ev_times, ob_ev_prices, ob_ev_hovers = [], [], []
            for ob in ict_result.order_blocks:
                end_x = ob.mitigation_time if (ob.is_mitigated and ob.mitigation_time) else chart_end
                if end_x < chart_start or ob.candle_time > chart_end:
                    continue
                bull = ob.ob_type.value == "BULLISH"
                shapes.append(dict(
                    type="rect",
                    x0=max(ob.candle_time, chart_start),
                    y0=ob.low,
                    x1=min(end_x, chart_end),
                    y1=ob.high,
                    fillcolor="rgba(59, 130, 246, 0.12)" if bull else "rgba(239, 68, 68, 0.12)",
                    line=dict(color="rgba(59, 130, 246, 0.5)" if bull else "rgba(239, 68, 68, 0.5)", width=1, dash="dot"),
                    layer="below", xref="x", yref="y",
                ))
                ev_t = ob.confirmed_time or ob.candle_time
                if chart_start <= ev_t <= chart_end:
                    ob_ev_times.append(ev_t)
                    ob_ev_prices.append((ob.high + ob.low) / 2)
                    ob_ev_hovers.append(f"<b>ICT {ob.ob_type.value} OB</b><br>Zone: {ob.low:.2f} — {ob.high:.2f}")
            if ob_ev_times:
                fig.add_trace(go.Scatter(
                    x=ob_ev_times, y=ob_ev_prices, mode="markers",
                    name="Order Block Events",
                    marker=dict(symbol="square", size=5, color="#60a5fa"),
                    hovertext=ob_ev_hovers, hoverinfo="text", showlegend=False,
                ), row=1, col=1)

        # 7.2 ICT FVGs
        if show_fvgs and hasattr(ict_result, "fvgs") and ict_result.fvgs:
            fvg_ev_times, fvg_ev_prices, fvg_ev_hovers = [], [], []
            for fvg in ict_result.fvgs:
                end_x = fvg.mitigation_time if fvg.mitigation_time else chart_end
                if end_x < chart_start or fvg.creation_time > chart_end:
                    continue
                bull = fvg.gap_type.value == "BULLISH"
                shapes.append(dict(
                    type="rect",
                    x0=max(fvg.creation_time, chart_start),
                    y0=fvg.bottom_price,
                    x1=min(end_x, chart_end),
                    y1=fvg.top_price,
                    fillcolor="rgba(8, 153, 129, 0.10)" if bull else "rgba(242, 54, 69, 0.10)",
                    line=dict(color="rgba(8, 153, 129, 0.45)" if bull else "rgba(242, 54, 69, 0.45)", width=1),
                    layer="below", xref="x", yref="y",
                ))
                if chart_start <= fvg.creation_time <= chart_end:
                    fvg_ev_times.append(fvg.creation_time)
                    fvg_ev_prices.append((fvg.top_price + fvg.bottom_price) / 2)
                    fvg_ev_hovers.append(f"<b>ICT {fvg.gap_type.value} FVG</b><br>Zone: {fvg.bottom_price:.2f} — {fvg.top_price:.2f}")
            if fvg_ev_times:
                fig.add_trace(go.Scatter(
                    x=fvg_ev_times, y=fvg_ev_prices, mode="markers",
                    name="FVG Events",
                    marker=dict(symbol="circle", size=5, color="#a78bfa"),
                    hovertext=fvg_ev_hovers, hoverinfo="text", showlegend=False,
                ), row=1, col=1)

        # 7.3 ICT Structure Breaks
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
                    ))

        # 7.4 ICT Liquidity Sweeps
        if show_sweeps and hasattr(ict_result, "liquidity_sweeps") and ict_result.liquidity_sweeps:
            sw_in = [s for s in ict_result.liquidity_sweeps if chart_start <= s.sweep_time <= chart_end]
            if sw_in:
                fig.add_trace(go.Scatter(
                    x=[s.sweep_time for s in sw_in],
                    y=[s.sweep_price for s in sw_in],
                    mode="markers",
                    name="Liquidity Sweep",
                    marker=dict(symbol="diamond", size=8, color="#ec4899"),
                    hovertext=[f"<b>ICT SWEEP</b><br>Level: {s.swept_swing.price:.2f}<br>Extreme: {s.sweep_price:.2f}" for s in sw_in],
                    hoverinfo="text", showlegend=False,
                ), row=1, col=1)

        # 7.5 ICT Fractal Swings
        if show_swings and hasattr(ict_result, "swings") and ict_result.swings:
            shs = [s for s in ict_result.swings if s.swing_type.value == "SWING_HIGH" and chart_start <= s.time <= chart_end]
            sls = [s for s in ict_result.swings if s.swing_type.value == "SWING_LOW" and chart_start <= s.time <= chart_end]
            if shs:
                fig.add_trace(go.Scatter(
                    x=[s.time for s in shs],
                    y=[s.price for s in shs],
                    mode="markers",
                    name="Swing Highs",
                    marker=dict(symbol="triangle-down", size=7, color=gold_color),
                    hovertext=[
                        f"<b>ICT Swing High</b><br>"
                        f"Price: ${s.price:,.2f}<br>"
                        f"Formed: {s.time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Confirmed: {s.confirmed_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Classification: {s.classification}"
                        for s in shs
                    ],
                    hoverinfo="text", showlegend=False,
                ), row=1, col=1)
            if sls:
                fig.add_trace(go.Scatter(
                    x=[s.time for s in sls],
                    y=[s.price for s in sls],
                    mode="markers",
                    name="Swing Lows",
                    marker=dict(symbol="triangle-up", size=7, color="#3b82f6"),
                    hovertext=[
                        f"<b>ICT Swing Low</b><br>"
                        f"Price: ${s.price:,.2f}<br>"
                        f"Formed: {s.time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Confirmed: {s.confirmed_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Classification: {s.classification}"
                        for s in sls
                    ],
                    hoverinfo="text", showlegend=False,
                ), row=1, col=1)

    # 8. Strategy Trade Executions Overlay
    if show_trades and trades is not None:
        tdf = pd.DataFrame(trades) if isinstance(trades, list) else trades.copy()
        if not tdf.empty and "entry_time" in tdf.columns:
            tdf["entry_time"] = pd.to_datetime(tdf["entry_time"], utc=True)
            mask = (tdf["entry_time"] >= chart_start) & (tdf["entry_time"] <= chart_end)
            w_trades = tdf[mask]

            if not w_trades.empty:
                long_mask = w_trades["side"] == "LONG" if "side" in w_trades.columns else w_trades.get("direction") == "LONG"
                longs = w_trades[long_mask] if long_mask is not None else pd.DataFrame()
                if not longs.empty:
                    fig.add_trace(go.Scatter(
                        x=longs["entry_time"], y=longs["entry_price"], mode="markers",
                        name="Trade Entry (Long)",
                        marker=dict(symbol="triangle-up", size=10, color="#00c087", line=dict(color="#ffffff", width=1.2)),
                        hovertext=[
                            f"<b>LONG ENTRY</b><br>ID: {r.get('setup_id', 'N/A')}<br>Price: ${float(r['entry_price']):.2f}<br>Time: {r['entry_time'].strftime('%Y-%m-%d %H:%M UTC')}<br>SL: ${float(r.get('stop_loss', 0)):.2f} | TP: ${float(r.get('take_profit', 0)):.2f}"
                            for _, r in longs.iterrows()
                        ],
                        hoverinfo="text", showlegend=False,
                    ), row=1, col=1)

                short_mask = w_trades["side"] == "SHORT" if "side" in w_trades.columns else w_trades.get("direction") == "SHORT"
                shorts = w_trades[short_mask] if short_mask is not None else pd.DataFrame()
                if not shorts.empty:
                    fig.add_trace(go.Scatter(
                        x=shorts["entry_time"], y=shorts["entry_price"], mode="markers",
                        name="Trade Entry (Short)",
                        marker=dict(symbol="triangle-down", size=10, color="#ff3b57", line=dict(color="#ffffff", width=1.2)),
                        hovertext=[
                            f"<b>SHORT ENTRY</b><br>ID: {r.get('setup_id', 'N/A')}<br>Price: ${float(r['entry_price']):.2f}<br>Time: {r['entry_time'].strftime('%Y-%m-%d %H:%M UTC')}<br>SL: ${float(r.get('stop_loss', 0)):.2f} | TP: ${float(r.get('take_profit', 0)):.2f}"
                            for _, r in shorts.iterrows()
                        ],
                        hoverinfo="text", showlegend=False,
                    ), row=1, col=1)

                # Exits
                if "exit_time" in w_trades.columns:
                    w_exits = w_trades[w_trades["exit_time"].notna()].copy()
                    w_exits["exit_time"] = pd.to_datetime(w_exits["exit_time"], utc=True)
                    exit_in_chart = w_exits[(w_exits["exit_time"] >= chart_start) & (w_exits["exit_time"] <= chart_end)]
                    if not exit_in_chart.empty:
                        win_exits = exit_in_chart[exit_in_chart["net_pnl"] > 0]
                        loss_exits = exit_in_chart[exit_in_chart["net_pnl"] <= 0]
                        if not win_exits.empty:
                            fig.add_trace(go.Scatter(
                                x=win_exits["exit_time"], y=win_exits["exit_price"], mode="markers",
                                name="Exit (Profit)",
                                marker=dict(symbol="circle", size=8, color="#00c087", line=dict(color="#ffffff", width=1)),
                                hovertext=[
                                    f"<b>WIN EXIT</b><br>ID: {r.get('setup_id', 'N/A')}<br>Exit: ${float(r.get('exit_price', 0)):.2f}<br>Net: +${float(r.get('net_pnl', 0)):.2f}<br>Reason: {r.get('exit_reason', 'N/A')}"
                                    for _, r in win_exits.iterrows()
                                ],
                                hoverinfo="text", showlegend=False,
                            ), row=1, col=1)
                        if not loss_exits.empty:
                            fig.add_trace(go.Scatter(
                                x=loss_exits["exit_time"], y=loss_exits["exit_price"], mode="markers",
                                name="Exit (Loss)",
                                marker=dict(symbol="x", size=8, color="#ff3b57", line=dict(color="#ffffff", width=1.5)),
                                hovertext=[
                                    f"<b>LOSS EXIT</b><br>ID: {r.get('setup_id', 'N/A')}<br>Exit: ${float(r.get('exit_price', 0)):.2f}<br>Net: ${float(r.get('net_pnl', 0)):.2f}<br>Reason: {r.get('exit_reason', 'N/A')}"
                                    for _, r in loss_exits.iterrows()
                                ],
                                hoverinfo="text", showlegend=False,
                            ), row=1, col=1)

                # SL/TP lines
                for _, r in w_trades.iterrows():
                    entry_t = r["entry_time"]
                    exit_t_raw = r.get("exit_time")
                    exit_t = pd.to_datetime(exit_t_raw, utc=True) if pd.notna(exit_t_raw) else chart_end
                    sl = float(r.get("stop_loss", 0))
                    tp = float(r.get("take_profit", 0))
                    if sl > 0:
                        shapes.append(dict(
                            type="line", x0=max(entry_t, chart_start), y0=sl, x1=min(exit_t, chart_end), y1=sl,
                            line=dict(color="rgba(255, 59, 87, 0.45)", width=1, dash="dot"),
                            xref="x", yref="y",
                        ))
                    if tp > 0:
                        shapes.append(dict(
                            type="line", x0=max(entry_t, chart_start), y0=tp, x1=min(exit_t, chart_end), y1=tp,
                            line=dict(color="rgba(0, 192, 135, 0.45)", width=1, dash="dot"),
                            xref="x", yref="y",
                        ))

    # 9. Title & Layout Configuration
    start_str = df["time"].iloc[0].strftime("%Y-%m-%d %H:%M")
    end_str = df["time"].iloc[-1].strftime("%Y-%m-%d %H:%M")
    total_bars = len(df)
    clean_sym = symbol if symbol and symbol not in ["triangle-up", "triangle-down"] else "XAUUSD"

    title_text = (
        f"<b>{clean_sym}</b> · {timeframe} &nbsp;|&nbsp; "
        f"<span style='font-size:12px; color:{text_color}'>{start_str} to {end_str} UTC ({total_bars:,} bars)</span>"
    )

    yaxis_config = dict(
        title="Price (USD)",
        showgrid=True,
        gridcolor=grid_color,
        gridwidth=1,
        side="right",
        color=text_color,
        tickformat=".2f",
    )
    if autoscale_y_to_visible:
        yaxis_config["range"] = [y_min_target, y_max_target]
        yaxis_config["autorange"] = False
    else:
        yaxis_config["autorange"] = True

    fig.update_layout(
        shapes=shapes,
        annotations=annotations,
        title=dict(
            text=title_text,
            x=0.02,
            y=0.97,
            font=dict(size=15, color=text_color),
        ),
        paper_bgcolor=paper_bg,
        plot_bgcolor=bg_color,
        xaxis=dict(
            showgrid=True,
            gridcolor=grid_color,
            gridwidth=1,
            rangeslider=dict(visible=False),
            color=text_color,
        ),
        yaxis=yaxis_config,
        margin=dict(l=20, r=65, t=50, b=20),
        height=height,
        hovermode="closest",
    )

    fig.update_xaxes(rangeslider_visible=False)

    # 10. Hide weekend trading gaps (Problem E resolution)
    if hide_weekends:
        fig.update_xaxes(
            rangebreaks=[
                dict(bounds=["sat", "mon"]),  # Hide Saturday 00:00 to Monday 00:00 UTC
            ]
        )

    if has_vol:
        fig.update_yaxes(
            title="Volume",
            row=2,
            col=1,
            showgrid=True,
            gridcolor=grid_color,
            side="right",
            color=text_color,
        )
        fig.update_xaxes(
            showgrid=True,
            gridcolor=grid_color,
            row=2,
            col=1,
            color=text_color,
        )

    return fig


def create_equity_curve_chart(
    equity_df: pd.DataFrame,
    initial_capital: float = 10000.0,
    dark_theme: bool = True,
    height: int = 480,
) -> go.Figure:
    """
    Construct high-performance dual-pane Plotly chart of strategy equity curve
    and underwater drawdown % profile.
    """
    if equity_df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No equity curve data available",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="#888888"),
        )
        return fig

    eq = equity_df.copy()
    if "time" in eq.columns:
        eq["time"] = pd.to_datetime(eq["time"], utc=True)
        time_col = eq["time"]
    else:
        time_col = pd.RangeIndex(len(eq))

    # Calculate drawdown series if missing
    realized_col = eq["realized_equity"] if "realized_equity" in eq.columns else eq["equity"]
    peak = realized_col.cummax()
    dd_pct = ((realized_col - peak) / peak) * 100.0

    bg_color = "#0c0f17" if dark_theme else "#ffffff"
    paper_bg = "#121520" if dark_theme else "#f8f9fa"
    grid_color = "#1a1f2c" if dark_theme else "#e9ecef"
    text_color = "#d1d4dc" if dark_theme else "#1f2937"

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.75, 0.25],
        subplot_titles=("Cumulative Portfolio Equity ($)", "Underwater Drawdown (%)"),
    )

    # 1. Realized Equity Line
    fig.add_trace(
        go.Scatter(
            x=time_col, y=realized_col,
            name="Realized Equity",
            mode="lines",
            line=dict(color="#00c087", width=2),
            hoverinfo="x+y",
        ), row=1, col=1,
    )

    # 2. Mark-to-Market Equity Line (if present and distinct)
    if "equity" in eq.columns and "realized_equity" in eq.columns:
        fig.add_trace(
            go.Scatter(
                x=time_col, y=eq["equity"],
                name="Mark-to-Market Equity",
                mode="lines",
                line=dict(color="rgba(240, 185, 11, 0.7)", width=1, dash="dot"),
                hoverinfo="x+y",
            ), row=1, col=1,
        )

    # Initial Capital Reference Baseline
    fig.add_shape(
        type="line",
        x0=time_col.iloc[0], y0=initial_capital,
        x1=time_col.iloc[-1], y1=initial_capital,
        line=dict(color="rgba(150, 160, 180, 0.5)", width=1, dash="dash"),
        row=1, col=1,
    )

    # 3. Underwater Drawdown Area
    fig.add_trace(
        go.Scatter(
            x=time_col, y=dd_pct,
            name="Drawdown %",
            mode="lines",
            line=dict(color="#ff3b57", width=1),
            fill="tozeroy",
            fillcolor="rgba(255, 59, 87, 0.18)",
            hoverinfo="x+y",
        ), row=2, col=1,
    )

    fig.update_layout(
        paper_bgcolor=paper_bg,
        plot_bgcolor=bg_color,
        font=dict(color=text_color),
        margin=dict(l=20, r=60, t=35, b=20),
        height=height,
        hovermode="x unified",
        legend=dict(orientation="h", y=1.05, x=0.01),
    )
    fig.update_xaxes(showgrid=True, gridcolor=grid_color, color=text_color, rangeslider_visible=False)
    fig.update_yaxes(showgrid=True, gridcolor=grid_color, color=text_color, side="right", row=1, col=1)
    fig.update_yaxes(showgrid=True, gridcolor=grid_color, color=text_color, side="right", row=2, col=1, ticksuffix="%")

    return fig


def create_pnl_distribution_chart(
    trades_df: pd.DataFrame,
    dark_theme: bool = True,
    height: int = 320,
) -> go.Figure:
    """
    Construct high-clarity histogram of trade Net P&L distribution.
    """
    if trades_df.empty or "net_pnl" not in trades_df.columns:
        fig = go.Figure()
        fig.add_annotation(
            text="No closed trades available for distribution",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="#888888"),
        )
        return fig

    pnl = trades_df["net_pnl"].dropna()
    bg_color = "#0c0f17" if dark_theme else "#ffffff"
    paper_bg = "#121520" if dark_theme else "#f8f9fa"
    grid_color = "#1a1f2c" if dark_theme else "#e9ecef"
    text_color = "#d1d4dc" if dark_theme else "#1f2937"

    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    mean_val = float(pnl.mean())

    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=pnl,
            nbinsx=40,
            marker=dict(
                color=["#00c087" if x > 0 else "#ff3b57" for x in pnl],
                line=dict(color=paper_bg, width=0.5),
            ),
            name="Trade Net P&L",
        )
    )

    # Zero Line
    fig.add_vline(x=0.0, line=dict(color="rgba(255, 255, 255, 0.6)", width=1.5, dash="dash"))
    # Mean Line
    fig.add_vline(
        x=mean_val,
        line=dict(color="#f0b90b", width=1.5, dash="dot"),
        annotation_text=f"Mean: ${mean_val:.2f}",
        annotation_position="top left",
    )

    fig.update_layout(
        title=f"Net P&L Distribution ({len(wins)} Wins / {len(losses)} Losses)",
        paper_bgcolor=paper_bg,
        plot_bgcolor=bg_color,
        font=dict(color=text_color),
        margin=dict(l=20, r=40, t=40, b=20),
        height=height,
        xaxis=dict(title="Net P&L ($)", showgrid=True, gridcolor=grid_color, color=text_color),
        yaxis=dict(title="Frequency", showgrid=True, gridcolor=grid_color, color=text_color),
        showlegend=False,
    )
    return fig


def create_trade_outcome_donut(
    trades_df: pd.DataFrame,
    dark_theme: bool = True,
    height: int = 300,
) -> go.Figure:
    """
    Construct donut chart showing exit reason breakdown.
    """
    if trades_df.empty or "exit_reason" not in trades_df.columns:
        fig = go.Figure()
        fig.add_annotation(text="No trades available", showarrow=False)
        return fig

    counts = trades_df["exit_reason"].value_counts()
    colors_map = {
        "TAKE_PROFIT": "#00c087",
        "TAKE_PROFIT_GAP": "#26e7a6",
        "STOP_LOSS": "#ff3b57",
        "STOP_GAP": "#b91c1c",
        "STOP_FIRST_COLLISION": "#f59e0b",
        "TIME_STOP": "#3b82f6",
        "END_OF_DATA": "#8b5cf6",
    }
    colors = [colors_map.get(k, "#64748b") for k in counts.index]

    bg_color = "#0c0f17" if dark_theme else "#ffffff"
    paper_bg = "#121520" if dark_theme else "#f8f9fa"
    text_color = "#d1d4dc" if dark_theme else "#1f2937"

    fig = go.Figure(data=[go.Pie(
        labels=counts.index,
        values=counts.values,
        hole=0.55,
        marker=dict(colors=colors, line=dict(color=paper_bg, width=2)),
        textinfo="label+percent",
        hoverinfo="label+value+percent",
    )])

    fig.update_layout(
        title="Exit Reason Breakdown",
        paper_bgcolor=paper_bg,
        plot_bgcolor=bg_color,
        font=dict(color=text_color),
        margin=dict(l=20, r=20, t=40, b=20),
        height=height,
        showlegend=False,
    )
    return fig


def create_performance_by_session_chart(
    trades_df: pd.DataFrame,
    dark_theme: bool = True,
    height: int = 320,
) -> go.Figure:
    """
    Construct bar chart showing Net P&L and trade counts broken down by trading session.
    """
    if trades_df.empty or "entry_time" not in trades_df.columns or "net_pnl" not in trades_df.columns:
        fig = go.Figure()
        fig.add_annotation(text="No trade time data available", showarrow=False)
        return fig

    df = trades_df.copy()
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["hour"] = df["entry_time"].dt.hour

    def categorize_session(h: int) -> str:
        if 0 <= h < 7: return "Asian (00-07 UTC)"
        elif 7 <= h < 13: return "London (07-13 UTC)"
        elif 13 <= h < 17: return "NY Overlap (13-17 UTC)"
        elif 17 <= h < 21: return "NY Afternoon (17-21 UTC)"
        else: return "Daily Close (21-24 UTC)"

    df["session"] = df["hour"].apply(categorize_session)
    order = [
        "Asian (00-07 UTC)",
        "London (07-13 UTC)",
        "NY Overlap (13-17 UTC)",
        "NY Afternoon (17-21 UTC)",
        "Daily Close (21-24 UTC)",
    ]
    grouped = df.groupby("session")["net_pnl"].agg(["sum", "count"]).reindex(order).fillna(0)

    bg_color = "#0c0f17" if dark_theme else "#ffffff"
    paper_bg = "#121520" if dark_theme else "#f8f9fa"
    grid_color = "#1a1f2c" if dark_theme else "#e9ecef"
    text_color = "#d1d4dc" if dark_theme else "#1f2937"

    bar_colors = ["#00c087" if v >= 0 else "#ff3b57" for v in grouped["sum"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=grouped.index,
        y=grouped["sum"],
        marker=dict(color=bar_colors, line=dict(color=paper_bg, width=1)),
        text=[f"${v:,.0f} ({c}t)" for v, c in zip(grouped["sum"], grouped["count"])],
        textposition="outside",
        hovertext=[
            f"<b>{sess}</b><br>Net P&L: ${v:,.2f}<br>Trades: {int(c)}"
            for sess, v, c in zip(grouped.index, grouped["sum"], grouped["count"])
        ],
        hoverinfo="text",
    ))

    fig.add_hline(y=0.0, line=dict(color="rgba(255, 255, 255, 0.4)", width=1))

    fig.update_layout(
        title="Net P&L by Trading Session",
        paper_bgcolor=paper_bg,
        plot_bgcolor=bg_color,
        font=dict(color=text_color),
        margin=dict(l=20, r=40, t=40, b=20),
        height=height,
        xaxis=dict(showgrid=False, color=text_color),
        yaxis=dict(title="Net P&L ($)", showgrid=True, gridcolor=grid_color, color=text_color),
        showlegend=False,
    )
    return fig


def create_monte_carlo_equity_fan_chart(
    pnls: Sequence[float],
    initial_capital: float = 10000.0,
    n_sims: int = 250,
    seed: int = 42,
    dark_theme: bool = True,
    height: int = 380,
) -> go.Figure:
    """Construct Monte Carlo equity fan chart displaying simulated equity trajectories,
    percentile bands (10th, 50th, 90th), and realized path.
    """
    arr = np.asarray(pnls, dtype=float)
    if len(arr) == 0:
        fig = go.Figure()
        fig.add_annotation(text="No trade records available for Monte Carlo simulation", showarrow=False)
        return fig

    rng = np.random.default_rng(seed)
    n_trades = len(arr)
    sim_indices = rng.integers(0, n_trades, size=(n_sims, n_trades))
    sim_pnls = arr[sim_indices]
    sim_curves = initial_capital + np.cumsum(sim_pnls, axis=1)
    sim_curves = np.column_stack([np.full(n_sims, initial_capital), sim_curves])
    steps = np.arange(n_trades + 1)

    p10 = np.percentile(sim_curves, 10, axis=0)
    p50 = np.percentile(sim_curves, 50, axis=0)
    p90 = np.percentile(sim_curves, 90, axis=0)
    realized_curve = np.concatenate([[initial_capital], initial_capital + np.cumsum(arr)])

    bg_color = "#0c0f17" if dark_theme else "#ffffff"
    paper_bg = "#121520" if dark_theme else "#f8f9fa"
    grid_color = "#1a1f2c" if dark_theme else "#e9ecef"
    text_color = "#d1d4dc" if dark_theme else "#1f2937"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=steps,
        y=p90,
        mode="lines",
        line=dict(color="rgba(16, 185, 129, 0.45)", width=1.5),
        name="90th Pct (Optimistic)",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=steps,
        y=p10,
        mode="lines",
        line=dict(color="rgba(239, 68, 68, 0.45)", width=1.5),
        fill="tonexty",
        fillcolor="rgba(99, 102, 241, 0.12)",
        name="10th Pct (Pessimistic)",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=steps,
        y=p50,
        mode="lines",
        line=dict(color="#60a5fa", width=2, dash="dash"),
        name="Median Simulated Path",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=steps,
        y=realized_curve,
        mode="lines",
        line=dict(color="#f59e0b", width=2.5),
        name="Realized Sequence",
        showlegend=True,
    ))

    fig.update_layout(
        title="Monte Carlo Resampled Equity Paths (Bootstrap Fan Chart)",
        paper_bgcolor=paper_bg,
        plot_bgcolor=bg_color,
        font=dict(color=text_color),
        margin=dict(l=40, r=30, t=40, b=30),
        height=height,
        xaxis=dict(title="Trade Step (N)", showgrid=True, gridcolor=grid_color, color=text_color),
        yaxis=dict(title="Equity ($)", showgrid=True, gridcolor=grid_color, color=text_color),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig
