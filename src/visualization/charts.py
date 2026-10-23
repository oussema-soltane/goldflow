"""
Interactive Financial Visualization Engine for GoldFlow.

Builds high-performance, academic-grade Plotly candlestick charts with:
- Synchronized multi-pane subplots (Price action + Volume).
- Institutional dark styling with explicit UTC timestamp axis.
- Configurable ICT Market Structure overlays:
  * Fractal Swing Highs & Lows (HH, LH, HL, LL)
  * Break of Structure (BOS) & Change of Character (CHoCH)
  * Fair Value Gaps (Bullish & Bearish with Consequent Encroachment)
  * Liquidity Sweeps (Buy-side & Sell-side stop runs)
  * Institutional Order Blocks (Bullish & Bearish OB zones)
"""

from __future__ import annotations

from typing import Any, List, Optional
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
    show_displacements: bool = True,
    show_liquidity_pools: bool = True,
) -> go.Figure:
    """
    Construct an interactive Plotly candlestick chart with volume and optional ICT overlays.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with columns ['time', 'open', 'high', 'low', 'close'] and optional ['tick_volume'].
    symbol : str
        Instrument symbol.
    timeframe : str
        Candle interval ('H4', 'H1', 'M15', 'M5').
    show_volume : bool, default True
        Whether to show volume subplot.
    dark_theme : bool, default True
        Dark styling suitable for technical market structure analysis.
    height : int, default 700
        Chart height in pixels.
    ict_result : ICTAnalysisResult, optional
        Existing ICT result from `analyze_market_structure` to overlay.
    smc_result : SMCAnalysisResult, optional
        Independent pure-SMC analysis result. Do not pass it together with ICT
        if you want the chart to display one methodology at a time.
    show_swings : bool, default True
        Display Swing Highs (HH/LH) and Lows (HL/LL).
    show_structure_breaks : bool, default True
        Display BOS and CHoCH lines and labels.
    show_fvgs : bool, default True
        Display Fair Value Gap boxes and 50% CE lines.
    show_sweeps : bool, default True
        Display Liquidity Sweeps.
    show_order_blocks : bool, default True
        Display Institutional Order Block zones.
    show_displacements : bool, default True
        Display directional displacement candles and their UTC timestamps.

    Returns
    -------
    go.Figure
        Configured Plotly figure.
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

    # Theme colors
    bg_color = "#0e1117" if dark_theme else "#ffffff"
    paper_bg = "#131722" if dark_theme else "#f8f9fa"
    grid_color = "#1e222d" if dark_theme else "#e9ecef"
    text_color = "#d1d4dc" if dark_theme else "#1f2937"
    bull_color = "#089981"  # Institutional green
    bear_color = "#f23645"  # Institutional red
    gold_color = "#f0b90b"  # Gold accent

    has_vol = show_volume and "tick_volume" in df.columns and df["tick_volume"].sum() > 0

    if has_vol:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.78, 0.22],
            specs=[[{"secondary_y": False}], [{"secondary_y": False}]],
        )
    else:
        fig = make_subplots(
            rows=1,
            cols=1,
            specs=[[{"secondary_y": False}]],
        )

    # 1. Candlestick Trace
    candlestick = go.Candlestick(
        x=df["time"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price",
        increasing=dict(line=dict(color=bull_color, width=1), fillcolor=bull_color),
        decreasing=dict(line=dict(color=bear_color, width=1), fillcolor=bear_color),
        showlegend=False,
    )
    fig.add_trace(candlestick, row=1, col=1)

    # 2. Volume Trace (if available)
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

    # 3. ICT Overlays
    if ict_result is not None:
        last_time = df["time"].iloc[-1]

        # 3.0 Directional displacement candles
        displacement_indices = getattr(ict_result, "displacement_indices", [])
        if show_displacements and displacement_indices:
            valid_indices = [i for i in displacement_indices if 0 <= i < len(df)]
            disp_times = [df["time"].iloc[i] for i in valid_indices]
            disp_prices = [float(df["close"].iloc[i]) for i in valid_indices]
            disp_directions = [
                "Bullish" if df["close"].iloc[i] >= df["open"].iloc[i] else "Bearish"
                for i in valid_indices
            ]
            disp_hovers = [
                f"<b>{direction.upper()} DISPLACEMENT</b><br>"
                f"Time: {df['time'].iloc[i].strftime('%Y-%m-%d %H:%M UTC')}<br>"
                f"Open: {df['open'].iloc[i]:.2f}<br>Close: {df['close'].iloc[i]:.2f}<br>"
                f"Body: {abs(float(df['close'].iloc[i]) - float(df['open'].iloc[i])):.2f}"
                for i, direction in zip(valid_indices, disp_directions)
            ]
            fig.add_trace(
                go.Scatter(
                    x=disp_times, y=disp_prices, mode="markers+text",
                    name="Displacement", text=[f"{d} Disp." for d in disp_directions],
                    textposition="top left", hovertext=disp_hovers, hoverinfo="text",
                    marker=dict(symbol="star", size=9, color="#f59e0b"),
                    textfont=dict(size=9, color="#f59e0b"), showlegend=False,
                ), row=1, col=1,
            )

        # 3.1 Order Blocks (Drawn as shaded zones)
        if show_order_blocks and hasattr(ict_result, "order_blocks") and ict_result.order_blocks:
            for ob in ict_result.order_blocks:
                end_x = ob.mitigation_time if (ob.is_mitigated and ob.mitigation_time) else last_time
                ob_color = "rgba(59, 130, 246, 0.18)" if ob.ob_type.value == "BULLISH" else "rgba(239, 68, 68, 0.18)"
                ob_border = "rgba(59, 130, 246, 0.6)" if ob.ob_type.value == "BULLISH" else "rgba(239, 68, 68, 0.6)"
                fig.add_shape(
                    type="rect",
                    x0=ob.candle_time,
                    y0=ob.low,
                    x1=end_x,
                    y1=ob.high,
                    fillcolor=ob_color,
                    line=dict(color=ob_border, width=1, dash="dot"),
                    layer="below",
                    row=1,
                    col=1,
                )

            ob_event_times = [ob.confirmed_time or ob.candle_time for ob in ict_result.order_blocks]
            ob_event_prices = [(ob.high + ob.low) / 2 for ob in ict_result.order_blocks]
            ob_event_texts = [f"{ob.ob_type.value.title()} OB" for ob in ict_result.order_blocks]
            ob_event_hovers = [
                f"<b>{ob.ob_type.value} ORDER BLOCK</b><br>"
                f"Origin candle: {ob.candle_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                f"Confirmed: {(ob.confirmed_time or ob.candle_time).strftime('%Y-%m-%d %H:%M UTC')}<br>"
                f"Zone: {ob.low:.2f}–{ob.high:.2f}<br>"
                f"Mitigated: {ob.is_mitigated}<br>Invalidated: {ob.is_invalidated}"
                + (f"<br>Mitigation: {ob.mitigation_time.strftime('%Y-%m-%d %H:%M UTC')}" if ob.mitigation_time else "")
                + (f"<br>Invalidation: {ob.invalidation_time.strftime('%Y-%m-%d %H:%M UTC')}" if ob.invalidation_time else "")
                for ob in ict_result.order_blocks
            ]
            if ob_event_times:
                fig.add_trace(
                    go.Scatter(
                        x=ob_event_times, y=ob_event_prices, mode="markers+text",
                        name="Order Block Events", text=ob_event_texts, textposition="bottom right",
                        marker=dict(symbol="square", size=5, color="#60a5fa"),
                        hovertext=ob_event_hovers, hoverinfo="text", showlegend=False,
                        textfont=dict(size=9, color="#60a5fa"),
                    ), row=1, col=1,
                )

        # 3.2 Fair Value Gaps (FVG)
        if show_fvgs and hasattr(ict_result, "fvgs") and ict_result.fvgs:
            for fvg in ict_result.fvgs:
                end_x = fvg.mitigation_time if fvg.mitigation_time else last_time
                fvg_color = "rgba(8, 153, 129, 0.18)" if fvg.gap_type.value == "BULLISH" else "rgba(242, 54, 69, 0.18)"
                fvg_border = "rgba(8, 153, 129, 0.5)" if fvg.gap_type.value == "BULLISH" else "rgba(242, 54, 69, 0.5)"
                
                # Gap Rectangle
                fig.add_shape(
                    type="rect",
                    x0=fvg.creation_time,
                    y0=fvg.bottom_price,
                    x1=end_x,
                    y1=fvg.top_price,
                    fillcolor=fvg_color,
                    line=dict(color=fvg_border, width=1),
                    layer="below",
                    row=1,
                    col=1,
                )

                # Consequent Encroachment (50% CE) Line
                fig.add_shape(
                    type="line",
                    x0=fvg.creation_time,
                    y0=fvg.consequent_encroachment,
                    x1=end_x,
                    y1=fvg.consequent_encroachment,
                    line=dict(color=fvg_border, width=1, dash="dot"),
                    layer="below",
                    row=1,
                    col=1,
                )

            # Event markers make FVG creation/confirmation times discoverable on hover.
            fvg_event_times = [f.creation_time for f in ict_result.fvgs]
            fvg_event_prices = [(f.top_price + f.bottom_price) / 2 for f in ict_result.fvgs]
            fvg_event_texts = [f"{f.gap_type.value.title()} FVG" for f in ict_result.fvgs]
            fvg_event_hovers = [
                f"<b>{f.gap_type.value} FVG</b><br>"
                f"Confirmed: {f.creation_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                f"Zone: {f.bottom_price:.2f}–{f.top_price:.2f}<br>"
                f"CE: {f.consequent_encroachment:.2f}<br>"
                f"Size: {f.size:.2f}<br>Status: {f.status.value}"
                + (f"<br>First mitigation: {f.mitigation_time.strftime('%Y-%m-%d %H:%M UTC')}" if f.mitigation_time else "")
                for f in ict_result.fvgs
            ]
            if fvg_event_times:
                fig.add_trace(
                    go.Scatter(
                        x=fvg_event_times, y=fvg_event_prices, mode="markers+text",
                        name="FVG Events", text=fvg_event_texts, textposition="middle right",
                        marker=dict(symbol="circle", size=5, color="#a78bfa"),
                        hovertext=fvg_event_hovers, hoverinfo="text", showlegend=False,
                        textfont=dict(size=9, color="#a78bfa"),
                    ), row=1, col=1,
                )

        # 3.3 Structure Breaks (BOS / CHoCH Lines)
        if show_structure_breaks and hasattr(ict_result, "structure_breaks") and ict_result.structure_breaks:
            for brk in ict_result.structure_breaks:
                brk_color = bull_color if brk.direction.value == "BULLISH" else bear_color
                dash_style = "dash" if brk.break_type.value == "BOS" else "longdash"
                
                # Horizontal line from broken swing time to break time
                fig.add_shape(
                    type="line",
                    x0=brk.broken_swing.time,
                    y0=brk.broken_swing.price,
                    x1=brk.break_time,
                    y1=brk.broken_swing.price,
                    line=dict(color=brk_color, width=1.5, dash=dash_style),
                    row=1,
                    col=1,
                )

                # Text annotation at the break
                label = (
                    f"<b>{brk.break_type.value}</b><br>"
                    f"{brk.break_time.strftime('%Y-%m-%d %H:%M UTC')}"
                )
                fig.add_annotation(
                    x=brk.break_time,
                    y=brk.broken_swing.price,
                    text=label,
                    showarrow=False,
                    font=dict(size=10, color=brk_color),
                    bgcolor=bg_color,
                    bordercolor=brk_color,
                    borderwidth=1,
                    borderpad=2,
                    row=1,
                    col=1,
                )

        # 3.4 Liquidity Sweeps
        if show_sweeps and hasattr(ict_result, "liquidity_sweeps") and ict_result.liquidity_sweeps:
            sweep_times = [sw.sweep_time for sw in ict_result.liquidity_sweeps]
            sweep_prices = [sw.sweep_price for sw in ict_result.liquidity_sweeps]
            sweep_texts = [f"⚡ {sw.sweep_type.value.split('_')[0]} Sweep" for sw in ict_result.liquidity_sweeps]
            sweep_hovers = [
                f"<b>{sw.sweep_type.value.replace('_', ' ')} SWEEP</b><br>"
                f"Time: {sw.sweep_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                f"Liquidity level: {sw.swept_swing.price:.2f}<br>"
                f"Sweep extreme: {sw.sweep_price:.2f}<br>"
                f"Close: {sw.close_price:.2f}<br>"
                f"Wick penetration: {sw.wick_penetration:.2f}"
                for sw in ict_result.liquidity_sweeps
            ]

            fig.add_trace(
                go.Scatter(
                    x=sweep_times,
                    y=sweep_prices,
                    mode="markers+text",
                    name="Liquidity Sweep",
                    marker=dict(symbol="diamond", size=9, color="#ec4899", line=dict(color="#ffffff", width=1)),
                    text=sweep_texts,
                    textposition="top center",
                    textfont=dict(size=10, color="#ec4899"),
                    hovertext=sweep_hovers,
                    hoverinfo="text",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )

        # 3.5 Fractal Swings (Highs & Lows)
        if show_swings and hasattr(ict_result, "swings") and ict_result.swings:
            shs = [s for s in ict_result.swings if s.swing_type.value == "SWING_HIGH"]
            sls = [s for s in ict_result.swings if s.swing_type.value == "SWING_LOW"]

            if shs:
                sh_hovers = [
                    f"<b>Swing High ({s.classification.value})</b><br>"
                    f"Price: ${s.price:,.2f}<br>"
                    f"Formed: {s.time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                    f"Confirmed: {s.confirmed_time.strftime('%Y-%m-%d %H:%M UTC')}"
                    for s in shs
                ]
                fig.add_trace(
                    go.Scatter(
                        x=[s.time for s in shs],
                        y=[s.price for s in shs],
                        mode="markers+text",
                        name="Swing Highs",
                        marker=dict(symbol="triangle-down", size=8, color=gold_color),
                        text=[s.classification.value for s in shs],
                        textposition="top center",
                        textfont=dict(size=10, color=gold_color),
                        hovertext=sh_hovers,
                        hoverinfo="text",
                        showlegend=False,
                    ),
                    row=1,
                    col=1,
                )

            if sls:
                sl_hovers = [
                    f"<b>Swing Low ({s.classification.value})</b><br>"
                    f"Price: ${s.price:,.2f}<br>"
                    f"Formed: {s.time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                    f"Confirmed: {s.confirmed_time.strftime('%Y-%m-%d %H:%M UTC')}"
                    for s in sls
                ]
                fig.add_trace(
                    go.Scatter(
                        x=[s.time for s in sls],
                        y=[s.price for s in sls],
                        mode="markers+text",
                        name="Swing Lows",
                        marker=dict(symbol="triangle-up", size=8, color="#3b82f6"),
                        text=[s.classification.value for s in sls],
                        textposition="bottom center",
                        textfont=dict(size=10, color="#3b82f6"),
                        hovertext=sl_hovers,
                        hoverinfo="text",
                        showlegend=False,
                    ),
                    row=1,
                    col=1,
                )

    # 4. Independent SMC overlays (no ICT-specific FVG/displacement dependency).
    if smc_result is not None:
        last_time = df["time"].iloc[-1]

        if show_order_blocks and getattr(smc_result, "order_blocks", None):
            ob_x, ob_y, ob_text, ob_hover = [], [], [], []
            for ob in smc_result.order_blocks:
                if ob.invalidation_time is not None:
                    end_x = ob.invalidation_time
                elif ob.mitigation_time is not None:
                    end_x = ob.mitigation_time
                else:
                    end_x = last_time
                bullish = ob.direction.value == "BULLISH"
                fill = "rgba(8, 153, 129, 0.16)" if bullish else "rgba(242, 54, 69, 0.16)"
                edge = "rgba(8, 153, 129, 0.75)" if bullish else "rgba(242, 54, 69, 0.75)"
                # Draw only from confirmation time, never backpaint the zone
                # into candles before the structural break made the OB knowable.
                fig.add_shape(
                    type="rect", x0=ob.created_time, y0=ob.low, x1=end_x, y1=ob.high,
                    fillcolor=fill, line=dict(color=edge, width=1, dash="dash"),
                    layer="below", row=1, col=1,
                )
                ob_x.append(ob.created_time)
                ob_y.append((ob.high + ob.low) / 2.0)
                ob_text.append(f"SMC {ob.direction.value.title()} OB")
                ob_hover.append(
                    f"<b>SMC {ob.direction.value} ORDER BLOCK</b><br>"
                    f"Origin candle: {ob.origin_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                    f"Known at break: {ob.created_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                    f"Zone: {ob.low:.2f}–{ob.high:.2f}<br>Status at dataset end: {ob.status.value}"
                )
            if ob_x:
                fig.add_trace(go.Scatter(
                    x=ob_x, y=ob_y, mode="markers+text", name="SMC Order Blocks",
                    text=ob_text, textposition="bottom right", hovertext=ob_hover,
                    hoverinfo="text", marker=dict(symbol="square", size=6, color="#22c55e"),
                    textfont=dict(size=9, color="#22c55e"), showlegend=False,
                ), row=1, col=1)

        if show_structure_breaks and getattr(smc_result, "structure_breaks", None):
            for event in smc_result.structure_breaks:
                bullish = event.direction.value == "BULLISH"
                event_color = bull_color if bullish else bear_color
                dash = "dash" if event.break_type.value == "BOS" else ("longdash" if event.break_type.value == "CHoCH" else "dot")
                fig.add_shape(
                    type="line", x0=event.broken_swing.confirmed_time,
                    y0=event.broken_swing.price, x1=event.break_time,
                    y1=event.broken_swing.price,
                    line=dict(color=event_color, width=1.5, dash=dash), row=1, col=1,
                )
                fig.add_annotation(
                    x=event.break_time, y=event.broken_swing.price,
                    text=f"SMC {event.break_type.value}<br>{event.break_time.strftime('%Y-%m-%d %H:%M UTC')}",
                    showarrow=False, font=dict(size=9, color=event_color), bgcolor=bg_color,
                    bordercolor=event_color, borderwidth=1, borderpad=2, row=1, col=1,
                )

        if show_liquidity_pools and getattr(smc_result, "liquidity_pools", None):
            sweep_by_pool = {id(event.liquidity_pool): event for event in smc_result.liquidity_sweeps}
            for pool in smc_result.liquidity_pools:
                sweep = sweep_by_pool.get(id(pool))
                end_x = sweep.sweep_time if sweep is not None else last_time
                buy_side = pool.liquidity_type.value == "BUY_SIDE"
                pool_color = "rgba(245, 158, 11, 0.90)" if buy_side else "rgba(96, 165, 250, 0.90)"
                fig.add_shape(
                    type="line", x0=pool.created_time, y0=pool.level, x1=end_x, y1=pool.level,
                    line=dict(color=pool_color, width=1.2, dash="dot"), row=1, col=1,
                )

        if show_swings and getattr(smc_result, "swings", None):
            for swing_type, trace_name, symbol, color in (
                ("SWING_HIGH", "SMC Confirmed Swing Highs", "triangle-down", "#f59e0b"),
                ("SWING_LOW", "SMC Confirmed Swing Lows", "triangle-up", "#60a5fa"),
            ):
                pivots = [s for s in smc_result.swings if s.swing_type.value == swing_type]
                if pivots:
                    fig.add_trace(go.Scatter(
                        x=[s.confirmed_time for s in pivots], y=[s.price for s in pivots],
                        mode="markers", name=trace_name,
                        marker=dict(symbol=symbol, size=7, color=color),
                        hovertext=[
                            f"<b>SMC {swing_type.replace('_', ' ')}</b><br>"
                            f"Price: {s.price:.2f}<br>Pivot formed: {s.time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                            f"Knowable from: {s.confirmed_time.strftime('%Y-%m-%d %H:%M UTC')}<br>Classification: {s.classification}"
                            for s in pivots
                        ], hoverinfo="text", showlegend=False,
                    ), row=1, col=1)

        if show_sweeps and getattr(smc_result, "liquidity_sweeps", None):
            sweeps = smc_result.liquidity_sweeps
            fig.add_trace(go.Scatter(
                x=[event.sweep_time for event in sweeps],
                y=[event.sweep_price for event in sweeps],
                mode="markers+text", name="SMC Liquidity Sweeps",
                text=[f"{event.liquidity_type.value.replace('_', ' ').title()} Sweep" for event in sweeps],
                textposition="top center", marker=dict(symbol="diamond", size=9, color="#ec4899"),
                hovertext=[
                    f"<b>SMC {event.liquidity_type.value.replace('_', ' ')} SWEEP</b><br>"
                    f"Pool level: {event.liquidity_pool.level:.2f}<br>"
                    f"Sweep extreme: {event.sweep_price:.2f}<br>Close: {event.close_price:.2f}<br>"
                    f"Penetration: {event.penetration:.2f}<br>"
                    f"Confirmed: {event.sweep_time.strftime('%Y-%m-%d %H:%M UTC')}"
                    for event in sweeps
                ], hoverinfo="text", textfont=dict(size=9, color="#ec4899"), showlegend=False,
            ), row=1, col=1)

    # Date range string for title
    start_str = df["time"].iloc[0].strftime("%Y-%m-%d %H:%M")
    end_str = df["time"].iloc[-1].strftime("%Y-%m-%d %H:%M")
    total_bars = len(df)

    title_text = (
        f"<b>{symbol}</b> — {timeframe} &nbsp;|&nbsp; "
        f"<span style='font-size:12px; color:{text_color}'>{start_str} to {end_str} UTC ({total_bars:,} bars)</span>"
    )

    fig.update_layout(
        title=dict(
            text=title_text,
            x=0.02,
            y=0.97,
            font=dict(size=16, color=text_color),
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
        yaxis=dict(
            title="Price (USD)",
            showgrid=True,
            gridcolor=grid_color,
            gridwidth=1,
            side="right",
            color=text_color,
            tickformat=".2f",
        ),
        margin=dict(l=20, r=60, t=50, b=20),
        height=height,
        hovermode="x unified",
    )

    # Explicitly disable rangeslider across all axes
    fig.update_xaxes(rangeslider_visible=False)

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
