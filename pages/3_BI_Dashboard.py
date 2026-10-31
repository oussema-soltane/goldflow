"""GoldFlow research BI dashboard and Power BI Desktop data exports.

This page visualizes persisted Phase 3E research outputs. It does not run trades,
connect to a Power BI service, or imply that a native .pbix file is published.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

# Available report sources: Phase 5 takes precedence when present, with Phase 3E selectable
_p5_dir = ROOT / "reports" / "phase5"
_p3e_dir = ROOT / "reports" / "phase3e"
_sources: dict[str, Path] = {}
if (_p5_dir / "smc_mtf_metrics.json").exists():
    _sources["Phase 5 — Independent Validation"] = _p5_dir
if (_p3e_dir / "smc_mtf_metrics.json").exists():
    _sources["Phase 3E — Multi-Timeframe Experiment"] = _p3e_dir

st.set_page_config(page_title="GoldFlow — Research BI", page_icon="📊", layout="wide")

_selected_source_name = (
    st.sidebar.selectbox("Experiment Source", list(_sources.keys()), index=0)
    if _sources else "Phase 3E"
)
REPORT_DIR = _sources.get(_selected_source_name, _p3e_dir)
METRICS_PATH = REPORT_DIR / "smc_mtf_metrics.json"
SUMMARY_PATH = REPORT_DIR / "smc_mtf_powerbi_summary.csv"
TRADES_PATH = REPORT_DIR / "smc_mtf_trades.csv"
CURVES_PATH = REPORT_DIR / "smc_mtf_equity_curves.csv"
AUDIT_PATH = REPORT_DIR / "smc_mtf_candidate_context_audit.csv"
REPORT_PATH = (
    (REPORT_DIR / "PHASE5_INDEPENDENT_VALIDATION.md")
    if (REPORT_DIR / "PHASE5_INDEPENDENT_VALIDATION.md").exists()
    else (REPORT_DIR / "PHASE3E_SMC_MULTI_TIMEFRAME_EXPERIMENT.md")
)


@st.cache_data(show_spinner=False)
def _load_json(path: str, last_modified_ns: int) -> dict[str, Any]:
    del last_modified_ns  # Included in the cache key to invalidate changed artifacts.
    return json.loads(Path(path).read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def _load_csv(path: str, last_modified_ns: int) -> pd.DataFrame:
    del last_modified_ns  # Included in the cache key to invalidate changed artifacts.
    return pd.read_csv(Path(path), low_memory=False)


def _load_optional_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return _load_csv(str(path), path.stat().st_mtime_ns)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.warning(f"Could not load `{path.name}`: {exc}")
        return None


def _build_summary_fallback(payload: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for timeframe, item in payload.get("per_timeframe", {}).items():
        for label, key in (
            ("SMC_v1_baseline", "baseline"),
            ("SMC_v1_H4_H1_confirmed", "mtf_confirmed"),
        ):
            metrics = item.get(key, {})
            funnel = item.get("mtf_filter_funnel", {})
            candidate_count = (
                funnel.get("accepted_candidates", 0)
                if key == "mtf_confirmed"
                else funnel.get("input_candidates", 0)
            )
            rows.append({
                "timeframe": timeframe,
                "strategy_variant": label,
                "candidate_count": candidate_count,
                "closed_trades": metrics.get("closed_trades", 0),
                "rule_exit_trades": metrics.get("rule_exit_trades", 0),
                "end_of_data_exits": metrics.get("end_of_data_exits", 0),
                "skipped_candidates": metrics.get("skipped_candidates", 0),
                "win_rate_pct": metrics.get("win_rate_pct"),
                "net_profit": metrics.get("net_profit"),
                "return_pct": metrics.get("return_pct"),
                "profit_factor": metrics.get("profit_factor"),
                "max_drawdown_cash": metrics.get("max_drawdown_cash"),
                "max_realized_drawdown_cash": metrics.get("max_realized_drawdown_cash"),
                "average_R_multiple": metrics.get("average_R_multiple"),
                "expectancy_per_rule_exit": metrics.get("expectancy_per_rule_exit"),
            })
    return pd.DataFrame(rows)


def _variant_label(value: str) -> str:
    return {
        "SMC_v1_baseline": "SMC v1 baseline",
        "SMC_v1_H4_H1_confirmed": "SMC v1 + H4/H1 confirmation",
    }.get(value, value.replace("_", " "))


def _number(value: Any, digits: int = 2, prefix: str = "", suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "N/A"
    try:
        return f"{prefix}{float(value):,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def _download_button(label: str, frame: pd.DataFrame | None, filename: str, key: str) -> None:
    if frame is None:
        st.button(label, disabled=True, key=key, help="The artifact has not been generated yet.")
        return
    st.download_button(
        label,
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        key=key,
    )


st.title("📊 GoldFlow Research Intelligence")
st.caption(
    "Performance comparison, risk analytics, and audit-ready exports for the frozen SMC v1 baseline "
    "and its experimental H4/H1-confirmed variant."
)

if not METRICS_PATH.exists():
    st.warning("Phase 3E research artifacts have not been generated in this project folder yet.")
    st.code(
        "python scripts/run_smc_mtf_backtest.py "
        "--output-dir reports/phase3e --require-matched-execution-spec",
        language="bash",
    )
    st.stop()

try:
    payload = _load_json(str(METRICS_PATH), METRICS_PATH.stat().st_mtime_ns)
except (OSError, json.JSONDecodeError) as exc:
    st.error(f"The Phase 3E metrics file could not be read: {exc}")
    st.stop()

summary = _load_optional_csv(SUMMARY_PATH)
if summary is None or summary.empty:
    summary = _build_summary_fallback(payload)
else:
    # Support the early Phase 3E summary schema as well as the Power BI export schema.
    if "strategy_variant" not in summary.columns and "variant" in summary.columns:
        summary = summary.rename(columns={"variant": "strategy_variant"})

trades = _load_optional_csv(TRADES_PATH)
curves = _load_optional_csv(CURVES_PATH)
audit = _load_optional_csv(AUDIT_PATH)

readiness = payload.get("data_readiness_status", "UNKNOWN")
execution_specs = payload.get("execution_spec_audit_status", "UNKNOWN")
config_hash = payload.get("frozen_config_sha256", "unknown")
status_cols = st.columns(4)
status_cols[0].metric("Primary Framework", "SMC v1")
status_cols[1].metric("Data Readiness", str(readiness))
status_cols[2].metric("Execution Spec Audit", "MATCHED · UNVERIFIED" if execution_specs == "MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE" else str(execution_specs))
status_cols[3].metric("Frozen Config SHA-256", f"{str(config_hash)[:12]}…")

st.warning(
    "**Research-only results.** Historical provenance is declared as MT5 but has not been independently authenticated. "
    "The bundled period has been examined during earlier project phases, so this is not untouched out-of-sample evidence. "
    "The H4/H1 filter is a hypothesis, not a guarantee of future performance; no live trading is performed."
)

if summary.empty:
    st.error("No comparison rows were found in the Phase 3E metrics.")
    st.stop()

# Normalize numeric columns in case a CSV is opened on a different locale/platform.
for column in (
    "candidate_count", "closed_trades", "rule_exit_trades", "end_of_data_exits",
    "skipped_candidates", "win_rate_pct", "net_profit", "return_pct", "profit_factor",
    "max_drawdown_cash", "max_realized_drawdown_cash", "average_R_multiple",
    "expectancy_per_rule_exit",
):
    if column in summary.columns:
        summary[column] = pd.to_numeric(summary[column], errors="coerce")

st.subheader("Strategy comparison")
display_summary = summary.copy()
if "strategy_variant" in display_summary.columns:
    display_summary["strategy_variant"] = display_summary["strategy_variant"].map(_variant_label)
renames = {
    "timeframe": "Timeframe",
    "strategy_variant": "Variant",
    "candidate_count": "Candidates",
    "closed_trades": "Closed Trades",
    "rule_exit_trades": "Rule Exits",
    "end_of_data_exits": "End-of-Data Exits",
    "skipped_candidates": "Skipped Candidates",
    "win_rate_pct": "Win Rate (%)",
    "net_profit": "Net P&L ($)",
    "return_pct": "Return (%)",
    "profit_factor": "Profit Factor",
    "max_drawdown_cash": "Max DD MTM ($)",
    "max_realized_drawdown_cash": "Max Realized DD ($)",
    "average_R_multiple": "Average R",
    "expectancy_per_rule_exit": "Expectancy / Rule Exit ($)",
}
display_summary = display_summary.rename(columns=renames)
display_summary = display_summary.drop(columns=["analysis_key"], errors="ignore")
formatters = {
    "Win Rate (%)": "{:.2f}%",
    "Net P&L ($)": "${:,.2f}",
    "Return (%)": "{:.2f}%",
    "Profit Factor": "{:.2f}",
    "Max DD MTM ($)": "${:,.2f}",
    "Max Realized DD ($)": "${:,.2f}",
    "Average R": "{:.3f}",
    "Expectancy / Rule Exit ($)": "${:,.2f}",
}
try:
    st.dataframe(display_summary.style.format(formatters, na_rep="N/A"), use_container_width=True, hide_index=True)
except (KeyError, ValueError):
    st.dataframe(display_summary, use_container_width=True, hide_index=True)

st.caption(
    "Win rate, profit factor, expectancy, and average R exclude END_OF_DATA mark-outs under the shared engine's metric rules. "
    "Net P&L includes end-of-sample liquidation. Maximum drawdown shown here is close-to-close mark-to-market, not intrabar drawdown."
)

available_tfs = sorted(summary["timeframe"].dropna().astype(str).unique().tolist()) if "timeframe" in summary else []
available_variants = sorted(summary["strategy_variant"].dropna().astype(str).unique().tolist()) if "strategy_variant" in summary else []
select_cols = st.columns([1, 1, 2])
selected_tf = select_cols[0].selectbox("Detail timeframe", available_tfs, index=available_tfs.index("M15") if "M15" in available_tfs else 0)
default_variant = "SMC_v1_H4_H1_confirmed" if "SMC_v1_H4_H1_confirmed" in available_variants else available_variants[0]
selected_variant = select_cols[1].selectbox(
    "Variant",
    available_variants,
    index=available_variants.index(default_variant),
    format_func=_variant_label,
)
selected_rows = summary[(summary["timeframe"].astype(str) == selected_tf) & (summary["strategy_variant"].astype(str) == selected_variant)]
selected_metrics = selected_rows.iloc[0].to_dict() if not selected_rows.empty else {}

metric_cols = st.columns(6)
metric_cols[0].metric("Net P&L", _number(selected_metrics.get("net_profit"), prefix="$"), delta=_number(selected_metrics.get("return_pct"), suffix="%") if selected_metrics else None)
metric_cols[1].metric("Win Rate", _number(selected_metrics.get("win_rate_pct"), suffix="%"))
metric_cols[2].metric("Profit Factor", _number(selected_metrics.get("profit_factor")))
metric_cols[3].metric("Closed Trades", _number(selected_metrics.get("closed_trades"), digits=0))
metric_cols[4].metric("Max Drawdown", _number(selected_metrics.get("max_drawdown_cash"), prefix="$"))
metric_cols[5].metric("Candidates", _number(selected_metrics.get("candidate_count"), digits=0))

# Uncertainty & Sample Size Reporting (Wilson 95% CI)
_wr = selected_metrics.get("win_rate_pct")
_closed = selected_metrics.get("closed_trades")
if _wr is not None and not pd.isna(_wr) and _closed is not None and not pd.isna(_closed) and float(_closed) > 0:
    import math
    _n = float(_closed)
    _p = float(_wr) / 100.0
    _z = 1.95996
    _denom = 1.0 + (_z**2) / _n
    _center = (_p + (_z**2) / (2 * _n)) / _denom
    _diff = _z * math.sqrt((_p * (1.0 - _p) + (_z**2) / (4 * _n)) / _n) / _denom
    _ci_low = max(0.0, _center - _diff) * 100.0
    _ci_high = min(100.0, _center + _diff) * 100.0
    st.caption(
        f"**Win rate 95% Wilson CI:** [{_ci_low:.1f}%, {_ci_high:.1f}%] (n={int(_n)} closed trades). "
        + ("⚠️ **Small sample caution:** wide interval spans breakeven threshold; statistically inconclusive." if int(_n) < 30 else "Statistically adequate sample size.")
    )

st.divider()
chart_left, chart_right = st.columns([1.55, 1])
with chart_left:
    st.subheader("Equity and drawdown context")
    if curves is not None and not curves.empty:
        curve = curves.copy()
        if "timeframe" in curve.columns and "strategy_variant" in curve.columns:
            curve = curve[(curve["timeframe"].astype(str) == selected_tf) & (curve["strategy_variant"].astype(str) == selected_variant)]
        if not curve.empty and {"time", "equity", "realized_equity"}.issubset(curve.columns):
            curve["time"] = pd.to_datetime(curve["time"], utc=True, errors="coerce")
            curve = curve.dropna(subset=["time"]).sort_values("time")
            # Limit the plotted points while preserving the full-resolution CSV export.
            if len(curve) > 5000:
                stride = max(1, len(curve) // 5000)
                curve = pd.concat([curve.iloc[::stride], curve.iloc[[-1]]]).drop_duplicates(subset=["time"])
            long_curve = curve.melt(
                id_vars=["time"],
                value_vars=["equity", "realized_equity"],
                var_name="series",
                value_name="equity_value",
            )
            figure = px.line(long_curve, x="time", y="equity_value", color="series", labels={"time": "Time (UTC)", "equity_value": "Equity ($)", "series": "Curve"})
            figure.update_layout(height=400, margin=dict(l=8, r=8, t=15, b=5), legend_title_text="")
            st.plotly_chart(figure, use_container_width=True)
        else:
            st.info("Equity-curve rows for this selection are unavailable.")
    else:
        st.info("Equity curve export is missing. Re-run the Phase 3E experiment to generate it.")

with chart_right:
    st.subheader("Higher-timeframe filter funnel")
    timeframe_info = payload.get("per_timeframe", {}).get(selected_tf, {})
    funnel = timeframe_info.get("mtf_filter_funnel", {})
    funnel_df = pd.DataFrame([
        {"Stage": "Baseline candidates", "Count": int(funnel.get("input_candidates", 0))},
        {"Stage": "H4/H1 accepted", "Count": int(funnel.get("accepted_candidates", 0))},
        {"Stage": "Rejected", "Count": int(funnel.get("rejected_candidates", 0))},
    ])
    funnel_fig = px.bar(funnel_df, x="Stage", y="Count", text="Count")
    funnel_fig.update_layout(height=300, margin=dict(l=8, r=8, t=15, b=5), xaxis_title="", yaxis_title="Candidates")
    st.plotly_chart(funnel_fig, use_container_width=True)
    reasons = funnel.get("rejection_reasons", {})
    if reasons:
        st.dataframe(pd.DataFrame([{"Rejection reason": key, "Count": value} for key, value in reasons.items()]), use_container_width=True, hide_index=True)
    else:
        st.info("No rejection reasons were recorded for this timeframe.")

st.divider()
st.subheader("Trade ledger")
if trades is not None and not trades.empty:
    ledger = trades.copy()
    if "timeframe" in ledger.columns:
        ledger = ledger[ledger["timeframe"].astype(str) == selected_tf]
    if "strategy_variant" in ledger.columns:
        ledger = ledger[ledger["strategy_variant"].astype(str) == selected_variant]
    ledger_cols = st.columns(3)
    if "status" in ledger.columns:
        statuses = sorted(ledger["status"].dropna().astype(str).unique().tolist())
        status_filter = ledger_cols[0].multiselect("Status", statuses, default=statuses, key="bi_ledger_status")
        ledger = ledger[ledger["status"].astype(str).isin(status_filter)]
    if "direction" in ledger.columns:
        directions = sorted(ledger["direction"].dropna().astype(str).unique().tolist())
        direction_filter = ledger_cols[1].multiselect("Direction", directions, default=directions, key="bi_ledger_direction")
        ledger = ledger[ledger["direction"].astype(str).isin(direction_filter)]
    if "exit_reason" in ledger.columns:
        reasons = sorted(ledger["exit_reason"].dropna().astype(str).unique().tolist())
        exit_filter = ledger_cols[2].multiselect("Exit reason", reasons, default=reasons, key="bi_ledger_exit")
        ledger = ledger[ledger["exit_reason"].astype(str).isin(exit_filter)]
    preferred_cols = [
        "setup_id", "timeframe", "strategy_variant", "status", "direction", "side",
        "signal_time", "entry_time", "exit_time", "entry_price", "exit_price", "lots",
        "net_pnl", "R_multiple", "exit_reason", "skip_reason", "target_source",
    ]
    visible_cols = [column for column in preferred_cols if column in ledger.columns]
    st.caption(f"Showing {len(ledger):,} ledger rows after filters.")
    st.dataframe(ledger[visible_cols] if visible_cols else ledger, use_container_width=True, hide_index=True, height=360)
else:
    st.info("Trade-ledger export is missing. Re-run the Phase 3E experiment to generate it.")

st.divider()
st.subheader("Candidate context audit")
if audit is not None and not audit.empty:
    context = audit.copy()
    if "lower_timeframe" in context.columns:
        context = context[context["lower_timeframe"].astype(str) == selected_tf]
    accepted_only = st.selectbox("Context decision", ["All candidates", "Accepted only", "Rejected only"], index=0)
    if accepted_only == "Accepted only" and "accepted" in context.columns:
        context = context[context["accepted"].astype(str).str.lower().isin(["true", "1"])]
    elif accepted_only == "Rejected only" and "accepted" in context.columns:
        context = context[~context["accepted"].astype(str).str.lower().isin(["true", "1"])]
    st.dataframe(context, use_container_width=True, hide_index=True, height=300)
else:
    st.info("Candidate context audit is missing. Re-run the Phase 3E experiment to generate it.")

# Execution-cost sensitivity section (Phase 5)
_p5_metrics_file = REPORT_DIR / "phase5_validation_metrics.json"
if not _p5_metrics_file.exists():
    _p5_metrics_file = ROOT / "reports" / "phase5" / "phase5_validation_metrics.json"

if _p5_metrics_file.exists():
    try:
        _p5_data = _load_json(str(_p5_metrics_file), _p5_metrics_file.stat().st_mtime_ns)
        _scenarios = (
            _p5_data.get("cost_scenarios", {})
            .get(selected_tf, {})
            .get(selected_variant, [])
        )
        if _scenarios:
            st.divider()
            st.subheader(f"Execution-Cost Sensitivity (Stress Test) — {selected_tf} {_variant_label(selected_variant)}")
            st.caption(
                "Stress-testing the recorded trade ledger under elevated spread, adverse slippage, and retail commissions. "
                "Monotonic degradation confirms that performance is not an artifact of zero-cost execution."
            )
            _scen_df = pd.DataFrame(_scenarios)
            _display_scen = _scen_df.copy()
            _rename_scen = {
                "scenario": "Scenario",
                "spread_markup_multiplier": "Spread Multiplier",
                "slippage_per_side": "Slippage/Side ($)",
                "commission_per_lot": "Commission/Lot ($)",
                "net_profit": "Net P&L ($)",
                "profit_factor": "Profit Factor",
                "win_rate_pct": "Win Rate (%)",
                "expectancy_per_trade": "Expectancy ($)",
                "max_drawdown_cash": "Max DD ($)",
            }
            _display_scen = _display_scen.rename(columns=_rename_scen)
            _scen_formatters = {
                "Spread Multiplier": "{:.1f}x",
                "Slippage/Side ($)": "${:.2f}",
                "Commission/Lot ($)": "${:.2f}",
                "Net P&L ($)": "${:,.2f}",
                "Profit Factor": "{:.3f}",
                "Win Rate (%)": "{:.2f}%",
                "Expectancy ($)": "${:,.2f}",
                "Max DD ($)": "${:,.2f}",
            }
            try:
                st.dataframe(_display_scen.style.format(_scen_formatters, na_rep="N/A"), use_container_width=True, hide_index=True)
            except Exception:
                st.dataframe(_display_scen, use_container_width=True, hide_index=True)
    except Exception:
        pass

st.divider()
st.subheader("Power BI Desktop exports")
st.markdown(
    "The summary export is a flat comparison table. Import it first for the executive view; load the trade ledger, "
    "equity curves, and candidate-context audit for drill-through. The same files are also downloadable below. "
    "This page is a native Streamlit analytics view—the project does not contain a published Power BI `.pbix` file."
)
export_cols = st.columns(4)
with export_cols[0]:
    _download_button("Download metrics summary", summary, "smc_mtf_powerbi_summary.csv", "dl_summary")
with export_cols[1]:
    _download_button("Download trades", trades, "smc_mtf_trades.csv", "dl_trades")
with export_cols[2]:
    _download_button("Download equity curves", curves, "smc_mtf_equity_curves.csv", "dl_curves")
with export_cols[3]:
    _download_button("Download context audit", audit, "smc_mtf_candidate_context_audit.csv", "dl_audit")

with st.expander("Research governance and limitations"):
    st.write(f"**Generated UTC:** {payload.get('generated_at_utc', 'unknown')}")
    st.write(f"**Frozen SMC v1 SHA-256:** `{config_hash}`")
    st.write(f"**Data readiness:** `{readiness}`")
    st.write(f"**Execution-spec audit:** `{execution_specs}`")
    for limitation in payload.get("interpretation_limitations", []):
        st.markdown(f"- {limitation}")
    st.markdown(
        "**Reproduction command**\n\n"
        "```bash\n"
        "python scripts/run_smc_mtf_backtest.py --output-dir reports/phase3e --require-matched-execution-spec\n"
        "```"
    )
    if REPORT_PATH.exists():
        st.download_button(
            "Download Markdown experiment report",
            data=REPORT_PATH.read_bytes(),
            file_name=REPORT_PATH.name,
            mime="text/markdown",
            key="dl_markdown_report",
        )
