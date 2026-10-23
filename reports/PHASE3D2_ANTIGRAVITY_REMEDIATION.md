# GoldFlow Phase 3D.2 — Antigravity Review Remediation

**Date:** 2026-10-20  
**Scope:** Apply three concrete findings from the independent execution review. No SMC entry/exit strategy parameters were optimized.

## Finding 1 — Pre-triggered stop accepted as an entry (MEDIUM)

**Fix:** `src/backtesting/engine.py` now validates the stop against the executable market quote at the next-bar open. Long candidates require `stop < bid_open`; short candidates require `stop > ask_open`, with `ask_open = bid_open + spread`. Invalid candidates are recorded with `invalid_stop_or_target_after_fill_costs` rather than entering and receiving a phantom entry-bar `STOP_GAP`.

**Regression coverage:**
- `test_pretriggered_short_stop_at_ask_open_is_rejected`
- `test_pretriggered_long_stop_at_bid_open_is_rejected`

## Finding 2 — Missing lifecycle horizons in the UI (LOW)

The Streamlit backtesting page now exposes these holding bar choices: `1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 96, 192, 288, 576`, plus `No time stop`. The help text warns that the count is bar-based and actual elapsed wall-clock time can diverge around market closures and gaps.

## Finding 3 — Stale verification count (LOW)

The current verification entry in `reports/SMC_PHASE_HANDOFF.md` now says **256 tests passed**, following the addition of the two new regression tests. Historical addenda retain the counts that were true when those earlier phases were run.

## Verification

| Check | Result |
|---|---|
| `python -m pytest tests/test_event_backtesting.py -q` | 22 passed |
| `python -m pytest tests/ -q` | 256 passed |
| `python -m compileall src pages scripts tests app.py -q` | Passed |
| `python scripts/research_readiness.py` | `READY_WITH_WARNINGS`; no critical blockers |

## Research governance retained

No holding horizon was selected as optimal. The strong M15 response to a nominal 4-hour cap remains a previously inspected in-sample sensitivity outcome, confounded by partial-profit harvesting and concurrency slot unblocking. An untouched forward period and broker-specific contract/spread verification are still required before any performance conclusion or live execution.
