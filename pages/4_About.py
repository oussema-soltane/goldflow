"""
GoldFlow — About & Academic Methodology
"""

import streamlit as st

st.set_page_config(page_title="GoldFlow — About", page_icon="📖", layout="wide")

st.title("📖 About GoldFlow — SMC Primary, ICT Retained")

st.markdown(
    """
    ## Academic & Quantitative Context
    **GoldFlow** is an end-to-end Data Science and Business Intelligence final project focusing on quantitative market structure analysis in Gold (**XAU/USD**).
    
    ### Strategy Architecture
    - **Primary: Pure SMC.** An independent SMC engine detects confirmed swings, close-based BOS/CHoCH, equal-high/low liquidity pools, wick-and-reclaim sweeps, structure-break-confirmed order blocks, and premium/discount context. Its current setup hypothesis is Sweep → opposite CHoCH → OB Retest/Rejection.
    - **Retained: ICT.** The existing ICT analysis engine remains separately selectable, preserving its FVG, displacement, MSS, liquidity-sweep, and ICT order-block logic. ICT-specific conditions are not silently added to SMC.
    - The SMC setup detector emits research candidates only. There is no claim of profitability or validated execution strategy.

    ### Core Tenets
    1. **Empirical Rigor**: No arbitrary win-rate claims. Evaluate expectancy, sample sizes, drawdown, costs, and out-of-sample behavior only after a real-data audit passes.
    2. **Data Integrity**: Never fabricate or interpolate missing price action; synthetic benchmarks remain distinguishable from broker data.
    3. **Look-Ahead Bias Elimination**: Swings, structure breaks, liquidity events, and order blocks become actionable only at their defined confirmation time.
    4. **Realistic Market Friction**: Backtests must model broker spread, slippage, commission, and conservative stop/target resolution.
    5. **Research Gate**: Bundled historical datasets remain quarantined until a live MT5 timestamp diagnostic and fresh raw-epoch-preserving retrieval pass validation.

    ### Technology Stack
    - **Language:** Python 3.11 / 3.13
    - **Data Pipeline:** MetaTrader 5 API, pandas, numpy
    - **Validation:** Automated geometric integrity tests, pytest
    - **Visualization:** Streamlit, Plotly
    - **BI Analytics:** Power BI
    
    ### Academic Mentor Notes
    This platform serves as an open, auditable research workbench suitable for institutional defense.
    """
)
