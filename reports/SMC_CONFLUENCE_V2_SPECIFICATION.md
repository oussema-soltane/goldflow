# SMC_CONFLUENCE_V2 — FORMAL ARCHITECTURAL SPECIFICATION
**Strategy Identifier:** `SMC_CONFLUENCE_V2`  
**Configuration File:** `configs/candidate_specs/smc_confluence_v2.json`  
**Configuration SHA-256:** `1eaa40373f9e89c3f65fb216badd6604fa7df428c973cf495902bf8a0bd7eb8c`  
**Base Strategy:** `SMC_CONFLUENCE`  
**Registration Date:** 2026-11-17  
**Governance Status:** **PRE-REGISTERED (FROZEN PRIOR TO OUT-OF-SAMPLE EVALUATION)**  

---

## 1. Executive Summary & Design Rationale

`SMC_CONFLUENCE_V2` is an institutional quantitative trading strategy engineered for XAU/USD. It builds upon the structural mechanics of Smart Money Concepts (SMC) while directly rectifying the empirical failure modes identified during the Phase 3 and Phase 3F forensic audits:

1. **Failure Mode 1 (Ranging Market Decay):** In unconstrained SMC, taking order block mitigation entries into choppy, low-volatility ranges generated a 63.5% loss rate and collapsed expectancy by 85% to \$1.84/trade.  
   *Remediation:* Formal **M15 ADX(14) > 22.0 Regime Gating** to suppress trade generation during consolidating markets.
2. **Failure Mode 2 (Asian & Off-Hours Capital Destruction):** Trading outside high-liquidity sessions produced -$429.16 net losses ($\text{PF} = 0.630$).  
   *Remediation:* Strict **Session Gating** restricting entries to the London open and New York overlap sessions (07:00–17:00 UTC).
3. **Failure Mode 3 (Counter-Trend Whipsaws):** Baseline SMC without higher-timeframe context lost -$298.78.  
   *Remediation:* Mandatory **H4 & D1 Structural Trend Alignment** via causal event-driven timelines.
4. **Failure Mode 4 (Premature Stop Outs from Noise):** Tight structural stops were vulnerable to institutional spread spikes.  
   *Remediation:* **$1.5 \times \text{ATR}(14)$ Dynamic Stop Buffering**.

---

## 2. Structural Market Architecture & Indicator Definitions

### 2.1 Execution Timeframe
- **Primary Execution Timeframe:** 15-Minute (M15).
- **Higher Context Timeframes:** 4-Hour (H4) and Daily (D1).

### 2.2 Swing Pivots & Structure Confirmation
- **Fractal Window ($W$):** $W = 2$ on M15; $W = 3$ on H4 and D1.
- **Swing Confirmation:** A swing high/low at bar $i$ is only knowable at bar $i + W$.
- **Structure Breaks (BOS / CHoCH):** Requires a candle close beyond a confirmed swing level. A break at bar $i$ requires `confirmed_index < i`.

### 2.3 Higher-Timeframe Directional Bias
- Evaluated via causal timeline queries (`at(decision_time)`).
- `available_at = break_time + tf_duration` ensures only fully closed H4 and D1 candles are consulted.
- **Long Requirement:** D1 Trend == BULLISH AND H4 Trend == BULLISH.
- **Short Requirement:** D1 Trend == BEARISH AND H4 Trend == BEARISH.
- If D1 and H4 conflict, or either is NEUTRAL, the market state is classified as conflicting and all trades are blocked (fail-closed).

### 2.4 Session Liquidity Filter
- **Allowed Hours:** 07:00:00 UTC to 16:59:59 UTC.
- Entries outside this window (including the 21:00–22:00 UTC daily rollover and Asian session) are rejected.

### 2.5 Volatility & Regime Filter (ADX Gating)
- **Indicator:** Average Directional Index (ADX) with 14-period Wilder smoothing.
- **Condition:** $\text{ADX}(14) > 22.0$ at signal bar close.
- Entries where $\text{ADX}(14) \le 22.0$ are rejected as low-momentum consolidation.

---

## 3. Order Execution & Trade Lifecycle Management

### 3.1 Entry Mechanics
- **Trigger:** Retracement to and mitigation of an active unmitigated Order Block aligned with the confirmed structure shift.
- **Execution Bar:** Bar $i+1$ Open.
- **Long Execution Price:** $\text{Ask}_{\text{open}} + \text{Slippage} = \text{Open} + \text{Spread} + \$0.05$.
- **Short Execution Price:** $\text{Bid}_{\text{open}} - \text{Slippage} = \text{Open} - \$0.05$.

### 3.2 Stop Loss Formulation
$$\text{Long Stop} = \min(\text{OB Low}, \text{Swing Low}) - (1.5 \times \text{ATR}_{14})$$
$$\text{Short Stop} = \max(\text{OB High}, \text{Swing High}) + (1.5 \times \text{ATR}_{14})$$

### 3.3 Take Profit Formulation
- Fixed Risk-to-Reward Ratio: $R:R = 2.0$.
$$\text{Target} = \text{Entry} \pm (2.0 \times |\text{Entry} - \text{Stop}|)$$

### 3.4 Breakeven Migration
- When unrealized favorable excursion reaches $+1.5R$:
$$\text{New Stop} = \text{Entry Price} \pm \$0.05 \text{ (Friction Buffer)}$$

### 3.5 Economic News Blackout
- Blackout window: 30 minutes before through 30 minutes after scheduled high-impact USD economic events (NFP, CPI, PPI, FOMC).

---

## 4. Risk Governance & Capital Allocation Rules

- **Initial Equity:** \$10,000.00 USD.
- **Risk Fraction per Trade:** $0.5\%$ (50 basis points) of realized equity at bar open.
- **Maximum Concurrency:** 1 open trade at any time.
- **Maximum Daily Loss Limit:** $2.0\%$ of starting daily equity (hard circuit breaker).
- **Prohibited Tactics:** Zero martingale, zero grid trading, zero averaging down.

---

## 5. Pre-Registered Promotion Gates (Institutional Standard)

To graduate from Research Candidate to Demo Incubation, `SMC_CONFLUENCE_V2` must satisfy ALL six pre-registered criteria on a truly unseen dataset:

1. **Sample Size:** $N \ge 100$ completed trades on the out-of-sample dataset.
2. **Walk-Forward Consistency:** $\ge 70.0\%$ of rolling out-of-sample folds must be profitable.
3. **Out-of-Sample Profit Factor:** Aggregate out-of-sample $\text{PF} \ge 1.30$.
4. **Statistical Significance:** Stationary Block Bootstrap ($L=5$) 95% CI Lower Bound for Profit Factor must be strictly $> 1.000$, with Student's $t$-test $p$-value $< 0.05$.
5. **Drawdown Tolerance:** Maximum Peak-to-Trough Drawdown $\le 10.0\%$.
6. **Execution Cost Robustness:** Strategy must remain profitable when simulated execution spread is doubled to \$0.40/oz and slippage is doubled to \$0.10/side.
