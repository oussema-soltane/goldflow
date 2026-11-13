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
    - **Language:** Python 3.14.7 (Windows)
    - **Data Pipeline:** MetaTrader 5 API, pandas, numpy, scipy
    - **Validation:** Automated geometric integrity tests, pytest (664 unit + integration tests)
    - **Visualization:** Streamlit, Plotly (interactive event-driven charts with 4 institutional presets)
    - **BI Analytics:** Streamlit BI Dashboard with canonical baseline and historical research source selection

    ### Research Integrity Commitments
    1. **Fail-Closed Canonical Data Guard:** Live MT5 fetches cannot overwrite verified canonical datasets.
    2. **Research Holdout Discipline:** Validation windows formally classified as CONSUMED after first examination.
    3. **Candidate Promotion Gate:** Hypothesis changes require pre-registered specs and pass a promotion gate (PF ≥ 1.10 on dev split) before unblinding holdout data.
    4. **Cryptographic Dataset Hashing:** SHA-256 hashes for all four canonical datasets and the frozen SMC v1 config are logged in audit reports.
    5. **100% Test Coverage:** 664 automated tests enforce data integrity, engine causality, backtest reproducibility, and UI AppTest verification.

    ### Academic Mentor Notes
    This platform serves as an open, auditable research workbench suitable for a final-year Data Science
    and Business Intelligence project defence. All quantitative claims are traceable to committed
    source code, versioned datasets, and reproducible backtest pipelines.
    """
)
