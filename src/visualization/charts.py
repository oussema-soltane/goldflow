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

    # Theme colors
    bg_color = "#0c0f17" if dark_theme else "#ffffff"
    paper_bg = "#121520" if dark_theme else "#f8f9fa"
    grid_color = "#1a1f2c" if dark_theme else "#e9ecef"
    text_color = "#d1d4dc" if dark_theme else "#1f2937"
    bull_color = "#00c087"  # Institutional teal green
    bear_color = "#ff3b57"  # Institutional crimson red
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
            ob_event_times = []
            ob_event_prices = []
            ob_event_texts = []
            ob_event_hovers = []
            for ob in ict_result.order_blocks:
                end_x = ob.mitigation_time if (ob.is_mitigated and ob.mitigation_time) else chart_end
                if end_x < chart_start or ob.candle_time > chart_end:
                    continue
                ob_color = "rgba(59, 130, 246, 0.18)" if ob.ob_type.value == "BULLISH" else "rgba(239, 68, 68, 0.18)"
                ob_border = "rgba(59, 130, 246, 0.6)" if ob.ob_type.value == "BULLISH" else "rgba(239, 68, 68, 0.6)"
                shapes.append(dict(
                    type="rect",
                    x0=max(ob.candle_time, chart_start),
                    y0=ob.low,
                    x1=min(end_x, chart_end),
                    y1=ob.high,
                    fillcolor=ob_color,
                    line=dict(color=ob_border, width=1, dash="dot"),
                    layer="below",
                    xref="x",
                    yref="y",
                ))
                ev_time = ob.confirmed_time or ob.candle_time
                if chart_start <= ev_time <= chart_end:
                    ob_event_times.append(ev_time)
                    ob_event_prices.append((ob.high + ob.low) / 2)
                    ob_event_texts.append(f"{ob.ob_type.value.title()} OB")
                    ob_event_hovers.append(
                        f"<b>{ob.ob_type.value} ORDER BLOCK</b><br>"
                        f"Origin candle: {ob.candle_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Confirmed: {ev_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Zone: {ob.low:.2f}–{ob.high:.2f}<br>"
                        f"Mitigated: {ob.is_mitigated}<br>Invalidated: {ob.is_invalidated}"
                        + (f"<br>Mitigation: {ob.mitigation_time.strftime('%Y-%m-%d %H:%M UTC')}" if ob.mitigation_time else "")
                        + (f"<br>Invalidation: {ob.invalidation_time.strftime('%Y-%m-%d %H:%M UTC')}" if ob.invalidation_time else "")
                    )
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
            fvg_event_times = []
            fvg_event_prices = []
            fvg_event_texts = []
            fvg_event_hovers = []
            for fvg in ict_result.fvgs:
                end_x = fvg.mitigation_time if fvg.mitigation_time else chart_end
                if end_x < chart_start or fvg.creation_time > chart_end:
                    continue
                fvg_color = "rgba(8, 153, 129, 0.18)" if fvg.gap_type.value == "BULLISH" else "rgba(242, 54, 69, 0.18)"
                fvg_border = "rgba(8, 153, 129, 0.5)" if fvg.gap_type.value == "BULLISH" else "rgba(242, 54, 69, 0.5)"
                shapes.append(dict(
                    type="rect",
                    x0=max(fvg.creation_time, chart_start),
                    y0=fvg.bottom_price,
                    x1=min(end_x, chart_end),
                    y1=fvg.top_price,
                    fillcolor=fvg_color,
                    line=dict(color=fvg_border, width=1),
                    layer="below",
                    xref="x",
                    yref="y",
                ))
                shapes.append(dict(
                    type="line",
                    x0=max(fvg.creation_time, chart_start),
                    y0=fvg.consequent_encroachment,
                    x1=min(end_x, chart_end),
                    y1=fvg.consequent_encroachment,
                    line=dict(color=fvg_border, width=1, dash="dot"),
                    layer="below",
                    xref="x",
                    yref="y",
                ))
                if chart_start <= fvg.creation_time <= chart_end:
                    fvg_event_times.append(fvg.creation_time)
                    fvg_event_prices.append((fvg.top_price + fvg.bottom_price) / 2)
                    fvg_event_texts.append(f"{fvg.gap_type.value.title()} FVG")
                    fvg_event_hovers.append(
                        f"<b>{fvg.gap_type.value} FVG</b><br>"
                        f"Confirmed: {fvg.creation_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Zone: {fvg.bottom_price:.2f}–{fvg.top_price:.2f}<br>"
                        f"CE: {fvg.consequent_encroachment:.2f}<br>"
                        f"Size: {fvg.size:.2f}<br>Status: {fvg.status.value}"
                        + (f"<br>First mitigation: {fvg.mitigation_time.strftime('%Y-%m-%d %H:%M UTC')}" if fvg.mitigation_time else "")
                    )
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
                if brk.break_time < chart_start or brk.broken_swing.time > chart_end:
                    continue
                brk_color = bull_color if brk.direction.value == "BULLISH" else bear_color
                dash_style = "dash" if brk.break_type.value == "BOS" else "longdash"
                shapes.append(dict(
                    type="line",
                    x0=max(brk.broken_swing.time, chart_start),
                    y0=brk.broken_swing.price,
                    x1=min(brk.break_time, chart_end),
                    y1=brk.broken_swing.price,
                    line=dict(color=brk_color, width=1.5, dash=dash_style),
                    xref="x",
                    yref="y",
                ))
                if chart_start <= brk.break_time <= chart_end:
                    label = (
                        f"<b>{brk.break_type.value}</b><br>"
                        f"{brk.break_time.strftime('%Y-%m-%d %H:%M UTC')}"
                    )
                    annotations.append(dict(
                        x=brk.break_time,
                        y=brk.broken_swing.price,
                        text=label,
                        showarrow=False,
                        font=dict(size=10, color=brk_color),
                        bgcolor=bg_color,
                        bordercolor=brk_color,
                        borderwidth=1,
                        borderpad=2,
                        xref="x",
                        yref="y",
                    ))

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
        if show_order_blocks and getattr(smc_result, "order_blocks", None):
            ob_x, ob_y, ob_text, ob_hover = [], [], [], []
            for ob in smc_result.order_blocks:
                if ob.invalidation_time is not None:
                    end_x = ob.invalidation_time
                elif ob.mitigation_time is not None:
                    end_x = ob.mitigation_time
                else:
                    end_x = chart_end
                if end_x < chart_start or ob.created_time > chart_end:
                    continue
                bullish = ob.direction.value == "BULLISH"
                fill = "rgba(8, 153, 129, 0.16)" if bullish else "rgba(242, 54, 69, 0.16)"
                edge = "rgba(8, 153, 129, 0.75)" if bullish else "rgba(242, 54, 69, 0.75)"
                # Draw only from confirmation time, never backpaint the zone
                # into candles before the structural break made the OB knowable.
                shapes.append(dict(
                    type="rect",
                    x0=max(ob.created_time, chart_start),
                    y0=ob.low,
                    x1=min(end_x, chart_end),
                    y1=ob.high,
                    fillcolor=fill,
                    line=dict(color=edge, width=1, dash="dash"),
                    layer="below",
                    xref="x",
                    yref="y",
                ))
                marker_time = max(ob.created_time, chart_start)
                if chart_start <= marker_time <= chart_end:
                    ob_x.append(marker_time)
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

        # 4.2 SMC Breaker Blocks (Inverted Order Blocks)
        if show_breakers and getattr(smc_result, "breaker_blocks", None):
            bb_x, bb_y, bb_text, bb_hover = [], [], [], []
            for bb in smc_result.breaker_blocks:
                end_x = bb.invalidation_time if bb.invalidation_time is not None else chart_end
                if end_x < chart_start or bb.created_time > chart_end:
                    continue
                bullish = bb.breaker_type.value == "BULLISH"
                # Bullish Breaker: failed supply -> support (cyan/teal border, dotted)
                # Bearish Breaker: failed demand -> resistance (pink/coral border, dotted)
                if bullish:
                    fill = "rgba(45, 212, 191, 0.12)" if bb.status.value != "INVALIDATED" else "rgba(45, 212, 191, 0.04)"
                    edge = "rgba(45, 212, 191, 0.70)" if bb.status.value != "INVALIDATED" else "rgba(45, 212, 191, 0.25)"
                else:
                    fill = "rgba(244, 114, 182, 0.12)" if bb.status.value != "INVALIDATED" else "rgba(244, 114, 182, 0.04)"
                    edge = "rgba(244, 114, 182, 0.70)" if bb.status.value != "INVALIDATED" else "rgba(244, 114, 182, 0.25)"

                shapes.append(dict(
                    type="rect",
                    x0=max(bb.created_time, chart_start),
                    y0=bb.low,
                    x1=min(end_x, chart_end),
                    y1=bb.high,
                    fillcolor=fill,
                    line=dict(color=edge, width=1, dash="dot"),
                    layer="below",
                    xref="x",
                    yref="y",
                ))
                marker_time = max(bb.created_time, chart_start)
                if chart_start <= marker_time <= chart_end:
                    bb_x.append(marker_time)
                    bb_y.append((bb.high + bb.low) / 2.0)
                    status_short = {"ACTIVE": "open", "TESTED": "tested", "INVALIDATED": "inv"}
                    tag = f"SMC {bb.breaker_type.value.title()} Breaker ({status_short.get(bb.status.value, '')})"
                    bb_text.append(tag)
                    bb_hover.append(
                        f"<b>SMC {bb.breaker_type.value} BREAKER BLOCK</b><br>"
                        f"Inverted at: {bb.created_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Zone: {bb.low:.2f}–{bb.high:.2f}<br>"
                        f"Status: {bb.status.value}"
                        + (f"<br>Retested: {bb.retest_time.strftime('%Y-%m-%d %H:%M UTC')}" if bb.retest_time else "")
                        + (f"<br>Invalidated: {bb.invalidation_time.strftime('%Y-%m-%d %H:%M UTC')}" if bb.invalidation_time else "")
                    )
            if bb_x:
                fig.add_trace(go.Scatter(
                    x=bb_x, y=bb_y, mode="markers+text", name="SMC Breaker Blocks",
                    text=bb_text, textposition="top right", hovertext=bb_hover,
                    hoverinfo="text", marker=dict(symbol="diamond", size=5, color="#f472b6"),
                    textfont=dict(size=8, color="#a78bfa"), showlegend=False,
                ), row=1, col=1)

        if show_structure_breaks and getattr(smc_result, "structure_breaks", None):
            for event in smc_result.structure_breaks:
                if event.break_time < chart_start or event.broken_swing.confirmed_time > chart_end:
                    continue
                bullish = event.direction.value == "BULLISH"
                event_color = bull_color if bullish else bear_color
                dash = "dash" if event.break_type.value == "BOS" else ("longdash" if event.break_type.value == "CHoCH" else "dot")
                shapes.append(dict(
                    type="line",
                    x0=max(event.broken_swing.confirmed_time, chart_start),
                    y0=event.broken_swing.price,
                    x1=min(event.break_time, chart_end),
                    y1=event.broken_swing.price,
                    line=dict(color=event_color, width=1.5, dash=dash),
                    xref="x",
                    yref="y",
                ))
                if chart_start <= event.break_time <= chart_end:
                    annotations.append(dict(
                        x=event.break_time,
                        y=event.broken_swing.price,
                        text=f"SMC {event.break_type.value}<br>{event.break_time.strftime('%Y-%m-%d %H:%M UTC')}",
                        showarrow=False,
                        font=dict(size=9, color=event_color),
                        bgcolor=bg_color,
                        bordercolor=event_color,
                        borderwidth=1,
                        borderpad=2,
                        xref="x",
                        yref="y",
                    ))

        # 4.5 SMC Fair Value Gaps — independent of ICT FVG/displacement logic.
        if show_fvgs and getattr(smc_result, "fair_value_gaps", None):
            fvg_label_x, fvg_label_y, fvg_label_text, fvg_label_hover = [], [], [], []
            for fvg in smc_result.fair_value_gaps:
                end_x = fvg.closed_time if fvg.closed_time is not None else chart_end
                if end_x < chart_start or fvg.creation_time > chart_end:
                    continue
                bullish_fvg = fvg.fvg_type.value == "BULLISH"
                if bullish_fvg:
                    zone_fill = "rgba(8, 153, 129, 0.14)"
                    zone_edge = "rgba(8, 153, 129, 0.55)"
                    ce_color = "rgba(8, 153, 129, 0.70)"
                else:
                    zone_fill = "rgba(242, 54, 69, 0.14)"
                    zone_edge = "rgba(242, 54, 69, 0.55)"
                    ce_color = "rgba(242, 54, 69, 0.70)"
                # Dim closed FVGs
                if fvg.status.value == "CLOSED":
                    zone_fill = zone_fill.replace("0.14", "0.05")
                    zone_edge = zone_edge.replace("0.55", "0.18")
                # Draw gap zone rectangle
                shapes.append(dict(
                    type="rect",
                    x0=max(fvg.creation_time, chart_start),
                    y0=fvg.bottom,
                    x1=min(end_x, chart_end),
                    y1=fvg.top,
                    fillcolor=zone_fill,
                    line=dict(color=zone_edge, width=1),
                    layer="below",
                    xref="x",
                    yref="y",
                ))
                # CE (50%) midpoint line
                shapes.append(dict(
                    type="line",
                    x0=max(fvg.creation_time, chart_start),
                    y0=fvg.midpoint,
                    x1=min(end_x, chart_end),
                    y1=fvg.midpoint,
                    line=dict(color=ce_color, width=1, dash="dot"),
                    xref="x",
                    yref="y",
                ))
                marker_time = max(fvg.creation_time, chart_start)
                if chart_start <= marker_time <= chart_end:
                    status_tag = {"OPEN": "open", "PARTIAL": "partial", "CLOSED": "✓filled"}
                    fvg_label_x.append(marker_time)
                    fvg_label_y.append(fvg.midpoint)
                    fvg_label_text.append("BFVG" if bullish_fvg else "SFVG")
                    fvg_label_hover.append(
                        f"<b>SMC {'BULLISH' if bullish_fvg else 'BEARISH'} FVG</b><br>"
                        f"Zone: {fvg.bottom:.2f} – {fvg.top:.2f}<br>"
                        f"CE (50%): {fvg.midpoint:.2f}<br>"
                        f"Size: {fvg.size:.2f} pts<br>"
                        f"Created: {fvg.creation_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Status: {fvg.status.value}"
                        + (f"<br>First touch: {fvg.first_touch_time.strftime('%Y-%m-%d %H:%M UTC')}" if fvg.first_touch_time else "")
                        + (f"<br>CE reached: {fvg.ce_time.strftime('%Y-%m-%d %H:%M UTC')}" if fvg.ce_time else "")
                        + (f"<br>Closed: {fvg.closed_time.strftime('%Y-%m-%d %H:%M UTC')}" if fvg.closed_time else "")
                    )
            if fvg_label_x:
                fvg_colors = [
                    "rgba(8,153,129,0.85)" if "BFVG" in t else "rgba(242,54,69,0.85)"
                    for t in fvg_label_text
                ]
                fig.add_trace(go.Scatter(
                    x=fvg_label_x, y=fvg_label_y,
                    mode="markers+text", name="SMC FVGs",
                    text=fvg_label_text,
                    textposition="middle right",
                    marker=dict(symbol="circle", size=5, color=fvg_colors),
                    hovertext=fvg_label_hover, hoverinfo="text",
                    textfont=dict(size=8, color="#888888"),
                    showlegend=False,
                ), row=1, col=1)

        if show_liquidity_pools and getattr(smc_result, "liquidity_pools", None):
            sweep_by_pool = {id(event.liquidity_pool): event for event in smc_result.liquidity_sweeps}
            pool_label_x: list = []
            pool_label_y: list = []
            pool_label_text: list = []
            pool_label_hover: list = []
            for pool in smc_result.liquidity_pools:
                sweep = sweep_by_pool.get(id(pool))
                is_swept = sweep is not None
                end_x = sweep.sweep_time if is_swept else chart_end
                if end_x < chart_start or pool.created_time > chart_end:
                    continue
                buy_side = pool.liquidity_type.value == "BUY_SIDE"
                # Zone rectangle: fills the tolerance band around the pool level.
                tol = float(pool.tolerance)
                zone_top = pool.level + tol
                zone_bot = pool.level - tol
                if buy_side:
                    # BSL: amber zone, dimmed if swept
                    fill = "rgba(245, 158, 11, 0.10)" if is_swept else "rgba(245, 158, 11, 0.18)"
                    edge = "rgba(245, 158, 11, 0.40)" if is_swept else "rgba(245, 158, 11, 0.75)"
                    line_color = "rgba(245, 158, 11, 0.65)" if is_swept else "rgba(245, 158, 11, 0.90)"
                else:
                    # SSL: blue zone, dimmed if swept
                    fill = "rgba(96, 165, 250, 0.10)" if is_swept else "rgba(96, 165, 250, 0.18)"
                    edge = "rgba(96, 165, 250, 0.40)" if is_swept else "rgba(96, 165, 250, 0.75)"
                    line_color = "rgba(96, 165, 250, 0.65)" if is_swept else "rgba(96, 165, 250, 0.90)"
                # Rectangle zone
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
                # Central midline at exact pool level
                shapes.append(dict(
                    type="line",
                    x0=max(pool.created_time, chart_start),
                    y0=pool.level,
                    x1=min(end_x, chart_end),
                    y1=pool.level,
                    line=dict(color=line_color, width=1.2, dash="dot"),
                    xref="x",
                    yref="y",
                ))
                marker_time = max(pool.created_time, chart_start)
                if chart_start <= marker_time <= chart_end:
                    label_type = "BSL" if buy_side else "SSL"
                    status_tag = " ✓swept" if is_swept else ""
                    pool_label_x.append(marker_time)
                    pool_label_y.append(pool.level)
                    pool_label_text.append(f"{label_type}{status_tag}")
                    pool_label_hover.append(
                        f"<b>SMC {pool.liquidity_type.value.replace('_', ' ')} POOL</b><br>"
                        f"Level: {pool.level:.2f} ± {tol:.2f}<br>"
                        f"Formed: {pool.created_time.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"Swept: {'Yes — ' + sweep.sweep_time.strftime('%Y-%m-%d %H:%M UTC') if is_swept else 'No'}"
                    )
            if pool_label_x:
                fig.add_trace(go.Scatter(
                    x=pool_label_x, y=pool_label_y,
                    mode="markers+text", name="SMC Liquidity Pools",
                    text=pool_label_text,
                    textposition="top right",
                    marker=dict(symbol="line-ew", size=10,
                                color=["rgba(245,158,11,0.9)" if "BSL" in t else "rgba(96,165,250,0.9)"
                                       for t in pool_label_text]),
                    hovertext=pool_label_hover, hoverinfo="text",
                    textfont=dict(size=8, color="#aaaaaa"),
                    showlegend=False,
                ), row=1, col=1)

        if show_swings and getattr(smc_result, "swings", None):
            for swing_type, trace_name, symbol, color in (
                ("SWING_HIGH", "SMC Confirmed Swing Highs", "triangle-down", "#f59e0b"),
                ("SWING_LOW", "SMC Confirmed Swing Lows", "triangle-up", "#60a5fa"),
            ):
                pivots = [
                    s for s in smc_result.swings
                    if s.swing_type.value == swing_type and chart_start <= s.confirmed_time <= chart_end
                ]
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
            sweeps = [
                event for event in smc_result.liquidity_sweeps
                if chart_start <= event.sweep_time <= chart_end
            ]
            if sweeps:
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

        # 4.6 SMC Dealing Range (High, Low, 50% Equilibrium)
        if show_dealing_range and smc_result is not None:
            eq = getattr(smc_result, "equilibrium", None)
            dr_high = getattr(smc_result, "dealing_range_high", None)
            dr_low = getattr(smc_result, "dealing_range_low", None)
            if eq is not None and dr_high is not None and dr_low is not None:
                shapes.append(dict(
                    type="line", x0=chart_start, y0=dr_high, x1=chart_end, y1=dr_high,
                    line=dict(color="rgba(245, 158, 11, 0.65)", width=1.2, dash="dash"),
                    xref="x", yref="y",
                ))
                shapes.append(dict(
                    type="line", x0=chart_start, y0=dr_low, x1=chart_end, y1=dr_low,
                    line=dict(color="rgba(96, 165, 250, 0.65)", width=1.2, dash="dash"),
                    xref="x", yref="y",
                ))
                shapes.append(dict(
                    type="line", x0=chart_start, y0=eq, x1=chart_end, y1=eq,
                    line=dict(color="rgba(220, 225, 235, 0.75)", width=1.2, dash="dot"),
                    xref="x", yref="y",
                ))

    # 5. Strategy Trade Executions Overlay
    if show_trades and trades is not None:
        tdf = pd.DataFrame(trades) if isinstance(trades, list) else trades.copy()
        if not tdf.empty and "entry_time" in tdf.columns:
            tdf["entry_time"] = pd.to_datetime(tdf["entry_time"], utc=True)
            chart_start = pd.to_datetime(df["time"].iloc[0], utc=True)
            chart_end = pd.to_datetime(df["time"].iloc[-1], utc=True)
            mask = (tdf["entry_time"] >= chart_start) & (tdf["entry_time"] <= chart_end)
            w_trades = tdf[mask]

            if not w_trades.empty:
                # Long entries
                long_mask = w_trades["side"] == "LONG" if "side" in w_trades.columns else w_trades.get("direction") == "LONG"
                longs = w_trades[long_mask] if long_mask is not None else pd.DataFrame()
                if not longs.empty:
                    long_hovers = [
                        f"<b>🟢 LONG ENTRY</b><br>"
                        f"ID: {r.get('setup_id', 'N/A')}<br>"
                        f"Entry: ${float(r['entry_price']):.2f}<br>"
                        f"Time: {r['entry_time'].strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"SL: ${float(r.get('stop_loss', 0)):.2f} | TP: ${float(r.get('take_profit', 0)):.2f}<br>"
                        f"Lots: {float(r.get('lots', 0)):.2f}<br>"
                        f"Net P&L: ${float(r.get('net_pnl', 0)):.2f} (R: {float(r.get('R_multiple', 0)):.2f})<br>"
                        f"Exit: {r.get('exit_reason', 'OPEN')}"
                        for _, r in longs.iterrows()
                    ]
                    fig.add_trace(go.Scatter(
                        x=longs["entry_time"], y=longs["entry_price"], mode="markers",
                        name="Trade Entry (Long)",
                        marker=dict(symbol="triangle-up", size=12, color="#00c087", line=dict(color="#ffffff", width=1.5)),
                        hovertext=long_hovers, hoverinfo="text", showlegend=False,
                    ), row=1, col=1)

                # Short entries
                short_mask = w_trades["side"] == "SHORT" if "side" in w_trades.columns else w_trades.get("direction") == "SHORT"
                shorts = w_trades[short_mask] if short_mask is not None else pd.DataFrame()
                if not shorts.empty:
                    short_hovers = [
                        f"<b>🔴 SHORT ENTRY</b><br>"
                        f"ID: {r.get('setup_id', 'N/A')}<br>"
                        f"Entry: ${float(r['entry_price']):.2f}<br>"
                        f"Time: {r['entry_time'].strftime('%Y-%m-%d %H:%M UTC')}<br>"
                        f"SL: ${float(r.get('stop_loss', 0)):.2f} | TP: ${float(r.get('take_profit', 0)):.2f}<br>"
                        f"Lots: {float(r.get('lots', 0)):.2f}<br>"
                        f"Net P&L: ${float(r.get('net_pnl', 0)):.2f} (R: {float(r.get('R_multiple', 0)):.2f})<br>"
                        f"Exit: {r.get('exit_reason', 'OPEN')}"
                        for _, r in shorts.iterrows()
                    ]
                    fig.add_trace(go.Scatter(
                        x=shorts["entry_time"], y=shorts["entry_price"], mode="markers",
                        name="Trade Entry (Short)",
                        marker=dict(symbol="triangle-down", size=12, color="#ff3b57", line=dict(color="#ffffff", width=1.5)),
                        hovertext=short_hovers, hoverinfo="text", showlegend=False,
                    ), row=1, col=1)

                # Exits & SL/TP lines
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
                                hovertext=[f"<b>WIN EXIT</b><br>ID: {r.get('setup_id', 'N/A')}<br>Exit: ${float(r.get('exit_price', 0)):.2f}<br>Net: +${float(r.get('net_pnl', 0)):.2f}<br>Reason: {r.get('exit_reason', 'N/A')}" for _, r in win_exits.iterrows()],
                                hoverinfo="text", showlegend=False,
                            ), row=1, col=1)
                        if not loss_exits.empty:
                            fig.add_trace(go.Scatter(
                                x=loss_exits["exit_time"], y=loss_exits["exit_price"], mode="markers",
                                name="Exit (Loss)",
                                marker=dict(symbol="x", size=8, color="#ff3b57", line=dict(color="#ffffff", width=1.5)),
                                hovertext=[f"<b>LOSS EXIT</b><br>ID: {r.get('setup_id', 'N/A')}<br>Exit: ${float(r.get('exit_price', 0)):.2f}<br>Net: ${float(r.get('net_pnl', 0)):.2f}<br>Reason: {r.get('exit_reason', 'N/A')}" for _, r in loss_exits.iterrows()],
                                hoverinfo="text", showlegend=False,
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
        shapes=shapes,
        annotations=annotations,
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
