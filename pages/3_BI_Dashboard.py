"""
GoldFlow — Power BI Dashboard Integration (Phase 6 Placeholder)
"""

import streamlit as st

st.set_page_config(page_title="GoldFlow — BI Dashboard", page_icon="📊", layout="wide")

st.title("📊 Power BI & Executive Analytics")
st.caption("Phase 6 Pipeline: Business Intelligence exports and interactive dashboards.")

st.info("🚧 **Power BI Dashboard integration is scheduled for Phase 6** following backtest execution.")

st.markdown(
    """
    ### Power BI Reporting Scope
    - Automated CSV/Parquet export ready for Microsoft Power BI desktop.
    - Trade logs aggregated by session (Asian, London, New York killzones).
    - Cumulative Net P&L and equity drawdown curve.
    - Setup distribution by day of week and market regime.
    """
)
