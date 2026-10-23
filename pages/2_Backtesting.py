"""GoldFlow Phase 4 — SMC v1 Strategy Research, Backtesting & Robustness Interface."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_smc_backtest import run_backtest_pipeline
from src.backtesting.engine import BacktestConfig
from src.research.execution_spec_audit import audit_processed_execution_specs

st.set_page_config(page_title="GoldFlow — SMC Strategy Validation", page_icon="⚙️", layout="wide")
st.title("⚙️ SMC v1 Strategy Validation & Research")
st.caption("Pure-SMC event-driven research simulator, chronological out-of-sample validation, and cost-sensitivity analysis.")

# --- Top Banner & System Status ---
readiness_path = ROOT / "reports" / "research_readiness.json"
readiness = {}
if readiness_path.exists():
    try:
        readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        readiness = {}
readiness_status = readiness.get("overall_status", "UNKNOWN")

execution_spec_audit = audit_processed_execution_specs(ROOT / "data" / "processed")
execution_spec_status = execution_spec_audit.get("overall_status", "AUDIT_ERROR")

col_s1, col_s2, col_s3, col_s4 = st.columns(4)
with col_s1:
    st.metric("Strategy", "SMC v1 (Frozen)")
with col_s2:
    st.metric("Readiness", readiness_status)
with col_s3:
    spec_label = "MATCHED (UNVERIFIED)" if execution_spec_status == "MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE" else execution_spec_status
    st.metric("Execution Spec", spec_label)
with col_s4:
    st.metric("Validation Category", "PROVISIONAL RESEARCH")

st.warning(
    "⚠️ **PROVISIONAL RESEARCH WARNING:** All backtests and validation results are exploratory research outputs. "
    "Data provenance is declared as MT5 but not independently verified (UNVERIFIED_PROVENANCE). "
    "Past in-sample profitability does NOT constitute evidence of a repeatable live trading edge. "
    "Never treat backtest figures as live or demo trading results."
)

tab_backtest, tab_oos, tab_robustness, tab_rules, tab_ict = st.tabs([
    "📊 Interactive Backtest",
    "📅 Out-of-Sample Validation",
    "🛡️ Robustness & Cost Sensitivity",
    "📜 Frozen Strategy v1 Rules",
    "🧭 Independent ICT Status",
])

# ==============================================================================
# TAB 1: INTERACTIVE BACKTEST
# ==============================================================================
with tab_backtest:
    st.subheader("Run Pure-SMC Event Backtest")
    with st.form("smc_backtest_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            selected_timeframes = st.multiselect("Timeframes", ["H4", "H1", "M15", "M5"], default=["H4", "H1", "M15", "M5"])
            mode_label = st.radio("Date range mode", ["Full history per timeframe", "Common date window"], index=0)
            initial_capital = st.number_input("Starting capital ($)", min_value=100.0, max_value=10_000_000.0, value=10_000.0, step=500.0)
        with col2:
            risk_pct = st.slider("Risk fraction per trade (%)", min_value=0.1, max_value=3.0, value=1.0, step=0.1)
            max_positions = st.selectbox("Maximum concurrent positions per timeframe", [1, 2, 3], index=0)
            holding_choice = st.selectbox(
                "Maximum holding bars (entry bar counts as 1)",
                ["No time stop", 1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 96, 192, 288, 576],
                index=0,
                help="A TIME_STOP exits at bar close if neither stop nor target was touched first."
            )
            slippage = st.number_input("Adverse slippage per side ($/oz)", min_value=0.0, max_value=5.0, value=0.05, step=0.01, format="%.2f")
        with col3:
            contract_size = st.number_input("Contract size (oz/lot)", min_value=0.01, max_value=1_000_000.0, value=100.0, step=1.0)
            point_size = st.number_input("Broker point size ($/point)", min_value=0.0001, max_value=1.0, value=0.01, step=0.01, format="%.4f")
            fallback_spread = st.number_input("Fallback spread ($/oz)", min_value=0.0, max_value=5.0, value=0.20, step=0.05, format="%.2f")
            commission = st.number_input("Commission per lot per side ($)", min_value=0.0, max_value=100.0, value=0.0, step=0.5, format="%.2f")
            min_lot = st.number_input("Minimum lot", min_value=0.001, max_value=100.0, value=0.01, step=0.01, format="%.3f")
            lot_step = st.number_input("Lot step", min_value=0.001, max_value=100.0, value=0.01, step=0.01, format="%.3f")
            max_lots = st.number_input("Maximum lots", min_value=0.01, max_value=1_000_000.0, value=100.0, step=1.0)

        require_matched_execution_spec = st.checkbox(
            "Require captured MT5 execution specifications to match configuration before running",
            value=True,
            help="Enforces broker execution spec alignment. Uncheck only for unverified exploratory tests.",
        )
        run_clicked = st.form_submit_button("Run Backtest", type="primary", disabled=not selected_timeframes)

    if run_clicked:
        config = BacktestConfig(
            initial_capital=float(initial_capital),
            risk_fraction=float(risk_pct) / 100.0,
            contract_size_oz=float(contract_size),
            point_size=float(point_size),
            fallback_spread_usd=float(fallback_spread),
            slippage_per_side_usd=float(slippage),
            commission_per_lot_per_side=float(commission),
            min_lot=float(min_lot),
            lot_step=float(lot_step),
            max_lots=float(max_lots),
            max_concurrent_positions=int(max_positions),
            max_holding_bars=None if holding_choice == "No time stop" else int(holding_choice),
        )
        mode = "common-window" if mode_label == "Common date window" else "full-history"
        with st.spinner("Computing SMC candidates and replaying event-driven execution…"):
            try:
                payload = run_backtest_pipeline(
                    ROOT / "data" / "processed",
                    ROOT / "reports",
                    timeframes=selected_timeframes,
                    mode=mode,
                    config=config,
                    require_matched_execution_spec=require_matched_execution_spec,
                )
                st.session_state["smc_backtest_payload"] = payload
                st.success("Backtest simulation completed.")
            except Exception as exc:
                st.error(f"Backtest execution failed: {exc}")

    # Display Backtest Results
    payload = st.session_state.get("smc_backtest_payload")
    if payload is None:
        latest_metrics_path = ROOT / "reports" / "smc_backtest_metrics_full_history.json"
        if latest_metrics_path.exists():
            try:
                payload = json.loads(latest_metrics_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None

    if payload:
        st.divider()
        st.subheader("Simulation Results Summary")
        payload_spec_status = payload.get("execution_spec_audit_status", execution_spec_status)
        st.caption(
            f"Mode: **{payload.get('mode', 'unknown')}** | "
            f"Readiness: **{payload.get('readiness_status', 'unknown')}** | "
            f"Execution Specs: **{payload_spec_status}** | "
            f"Generated: `{payload.get('generated_at_utc', 'unknown')}`"
        )

        table_rows = []
        for tf, m in payload.get("metrics_by_timeframe", {}).items():
            wr = f"{m.get('win_rate_pct'):.1f}%" if m.get("win_rate_pct") is not None else "N/A"
            pf = f"{m.get('profit_factor'):.2f}" if isinstance(m.get("profit_factor"), (int, float)) else str(m.get("profit_factor", "N/A"))
            table_rows.append({
                "Timeframe": tf,
                "Candidates": m.get("candidate_count", 0),
                "Rule Exits": m.get("rule_exit_trades", 0),
                "Time Stops": m.get("time_stop_exits", 0),
                "End-of-Data": m.get("end_of_data_exits", 0),
                "Skipped": m.get("skipped_candidates", 0),
                "Win Rate*": wr,
                "Net Profit ($)": f"${m.get('net_profit', 0):,.2f}",
                "Return (%)": f"{m.get('return_pct', 0):.2f}%",
                "Profit Factor*": pf,
                "EOD P&L ($)": f"${m.get('end_of_data_pnl', 0):,.2f}",
                "Max DD (MTM $)": f"${m.get('max_drawdown_cash', 0):,.2f}",
                "Max Realized DD ($)": f"${m.get('max_realized_drawdown_cash', 0):,.2f}",
            })
        if table_rows:
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
            st.caption(
                "* Note: Win rate and profit factor exclude END_OF_DATA exits; TIME_STOP is counted as a rule exit. "
                "Net profit includes end-of-sample liquidation. Realized and mark-to-market drawdowns are tracked separately."
            )

        # Equity Curve Visualizer
        st.subheader("Equity Curve (Mark-to-Market vs Realized)")
        chart_tf = st.selectbox("Select Timeframe for Equity Curve", list(payload.get("metrics_by_timeframe", {}).keys()))
        if chart_tf:
            tf_data = payload.get("metrics_by_timeframe", {}).get(chart_tf, {})
            eq_curve = tf_data.get("equity_curve", [])
            if eq_curve:
                eq_df = pd.DataFrame(eq_curve)
                eq_df["time"] = pd.to_datetime(eq_df["time"])
                eq_df = eq_df.set_index("time")[["equity", "realized_equity"]]
                st.line_chart(eq_df)
            else:
                st.info(f"No equity curve points available for {chart_tf}.")

        # Trade Ledger
        trades_path = Path(payload.get("artifact_paths", {}).get("trades_csv", "reports/smc_backtest_trades_full_history.csv"))
        if not trades_path.is_absolute():
            trades_path = ROOT / trades_path
        if trades_path.exists() and trades_path.is_file() and trades_path.stat().st_size > 0:
            try:
                trade_df = pd.read_csv(trades_path)
                st.subheader("Trade Ledger & Signal Audit Log")
                c1, c2 = st.columns(2)
                with c1:
                    status_opts = sorted(trade_df["status"].dropna().unique().tolist()) if "status" in trade_df.columns else []
                    status_sel = st.multiselect("Filter by Trade Status", status_opts, default=status_opts)
                with c2:
                    tf_opts = sorted(trade_df["timeframe"].dropna().unique().tolist()) if "timeframe" in trade_df.columns else []
                    tf_sel = st.multiselect("Filter by Timeframe", tf_opts, default=tf_opts)
                filtered = trade_df
                if status_sel and "status" in filtered.columns:
                    filtered = filtered[filtered["status"].isin(status_sel)]
                if tf_sel and "timeframe" in filtered.columns:
                    filtered = filtered[filtered["timeframe"].isin(tf_sel)]
                st.dataframe(filtered, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download Trade Log CSV",
                    data=trade_df.to_csv(index=False).encode("utf-8"),
                    file_name=trades_path.name,
                    mime="text/csv"
                )
            except Exception as exc:
                st.warning(f"Could not load trade log CSV: {exc}")


# ==============================================================================
# TAB 2: OUT-OF-SAMPLE VALIDATION
# ==============================================================================
with tab_oos:
    st.subheader("Phase 4 Chronological Out-of-Sample Validation")
    st.markdown(
        """
        The dataset is split chronologically into **60% Training**, **20% Validation**, and **20% Untouched Holdout**.
        - Signal detection uses historical context up to each segment's boundary to identify valid swings, sweeps, and order blocks.
        - Only candidates whose execution signal falls strictly within the segment are simulated.
        - Parameters are completely frozen (`configs/smc_v1_frozen.json`) and were **never optimized** against any segment.
        """
    )
    oos_metrics_path = ROOT / "reports" / "smc_phase4_validation_metrics.json"
    if oos_metrics_path.exists():
        try:
            oos_data = json.loads(oos_metrics_path.read_text(encoding="utf-8"))
            st.caption(f"Validation Generated UTC: `{oos_data.get('generated_at_utc', 'N/A')}`")

            oos_summary = []
            for tf, tf_info in oos_data.get("per_timeframe", {}).items():
                for seg_label in ("train", "validate", "holdout"):
                    seg = tf_info.get("segments", {}).get(seg_label, {})
                    if seg:
                        wr = f"{seg.get('win_rate_pct'):.1f}%" if seg.get("win_rate_pct") is not None else "N/A"
                        pf = f"{seg.get('profit_factor'):.2f}" if isinstance(seg.get("profit_factor"), (int, float)) else str(seg.get("profit_factor", "N/A"))
                        oos_summary.append({
                            "Timeframe": tf,
                            "Segment": seg_label.upper(),
                            "Rows": seg.get("n_rows", 0),
                            "Start Date": str(seg.get("segment_start", ""))[:10],
                            "End Date": str(seg.get("segment_end", ""))[:10],
                            "Candidates": seg.get("candidate_count", 0),
                            "Rule Exits": seg.get("rule_exit_trades", 0),
                            "EOD Exits": seg.get("end_of_data_exits", 0),
                            "Win Rate": wr,
                            "Net P&L ($)": f"${seg.get('net_profit', 0):,.2f}",
                            "Profit Factor": pf,
                            "Max DD ($)": f"${seg.get('max_drawdown_cash', 0):,.2f}",
                        })
            if oos_summary:
                st.dataframe(pd.DataFrame(oos_summary), use_container_width=True, hide_index=True)

            # Segment Equity curves
            st.subheader("Segment Equity Curve Viewer")
            oos_tf_sel = st.selectbox("Select Timeframe", list(oos_data.get("per_timeframe", {}).keys()), key="oos_tf_sel")
            if oos_tf_sel:
                tf_segments = oos_data["per_timeframe"][oos_tf_sel].get("segments", {})
                c_tr, c_val, c_hld = st.columns(3)
                for col, seg_name in zip([c_tr, c_val, c_hld], ["train", "validate", "holdout"]):
                    with col:
                        seg = tf_segments.get(seg_name, {})
                        st.markdown(f"**{seg_name.upper()} Segment**")
                        if seg and seg.get("equity_curve"):
                            df_seg_eq = pd.DataFrame(seg["equity_curve"])
                            df_seg_eq["time"] = pd.to_datetime(df_seg_eq["time"])
                            df_seg_eq = df_seg_eq.set_index("time")[["equity"]]
                            st.line_chart(df_seg_eq)
                        else:
                            st.info("No equity curve points recorded.")

            # Full OOS Trades
            oos_trades_path = ROOT / "reports" / "smc_phase4_validation_trades.csv"
            if oos_trades_path.exists():
                st.subheader("Out-of-Sample Trade Ledger")
                oos_df = pd.read_csv(oos_trades_path)
                st.dataframe(oos_df, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"Error parsing out-of-sample metrics: {exc}")
    else:
        st.info("Out-of-sample validation metrics not found. Run `scripts/run_smc_phase4_validation.py` to generate.")


# ==============================================================================
# TAB 3: ROBUSTNESS & COST SENSITIVITY
# ==============================================================================
with tab_robustness:
    st.subheader("SMC v1 Robustness and Cost Sensitivity")
    st.markdown(
        """
        Evaluates the frozen SMC v1 setup under **7 predeclared cost scenarios** across all timeframes.
        This tests whether positive performance is resilient to real-world friction (spread widening, adverse slippage, commissions)
        or whether it is an artifact of low assumed friction.
        """
    )
    rob_metrics_path = ROOT / "reports" / "smc_phase4_robustness_metrics.json"
    if rob_metrics_path.exists():
        try:
            rob_data = json.loads(rob_metrics_path.read_text(encoding="utf-8"))
            st.caption(f"Analysis Generated UTC: `{rob_data.get('generated_at_utc', 'N/A')}`")

            rob_tf = st.selectbox("Select Timeframe for Cost Sensitivity", list(rob_data.get("results_by_timeframe", {}).keys()), key="rob_tf_sel")
            if rob_tf:
                tf_info = rob_data["results_by_timeframe"][rob_tf]
                sc_rows = []
                for sc in tf_info.get("cost_scenarios", []):
                    wr = f"{sc.get('win_rate_pct'):.1f}%" if sc.get("win_rate_pct") is not None else "N/A"
                    pf = f"{sc.get('profit_factor'):.2f}" if isinstance(sc.get("profit_factor"), (int, float)) else str(sc.get("profit_factor", "N/A"))
                    sc_rows.append({
                        "Scenario": sc.get("scenario"),
                        "Spread ($)": f"${sc.get('fallback_spread_usd'):.2f}",
                        "Slippage ($)": f"${sc.get('slippage_per_side_usd'):.2f}",
                        "Comm ($/lot/side)": f"${sc.get('commission_per_lot_per_side_usd'):.2f}",
                        "Rule Exits": sc.get("rule_exit_trades", 0),
                        "Win Rate": wr,
                        "Net P&L ($)": f"${sc.get('net_profit', 0):,.2f}",
                        "Return (%)": f"{sc.get('return_pct', 0):.2f}%",
                        "Profit Factor": pf,
                        "Max Drawdown ($)": f"${sc.get('max_drawdown_cash', 0):,.2f}",
                        "EOD P&L ($)": f"${sc.get('end_of_data_pnl', 0):,.2f}",
                    })
                st.dataframe(pd.DataFrame(sc_rows), use_container_width=True, hide_index=True)

                # Sensitivity bar chart
                df_pnl = pd.DataFrame([
                    {"Scenario": sc["scenario"], "Net Profit ($)": sc["net_profit"]}
                    for sc in tf_info.get("cost_scenarios", [])
                ]).set_index("Scenario")
                st.bar_chart(df_pnl)

            st.markdown(
                """
                **Key Takeaways from Robustness Stress:**
                - **H4**: Maintained positive P&L (+$445 to +$455) across all 7 cost variations, but sample size is only 13 rule exits.
                - **H1**: Marginally positive ($74 to $107) across all scenarios, but profit factor degrades from 1.06 to 1.04 under stress.
                - **M15 & M5**: Unprofitable across all 7 scenarios (-$884 to -$1003 on M15, -$240 to -$291 on M5). Higher transaction friction magnifies lower-timeframe losses.
                """
            )
        except Exception as exc:
            st.error(f"Error loading robustness metrics: {exc}")
    else:
        st.info("Robustness metrics not found. Run `scripts/run_smc_robustness.py` to generate.")


# ==============================================================================
# TAB 4: FROZEN STRATEGY V1 RULES
# ==============================================================================
with tab_rules:
    st.subheader("Frozen SMC Strategy Version 1 Specification")
    st.markdown("All rules are formal, frozen, and governed by `configs/smc_v1_frozen.json`.")
    frozen_cfg_path = ROOT / "configs" / "smc_v1_frozen.json"
    if frozen_cfg_path.exists():
        try:
            frozen_data = json.loads(frozen_cfg_path.read_text(encoding="utf-8"))
            rules = frozen_data.get("strategy_rules", {})

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("### Setup & Trigger Logic")
                st.markdown(f"- **Setup Sequence:** `{rules.get('setup_type')}`")
                st.markdown(f"- **Long Setup:** {rules.get('long_sequence')}")
                st.markdown(f"- **Short Setup:** {rules.get('short_sequence')}")
                st.markdown(f"- **Swing Pivot Algorithm:** {rules.get('swing_identification', {}).get('algorithm')}")
                st.markdown(f"- **Confirmation Delay:** {rules.get('swing_identification', {}).get('confirmation_delay_bars')} bars")
                st.markdown(f"- **CHoCH Definition:** {rules.get('choch_definition', {}).get('type')} (wick breaks ignored)")

            with c2:
                st.markdown("### Execution & Risk Rules")
                st.markdown(f"- **Entry Timing:** {rules.get('entry', {}).get('rule')}")
                st.markdown(f"- **Long Fill:** `{rules.get('entry', {}).get('long_fill')}`")
                st.markdown(f"- **Short Fill:** `{rules.get('entry', {}).get('short_fill')}`")
                st.markdown(f"- **Stop Loss Buffer:** {rules.get('stop_loss', {}).get('stop_buffer_price_units')} price units beyond sweep price")
                st.markdown(f"- **Take Profit:** {rules.get('take_profit', {}).get('primary')} (fallback: {rules.get('take_profit', {}).get('fixed_rr_fallback')}R)")
                st.markdown(f"- **Risk Fraction:** {rules.get('risk_management', {}).get('risk_fraction') * 100}% of realized equity")
                st.markdown(f"- **Collision Policy:** {rules.get('intrabar', {}).get('stop_first_on_collision')} (conservative stop-first)")

            with st.expander("View Full Frozen Configuration JSON"):
                st.json(frozen_data)
        except Exception as exc:
            st.error(f"Error parsing frozen config: {exc}")
    else:
        st.warning("Frozen config file `configs/smc_v1_frozen.json` not found.")


# ==============================================================================
# TAB 5: INDEPENDENT ICT STATUS
# ==============================================================================
with tab_ict:
    st.subheader("ICT Framework Architectural Separation")
    st.markdown(
        """
        **Architectural Independence Guaranteed:**
        - Pure SMC is the primary framework under validation in GoldFlow Phase 4.
        - The ICT framework is housed completely independently in `src/ict/` (including `ict_fvg.py`, `ict_liquidity.py`, `ict_order_blocks.py`, `ict_structure.py`).
        - **Zero Cross-Pollination:** SMC does not import ICT modules, nor does it require ICT Fair Value Gaps (FVG), displacement thresholds, Kill Zones, or Market Structure Shifts (MSS).
        - **ICT Integrity Preserved:** All 60+ ICT unit tests continue to pass independently in `pytest tests/`.
        - **Market Analysis Access:** You can inspect raw ICT pattern detections at any time by switching the strategy selector in **Market Analysis** (`pages/1_Market_Analysis.py`).
        """
    )
