# GoldFlow Phase 3D.2 — Position Lifecycle and Time-Stop Sensitivity

**Generated UTC:** 2026-10-20T14:40:23.637559+00:00
**Data readiness:** READY_WITH_WARNINGS
**Execution specification audit:** MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE

> This is a frozen-entry-rule execution sensitivity study. It is not a strategy optimization and does not establish profitability.

## Protocol

- Entry, target, stop, spread, slippage, commission, sizing, and collision rules are unchanged across scenarios.
- The no-time-stop baseline is compared against nominal 4h, 8h, 24h, and 48h holding caps by default.
- Stop/target/gap exits have priority; otherwise the time stop closes at the completed bar close when the bar cap is reached.
- The entry bar counts as bar 1. Nominal hours are converted to timeframe bars; actual wall-clock duration may be longer across closures and data gaps.
- Time stops can free concurrency slots, so both accepted entries and skipped candidates may change between scenarios.
- This same bundled history was reviewed earlier; treat this as a diagnostic, not genuine unseen out-of-sample confirmation.

## Results

| TF | Scenario | Max bars | Candidates | Closed | Rule exits | Time stops | EOD exits | Skipped | Rule-exit P&L | EOD P&L | Net P&L | Max DD MTM | Mean held bars |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H4 | no_time_stop | — | 15 | 13 | 13 | 0 | 0 | 2 | $448.73 | $0.00 | $448.73 | $751.76 | 23.15 |
| H4 | max_4h_nominal | 1 | 15 | 14 | 14 | 10 | 0 | 1 | $-378.82 | $0.00 | $-378.82 | $386.11 | 1.00 |
| H4 | max_8h_nominal | 2 | 15 | 14 | 14 | 10 | 0 | 1 | $5.72 | $0.00 | $5.72 | $222.52 | 1.71 |
| H4 | max_24h_nominal | 6 | 15 | 14 | 14 | 9 | 0 | 1 | $-159.58 | $0.00 | $-159.58 | $402.89 | 4.36 |
| H4 | max_48h_nominal | 12 | 15 | 14 | 14 | 7 | 0 | 1 | $-96.59 | $0.00 | $-96.59 | $547.70 | 7.93 |
| H1 | no_time_stop | — | 30 | 27 | 27 | 0 | 0 | 3 | $107.96 | $0.00 | $107.96 | $993.62 | 24.81 |
| H1 | max_4h_nominal | 4 | 30 | 28 | 28 | 22 | 0 | 2 | $-445.78 | $0.00 | $-445.78 | $780.04 | 3.46 |
| H1 | max_8h_nominal | 8 | 30 | 28 | 28 | 17 | 0 | 2 | $-314.41 | $0.00 | $-314.41 | $849.98 | 6.43 |
| H1 | max_24h_nominal | 24 | 30 | 27 | 27 | 8 | 0 | 3 | $-377.09 | $0.00 | $-377.09 | $903.76 | 13.74 |
| H1 | max_48h_nominal | 48 | 30 | 27 | 27 | 4 | 0 | 3 | $-158.67 | $0.00 | $-158.67 | $789.59 | 19.04 |
| M15 | no_time_stop | — | 49 | 36 | 36 | 0 | 0 | 13 | $-884.02 | $0.00 | $-884.02 | $1,505.34 | 39.58 |
| M15 | max_4h_nominal | 16 | 49 | 49 | 49 | 23 | 0 | 0 | $1,311.22 | $0.00 | $1,311.22 | $688.80 | 10.92 |
| M15 | max_8h_nominal | 32 | 49 | 48 | 48 | 13 | 0 | 1 | $754.03 | $0.00 | $754.03 | $1,693.09 | 16.23 |
| M15 | max_24h_nominal | 96 | 49 | 42 | 42 | 3 | 0 | 7 | $1,345.47 | $0.00 | $1,345.47 | $1,949.35 | 26.19 |
| M15 | max_48h_nominal | 192 | 49 | 40 | 40 | 2 | 0 | 9 | $753.19 | $0.00 | $753.19 | $1,815.48 | 32.58 |
| M5 | no_time_stop | — | 42 | 32 | 31 | 0 | 1 | 10 | $-530.02 | $277.68 | $-252.34 | $1,304.86 | 23.94 |
| M5 | max_4h_nominal | 48 | 42 | 38 | 38 | 5 | 0 | 4 | $-781.23 | $0.00 | $-781.23 | $1,782.65 | 16.37 |
| M5 | max_8h_nominal | 96 | 42 | 34 | 33 | 2 | 1 | 8 | $-764.32 | $277.68 | $-486.64 | $1,583.97 | 19.42 |
| M5 | max_24h_nominal | 288 | 42 | 32 | 31 | 0 | 1 | 10 | $-530.02 | $277.68 | $-252.34 | $1,304.86 | 23.94 |
| M5 | max_48h_nominal | 576 | 42 | 32 | 31 | 0 | 1 | 10 | $-530.02 | $277.68 | $-252.34 | $1,304.86 | 23.94 |

## Interpretation safeguards

- P&L still includes explicitly labeled END_OF_DATA liquidations; compare rule-exit P&L and EOD P&L separately.
- Drawdown is close-to-close mark-to-market, not intrabar tick-level drawdown.
- A time stop changes trade management and concurrency, not merely a report filter. Do not choose the best-looking horizon on this same sample and report it as validated.
- Confirm broker symbol contract size, point size, spread interpretation, commission, and slippage before treating simulated cash metrics as broker-equivalent.
- MT5 provenance in sidecars is declared, not independently authenticated.

## Artifacts

- `smc_lifecycle_stress_metrics.json` — scenario metrics.
- `smc_lifecycle_stress_trades.csv` — full scenario-level trade and skip log.
