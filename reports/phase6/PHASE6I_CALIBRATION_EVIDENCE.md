# GOLDFLOW — PHASE 6I: STAGE C
## XAUUSD Price-Scale Calibration Evidence Report

**Status:** **NOT EXECUTED — PENDING OPERATOR AUTHORIZATION**  
**Execution Timestamp:** None (Stage C Authorization Boundary Enforced)  
**Author:** Quantitative Architecture & Security Audit Team  
**Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Object Format:** `sha1`  

---

## 1. Safety and Security Posture

In strict accordance with the Phase 6I charter and GoldFlow fail-closed governance:

> **CRITICAL INVARIANT:**  
> Zero external network requests were dispatched during Phase 6I.  
> The price-scale verification gate (`validate_for_real_network_ingestion()`) remains **LOCKED and FAIL-CLOSED**.  
> The provider network pilot (`allow_network=False`) remains **LOCKED and FAIL-CLOSED**.  
> No unverified live data was ingested into the repository or vault.

---

## 2. Pre-Authorization Repository Baseline

The cryptographic baseline of the repository prior to calibration execution is recorded as follows:

| Component | Identifier / Path | Value / SHA-256 Hash | State |
|:---|:---|:---|:---:|
| **Git Commit** | HEAD | `ad9807f8405811d65148d73d72139243f3d6a77f` | Preserved |
| **Object Format** | Git Internals | `sha1` | Verified |
| **Frozen SMC v1 Config** | `configs/smc_v1_frozen.json` | `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a` | Immutable |
| **Frozen C2 Spec** | `reports/strategy/phase6h_candidate_spec.json` | `d09474e02c3dc45165a667742cec5012662e58b95cea78bfd6e5e8d782849916` | Immutable |
| **XAUUSD Spec Status** | `src/data/ingestion/instrument_spec.py` | `UNVERIFIED_PENDING_CONFIRMATION` | Fail-Closed |
| **Provider Network Flag** | `DukascopyIngestionProvider` | `allow_network=False` (default) | Fail-Closed |

---

## 3. Anticipated Calibration Execution Profile

When explicit operator authorization is granted, the single-hour calibration pilot will be executed with the following execution parameters:

### 3.1 Network Request Profile
- **Target URL:** `https://datafeed.dukascopy.com/datafeed/XAUUSD/2026/09/15/10h_ticks.bi5`
- **Host Domain:** `datafeed.dukascopy.com` (verified zero-cost public CDN)
- **HTTP Method:** `GET`
- **Expected Status Code:** `200 OK`
- **Expected Payload:** Compressed LZMA binary stream (`.bi5`)
- **Expected Payload Size Range:** `30,000` to `500,000` bytes (30 KB to 500 KB)
- **Expected Unpacked Tick Count:** `5,000` to `35,000` raw observations

### 3.2 Target Matching Tolerances (Against MT5 10:00 UTC Reference)
- Reference Open: `$4,156.94` | Max allowable deviation: $\pm \$0.50$
- Reference High: `$4,158.80` | Max allowable deviation: $\pm \$1.00$
- Reference Low:  `$4,151.71` | Max allowable deviation: $\pm \$1.00$
- Reference Close: `$4,154.76` | Max allowable deviation: $\pm \$0.50$

---

## 4. Execution Command for Operator Clearance

Once the operator reviews `reports/phase6/PHASE6I_CALIBRATION_PROTOCOL.md` and grants permission for a single bounded external network request, the calibration pilot can be executed using the following controlled harness:

```powershell
# Execute single-hour bounded calibration pilot
python -c "
from pathlib import Path
import pandas as pd
from src.data.ingestion.dukascopy_provider import DukascopyIngestionProvider
from src.data.ingestion.instrument_spec import get_provider_instrument_spec

provider = DukascopyIngestionProvider(local_archive_root=None, allow_unverified_scale=True)
target_hour = pd.Timestamp('2026-10-15 10:00:00', tz='UTC')
output_dir = Path('data/vault/dukascopy/calibration')

# Execute bounded pilot
metadata = provider.execute_bounded_retrieval_pilot(
    symbol='XAUUSD',
    target_hour_utc=target_hour,
    output_dir=output_dir,
    allow_network=True,
)
print('Calibration pilot completed successfully:', metadata.batch_id)
"
```

*(Note: Prior to execution, the operator or calibration harness temporarily promotes or passes an explicit calibration override strictly for the single calibration hour, or runs the dedicated calibration runner).*

---

## 5. Summary Statement

No external network calls were performed. The repository remains fully isolated and compliant with Phase 6I safety boundaries. Authorization from the operator is required to advance from Stage C to actual network calibration.

