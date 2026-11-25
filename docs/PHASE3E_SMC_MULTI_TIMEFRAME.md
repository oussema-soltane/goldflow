# Phase 3E — Multi-Timeframe SMC Confirmation Experiment

## Purpose

Phase 3E tests whether requiring completed higher-timeframe structure alignment can improve the quality of lower-timeframe SMC setup candidates. The existing frozen SMC v1 configuration remains the baseline; the experiment is implemented as a separate filter and does not silently alter SMC v1 rules.

- **Instrument:** XAUUSD
- **Entry timeframes:** M15 and M5
- **Context timeframes:** H4 and H1
- **Candidate hypothesis:** sweep → opposite CHoCH → order-block retest/rejection
- **Context rule:** at the intended entry timestamp, the latest completed H4 and H1 structure directions must be non-neutral, agree with each other, and match the candidate direction.
- **Execution model:** shared event-driven OHLC engine, with frozen SMC v1 entry/exit and sizing configuration.

## Causal timing contract

The bundled dataset timestamps represent candle-open times. A structure-break event from a higher timeframe is treated as known only at:

`available_at = break_time + source_timeframe_duration`

For each setup, context is queried at `candidate.next_bar_time`, which is the intended next-bar entry open. Only events with `available_at <= entry_time` are eligible. A missing next bar, missing/neutral higher-timeframe state, H4/H1 disagreement, or candidate-direction mismatch rejects the experimental candidate.

This prevents a still-forming H4/H1 candle from influencing an earlier entry. It does not independently prove the correctness of the market data timestamps or authenticate the broker's history.

## Reproduce the experiment

Run from the repository root in the project's configured Python environment:

```bash
python scripts/run_smc_mtf_backtest.py --output-dir reports/phase3e --require-matched-execution-spec
```

To run only one entry timeframe:

```bash
python scripts/run_smc_mtf_backtest.py --timeframes M15 --output-dir reports/phase3e_m15 --require-matched-execution-spec
```

The runner first validates the frozen configuration, audits execution specifications and data readiness, and loads the required H4/H1/entry-timeframe datasets through the existing research data gate. It rejects fatal execution-specification mismatches. The optional `--require-matched-execution-spec` additionally requires the expected captured-defaults audit state.

## Outputs

The runner writes five reproducible artifacts to the chosen output directory:

- `PHASE3E_SMC_MULTI_TIMEFRAME_EXPERIMENT.md` — human-readable comparison, funnel, timing contract, and limitations.
- `smc_mtf_metrics.json` — configuration hash, data/readiness audit, per-timeframe metrics, and both variant summaries.
- `smc_mtf_trades.csv` — baseline and filtered trade ledgers; the variant is explicit and candidate IDs are stable within each timeframe.
- `smc_mtf_equity_curves.csv` — per-bar realized and mark-to-market equity values.
- `smc_mtf_candidate_context_audit.csv` — the H4/H1 directions, context availability timestamps, accept/reject decision, and rejection reason for each candidate.
- `smc_mtf_powerbi_summary.csv` — flat metric rows keyed by `timeframe` and `variant`, ready to import into Power BI Desktop.

The frozen config SHA-256 is embedded in the JSON and Markdown output. Project-local paths inside the audit JSON are saved relative to the repository where possible, avoiding references to the temporary runtime location. The experiment is separate from the existing frozen SMC v1 validation artifacts.

## Implementation and performance work

The SMC engine's liquidity-sweep and order-block lifecycle scans were changed from repeated Pandas row iteration to chunked NumPy checks that stop at the same first qualifying bar. The lifecycle scan retains invalidation-before-mitigation precedence when both conditions occur on a candle. The former liquidity-pool detector also repeatedly searched slices of all prior swings, causing quadratic work; it now uses a price-range segment tree to select the same latest eligible, unpaired prior swing. A deterministic test compares the indexed pairing output with the original backward-scan implementation. The setup candidate detector pre-indexes sweeps and liquidity pools rather than repeatedly filtering full collections.

In the supplied environment, `analyze_smc` on a 5,000-bar M5 sample improved from approximately 7.6 seconds across the measured event stages to approximately 0.47 seconds for the complete analysis. After the liquidity-pool index was added, the 99,999-bar M5 analysis completed in approximately 5.66 seconds in the latest measured run (pool pairing: 0.45 seconds; sweep detection: 0.52 seconds; order-block lifecycle: 0.46 seconds). The event-driven backtester also caches time/OHLC/spread columns as arrays instead of allocating a Pandas row for each of 100,000 bars. These are local implementation timings, not universal benchmarks.

Regression checks include the setup candidate output and funnel matching the pre-optimization implementation on the 5,000-bar sample, targeted tests for lifecycle behavior across the chunk boundary, and the repository-wide test suite.

## Interpretation rules and limitations

- This is an exploratory full-history comparison. The available history has been inspected during earlier project phases and is not a genuinely untouched out-of-sample period.
- Historical sidecars declare MT5 as the source, but independent source authentication is unavailable. The execution-spec audit status `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE` does not authenticate OHLC history.
- The available event and trade counts are not sufficient to establish a stable win rate or strategy edge. Report trade counts, profit factor, expectancy, drawdown, and costs together; do not optimize on win rate alone.
- The H4/H1 filter is an explicit mechanical proxy for directional market structure, not a complete representation of discretionary SMC analysis.
- OHLC backtesting cannot reconstruct the tick-level intrabar path, variable spread at each historical instant, or guarantee live execution outcomes.
- No live orders or automated execution are introduced by this phase.

## Next research gate

Do not promote the filtered variant to the new primary strategy based on this single comparison. First preserve the current version as a hypothesis, inspect the candidate audit and trade ledgers, repeat cost/parameter sensitivity without using a holdout for selection, and collect a future untouched forward period after the rules have been frozen. Keep ICT as a separate benchmark rather than mixing ICT conditions into the SMC engine.
