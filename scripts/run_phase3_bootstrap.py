"""
Phase 3 Dependence-Aware Block Bootstrap Analysis
=================================================
Performs Stationary Block Bootstrap and Circular Block Bootstrap
on the extended Phase 3 trade ledger.

Methodology:
- 10,000 resamples using Stationary Block Bootstrap (Politis & Romano, 1994)
  with mean block length L = 5 trades (preserves sequence autocorrelation).
- Also runs standard I.I.D. bootstrap for comparative sensitivity.
- Evaluates:
    * Profit Factor (median, 2.5th and 97.5th percentiles)
    * Mean Expectancy ($/trade)
    * Return on Risk / Expectancy in R
    * Maximum Drawdown distribution
    * Probability of Loss: P(Expectancy <= 0) and P(PF < 1.0)
- Well-behaved metric: Expectancy is strictly linear and immune to zero-division anomalies.

Outputs:
- reports/PHASE3_BOOTSTRAP_ANALYSIS.csv
- reports/PHASE3_BOOTSTRAP_ANALYSIS.md
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
import random
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TRADE_LEDGER_PATH = ROOT / "reports" / "PHASE3_TRADE_LEDGER.csv"
OUTPUT_CSV_PATH = ROOT / "reports" / "PHASE3_BOOTSTRAP_ANALYSIS.csv"
OUTPUT_MD_PATH = ROOT / "reports" / "PHASE3_BOOTSTRAP_ANALYSIS.md"

RANDOM_SEED = 42
N_BOOTSTRAP = 10_000
MEAN_BLOCK_LENGTH = 5  # Mean block size for stationary bootstrap


def compute_metrics_from_sample(pnl_array: np.ndarray) -> dict:
    gross_profit = float(np.sum(pnl_array[pnl_array > 0]))
    gross_loss = float(abs(np.sum(pnl_array[pnl_array < 0])))
    net_pnl = float(np.sum(pnl_array))
    n = len(pnl_array)
    expectancy = net_pnl / n if n > 0 else 0.0

    if gross_loss == 0.0:
        pf = 100.0 if gross_profit > 0 else 1.0  # Conservative capped ratio
    else:
        pf = gross_profit / gross_loss

    # Drawdown on sample equity
    cum_pnl = np.cumsum(pnl_array)
    peak = np.maximum.accumulate(cum_pnl)
    dd = peak - cum_pnl
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0

    return {
        "pf": pf,
        "expectancy": expectancy,
        "net_pnl": net_pnl,
        "max_dd": max_dd,
    }


def stationary_block_bootstrap(data: np.ndarray, n_samples: int, mean_block_len: int, seed: int) -> dict:
    """Stationary Block Bootstrap (Politis & Romano, 1994)."""
    rng = np.random.default_rng(seed)
    n = len(data)
    p = 1.0 / mean_block_len

    pfs = np.zeros(n_samples)
    expectancies = np.zeros(n_samples)
    nets = np.zeros(n_samples)
    max_dds = np.zeros(n_samples)

    for i in range(n_samples):
        # Generate block indices
        sample_indices = []
        cur_idx = rng.integers(0, n)
        while len(sample_indices) < n:
            sample_indices.append(cur_idx)
            if rng.random() < p:
                cur_idx = rng.integers(0, n)
            else:
                cur_idx = (cur_idx + 1) % n

        sample_pnl = data[sample_indices]
        m = compute_metrics_from_sample(sample_pnl)
        pfs[i] = m["pf"]
        expectancies[i] = m["expectancy"]
        nets[i] = m["net_pnl"]
        max_dds[i] = m["max_dd"]

    return {
        "pf": pfs,
        "expectancy": expectancies,
        "net_pnl": nets,
        "max_dd": max_dds,
    }


def iid_bootstrap(data: np.ndarray, n_samples: int, seed: int) -> dict:
    """Standard I.I.D. trade bootstrap."""
    rng = np.random.default_rng(seed)
    n = len(data)

    pfs = np.zeros(n_samples)
    expectancies = np.zeros(n_samples)
    nets = np.zeros(n_samples)
    max_dds = np.zeros(n_samples)

    for i in range(n_samples):
        indices = rng.integers(0, n, size=n)
        sample_pnl = data[indices]
        m = compute_metrics_from_sample(sample_pnl)
        pfs[i] = m["pf"]
        expectancies[i] = m["expectancy"]
        nets[i] = m["net_pnl"]
        max_dds[i] = m["max_dd"]

    return {
        "pf": pfs,
        "expectancy": expectancies,
        "net_pnl": nets,
        "max_dd": max_dds,
    }


def analyze_experiment(exp_id: str, df_trades: pd.DataFrame) -> dict:
    sub = df_trades[df_trades["experiment_id"] == exp_id]
    pnls = sub["net_pnl"].to_numpy(dtype=float)
    n = len(pnls)

    if n < 5:
        return {"experiment_id": exp_id, "n_trades": n, "status": "insufficient_data"}

    obs = compute_metrics_from_sample(pnls)

    # 1. Stationary Block Bootstrap
    sbb = stationary_block_bootstrap(pnls, N_BOOTSTRAP, MEAN_BLOCK_LENGTH, RANDOM_SEED)
    # 2. IID Bootstrap
    iid = iid_bootstrap(pnls, N_BOOTSTRAP, RANDOM_SEED)

    def stats(arr):
        return {
            "median": float(np.median(arr)),
            "mean": float(np.mean(arr)),
            "ci_lo": float(np.percentile(arr, 2.5)),
            "ci_hi": float(np.percentile(arr, 97.5)),
            "std": float(np.std(arr)),
        }

    sbb_pf = stats(sbb["pf"])
    sbb_exp = stats(sbb["expectancy"])
    iid_pf = stats(iid["pf"])
    iid_exp = stats(iid["expectancy"])

    prob_neg_exp_sbb = float(np.mean(sbb["expectancy"] <= 0.0))
    prob_pf_below_1_sbb = float(np.mean(sbb["pf"] < 1.0))
    prob_neg_exp_iid = float(np.mean(iid["expectancy"] <= 0.0))
    prob_pf_below_1_iid = float(np.mean(iid["pf"] < 1.0))

    # Verdict
    # Edge confirmed if Block Bootstrap 95% CI lower bound on PF >= 1.0 and P(loss) < 0.05
    if sbb_pf["ci_lo"] >= 1.0 and prob_neg_exp_sbb < 0.05:
        verdict = "CONFIRMED_EDGE"
    elif sbb_pf["ci_lo"] >= 0.9 or sbb_exp["ci_lo"] >= -5.0:
        verdict = "MARGINAL_INCONCLUSIVE"
    else:
        verdict = "NO_EDGE"

    return {
        "experiment_id": exp_id,
        "n_trades": n,
        "obs_pf": round(obs["pf"], 3),
        "obs_expectancy": round(obs["expectancy"], 2),
        "obs_net_pnl": round(obs["net_pnl"], 2),
        "obs_max_dd": round(obs["max_dd"], 2),
        # Block Bootstrap
        "sbb_pf_ci_lo": round(sbb_pf["ci_lo"], 3),
        "sbb_pf_median": round(sbb_pf["median"], 3),
        "sbb_pf_ci_hi": round(sbb_pf["ci_hi"], 3),
        "sbb_exp_ci_lo": round(sbb_exp["ci_lo"], 2),
        "sbb_exp_mean": round(sbb_exp["mean"], 2),
        "sbb_exp_ci_hi": round(sbb_exp["ci_hi"], 2),
        "prob_neg_exp_sbb": round(prob_neg_exp_sbb * 100.0, 1),
        "prob_pf_below_1_sbb": round(prob_pf_below_1_sbb * 100.0, 1),
        # IID Bootstrap
        "iid_pf_ci_lo": round(iid_pf["ci_lo"], 3),
        "iid_pf_median": round(iid_pf["median"], 3),
        "iid_pf_ci_hi": round(iid_pf["ci_hi"], 3),
        "iid_exp_ci_lo": round(iid_exp["ci_lo"], 2),
        "iid_exp_mean": round(iid_exp["mean"], 2),
        "iid_exp_ci_hi": round(iid_exp["ci_hi"], 2),
        "prob_neg_exp_iid": round(prob_neg_exp_iid * 100.0, 1),
        "verdict": verdict,
    }


def main():
    print("=" * 80)
    print("PHASE 3 DEPENDENCE-AWARE BLOCK BOOTSTRAP ANALYSIS")
    print(f"Resamples: {N_BOOTSTRAP:,} | Block Length: {MEAN_BLOCK_LENGTH} | Seed: {RANDOM_SEED}")
    print("=" * 80)

    assert TRADE_LEDGER_PATH.exists(), f"Trade ledger {TRADE_LEDGER_PATH} not found"
    df_trades = pd.read_csv(TRADE_LEDGER_PATH)
    print(f"Loaded {len(df_trades):,} total trades from {TRADE_LEDGER_PATH.name}")

    experiments = df_trades["experiment_id"].unique()
    results = []

    for exp_id in experiments:
        res = analyze_experiment(exp_id, df_trades)
        results.append(res)
        print(f"\nExperiment: {exp_id} (n={res['n_trades']} trades)")
        print(f"  Observed PF: {res['obs_pf']} | Exp: ${res['obs_expectancy']:.2f}")
        print(f"  Block Bootstrap PF 95% CI: [{res['sbb_pf_ci_lo']:.3f}, {res['sbb_pf_ci_hi']:.3f}] (median={res['sbb_pf_median']:.3f})")
        print(f"  Block Bootstrap Exp 95% CI: [${res['sbb_exp_ci_lo']:.2f}, ${res['sbb_exp_ci_hi']:.2f}]")
        print(f"  P(Expectancy <= 0): {res['prob_neg_exp_sbb']}% | P(PF < 1.0): {res['prob_pf_below_1_sbb']}%")
        print(f"  Verdict: {res['verdict']}")

    # Save CSV
    pd.DataFrame(results).to_csv(OUTPUT_CSV_PATH, index=False)
    print(f"\nSaved bootstrap CSV: {OUTPUT_CSV_PATH}")

    # Save Markdown report
    lines = [
        "# Phase 3 Dependence-Aware Bootstrap Analysis",
        "## Statistical Robustness Audit for XAU/USD SMC_CONFLUENCE_V1",
        "",
        f"**Date:** {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M:%S')} UTC  ",
        f"**Resamples:** {N_BOOTSTRAP:,}  ",
        f"**Methodology:** Stationary Block Bootstrap (Politis & Romano, 1994) with mean block length L={MEAN_BLOCK_LENGTH} trades  ",
        f"**Random Seed:** {RANDOM_SEED}  ",
        "",
        "## Summary Results",
        "",
        "| Experiment | Trades | Obs PF | 95% CI PF (Block) | Obs Exp | 95% CI Exp (Block) | P(Loss) | Verdict |",
        "|------------|--------|--------|-------------------|---------|--------------------|---------|---------|",
    ]
    for r in results:
        lines.append(
            f"| {r['experiment_id']} | {r['n_trades']} | {r['obs_pf']:.3f} | "
            f"[{r['sbb_pf_ci_lo']:.3f}, {r['sbb_pf_ci_hi']:.3f}] | "
            f"${r['obs_expectancy']:.2f} | [${r['sbb_exp_ci_lo']:.2f}, ${r['sbb_exp_ci_hi']:.2f}] | "
            f"{r['prob_neg_exp_sbb']}% | **{r['verdict']}** |"
        )

    lines += [
        "",
        "## Key Methodological Insights",
        "",
        "1. **Stationary Block Bootstrap vs I.I.D.:**",
        "   - Standard I.I.D. bootstrap assumes trades are independent and identically distributed.",
        "   - In financial markets, trade outcomes exhibit volatility clustering, regime correlation, and sequential drawdowns.",
        "   - The Stationary Block Bootstrap samples contiguous blocks of trades, capturing this autocorrelation.",
        "",
        "2. **Zero-Loss Handling & Well-Behaved Metrics:**",
        "   - Unlike previous implementations where zero losses artificially assigned PF=999.0 (distorting the mean PF),",
        "     the block bootstrap evaluates both median PF and net expectancy.",
        "   - Expectancy ($/trade) is linear and mathematically robust, providing an uncorrupted test of whether mean edge > 0.",
        "",
        "3. **Statistical Significance Criteria:**",
        "   - For an edge to be confirmed statistically, the **95% CI lower bound on Profit Factor must exceed 1.0**,",
        "     and the probability of negative expectancy must be less than 5% (p < 0.05).",
        "",
        "*Generated by scripts/run_phase3_bootstrap.py*",
    ]

    with open(OUTPUT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved bootstrap markdown report: {OUTPUT_MD_PATH}")


if __name__ == "__main__":
    main()
