# GoldFlow — Power BI Desktop Data Model Guide

## Scope

GoldFlow now produces a flat, reproducible Phase 3E performance summary and related trade/equity/context tables. The Streamlit page at `pages/3_BI_Dashboard.py` is the interactive in-app BI view. A native Power BI `.pbix` report or Power BI Service publication is not included because it must be created and authenticated in the user's Power BI environment.

## Generate or refresh the source tables

From the repository root:

```bash
python scripts/run_smc_mtf_backtest.py --output-dir reports/phase3e --require-matched-execution-spec
```

The runner validates the frozen SMC v1 config and source readiness before running. It writes:

- `reports/phase3e/smc_mtf_powerbi_summary.csv`
- `reports/phase3e/smc_mtf_trades.csv`
- `reports/phase3e/smc_mtf_equity_curves.csv`
- `reports/phase3e/smc_mtf_candidate_context_audit.csv`
- `reports/phase3e/smc_mtf_metrics.json`

Re-run the command after regenerating the underlying research output. Power BI Desktop can import the CSVs with **Home → Get data → Text/CSV**.

## Tables and relationships

### `smc_mtf_powerbi_summary.csv`

One row per `timeframe` and `strategy_variant`. It contains the main comparison metrics: candidate count, closed trades, win rate, net P&L, return, profit factor, drawdown, average R, and expectancy. `analysis_key` is a unique composite key for the pair, for example `M15|SMC_v1_H4_H1_confirmed`.

### `smc_mtf_trades.csv`

Trade and skip ledger with entry/exit timestamps, direction, stop/target, lots, costs, P&L, exit reason, and a matching `analysis_key`. This allows drill-through from a summary row to its ledger.

### `smc_mtf_equity_curves.csv`

Bar-by-bar mark-to-market and realized equity values with `timeframe`, `strategy_variant`, and matching `analysis_key`. This is the source for equity charts. It is larger than the summary table because the M5 history contains nearly 100,000 bars.

### `smc_mtf_candidate_context_audit.csv`

Each baseline SMC candidate's H4/H1 directions, context availability timestamps, acceptance decision, rejection reason, and `analysis_key` for the H4/H1-confirmed variant. `lower_timeframe` identifies whether the candidate came from M15 or M5.

In **Model view**, create one-to-many relationships from `smc_mtf_powerbi_summary[analysis_key]` to `smc_mtf_trades[analysis_key]`, `smc_mtf_equity_curves[analysis_key]`, and `smc_mtf_candidate_context_audit[analysis_key]`. The summary's `analysis_key` is unique; each detail table can contain many rows per key. Keep the summary table as the one-side of these relationships. If you choose to build a star schema, you can split timeframe and strategy variant into separate dimension tables later.

Set timestamps to Date/Time (UTC where supported), numeric P&L/price columns to Decimal Number, count columns to Whole Number, and win/return percentages to Decimal Number. The exported `win_rate_pct` and `return_pct` values are already expressed as percentage points (for example, `36.36` means 36.36%), not fractions.

## Suggested measures (DAX)

These measures preserve GoldFlow's reporting distinction between rule exits and end-of-data liquidation. Adjust table names if Power BI renames them during import.

```DAX
Net P&L ($) = SUM(smc_mtf_powerbi_summary[net_profit])

Closed Trades = SUM(smc_mtf_powerbi_summary[closed_trades])

Rule-Exit Trades =
CALCULATE(
    COUNTROWS(smc_mtf_trades),
    smc_mtf_trades[status] = "CLOSED",
    smc_mtf_trades[exit_reason] <> "END_OF_DATA"
)

Rule-Exit Wins =
CALCULATE(
    COUNTROWS(smc_mtf_trades),
    smc_mtf_trades[status] = "CLOSED",
    smc_mtf_trades[exit_reason] <> "END_OF_DATA",
    smc_mtf_trades[net_pnl] > 0
)

Win Rate (%) = DIVIDE([Rule-Exit Wins], [Rule-Exit Trades]) * 100

Gross Profit (Rule Exits) =
CALCULATE(
    SUM(smc_mtf_trades[net_pnl]),
    smc_mtf_trades[status] = "CLOSED",
    smc_mtf_trades[exit_reason] <> "END_OF_DATA",
    smc_mtf_trades[net_pnl] > 0
)

Gross Loss (Rule Exits) =
- CALCULATE(
    SUM(smc_mtf_trades[net_pnl]),
    smc_mtf_trades[status] = "CLOSED",
    smc_mtf_trades[exit_reason] <> "END_OF_DATA",
    smc_mtf_trades[net_pnl] < 0
)

Profit Factor (Rule Exits) = DIVIDE([Gross Profit (Rule Exits)], [Gross Loss (Rule Exits)])
```

Use the precomputed `max_drawdown_cash` and `max_realized_drawdown_cash` columns from the summary for the frozen run rather than trying to reconstruct a single drawdown number from a filtered time series without an explicit chronological DAX measure. The standard engine labels its maximum mark-to-market drawdown as close-to-close, not intrabar drawdown.

## Suggested report pages

1. **Executive Overview:** Net P&L, return, win rate, profit factor, max drawdown, closed trades; slicers for timeframe and strategy variant.
2. **Equity & Risk:** Mark-to-market versus realized equity, drawdown context, baseline versus H4/H1-confirmed variant.
3. **Trade Analysis:** Exit-reason distribution, direction split, trade ledger drill-through, cost/P&L inspection.
4. **Signal Quality:** Candidate funnel, accepted/rejected counts, rejection reasons, and H4/H1 context-audit records.
5. **Data Governance:** Readiness status, execution-spec audit status, frozen-config hash, and interpretation limitations from `smc_mtf_metrics.json`.

## Important interpretation rules

- Net P&L includes end-of-data liquidation; win rate, profit factor, expectancy, and average R exclude `END_OF_DATA` mark-outs under the shared engine's rules.
- The H4/H1-confirmed M15 sample contains only 11 accepted candidates. Its observed win rate and profitability are descriptive, not statistically convincing evidence of a repeatable edge.
- M5 remains loss-making in the current historical comparison, including after the H4/H1 filter.
- Dataset provenance is declared as MetaTrader 5 but not independently authenticated. `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE` verifies alignment to captured/default execution assumptions, not the authenticity of OHLC history.
- The bundled period has been examined during earlier research phases. Do not label this report a genuinely untouched holdout or a live-trading result.
