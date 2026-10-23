"""
GoldFlow — Market Analysis, Data Quality & ICT Market Structure Engine
Phase 2: MT5 Ingestion, Quality Audit & Institutional Market Structure Analytics
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import json

import pandas as pd
import streamlit as st

from src.data.cleaner import clean_market_data, save_processed_data
from src.data.loader import (
    check_mt5_status,
    discover_gold_symbols,
    fetch_historical_bars,
    generate_synthetic_gold_data,
    load_local_data,
    save_raw_data,
    shutdown_mt5,
)
from src.data.validator import validate_market_data
from src.ict.engine import analyze_market_structure
from src.smc.engine import SMCConfig, analyze_smc
from src.strategy.smc_setups import SMCSetupConfig, detect_smc_setup_candidates
from src.visualization.charts import create_candlestick_chart

st.set_page_config(page_title="GoldFlow — SMC Primary & ICT Analysis", page_icon="📈", layout="wide")

st.title("📈 GoldFlow — SMC Primary / ICT Secondary")
st.caption(
    "Analyze XAU/USD market structure with a standalone Smart Money Concepts engine as the default framework, "
    "while preserving the existing ICT engine as a separate selectable analysis mode."
)

# Initialize session state for cached data
if "current_df" not in st.session_state:
    st.session_state["current_df"] = None
if "current_meta" not in st.session_state:
    st.session_state["current_meta"] = None
if "current_report" not in st.session_state:
    st.session_state["current_report"] = None
if "current_source" not in st.session_state:
    st.session_state["current_source"] = None
if "loaded_at" not in st.session_state:
    st.session_state["loaded_at"] = None

# --- SIDEBAR CONTROLS ---
st.sidebar.header("🛠️ Data Pipeline Controls")

# 1. MT5 Terminal Status Widget
mt5_status = check_mt5_status()
if mt5_status["connected"]:
    st.sidebar.success(f"🟢 MT5 Connected: {mt5_status['account_info']['server']}")
    st.sidebar.caption(f"Account #{mt5_status['account_info']['login']} (Demo)")
else:
    st.sidebar.warning("🔴 MT5 Terminal Offline")
    st.sidebar.caption("Open MT5 desktop & log into your Demo account.")

if st.sidebar.button("🔄 Refresh MT5 Connection"):
    st.rerun()

st.sidebar.markdown("---")

# 2. Ingestion Source Selector
data_source = st.sidebar.radio(
    "Data Source Mode",
    options=["Live MT5 Terminal", "Existing Processed CSV", "Synthetic Benchmark (Offline)"],
    index=1 if not mt5_status["connected"] else 0,
)

# 3. Symbol Selection
gold_candidates = []
if mt5_status["connected"]:
    gold_candidates = discover_gold_symbols()

candidate_names = [s["name"] for s in gold_candidates] if gold_candidates else ["XAUUSD", "GOLD", "XAUUSD.a"]

if data_source == "Live MT5 Terminal":
    if not mt5_status["connected"]:
        st.sidebar.error("Live MT5 extraction requires an active terminal connection. Switch to Existing CSV or Synthetic mode, or open MT5.")
    selected_symbol = st.sidebar.selectbox("Broker Gold Symbol", options=candidate_names, index=0)
    st.sidebar.caption(
        "Broker symbols differ (e.g. XAUUSD vs GOLD vs XAUUSD.a). Verify in your Market Watch."
    )
elif data_source == "Existing Processed CSV":
    processed_dir = Path("data/processed")
    csv_files = list(processed_dir.glob("*.csv")) if processed_dir.exists() else []
    if csv_files:
        chosen_file = st.sidebar.selectbox("Select Dataset", options=[f.name for f in csv_files])
        parts = chosen_file.split("_")
        selected_symbol = parts[0]
        # Auto-detect timeframe from filename pattern (e.g. XAUUSD_H1_clean.csv -> H1)
        detected_tf = parts[1] if len(parts) > 1 and parts[1] in ["M5", "M15", "H1", "H4"] else None
    else:
        st.sidebar.info("No processed CSVs found yet. Run synthetic ingestion or connect MT5.")
        selected_symbol = "XAUUSD"
        chosen_file = None
        detected_tf = None
else:
    selected_symbol = st.sidebar.text_input("Symbol Name", value="XAUUSD")
    detected_tf = None

# 4. Timeframe Hierarchy
tf_options = ["M15", "M5", "H1", "H4"]
tf_default_idx = tf_options.index(detected_tf) if (data_source == "Existing Processed CSV" and detected_tf in tf_options) else 0

selected_tf = st.sidebar.selectbox(
    "Timeframe",
    options=tf_options,
    index=tf_default_idx,
    help="Higher-timeframe context: H4/H1 | Setup analysis: M15/M5",
)

# 5. Bar Count
n_bars = st.sidebar.slider("Number of Candles", min_value=100, max_value=5000, value=1500, step=100)

# 6. Explicit timestamp interpretation for live MT5 data
timestamp_mode = "posix_utc"
server_timezone = None
timestamp_mode_verified = False
if data_source == "Live MT5 Terminal":
    with st.sidebar.expander("🕒 Timestamp Integrity", expanded=True):
        timestamp_mode = st.selectbox(
            "MT5 timestamp interpretation",
            options=["posix_utc", "server_wall_clock"],
            index=0,
            help=(
                "Default follows the official MT5 UTC timestamp convention. "
                "Choose server_wall_clock only after the live diagnostic supports it."
            ),
        )
        if timestamp_mode == "server_wall_clock":
            server_timezone = st.text_input(
                "Verified IANA server timezone",
                value="",
                placeholder="e.g. Europe/Athens",
                help="Enter only after confirming the server's historical timezone/DST rules.",
            ).strip() or None
        timestamp_mode_verified = st.checkbox(
            "I ran the live timestamp diagnostic and verified this mode",
            value=False,
            help="Without this confirmation, GoldFlow keeps research readiness blocked.",
        )

# Fetch Data Button
c_load, c_reset = st.sidebar.columns([3, 2])
load_btn = c_load.button("📥 Load Data", type="primary")
reset_btn = c_reset.button("🗑️ Reset")

if reset_btn:
    st.session_state["current_df"] = None
    st.session_state["current_meta"] = None
    st.session_state["current_report"] = None
    st.session_state["current_source"] = None
    st.session_state["loaded_at"] = None
    st.rerun()

st.sidebar.markdown("---")

# 7. Primary market-analysis framework and separate engine settings
analysis_framework = st.sidebar.radio(
    "Primary Analysis Framework",
    ["SMC (Primary)", "ICT (Existing)"],
    index=0,
    help="SMC and ICT are implemented as separate engines. SMC is the default; switch to ICT to use the existing ICT-specific analysis.",
)

# Shared defaults keep inactive-framework arguments well-defined.
enable_smc = False
enable_ict = False
smc_swing_window = 2
smc_equal_level_tolerance = 0.50
smc_min_sweep_penetration = 0.0
smc_order_block_lookback = 5
smc_order_block_zone_basis = "wick"
smc_track_lifecycle = True
smc_max_sweep_to_choch_bars = 20
smc_max_choch_to_retest_bars = 20
smc_stop_buffer = 0.50
smc_fixed_rr = 2.0
smc_use_liquidity_target = True
smc_require_premium_discount = False
show_smc_swings = True
show_smc_breaks = True
show_smc_pools = True
show_smc_sweeps = True
show_smc_obs = True
swing_window = 2
break_mode = "Candle Close (Institutional)"
min_fvg_gap = 0.5
displacement_atr_period = 14
displacement_multiplier = 1.5
displacement_body_ratio = 0.6
track_mitigation = True
show_swings = True
show_breaks = True
show_fvgs = True
show_sweeps = True
show_obs = True
show_displacements = True

if analysis_framework == "SMC (Primary)":
    with st.sidebar.expander("🧭 Pure SMC Settings", expanded=True):
        enable_smc = st.checkbox("Enable SMC Engine", value=True)
        smc_swing_window = st.slider("Swing Confirmation Window", min_value=1, max_value=5, value=2,
                                     help="Bars required on each side. A pivot becomes actionable only after confirmation.")
        smc_equal_level_tolerance = st.number_input("Equal High/Low Tolerance ($)", min_value=0.0, max_value=20.0,
                                                    value=0.50, step=0.05,
                                                    help="Absolute XAUUSD price-distance allowed between two confirmed pivots to form a liquidity pool.")
        smc_min_sweep_penetration = st.number_input("Minimum Sweep Penetration ($)", min_value=0.0, max_value=20.0,
                                                    value=0.0, step=0.05)
        smc_order_block_lookback = st.slider("Order Block Search Bars", min_value=1, max_value=20, value=5)
        smc_order_block_zone_basis = st.radio("Order Block Zone", ["wick", "body"], index=0,
                                               help="wick uses the full candle high/low; body uses open/close bounds.")
        smc_track_lifecycle = st.checkbox("Track OB Mitigation/Invalidation", value=True)
        st.markdown("**SMC Setup Hypothesis: Sweep → CHoCH → OB Retest**")
        smc_max_sweep_to_choch_bars = st.slider("Max Bars: Sweep to CHoCH", min_value=1, max_value=100, value=20)
        smc_max_choch_to_retest_bars = st.slider("Max Bars: CHoCH to OB Retest", min_value=1, max_value=100, value=20)
        smc_stop_buffer = st.number_input("Stop Buffer Beyond Sweep ($)", min_value=0.0, max_value=50.0, value=0.50, step=0.05)
        smc_fixed_rr = st.number_input("Fallback Risk:Reward", min_value=0.25, max_value=10.0, value=2.0, step=0.25)
        smc_use_liquidity_target = st.checkbox("Use Opposing Liquidity Target When Available", value=True)
        smc_require_premium_discount = st.checkbox("Require Discount for Long / Premium for Short", value=False)
        st.markdown("**SMC Chart Overlays**")
        show_smc_swings = st.checkbox("Confirmed Swing Highs/Lows", value=True)
        show_smc_breaks = st.checkbox("BOS / CHoCH / Initial Breaks", value=True)
        show_smc_pools = st.checkbox("Equal High/Low Liquidity Pools", value=True)
        show_smc_sweeps = st.checkbox("Liquidity Sweeps", value=True)
        show_smc_obs = st.checkbox("SMC Order Blocks", value=True)
else:
    with st.sidebar.expander("🏛️ Existing ICT Settings", expanded=True):
        enable_ict = st.checkbox("Enable ICT Engine", value=True)
        swing_window = st.slider("Swing Window (Fractal k)", min_value=1, max_value=5, value=2,
                                 help="Bars required on each side to confirm a swing peak/trough.")
        break_mode = st.radio("Break Rule", ["Candle Close (Institutional)", "Wick Penetration"], index=0)
        min_fvg_gap = st.number_input("Min FVG Gap (pts)", min_value=0.0, max_value=10.0, value=0.5, step=0.1)
        displacement_atr_period = st.slider("Displacement ATR Period", min_value=2, max_value=50, value=14)
        displacement_multiplier = st.slider("Displacement Body / ATR", min_value=0.5, max_value=4.0, value=1.5, step=0.1)
        displacement_body_ratio = st.slider("Min Displacement Body / Range", min_value=0.1, max_value=1.0, value=0.6, step=0.05)
        track_mitigation = st.checkbox("Track Forward Mitigation", value=True)
        st.markdown("**ICT Chart Overlays**")
        show_swings = st.checkbox("Swing Highs/Lows (HH/LH/HL/LL)", value=True)
        show_breaks = st.checkbox("BOS & CHoCH Lines", value=True)
        show_fvgs = st.checkbox("Fair Value Gaps (FVG)", value=True)
        show_sweeps = st.checkbox("Liquidity Sweeps (⚡)", value=True)
        show_obs = st.checkbox("Order Blocks (OB)", value=True)
        show_displacements = st.checkbox("Displacement Candles (★)", value=True)

# Execute Data Ingestion / Loading
if load_btn or st.session_state["current_df"] is None:
    with st.spinner("Retrieving and auditing market data..."):
        df_raw = None
        meta = None
        raw_saved_path = None

        if data_source == "Live MT5 Terminal":
            if not mt5_status["connected"]:
                st.error("Cannot fetch live bars: MT5 is disconnected. Please open MetaTrader 5 desktop.")
            else:
                try:
                    df_raw, meta = fetch_historical_bars(
                        symbol=selected_symbol,
                        timeframe=selected_tf,
                        n_bars=n_bars,
                        exclude_incomplete=True,
                        timestamp_mode=timestamp_mode,
                        server_timezone=server_timezone,
                        timestamp_mode_verified=timestamp_mode_verified,
                    )
                    raw_saved_path = save_raw_data(df_raw, selected_symbol, selected_tf)
                except Exception as exc:
                    st.error(f"Failed to fetch data from MT5: {exc}")

        elif data_source == "Existing Processed CSV":
            if chosen_file:
                target_path = Path("data/processed") / chosen_file
                df_raw = load_local_data(target_path)
                raw_saved_path = None
                # Locate sidecar: e.g., XAUUSD_H1_clean.meta.json
                sidecar_candidates = [
                    target_path.with_suffix(".meta.json"),
                    target_path.parent / f"{target_path.stem}.meta.json",
                    target_path.with_name(f"{chosen_file}.meta.json"),
                ]
                sidecar_to_read = next((p for p in sidecar_candidates if p.is_file()), None)
                meta = {
                    "symbol": selected_symbol,
                    "timeframe": selected_tf,
                    "source": str(target_path),
                    "is_synthetic": False,
                }
                if sidecar_to_read and sidecar_to_read.exists():
                    try:
                        with open(sidecar_to_read, "r", encoding="utf-8") as mf:
                            sidecar_data = json.load(mf)
                            meta.update(sidecar_data)
                    except Exception:
                        pass
            else:
                df_raw, meta = generate_synthetic_gold_data(
                    symbol=selected_symbol, timeframe=selected_tf, n_bars=n_bars
                )
                raw_saved_path = save_raw_data(df_raw, selected_symbol, selected_tf)

        else:  # Synthetic benchmark
            df_raw, meta = generate_synthetic_gold_data(
                symbol=selected_symbol, timeframe=selected_tf, n_bars=n_bars
            )
            raw_saved_path = save_raw_data(df_raw, selected_symbol, selected_tf)

        if df_raw is not None and not df_raw.empty:
            # Audit Quality
            report = validate_market_data(df_raw, symbol=selected_symbol, timeframe=selected_tf)
            # Clean and persist with provenance sidecar
            df_clean, audit = clean_market_data(df_raw, symbol=selected_symbol, timeframe=selected_tf)
            if data_source != "Existing Processed CSV":
                clean_path, meta_path = save_processed_data(
                    df_clean,
                    selected_symbol,
                    selected_tf,
                    raw_source_path=raw_saved_path,
                    audit_log=audit,
                    source_metadata=meta,
                )
            
            # Save reports
            report.save_json("reports/data_quality_report.json")
            report.save_markdown("reports/data_quality_report.md")

            st.session_state["current_df"] = df_clean
            st.session_state["current_meta"] = meta
            st.session_state["current_report"] = report
            st.session_state["current_source"] = data_source
            st.session_state["loaded_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# --- MAIN PANEL VISUALIZATION & AUDIT ---
df = st.session_state["current_df"]
report = st.session_state["current_report"]
meta = st.session_state["current_meta"]
src_used = st.session_state.get("current_source", "Unknown")
load_time = st.session_state.get("loaded_at", "N/A")

if df is not None and not df.empty and report is not None:
    # Run only the selected primary framework. SMC and ICT remain independent.
    ict_res = None
    smc_res = None
    if analysis_framework == "SMC (Primary)" and enable_smc:
        smc_res = analyze_smc(
            df=df,
            symbol=report.symbol,
            timeframe=report.timeframe,
            config=SMCConfig(
                swing_window=smc_swing_window,
                equal_level_tolerance=smc_equal_level_tolerance,
                min_sweep_penetration=smc_min_sweep_penetration,
                order_block_lookback=smc_order_block_lookback,
                order_block_zone_basis=smc_order_block_zone_basis,
                track_order_block_lifecycle=smc_track_lifecycle,
            ),
        )
    elif analysis_framework == "ICT (Existing)" and enable_ict:
        ict_res = analyze_market_structure(
            df=df,
            symbol=report.symbol,
            timeframe=report.timeframe,
            swing_window=swing_window,
            break_on_close=(break_mode.startswith("Candle Close")),
            min_gap_points=min_fvg_gap,
            track_mitigation=track_mitigation,
            displacement_atr_period=displacement_atr_period,
            displacement_multiplier=displacement_multiplier,
            displacement_min_body_ratio=displacement_body_ratio,
        )
    active_res = smc_res if smc_res is not None else ict_res
    smc_setup_candidates = []
    if smc_res is not None:
        smc_setup_candidates = detect_smc_setup_candidates(
            df,
            smc_res,
            SMCSetupConfig(
                max_sweep_to_choch_bars=smc_max_sweep_to_choch_bars,
                max_bars_choch_to_retest=smc_max_choch_to_retest_bars,
                stop_buffer=smc_stop_buffer,
                fixed_rr=smc_fixed_rr,
                use_opposing_liquidity_target=smc_use_liquidity_target,
                require_premium_discount=smc_require_premium_discount,
            ),
        )

    # Provenance Banner
    if src_used != data_source:
        st.warning(
            f"⚠️ **Data Source Mismatch:** Currently viewing `{report.symbol}` ({report.timeframe}) "
            f"loaded via **'{src_used}'** at {load_time}. Sidebar is set to **'{data_source}'**. "
            "Click 'Load Data' to fetch using new settings."
        )
    else:
        trend_badge = f" | Trend: **{active_res.current_trend.value}**" if active_res else ""
        st.info(f"ℹ️ **Data Provenance:** Symbol: `{report.symbol}` | Timeframe: `{report.timeframe}` | Source: **{src_used}** | Ingested: {load_time}{trend_badge}")

    if meta and meta.get("is_synthetic") is True:
        st.warning("Synthetic benchmark data is for UI/logic testing only. Do not treat its signals or statistics as real-market evidence.")
    elif meta and (
        meta.get("timestamp_integrity_status") != "verified"
        or not meta.get("timestamp_mode_verified", False)
    ):
        st.error(
            "TIMESTAMP INTEGRITY NOT VERIFIED. Charts may be used for debugging only; "
            "do not use this dataset for session analysis, event statistics, or backtesting. "
            "Run scripts/diagnose_mt5_timestamps.py, choose the correct mode, then re-download."
        )
    elif meta and meta.get("source_verification_status") == "declared_not_independently_verified":
        st.warning("The source is declared by the ingestion pipeline, not independently verified. Preserve the retrieval report and inspect the raw timestamp epoch column.")

    # Top KPI Metrics Strip
    k1, k2, k3, k4, k5 = st.columns(5)
    last_close = df["close"].iloc[-1]
    high_max = df["high"].max()
    low_min = df["low"].min()
    bars_total = len(df)
    
    k1.metric("Latest Price", f"${last_close:,.2f}")
    k2.metric("Period High", f"${high_max:,.2f}")
    k3.metric("Period Low", f"${low_min:,.2f}")
    k4.metric("Audited Bars", f"{bars_total:,}")
    
    if active_res:
        trend_color = "🟢" if active_res.current_trend.value == "BULLISH" else ("🔴" if active_res.current_trend.value == "BEARISH" else "⚪")
        k5.metric("Market Structure Trend", f"{trend_color} {active_res.current_trend.value}")
    else:
        status_label = "🟢 PASSED" if report.status == "PASSED" else "🟡 WARNINGS"
        k5.metric("Data Quality Status", status_label)

    # Interactive Candlestick Chart with selected SMC or ICT overlays
    fig = create_candlestick_chart(
        df=df,
        symbol=report.symbol,
        timeframe=report.timeframe,
        show_volume=True,
        dark_theme=True,
        height=640,
        ict_result=ict_res,
        smc_result=smc_res,
        show_swings=show_smc_swings if smc_res else show_swings,
        show_structure_breaks=show_smc_breaks if smc_res else show_breaks,
        show_fvgs=show_fvgs if ict_res else False,
        show_sweeps=show_smc_sweeps if smc_res else show_sweeps,
        show_order_blocks=show_smc_obs if smc_res else show_obs,
        show_displacements=show_displacements if ict_res else False,
        show_liquidity_pools=show_smc_pools if smc_res else False,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Transparency & Analytics Tabs
    first_tab_title = "🧭 SMC Structure & Liquidity" if smc_res is not None or analysis_framework == "SMC (Primary)" else "🏛️ ICT Market Structure & Order Flow"
    tab_ict, tab_quality, tab_data, tab_export = st.tabs([
        first_tab_title,
        "📋 Data Quality & Integrity Report",
        "📊 Summary Statistics & Raw Data",
        "💾 Audit Export & Download",
    ])

    # TAB 1: Selected primary framework analytics
    with tab_ict:
        if smc_res:
            st.subheader("🧭 Pure SMC Structure Summary")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Confirmed Swings", len(smc_res.swings))
            m2.metric("BOS", smc_res.bos_count)
            m3.metric("CHoCH", smc_res.choch_count)
            m4.metric("Initial Breaks", smc_res.initial_break_count)
            m5, m6, m7, m8 = st.columns(4)
            m5.metric("Liquidity Pools", len(smc_res.liquidity_pools))
            m6.metric("Liquidity Sweeps", len(smc_res.liquidity_sweeps))
            m7.metric("SMC Order Blocks", len(smc_res.order_blocks))
            m8.metric("Current Dealing Zone", smc_res.current_zone)
            st.metric("SMC Setup Candidates", len(smc_setup_candidates))
            if smc_res.equilibrium is not None:
                st.caption(
                    f"Current swing dealing range: ${smc_res.dealing_range_low:,.2f}–${smc_res.dealing_range_high:,.2f}; "
                    f"equilibrium (50%): ${smc_res.equilibrium:,.2f}. Zone reflects the latest confirmed swing range."
                )
            st.markdown("#### 1. Confirmed Structure Breaks")
            if smc_res.structure_breaks:
                st.dataframe(pd.DataFrame([{
                    "Type": event.break_type.value,
                    "Direction": event.direction.value,
                    "Broken Level ($)": round(event.broken_swing.price, 2),
                    "Break Close ($)": round(event.break_price, 2),
                    "Time UTC": event.break_time.strftime("%Y-%m-%d %H:%M"),
                    "Prior Trend": event.prior_trend.value,
                    "Resulting Trend": event.resulting_trend.value,
                } for event in smc_res.structure_breaks]), use_container_width=True)
            else:
                st.info("No close-confirmed SMC structure breaks detected in this range.")
            col_pool, col_sweep = st.columns(2)
            with col_pool:
                st.markdown("#### 2. Equal High/Low Liquidity Pools")
                if smc_res.liquidity_pools:
                    st.dataframe(pd.DataFrame([{
                        "Side": pool.liquidity_type.value,
                        "Level ($)": round(pool.level, 2),
                        "Tolerance ($)": round(pool.tolerance, 2),
                        "Created UTC": pool.created_time.strftime("%Y-%m-%d %H:%M"),
                    } for pool in smc_res.liquidity_pools]), use_container_width=True)
                else:
                    st.info("No equal-high/low pools matched the current tolerance.")
            with col_sweep:
                st.markdown("#### 3. Liquidity Sweeps")
                if smc_res.liquidity_sweeps:
                    st.dataframe(pd.DataFrame([{
                        "Side": event.liquidity_type.value,
                        "Pool ($)": round(event.liquidity_pool.level, 2),
                        "Extreme ($)": round(event.sweep_price, 2),
                        "Close ($)": round(event.close_price, 2),
                        "Penetration ($)": round(event.penetration, 2),
                        "Time UTC": event.sweep_time.strftime("%Y-%m-%d %H:%M"),
                    } for event in smc_res.liquidity_sweeps]), use_container_width=True)
                else:
                    st.info("No post-confirmation wick-and-reclaim sweeps detected.")
            st.markdown("#### 4. Order Blocks (Known from Break Confirmation)")
            if smc_res.order_blocks:
                st.dataframe(pd.DataFrame([{
                    "Direction": ob.direction.value,
                    "Origin UTC": ob.origin_time.strftime("%Y-%m-%d %H:%M"),
                    "Known UTC": ob.created_time.strftime("%Y-%m-%d %H:%M"),
                    "High ($)": round(ob.high, 2),
                    "Low ($)": round(ob.low, 2),
                    "Status at Dataset End": ob.status.value,
                    "Confirming Event": ob.confirming_break_type.value,
                } for ob in smc_res.order_blocks]), use_container_width=True)
            else:
                st.info("No opposing candle was found in the configured lookback before a structure break.")
            st.markdown("#### 5. Pure-SMC Setup Candidates (Not Executed)")
            if smc_setup_candidates:
                st.dataframe(pd.DataFrame([{
                    "Direction": setup.direction.value,
                    "Signal UTC": setup.signal_time.strftime("%Y-%m-%d %H:%M"),
                    "Sweep UTC": setup.sweep_time.strftime("%Y-%m-%d %H:%M"),
                    "CHoCH UTC": setup.choch_time.strftime("%Y-%m-%d %H:%M"),
                    "Entry Reference ($)": round(setup.entry_reference_price, 2),
                    "Stop Reference ($)": round(setup.stop_loss_reference, 2),
                    "Target Reference ($)": round(setup.take_profit_reference, 2),
                    "Target Source": setup.target_source,
                    "Risk:Reward": round(setup.reward_risk_ratio, 2),
                } for setup in smc_setup_candidates]), use_container_width=True)
            else:
                st.info("No setup met the configured Sweep → CHoCH → OB Retest sequence.")
            st.info("These are research setup candidates only, not orders or claims of profitability. Reference entry is the retest-rejection candle close. Dataset-end OB lifecycle is retrospective. The Phase 3B real-data readiness gate remains mandatory before performance research.")
        elif ict_res:
            st.subheader("🏛️ Institutional Structure Summary")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Swings", len(ict_res.swings))
            m2.metric("BOS (Continuation)", ict_res.bos_count)
            m3.metric("CHoCH (Reversal)", ict_res.choch_count)
            m4.metric("Active FVGs", len(ict_res.active_fvgs))

            m5, m6, m7, m8 = st.columns(4)
            m5.metric("Liquidity Sweeps", len(ict_res.liquidity_sweeps))
            m6.metric("Market Structure Shifts", len(ict_res.market_structure_shifts))
            m7.metric("Displacement Candles", len(ict_res.displacement_indices))
            m8.metric("Active Order Blocks", len(ict_res.active_order_blocks))

            st.markdown("---")

            # 1. Structural Breaks Table
            st.markdown("#### 1. Confirmed Structural Breaks (BOS / CHoCH)")
            if ict_res.structure_breaks:
                brk_records = []
                for b in ict_res.structure_breaks:
                    brk_records.append({
                        "Type": b.break_type.value,
                        "Direction": b.direction.value,
                        "Break Price ($)": f"${b.break_price:,.2f}",
                        "Broken Level ($)": f"${b.broken_swing.price:,.2f}",
                        "Break Time (UTC)": b.break_time.strftime("%Y-%m-%d %H:%M"),
                        "Prior Trend": b.prior_trend.value,
                        "Resulting Trend": b.resulting_trend.value,
                    })
                st.dataframe(pd.DataFrame(brk_records), use_container_width=True)
            else:
                st.info("No structural breaks detected in this range.")

            # 2. Fair Value Gaps Table
            st.markdown("#### 2. Fair Value Gaps (FVG) & Consequent Encroachment (50% CE)")
            if ict_res.fvgs:
                fvg_records = []
                for f in ict_res.fvgs:
                    fvg_records.append({
                        "Type": f.gap_type.value,
                        "Status": f.status.value,
                        "Top ($)": f"${f.top_price:,.2f}",
                        "Bottom ($)": f"${f.bottom_price:,.2f}",
                        "CE 50% ($)": f"${f.consequent_encroachment:,.2f}",
                        "Height (pts)": round(f.size, 2),
                        "Created (UTC)": f.creation_time.strftime("%Y-%m-%d %H:%M"),
                        "Mitigated (UTC)": f.mitigation_time.strftime("%Y-%m-%d %H:%M") if f.mitigation_time else "Untested",
                    })
                st.dataframe(pd.DataFrame(fvg_records), use_container_width=True)
            else:
                st.info("No Fair Value Gaps detected exceeding the threshold.")

            # 3. Liquidity Sweeps & Order Blocks
            st.markdown("#### 3. Liquidity Sweeps & Institutional Order Blocks")
            col_sw, col_ob = st.columns(2)
            with col_sw:
                st.markdown("**Liquidity Sweeps (Stop Runs / False Breaks)**")
                if ict_res.liquidity_sweeps:
                    sw_records = []
                    for sw in ict_res.liquidity_sweeps:
                        sw_records.append({
                            "Type": sw.sweep_type.value,
                            "Swept Level ($)": f"${sw.swept_swing.price:,.2f}",
                            "Extreme Price ($)": f"${sw.sweep_price:,.2f}",
                            "Close Price ($)": f"${sw.close_price:,.2f}",
                            "Wick Penetration (pts)": round(sw.wick_penetration, 2),
                            "Time (UTC)": sw.sweep_time.strftime("%Y-%m-%d %H:%M"),
                        })
                    st.dataframe(pd.DataFrame(sw_records), use_container_width=True)
                else:
                    st.info("No liquidity sweeps detected.")

            with col_ob:
                st.markdown("**Institutional Order Blocks (OB)**")
                if ict_res.order_blocks:
                    ob_records = []
                    for ob in ict_res.order_blocks:
                        ob_records.append({
                            "Type": ob.ob_type.value,
                            "OB High ($)": f"${ob.high:,.2f}",
                            "OB Low ($)": f"${ob.low:,.2f}",
                            "Mitigated": "Yes" if ob.is_mitigated else "No (Active)",
                            "Time (UTC)": ob.candle_time.strftime("%Y-%m-%d %H:%M"),
                        })
                    st.dataframe(pd.DataFrame(ob_records), use_container_width=True)
                else:
                    st.info("No order blocks detected.")

            # 4. Market Structure Shifts & Institutional Displacement
            st.markdown("#### 4. Market Structure Shifts (MSS) & Institutional Displacement")
            col_mss, col_disp = st.columns(2)
            with col_mss:
                st.markdown("**Market Structure Shifts (Sweep → Counter-Break Confluence)**")
                if ict_res.market_structure_shifts:
                    mss_records = []
                    for mss in ict_res.market_structure_shifts:
                        fvg_note = f"FVG [{mss.displacement_fvg.bottom_price:.2f}–{mss.displacement_fvg.top_price:.2f}]" if mss.displacement_fvg else "None"
                        mss_records.append({
                            "Direction": mss.direction.value,
                            "Shift Time (UTC)": mss.shift_time.strftime("%Y-%m-%d %H:%M"),
                            "Sweep Price ($)": f"${mss.sweep.sweep_price:,.2f}",
                            "Break Price ($)": f"${mss.structure_break.break_price:,.2f}",
                            "Confluence FVG": fvg_note,
                        })
                    st.dataframe(pd.DataFrame(mss_records), use_container_width=True)
                else:
                    st.info("No Market Structure Shifts detected.")

            with col_disp:
                st.markdown("**Displacement Candles (Impulsive Volume/Body)**")
                if ict_res.displacement_indices:
                    disp_records = []
                    for idx in ict_res.displacement_indices:
                        if 0 <= idx < len(df):
                            row = df.iloc[idx]
                            b_type = "Bullish" if row["close"] >= row["open"] else "Bearish"
                            body_pts = abs(float(row["close"]) - float(row["open"]))
                            disp_records.append({
                                "Time (UTC)": row["time"].strftime("%Y-%m-%d %H:%M"),
                                "Type": b_type,
                                "Open ($)": f"${row['open']:,.2f}",
                                "Close ($)": f"${row['close']:,.2f}",
                                "Body (pts)": round(body_pts, 2),
                                "Volume": int(row.get("tick_volume", 0)),
                            })
                    st.dataframe(pd.DataFrame(disp_records), use_container_width=True)
                else:
                    st.info("No displacement candles detected with current threshold.")

            # Methodology and Limitations Box
            with st.expander("📖 ICT Methodology, Rules & Look-Ahead Prevention"):
                st.markdown("""
                **Methodological Guarantees:**
                1. **Zero Look-Ahead Bias:** A fractal swing point with window $k=2$ is only confirmed at candle $i+k$. No break, sweep, or reaction can be evaluated prior to bar $i+k$.
                2. **Institutional Break Rules:** Standard structural breaks require a full candle body close (`Close > SwingHigh.price`). Wick-only breaches are classified as liquidity sweeps (false breakouts).
                3. **UTC Time Basis:** All bar timestamps and session schedules strictly adhere to UTC (`datetime64[ns, UTC]`).
                4. **Known Limitations & Edge Cases:**
                   - Extremely volatile news candles (e.g. NFP / FOMC) may create large dual-sided wicks that sweep both sides simultaneously.
                   - Low liquidity Sunday open candles may produce micro-gaps that are technically imbalances but lack institutional sponsorship.
                """)
        else:
            st.info("Enable the selected analysis engine in the sidebar to view market structure analytics.")

    # TAB 2: Data Quality & Integrity Report
    with tab_quality:
        st.subheader("Integrity Audit Breakdown")
        q1, q2, q3 = st.columns(3)
        
        with q1:
            st.markdown("**Geometric & Structure Checks**")
            st.write(f"- Chronological Order: {'✅ Monotonic' if report.is_chronological else '❌ Out-of-Order'}")
            st.write(f"- Duplicate Timestamps: **{report.duplicate_timestamps_count}**")
            st.write(f"- Invalid OHLC Rows: **{report.invalid_ohlc_count}**")
        
        with q2:
            st.markdown("**Completeness & Continuity**")
            st.write(f"- Missing Cell Count (NaN): **{sum(report.missing_values_by_column.values())}**")
            st.write(f"- Standard Weekend Closures: **{report.weekend_gaps_count}**")
            st.write(f"- Abnormal Intraday Gaps: **{report.abnormal_gaps_count}**")
            
        with q3:
            st.markdown("**Dataset Boundary**")
            st.write(f"- Period Start: `{report.start_date}`")
            st.write(f"- Period End: `{report.end_date}`")
            st.write(f"- Incomplete Candle Excluded: `True`")

        if report.warnings:
            st.warning("⚠️ **Pipeline Warnings:**\n" + "\n".join([f"- {w}" for w in report.warnings]))
        if report.errors:
            st.error("🔴 **Critical Errors Detected:**\n" + "\n".join([f"- {e}" for e in report.errors]))

        if report.abnormal_gaps:
            with st.expander("🔍 View Detected Abnormal Trading Gaps"):
                st.table(pd.DataFrame(report.abnormal_gaps))

    # TAB 3: Summary Statistics & Raw Data
    with tab_data:
        st.subheader("Statistical Profile (XAU/USD)")
        stat_cols = [c for c in ["open", "high", "low", "close", "tick_volume", "spread"] if c in df.columns]
        if stat_cols:
            st.dataframe(df[stat_cols].describe().T.style.format("{:.2f}"), use_container_width=True)
        
        st.subheader("Recent Candles (Tail)")
        st.dataframe(df.tail(10), use_container_width=True)

    # TAB 4: Download & Export
    with tab_export:
        st.subheader("Download Audited Artifacts")
        c_csv, c_json, c_md = st.columns(3)
        
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        c_csv.download_button(
            label="📥 Download Clean CSV",
            data=csv_bytes,
            file_name=f"{report.symbol}_{report.timeframe}_clean.csv",
            mime="text/csv",
        )

        json_bytes = json.dumps(report.to_dict(), indent=2).encode("utf-8")
        c_json.download_button(
            label="📥 Download JSON Report",
            data=json_bytes,
            file_name=f"data_quality_report_{report.symbol}_{report.timeframe}.json",
            mime="application/json",
        )

        md_content = Path("reports/data_quality_report.md").read_text(encoding="utf-8") if Path("reports/data_quality_report.md").exists() else ""
        c_md.download_button(
            label="📥 Download Markdown Report",
            data=md_content.encode("utf-8"),
            file_name="data_quality_report.md",
            mime="text/markdown",
        )

else:
    st.info("No dataset is currently loaded. Click **'Load Data'** in the sidebar to begin.")
