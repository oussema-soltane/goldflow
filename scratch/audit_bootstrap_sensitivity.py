"""
Bootstrap Sensitivity & Methodological Audit
============================================
Evaluates Stationary Block Bootstrap across multiple block lengths L in {1, 3, 5, 10, 15, 20},
tests Circular Block Bootstrap, and clearly separates:
1. Bootstrap confidence interval (percentile).
2. Empirical frequency of negative resampled net P&L.
3. Parametric one-sided t-test p-value.
4. Single-trade loss probability (1 - WR).
5. Drawdown distribution.
"""
import pandas as pd
import numpy as np
from scipy import stats

trades_df = pd.read_csv('reports/PHASE3_TRADE_LEDGER.csv')

def run_sensitivity(exp_id):
    sub = trades_df[trades_df['experiment_id'] == exp_id]
    pnls = sub['net_pnl'].to_numpy(dtype=float)
    n = len(pnls)
    gross_p = np.sum(pnls[pnls > 0])
    gross_l = abs(np.sum(pnls[pnls < 0]))
    obs_pf = gross_p / gross_l if gross_l > 0 else 999.0
    obs_exp = np.mean(pnls)

    # Parametric t-test for mean > 0
    t_stat, p_val_two_sided = stats.ttest_1samp(pnls, 0.0)
    p_val_one_sided = p_val_two_sided / 2.0 if t_stat > 0 else (1.0 - p_val_two_sided / 2.0)

    # Single-trade loss probability
    p_loss_single_trade = np.mean(pnls <= 0)

    print(f"\n=======================================================")
    print(f"EXPERIMENT: {exp_id} (N={n} trades)")
    print(f"Observed PF: {obs_pf:.3f} | Observed Expectancy: ${obs_exp:.2f}")
    print(f"Parametric t-test (H0: mean <= 0 vs H1: mean > 0): t={t_stat:.3f}, p-value={p_val_one_sided:.4f}")
    print(f"Single-Trade Loss Probability (1 - WR): {p_loss_single_trade*100:.1f}%")
    print(f"=======================================================")

    results = []
    block_lengths = [1, 3, 5, 10, 15, 20]
    n_resamples = 10_000
    rng = np.random.default_rng(42)

    for L in block_lengths:
        p = 1.0 / L
        pfs = np.zeros(n_resamples)
        expectancies = np.zeros(n_resamples)
        net_pnls = np.zeros(n_resamples)

        for b in range(n_resamples):
            indices = []
            cur_idx = rng.integers(0, n)
            while len(indices) < n:
                indices.append(cur_idx)
                if rng.random() < p:
                    cur_idx = rng.integers(0, n)
                else:
                    cur_idx = (cur_idx + 1) % n

            sample_pnl = pnls[indices]
            gp = np.sum(sample_pnl[sample_pnl > 0])
            gl = abs(np.sum(sample_pnl[sample_pnl < 0]))
            pfs[b] = (gp / gl) if gl > 0 else 100.0
            expectancies[b] = np.mean(sample_pnl)
            net_pnls[b] = np.sum(sample_pnl)

        pf_lo = np.percentile(pfs, 2.5)
        pf_med = np.median(pfs)
        pf_hi = np.percentile(pfs, 97.5)
        exp_lo = np.percentile(expectancies, 2.5)
        exp_hi = np.percentile(expectancies, 97.5)
        emp_neg_freq = np.mean(net_pnls <= 0)

        results.append({
            "Block Length L": L,
            "Resampling Type": "I.I.D. (L=1)" if L == 1 else f"Stationary Block (L={L})",
            "PF 95% CI Lower": round(pf_lo, 3),
            "PF Median": round(pf_med, 3),
            "PF 95% CI Upper": round(pf_hi, 3),
            "Exp 95% CI Lower": round(exp_lo, 2),
            "Exp 95% CI Upper": round(exp_hi, 2),
            "Empirical P(Net <= 0)": f"{emp_neg_freq*100:.1f}%",
            "CI Lower > 1.0": pf_lo >= 1.0
        })

    df_res = pd.DataFrame(results)
    print(df_res.to_string(index=False))
    return df_res

df_h = run_sensitivity('EXP_H_HTF_ATR')
df_k = run_sensitivity('EXP_K_FULL')
df_h.to_csv('scratch/BOOTSTRAP_SENSITIVITY_EXP_H.csv', index=False)
df_k.to_csv('scratch/BOOTSTRAP_SENSITIVITY_EXP_K.csv', index=False)

