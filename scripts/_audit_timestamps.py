"""
Phase 3B — Timestamp & Provenance Audit Script.
Runs a full inspection without modifying any raw or processed data.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw"
PROC = ROOT / "data/processed"
REPORTS = ROOT / "reports"
TIMEFRAMES = ["M5", "M15", "H1", "H4"]

def main() -> None:
    now_utc = datetime.now(timezone.utc)
    print("=" * 70)
    print("  GOLDFLOW — PHASE 3B TIMESTAMP & PROVENANCE AUDIT")
    print("=" * 70)
    print(f"\nAudit run at (UTC): {now_utc.isoformat()}")
    print()

    results = {}

    for tf in TIMEFRAMES:
        raw_path = RAW / f"XAUUSD_{tf}_raw.csv"
        meta_path = PROC / f"XAUUSD_{tf}_clean.meta.json"
        entry = {
            "timeframe": tf,
            "raw_exists": raw_path.exists(),
            "meta_exists": meta_path.exists(),
        }

        print(f"--- {tf} ---")

        # ── File modification time ──────────────────────────────────────────
        if raw_path.exists():
            mtime_utc = datetime.fromtimestamp(raw_path.stat().st_mtime, tz=timezone.utc)
            entry["raw_file_mtime_utc"] = mtime_utc.isoformat()
            print(f"  raw CSV filesystem mtime (UTC) : {mtime_utc.isoformat()}")

            # ── Load and inspect timestamps ─────────────────────────────────
            df = pd.read_csv(raw_path)
            df["time"] = pd.to_datetime(df["time"], utc=True)
            entry["row_count"] = len(df)
            entry["first_ts"] = df["time"].iloc[0].isoformat()
            entry["last_ts"] = df["time"].iloc[-1].isoformat()
            print(f"  rows                           : {len(df)}")
            print(f"  first timestamp (parsed UTC)   : {df['time'].iloc[0]}")
            print(f"  last  timestamp (parsed UTC)   : {df['time'].iloc[-1]}")

            # ── Future candle detection ─────────────────────────────────────
            now_ts = pd.Timestamp(now_utc)
            future_df = df[df["time"] > now_ts]
            entry["future_candle_count"] = int(len(future_df))
            entry["latest_future_candle"] = future_df["time"].max().isoformat() if len(future_df) > 0 else None
            print(f"  candles after audit UTC clock  : {len(future_df)}")
            if len(future_df) > 0:
                print(f"  *** FUTURE CANDLE DETECTED ***   : {future_df['time'].max()}")

            # ── Check first raw Unix timestamp (before pd conversion) ───────
            df_raw2 = pd.read_csv(raw_path)
            sample_ts_str = df_raw2["time"].iloc[-1]
            entry["last_ts_raw_string"] = str(sample_ts_str)
            print(f"  last timestamp raw string      : {sample_ts_str!r}")

            # ── SHA256 of raw file ──────────────────────────────────────────
            raw_bytes = raw_path.read_bytes()
            sha256 = hashlib.sha256(raw_bytes).hexdigest()
            entry["raw_sha256_actual"] = sha256
            print(f"  raw SHA256                     : {sha256[:24]}...")
        else:
            print(f"  [MISSING] raw file not found: {raw_path}")

        # ── Metadata sidecar ────────────────────────────────────────────────
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            stored_sha = meta.get("raw_file_sha256", "")
            actual_sha = entry.get("raw_sha256_actual", "")
            sha_match = stored_sha == actual_sha if stored_sha and actual_sha else None

            entry["meta_source"] = meta.get("source")
            entry["source_verification_status"] = meta.get("source_verification_status")
            entry["raw_timestamp_epoch_preserved"] = meta.get("raw_timestamp_epoch_preserved")
            entry["timestamp_mode"] = meta.get("timestamp_mode")
            entry["timestamp_integrity_status"] = meta.get("timestamp_integrity_status")
            entry["server_timezone"] = meta.get("server_timezone")
            entry["timestamp_correction_applied_seconds"] = meta.get("timestamp_correction_applied_seconds")
            entry["meta_is_synthetic"] = meta.get("is_synthetic")
            entry["meta_retrieval_utc"] = meta.get("retrieval_date_utc")
            entry["meta_start_time"] = meta.get("start_time")
            entry["meta_end_time"] = meta.get("end_time")
            entry["meta_sha256_stored"] = stored_sha
            entry["sha256_match"] = sha_match
            entry["incomplete_bar_excluded"] = meta.get("incomplete_bar_excluded")

            print(f"  meta source                    : {meta.get('source')!r}")
            print(f"  source verification             : {meta.get('source_verification_status')!r}")
            print(f"  raw epoch preserved             : {meta.get('raw_timestamp_epoch_preserved')!r}")
            print(f"  timestamp mode                  : {meta.get('timestamp_mode')!r}")
            print(f"  timestamp integrity status      : {meta.get('timestamp_integrity_status')!r}")
            print(f"  server timezone                 : {meta.get('server_timezone')!r}")
            print(f"  applied correction seconds      : {meta.get('timestamp_correction_applied_seconds')!r}")
            print(f"  meta is_synthetic              : {meta.get('is_synthetic')}")
            print(f"  meta retrieval_date_utc        : {meta.get('retrieval_date_utc')}")
            print(f"  meta incomplete_bar_excluded   : {meta.get('incomplete_bar_excluded')}")
            print(f"  meta start_time                : {meta.get('start_time')}")
            print(f"  meta end_time                  : {meta.get('end_time')}")
            sha_label = "MATCH" if sha_match else ("MISMATCH — file changed post-ingest" if sha_match is False else "NOT STORED")
            print(f"  SHA256 integrity               : {sha_label}")
        else:
            print(f"  [MISSING] meta.json not found: {meta_path}")

        results[tf] = entry
        print()

    # ── Cross-timeframe OHLC duplication check ──────────────────────────────
    print("=" * 70)
    print("  D. CROSS-TIMEFRAME OHLC DUPLICATION CHECK")
    print("=" * 70)
    dfs = {}
    for tf in TIMEFRAMES:
        raw_path = RAW / f"XAUUSD_{tf}_raw.csv"
        if raw_path.exists():
            df = pd.read_csv(raw_path)
            df["time"] = pd.to_datetime(df["time"], utc=True)
            dfs[tf] = df

    pair_results = {}
    tf_list = list(dfs.keys())
    for i, tf_a in enumerate(tf_list):
        for tf_b in tf_list[i+1:]:
            da = dfs[tf_a][["open","high","low","close"]].round(4)
            db = dfs[tf_b][["open","high","low","close"]].round(4)
            min_len = min(len(da), len(db))
            overlap = (da.head(min_len).values == db.head(min_len).values).all(axis=1).sum()
            pct = 100.0 * overlap / min_len if min_len > 0 else 0.0
            key = f"{tf_a}_vs_{tf_b}"
            pair_results[key] = {"identical_rows": int(overlap), "compared": min_len, "pct_identical": round(pct, 2)}
            flag = "  *** DUPLICATE OHLC DETECTED ***" if pct > 20 else ""
            print(f"  {tf_a} vs {tf_b}: {overlap}/{min_len} rows identical ({pct:.1f}%){flag}")

    # ── Save JSON result ─────────────────────────────────────────────────────
    REPORTS.mkdir(parents=True, exist_ok=True)
    audit_payload = {
        "audit_run_utc": now_utc.isoformat(),
        "timeframes": results,
        "cross_timeframe_ohlc_duplication": pair_results,
    }
    json_out = REPORTS / "timestamp_integrity_raw_audit.json"
    json_out.write_text(json.dumps(audit_payload, indent=2, default=str), encoding="utf-8")
    print(f"\nRaw audit JSON saved: {json_out}")
    print("\nAudit complete. Proceed to gap analysis and report generation.")


if __name__ == '__main__':
    main()
