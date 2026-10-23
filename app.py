"""
GoldFlow — SMC-Primary & ICT Trading Analytics Platform
Main Entry Point & Executive Overview Dashboard
"""

from __future__ import annotations

import streamlit as st
from pathlib import Path

# Streamlit Page Configuration
st.set_page_config(
    page_title="GoldFlow — SMC + ICT Analytics",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for rich institutional styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #f0b90b;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #94a3b8;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #1e222d;
        border: 1px solid #2a2e39;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .metric-title {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-val {
        font-size: 1.4rem;
        font-weight: 600;
        color: #ffffff;
        margin-top: 4px;
    }
    .status-badge-ok {
        background-color: #08998122;
        color: #089981;
        border: 1px solid #089981;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-badge-warn {
        background-color: #f0b90b22;
        color: #f0b90b;
        border: 1px solid #f0b90b;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Header
st.markdown('<div class="main-header">🪙 GOLDFLOW</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Pure SMC Primary · Existing ICT Framework Preserved — XAU/USD (Gold)</div>',
    unsafe_allow_html=True,
)

# System Status Check
from src.data.loader import check_mt5_status

status = check_mt5_status()

# Top KPI row
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">Target Instrument</div>
            <div class="metric-val">XAU/USD</div>
            <span style="color:#089981; font-size:0.8rem;">Gold Spot vs US Dollar</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    badge_html = (
        '<span class="status-badge-ok">CONNECTED</span>'
        if status["connected"]
        else '<span class="status-badge-warn">TERMINAL OFFLINE</span>'
    )
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">MT5 Pipeline Status</div>
            <div class="metric-val">{badge_html}</div>
            <span style="color:#94a3b8; font-size:0.8rem;">{status['account_info']['server'] if status['account_info'] else 'Demo Account'}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        """
        <div class="metric-card">
            <div class="metric-title">Timeframe Hierarchy</div>
            <div class="metric-val">H4 · H1 · M15 · M5</div>
            <span style="color:#94a3b8; font-size:0.8rem;">HTF Context & LTF Setups</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c4:
    st.markdown(
        """
        <div class="metric-card">
            <div class="metric-title">Implementation Phase</div>
            <div class="metric-val">Phase 3D.3.2.1</div>
            <span style="color:#089981; font-size:0.8rem;">Dynamic MT5 Calc-Mode Guard & SMC Backtest</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")

# Main Dashboard Content
col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("Platform Architecture & Roadmap")
    st.markdown(
        """
        GoldFlow is structured into modular, reproducible engineering phases:
        
        1. **Phase 1 — Market Data Pipeline (Complete)**
           - MetaTrader 5 broker connectivity & automatic gold symbol discovery.
           - Historical ingestion across H4, H1, M15, M5 timeframes.
           - Deterministic OHLC geometric validation, duplicate pruning & smart gap auditing.
           - Traceable storage (`data/raw/` and `data/processed/`) with zero price fabrication.
        
        2. **Primary Analysis — Pure Smart Money Concepts (SMC)**
           - Independent SMC engine for confirmed swing structure, close-based BOS/CHoCH, equal-high/low liquidity, sweeps, order blocks, and premium/discount context.
           - Primary setup hypothesis: *Liquidity Sweep → opposite CHoCH → Order-Block Retest/Rejection*.

        3. **Retained Framework — Existing ICT Engine**
           - The existing ICT analysis remains separately selectable, including its own BOS/CHoCH, MSS, FVG, displacement, sweeps, and order-block logic.
           - SMC rules do not inherit ICT FVG, displacement, MSS, or kill-zone requirements.

        4. **Current Gate — Historical Data Integrity**
           - Existing bundled timestamps remain quarantined pending a live MT5 timestamp diagnostic and fresh raw-epoch-preserving download.

        5. **Next — Research and Backtesting**
           - Once real-data readiness passes: evaluate SMC setup candidates, formalize a separate ICT setup hypothesis from its intended rules, then compare them using spread/slippage-aware, out-of-sample backtests.
        """
    )
    
    st.info("👉 Navigate to **'1_Market_Analysis'** to use **SMC as the primary framework** or switch to the retained ICT analysis. Real-market research remains blocked until the MT5 timestamp and data-readiness audits pass.")

with col_right:
    st.subheader("MetaTrader 5 Terminal Diagnostics")
    
    if status["connected"]:
        acc = status["account_info"]
        login_str = f"Account #{acc.get('login')}" if acc and acc.get('login') else "Account"
        server_str = acc.get('server', 'Demo Server') if acc else 'Demo Server'
        mode_str = acc.get('trade_mode', 'Demo') if acc else 'Demo'
        curr_str = acc.get('currency', 'USD') if acc else 'USD'
        bal_val = acc.get('balance') if acc else None
        eq_val = acc.get('equity') if acc else None
        lev_val = acc.get('leverage') if acc else None

        st.success(f"✅ MT5 is connected to **{server_str}** ({login_str}, Mode: {mode_str}).")
        st.write(f"- **Leverage:** {'1:' + str(lev_val) if lev_val is not None else 'N/A'}")
        st.write(f"- **Balance:** {f'${bal_val:,.2f} {curr_str}' if bal_val is not None else 'N/A'}")
        st.write(f"- **Equity:** {f'${eq_val:,.2f} {curr_str}' if eq_val is not None else 'N/A'}")
    else:
        st.warning("⚠️ MT5 terminal is not currently connected.")
        st.write(f"**Diagnostic Details:**")
        st.write(f"- **MT5 Python Library:** {'Installed' if status['package_installed'] else 'Missing'}")
        st.write(f"- **Terminal Executable:** {status['terminal_path'] or 'Not found'}")
        st.write(f"- **Terminal Process Running:** {'Yes' if status.get('terminal_running') else 'No'}")
        st.caption(status["actionable_message"])
        st.markdown(
            """
            > **How to connect:**
            > 1. Launch your **MetaTrader 5** desktop application.
            > 2. Log in to your **Demo Account** (Tools -> Options -> Server).
            > 3. Ensure **'Allow Algo Trading'** is toggled on.
            > 4. Go to **Market Analysis** page to extract data.
            """
        )

    st.subheader("Workspace Data Inventory")
    data_dir = Path("data/processed")
    if data_dir.exists():
        files = list(data_dir.glob("*.csv"))
        if files:
            st.write(f"Found **{len(files)}** processed dataset(s):")
            for f in files:
                size_kb = f.stat().st_size / 1024
                st.code(f"{f.name} ({size_kb:.1f} KB)")
        else:
            st.caption("No processed CSVs found in data/processed/. Run ingestion in '1_Market_Analysis'.")
    else:
        st.caption("Directory data/processed/ will be initialized upon first download.")
