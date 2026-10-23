> **Historical audit notice (2026-10-19):** This report describes the pre-reingestion dataset and is superseded for current readiness by `reports/research_readiness.md` and Phase 3C/3D reports. The current sidecars record preserved raw timestamp epochs and verified timestamp integrity, but declare MT5 provenance as not independently authenticated.

# GoldFlow Phase 3B — Timestamp Integrity Review

**Status: BLOCKED.** The uploaded code used a fixed three-hour correction across all historical bars. That is unsafe for a dataset spanning seasonal timezone changes. The original MT5 epoch integers are not preserved in the bundled CSVs, so those files are quarantined.

The loader now defaults to the official MT5 POSIX-UTC timestamp convention and supports an explicit, DST-aware server-wall-clock mode only when verified for the specific feed. A read-only diagnostic script was added to compare timestamp candidates against the machine UTC clock. The current data must be re-downloaded after a live diagnostic.

## Automated validation

- Python compilation: passed.
- Full automated test suite: **146 passed, 0 failed**.
- Research-readiness audit: **BLOCKED**, as expected for the quarantined legacy datasets.
- Live MT5 retrieval in this review: **not performed**; the review environment does not have access to the user's terminal.

See `reports/REVIEW_AND_REMEDIATION.md` for the full findings and safe next steps.
