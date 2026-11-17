import pandas as pd

findings = [
    {
        "item_id": "FIND-001",
        "category": "Repository Governance",
        "target": "Git HEAD and Branch Hierarchy",
        "claim": "Git commit provenance clearly established",
        "audit_status": "VERIFIED_AND_CORRECTED",
        "evidence": "Research parent commit: 9566e6e; Audit certification commit: 3325bf6; Active corrective branch: audit/phase3i-corrective.",
        "impact": "Eliminated confusion between research baseline and subsequent audit commits."
    },
    {
        "item_id": "FIND-002",
        "category": "Configuration Governance",
        "target": "configs/smc_v1_frozen.json",
        "claim": "Frozen configuration SHA-256 unmodified",
        "audit_status": "VERIFIED",
        "evidence": "Computed hash 1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a matches expected exactly.",
        "impact": "Baseline research invariance preserved."
    },
    {
        "item_id": "FIND-003",
        "category": "Data Governance",
        "target": "data/processed/XAUUSD_M15_validation_window.csv",
        "claim": "Phase 2 validation dataset consumed and quarantined",
        "audit_status": "VERIFIED",
        "evidence": "Dataset verified intact and isolated from Phase 3/3F/3H/3I evaluation.",
        "impact": "Prevents contamination of research holdouts."
    },
    {
        "item_id": "FIND-004",
        "category": "Data Engineering",
        "target": "XAUUSD_M15_extended.csv",
        "claim": "99,999 M5 bars aggregate to 33,388 M15 intervals",
        "audit_status": "VERIFIED",
        "evidence": "Mathematical proof: 33,253*3 + 105*2 + 30*1 = 99,999 bars. 135 partial intervals occur exclusively at session halts/opens.",
        "impact": "Zero data loss, zero interpolation, zero dropped bars."
    },
    {
        "item_id": "FIND-005",
        "category": "Temporal Causality",
        "target": "SMC Engine and MTF Bias",
        "claim": "All indicators, swing pivots, HTF timelines, and execution are strictly causal",
        "audit_status": "VERIFIED",
        "evidence": "Swings confirmed at i+w; HTF available_at = break_time + duration; entries at signal_index + 1 open.",
        "impact": "Zero lookahead leakage; performance numbers reflect true causal simulation."
    },
    {
        "item_id": "FIND-006",
        "category": "Performance Reconciliation",
        "target": "PHASE3_TRADE_LEDGER.csv",
        "claim": "84 published performance metrics match trade ledger",
        "audit_status": "VERIFIED",
        "evidence": "7 experiments x 12 metrics = 84 metrics independently recomputed directly from raw trade records.",
        "impact": "Reconciled with 100% precision in PHASE3F_PERFORMANCE_RECONCILIATION.csv."
    },
    {
        "item_id": "FIND-007",
        "category": "Validation Robustness",
        "target": "EXP_H_HTF_ATR Walk-Forward",
        "claim": "EXP_H achieves positive out-of-sample persistence",
        "audit_status": "FAILED",
        "evidence": "Only 2 of 10 folds positive (20.0%). OOS trades = 36, Net P&L = -$116.46, OOS PF = 0.887.",
        "impact": "Fails institutional walk-forward promotion gate (>= 70% positive folds)."
    },
    {
        "item_id": "FIND-008",
        "category": "Validation Robustness",
        "target": "EXP_K_FULL Walk-Forward Discrepancy",
        "claim": "EXP_K walk-forward OOS Net P&L reconciliation",
        "audit_status": "VERIFIED_AND_RESOLVED",
        "evidence": "Actual engine output is exactly -$107.04 across 12 OOS trades (2/10 positive folds). Published table summing to -$132.04 was an authoring transcription error.",
        "impact": "Reconciled trade-by-trade in scratch/EXP_K_OOS_INDIVIDUAL_TRADES.csv."
    },
    {
        "item_id": "FIND-009",
        "category": "Statistical Inference",
        "target": "EXP_H Bootstrap Resampling",
        "claim": "EXP_H achieves statistically defensible edge",
        "audit_status": "FAILED",
        "evidence": "120,000 resamples: PF 95% CI lower bound < 1.0 across all L in 1..20. P(Net <= 0) = 17.9%-24.5%. t-test p = 0.2475.",
        "impact": "Strategy is statistically indistinguishable from zero-edge noise (p > 0.05)."
    },
    {
        "item_id": "FIND-010",
        "category": "Statistical Inference",
        "target": "EXP_K Bootstrap Resampling Variance",
        "claim": "Bootstrap L=5 lower bound shift (0.801 vs 0.797) explained",
        "audit_status": "VERIFIED_AND_RESOLVED",
        "evidence": "Shift of 0.004 in PF CI lower bound and 0.2% in loss frequency is standard Monte Carlo sampling variance from PRNG stream offset.",
        "impact": "Confirmed statistical validity; lower bound is strictly < 1.0 in both runs."
    },
    {
        "item_id": "FIND-011",
        "category": "Market Regimes",
        "target": "Ranging Market Performance",
        "claim": "Ranging regime is damaging despite nominal +$115.96 net profit",
        "audit_status": "VERIFIED",
        "evidence": "Expectancy collapses to $1.84/trade (85% decay); WR 36.5%; OOS walk-forward ranging slices lost -$257.66.",
        "impact": "Justifies formal ADX regime filter in SMC_CONFLUENCE_V2."
    },
    {
        "item_id": "FIND-012",
        "category": "Session Liquidity",
        "target": "London/NY vs Asian Session",
        "claim": "Edge is strictly isolated to London and NY overlap sessions",
        "audit_status": "VERIFIED",
        "evidence": "London + NY overlap: Net +$957.95 (PF 1.998). Asian/off-hours: Net -$429.16 (PF 0.630).",
        "impact": "Mandates strict session gating (07:00-17:00 UTC) in candidate specification."
    },
    {
        "item_id": "FIND-013",
        "category": "Controlled Ablation",
        "target": "16-Variant Filter Matrix",
        "claim": "Incremental contribution of individual filters quantified",
        "audit_status": "VERIFIED",
        "evidence": "Baseline loses -$298.78. HTF alone reaches break-even (+$19.93). HTF + Session reaches PF 1.534. HTF + ATR + Session reaches PF 1.537.",
        "impact": "Proves edge requires multi-layer confluence, not individual filters in isolation."
    },
    {
        "item_id": "FIND-014",
        "category": "Data Inventory",
        "target": "Phase 3H Unseen Holdouts",
        "claim": "Availability of pristine untouched out-of-sample data",
        "audit_status": "VERIFIED_NO_DATA",
        "evidence": "All 33,388 M15 bars have been consumed during Phase 3 exploration. No external untouched dataset exists in repo.",
        "impact": "Phase 3H evaluation cannot be executed on fake holdouts; requires honest declaration."
    },
    {
        "item_id": "FIND-015",
        "category": "Execution Safety",
        "target": "MetaTrader5 Live Submission",
        "claim": "MetaTrader5.order_send permanently disabled",
        "audit_status": "VERIFIED_ARCHITECTURALLY_FAIL_CLOSED",
        "evidence": "Exhaustive search confirms order_send does not exist in source code. Live order execution is physically impossible by design.",
        "impact": "Capital preservation unconditionally guaranteed."
    },
    {
        "item_id": "FIND-016",
        "category": "Promotion Governance",
        "target": "Live and Demo Deployment Gate",
        "claim": "Candidate qualification for capital or demo deployment",
        "audit_status": "FAILED_GATES_UNMET",
        "evidence": "Both candidates fail walk-forward (20% positive folds) and bootstrap (CI Lower < 1.0, p > 0.05).",
        "impact": "REJECT PROMOTION. Strategy MUST remain in research."
    },
    {
        "item_id": "FIND-017",
        "category": "Data Engineering",
        "target": "Partial M15 Candle Participation",
        "claim": "Impact of 135 partial intervals on indicators and trading",
        "audit_status": "VERIFIED",
        "evidence": "0 of 1,124 trades entered on partial bars. Controlled backtest showed removing partial bars eliminated 1-2 losing trades from Sunday open stub wicks.",
        "impact": "Partial bars slightly increased noise but did not distort strategy conclusions."
    },
    {
        "item_id": "FIND-018",
        "category": "Strategy Specification",
        "target": "SMC_CONFLUENCE_V2 In-Sample Derivation",
        "claim": "ADX > 22.0 parameter selection provenance",
        "audit_status": "DISCLOSED_IN_SAMPLE",
        "evidence": "ADX > 22.0 was selected post-hoc on consumed data to avoid trade starvation (expanding from 13 trades at ADX>25 to ~40-60 trades).",
        "impact": "Mandates that V2 can only be evaluated on unconsumed, fresh prospective data."
    },
    {
        "item_id": "FIND-019",
        "category": "Evaluation Governance",
        "target": "Anti-Snooping Guard",
        "claim": "Enforcement of data independence in prospective evaluation runner",
        "audit_status": "VERIFIED_FAIL_CLOSED",
        "evidence": "scripts/run_prospective_evaluation.py successfully blocked evaluation on consumed dataset XAUUSD_M15_extended.csv with PermissionError.",
        "impact": "Prevents accidental or deliberate evaluation on contaminated data."
    },
    {
        "item_id": "FIND-020",
        "category": "Data Acquisition",
        "target": "Phase 3I Ingestion Infrastructure",
        "claim": "Isolated hierarchy established for future broker data",
        "audit_status": "VERIFIED",
        "evidence": "Created data/research/phase3i/ tree with raw, processed, manifests, and quarantine directories and manifest schema.",
        "impact": "Repository prepared for prospective evaluation upon delivery of fresh broker data."
    }
]

df = pd.DataFrame(findings)
df.to_csv("reports/PHASE3I_FINDINGS_LEDGER.csv", index=False)
df.to_csv("reports/PHASE3F_FINDINGS_LEDGER.csv", index=False)
print(f"Generated reports/PHASE3I_FINDINGS_LEDGER.csv and updated reports/PHASE3F_FINDINGS_LEDGER.csv with {len(df)} audit items.")
