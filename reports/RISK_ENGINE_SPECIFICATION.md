# GoldFlow — Capital Preservation & Risk Management Engine Specification
## Technical Specification & Operational Rules for Systematic XAU/USD Trading

**Package:** `src.risk`  
**Version:** 1.0.0  
**Target Instrument:** Spot Gold (XAU/USD)  
**Contract Standard:** 100 Troy Ounces per Standard Lot | Tick Size: $0.01 ($1.00 per standard lot)  
**Verification Suite:** `tests/test_risk_engine.py`, `tests/test_lot_sizing.py` (100% Pass)  

---

## 1. Architectural Philosophy: Capital Preservation First

Systematic trading on gold cannot rely on pattern detection alone. Gold is prone to high volatility, wide bid-ask spreads during market transitions, and violent macroeconomic liquidation spikes. The GoldFlow Risk Engine enforces a strict hierarchy:

> **"PROTECT CAPITAL FIRST. PROVE THE EDGE SECOND. AUTOMATE EXECUTION THIRD."**

Every trade candidate must pass through four sequential risk gates before any order can be dispatched:
1. **Concurrency Gate:** Max 1 concurrent open position across the account (no pyramiding).
2. **Spread Threshold Gate:** Bid-Ask spread must not exceed **$0.35/oz** at the moment of entry.
3. **Daily Loss Circuit Breaker:** Daily cumulative realized loss must not exceed **2.0%** of account equity.
4. **Lot Sizing & Minimum Lot Gate:** Exact downward-floored position sizing respecting the **0.5%** risk budget.

If any single gate fails, the trade is rejected immediately (**FAIL-CLOSED**).

---

## 2. Mathematical Lot Sizing Engine (`src/risk/lot_sizing.py`)

### 2.1 Position Sizing Formula
For any trade with entry price $P_{\text{entry}}$, stop loss $P_{\text{stop}}$, and account equity $E$:

$$\text{Risk Budget (\USD)} = E \times \text{risk\_per\_trade\_pct} \quad (\text{default: } 0.005 = 0.5\%)$$

$$\text{Risk Distance (Points)} = |P_{\text{entry}} - P_{\text{stop}}|$$

$$\text{Dollar Risk per Standard Lot} = \text{Risk Distance} \times 100.0 + 2 \times \text{commission\_per\_lot}$$

$$\text{Raw Lots} = \min\left(\text{max\_lots}, \frac{\text{Risk Budget}}{\text{Dollar Risk per Standard Lot}}\right)$$

### 2.2 Strict Downward Floor Rounding
To guarantee that the planned cash risk never exceeds the maximum allowable budget under lot step constraints:

$$\text{Executable Lots} = \left\lfloor \frac{\text{Raw Lots}}{\text{lot\_step}} \right\rfloor \times \text{lot\_step} \quad (\text{lot\_step} = 0.01)$$

### 2.3 Rejection Conditions:
- If $\text{Executable Lots} < \text{min\_lot}$ ($0.01$): Reject with `REJECTED_STOP_TOO_WIDE_FOR_MIN_LOT`.
- If $\text{Risk Distance} \le 0$: Reject with `REJECTED_INVALID_STOP_DISTANCE`.
- If $E \le 0$: Reject with `REJECTED_INSUFFICIENT_EQUITY`.

---

## 3. Daily Drawdown Circuit Breaker (`src/risk/engine.py`)

### 3.1 State Tracking
The `DailyDrawdownTracker` maintains:
- `current_date`: UTC calendar date ($00:00:00$ to $23:59:59.999$).
- `day_starting_equity`: Account equity at the beginning of the UTC day.
- `day_realized_pnl`: Sum of realized net P&L from trades closed on the current day.
- `circuit_breaker_active`: Boolean latch.

### 3.2 Circuit Breaker Logic
$$\text{Max Allowable Daily Loss} = \text{day\_starting\_equity} \times \text{max\_daily\_drawdown\_pct} \quad (0.02 = 2.0\%)$$

$$\text{If } \text{day\_realized\_pnl} \le -\text{Max Allowable Daily Loss} \implies \text{circuit\_breaker\_active} = \text{True}$$

When active, all subsequent trade entries are rejected with `REJECTED_DAILY_DRAWDOWN_LIMIT`.

### 3.3 Automatic 00:00:00 UTC Reset
At the arrival of the first tick/bar of a new UTC calendar day (`current_time.date() != previous_date`), the circuit breaker resets to `False`, and `day_starting_equity` updates to the current balance.

---

## 4. Volatility Adaptation & Dynamic Stops (`src/risk/trade_management.py`)

### 4.1 Average True Range (ATR) Calculation
True Range is computed on OHLC bars:
$$\text{TR}_t = \max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)$$
Smoothed using Wilder's 14-period exponential moving average ($\alpha = 1/14$).

### 4.2 Volatility-Adjusted Minimum Stop Expansion
$$\text{Minimum Allowable Stop Distance} = 1.5 \times \text{ATR}_{14}$$
If the structural order-block stop distance is less than $1.5 \times \text{ATR}$:
1. Stop Loss is expanded to $P_{\text{entry}} \mp (1.5 \times \text{ATR})$.
2. Take Profit is recalculated to preserve the configured Reward-to-Risk ratio:
   $$P_{\text{target}} = P_{\text{entry}} \pm \text{fixed\_rr} \times (1.5 \times \text{ATR}) \quad (\text{fixed\_rr} = 2.0)$$
3. Audit tag is updated to `target_source = "atr_expanded_fixed_rr"`.

---

## 5. Breakeven Trade Management (`src/risk/trade_management.py`)

### 5.1 Favorable Excursion Trigger (+1.5R)
During trade holding:
- For Longs: If $\text{High}_t \ge P_{\text{entry}} + 1.5 \times \text{Initial Risk Distance}$
- For Shorts: If $\text{Low}_t \le P_{\text{entry}} - 1.5 \times \text{Initial Risk Distance}$

### 5.2 Stop Loss Advancement
When triggered:
$$\text{New Stop Loss} = P_{\text{entry}} \pm \$0.05 \quad (\text{covering broker friction})$$
- The stop loss is moved forward strictly. It is never moved backward.
- Trade status is flagged with `breakeven_active = True`.

---

## 6. Integration and Compliance

- **No MT5 Execution:** Live dispatch remains disabled.
- **Fail-Closed Verification:** Every risk gate fails closed upon uninitialized context or boundary violations.
- **Test Coverage:** All behaviors verified via pytest test suite (`tests/test_risk_engine.py`, `tests/test_lot_sizing.py`).

