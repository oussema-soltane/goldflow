"""Capture live MT5 symbol specifications into matching data sidecars only.

This command does not download, rewrite, or modify OHLC CSV files. It attaches
instrument metadata only when the selected symbol exactly matches the dataset
sidecar symbol and the terminal server matches the sidecar broker server.

Example (run on the machine with the intended MT5 desktop terminal open/logged in):
    python scripts/capture_mt5_execution_specs.py --symbol XAUUSD

If the terminal symbol or broker differs from the existing data sidecars, stop
and re-ingest the historical bars from the intended terminal instead of attaching
unrelated contract specifications.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import (
    MT5_AVAILABLE,
    capture_symbol_execution_specification,
    check_mt5_status,
    mt5,
    shutdown_mt5,
)


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    """Write one JSON sidecar atomically so interruption preserves the old file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(value, handle, indent=2, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _stage_bytes_backup(path: Path, content: bytes) -> Path:
    """Stage an exact sidecar backup on the same filesystem for rollback."""
    backup_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}.rollback.", suffix=".tmp", delete=False
        ) as handle:
            backup_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(backup_path, stat.S_IMODE(path.stat().st_mode))
        except OSError:
            # Permission preservation is best effort; contents remain staged.
            pass
        return backup_path
    except BaseException:
        if backup_path is not None and backup_path.exists():
            try:
                backup_path.unlink()
            except OSError:
                pass
        raise


def attach_execution_spec_to_sidecars(
    data_dir: str | Path,
    *,
    symbol: str,
    specification: dict[str, Any],
    broker_server: str | None,
    broker_company: str | None = None,
) -> list[Path]:
    """Attach a complete specification to exact-symbol, same-server sidecars.

    All candidate sidecars are validated before the first write. Exact byte-level
    backups are staged before mutation; if a later write fails, already-attempted
    sidecars are restored atomically from those backups. A rollback failure is
    raised explicitly rather than silently leaving a mixed metadata state.
    """
    root = Path(data_dir)
    sidecars = sorted(root.glob("*_clean.meta.json"))
    matches: list[tuple[Path, dict[str, Any]]] = []
    for sidecar in sidecars:
        try:
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot read metadata sidecar {sidecar}: {exc}") from exc
        if metadata.get("symbol") == symbol:
            if metadata.get("is_synthetic") is True:
                raise RuntimeError(f"Refusing to attach broker specifications to synthetic dataset: {sidecar}")
            matches.append((sidecar, metadata))

    if not matches:
        found = sorted({
            str(json.loads(path.read_text(encoding="utf-8")).get("symbol"))
            for path in sidecars if path.is_file()
        }) if sidecars else []
        raise RuntimeError(
            f"No data sidecar has the exact symbol {symbol!r}. Existing sidecar symbols: {found}. "
            "Re-ingest data using the intended MT5 symbol; aliases are not attached automatically."
        )

    if specification.get("status") != "captured_complete":
        raise RuntimeError(
            "MT5 did not return a complete symbol specification; no sidecars were changed. "
            f"Capture status: {specification.get('status')}"
        )
    if specification.get("symbol") != symbol:
        raise RuntimeError(
            f"Specification symbol {specification.get('symbol')!r} does not exactly match requested symbol {symbol!r}."
        )

    # Validate every matching sidecar before writing any of them.
    for sidecar, metadata in matches:
        dataset_server = metadata.get("broker_server")
        if dataset_server and broker_server:
            if str(dataset_server).strip().casefold() != str(broker_server).strip().casefold():
                raise RuntimeError(
                    f"Broker server mismatch for {sidecar.name}: dataset={dataset_server!r}, "
                    f"terminal={broker_server!r}. Re-ingest data from this terminal; do not combine broker specs."
                )
        else:
            raise RuntimeError(
                f"Cannot prove broker server matches sidecar {sidecar.name}. "
                "Re-ingest the data from the intended MT5 terminal so its broker server is captured."
            )

    captured_at = specification.get("captured_at_utc") or datetime.now(timezone.utc).isoformat()
    prepared: list[tuple[Path, dict[str, Any]]] = []
    for sidecar, metadata in matches:
        spec = dict(specification)
        spec["broker_server"] = broker_server
        spec["broker_company"] = broker_company
        metadata["execution_specification"] = spec
        metadata["execution_specification_status"] = spec["status"]
        metadata["account_currency"] = spec.get("account_currency")
        metadata["execution_specification_capture"] = {
            "captured_at_utc": captured_at,
            "captured_symbol": symbol,
            "attached_to_data_symbol": metadata.get("symbol"),
            "broker_server": broker_server,
            "broker_company": broker_company,
            "same_broker_server_as_data": bool(
                metadata.get("broker_server") and broker_server
                and str(metadata.get("broker_server")).strip().casefold() == str(broker_server).strip().casefold()
            ),
            "ohlc_csv_modified": False,
        }
        prepared.append((sidecar, metadata))

    # Stage every rollback copy before touching the first sidecar. The backups
    # reside beside the originals so os.replace remains on the same filesystem.
    backups: dict[Path, Path] = {}
    attempted: list[Path] = []
    preserve_backup_paths: set[Path] = set()
    try:
        for sidecar, _ in prepared:
            backups[sidecar] = _stage_bytes_backup(sidecar, sidecar.read_bytes())
        for sidecar, metadata in prepared:
            # Include the current file in rollback even if a writer raises after
            # replacing it but before returning to this function.
            attempted.append(sidecar)
            _atomic_json_write(sidecar, metadata)
    except BaseException as write_error:
        rollback_errors: list[str] = []
        for sidecar in reversed(attempted):
            backup_path = backups.get(sidecar)
            if backup_path is None:
                continue
            try:
                os.replace(backup_path, sidecar)
                backups.pop(sidecar, None)
            except OSError as rollback_error:
                preserve_backup_paths.add(backup_path)
                rollback_errors.append(f"{sidecar.name}: {rollback_error} (recovery copy: {backup_path})")
        if rollback_errors:
            raise RuntimeError(
                "Execution-spec capture failed and rollback was incomplete; inspect sidecars immediately. "
                "Original recovery copies were preserved at the paths shown. "
                + "; ".join(rollback_errors)
            ) from write_error
        raise
    finally:
        for backup_path in backups.values():
            if backup_path in preserve_backup_paths:
                continue
            try:
                backup_path.unlink(missing_ok=True)
            except OSError:
                pass

    return [sidecar for sidecar, _ in prepared]


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture MT5 XAUUSD execution specifications into matching metadata sidecars")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name; must match the sidecar symbol, e.g. XAUUSD")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data" / "processed")
    parser.add_argument("--reports-dir", type=Path, default=PROJECT_ROOT / "reports")
    args = parser.parse_args()

    if not MT5_AVAILABLE or mt5 is None:
        print("CAPTURE BLOCKED: MetaTrader5 Python package is unavailable. Run this script on the Windows machine with MT5 installed.", file=sys.stderr)
        return 2

    connection = check_mt5_status()
    if not connection.get("connected") and connection.get("terminal_installed"):
        direct = check_mt5_status(require_running_process=False)
        if direct.get("connected"):
            connection = direct
    if not connection.get("connected"):
        print(f"CAPTURE BLOCKED: {connection.get('actionable_message')}", file=sys.stderr)
        return 2

    try:
        specification = capture_symbol_execution_specification(args.symbol)
        account = mt5.account_info()
        terminal = mt5.terminal_info()
        broker_server = getattr(account, "server", None) if account is not None else None
        account_currency = getattr(account, "currency", None) if account is not None else None
        broker_company = getattr(terminal, "company", None) if terminal is not None else None
        specification["account_currency"] = account_currency if isinstance(account_currency, str) else None
        try:
            written = attach_execution_spec_to_sidecars(
                args.data_dir,
                symbol=args.symbol,
                specification=specification,
                broker_server=broker_server if isinstance(broker_server, str) else None,
                broker_company=broker_company if isinstance(broker_company, str) else None,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"CAPTURE BLOCKED: {exc}", file=sys.stderr)
            return 2
    finally:
        shutdown_mt5()

    print(f"Captured MT5 specification for {args.symbol}; updated {len(written)} metadata sidecar(s).")
    rec = specification.get("tick_value_reconciliation")
    if isinstance(rec, dict) and rec.get("reconciliation_status") == "linear_contract_size_verified_by_terminal_api":
        print(f"Empirical inquiry: MT5 order_calc_profit verified 1-lot tick value = ${rec.get('inquired_order_calc_profit_1lot', 0.0):.2f} USD.")
        if rec.get("discrepancy_detected"):
            print(f"Discrepancy noted: symbol_info.trade_tick_value={rec.get('reported_property_tick_value')} vs order_calc_profit={rec.get('inquired_order_calc_profit_1lot', 0.0):.2f} USD.")
    print("OHLC CSV files were not modified.")
    print("Re-running the specification audit...")
    audit_script = PROJECT_ROOT / "scripts" / "audit_execution_specs.py"
    # Use the same interpreter/environment as the capture command.
    import subprocess
    command = [
        sys.executable, str(audit_script),
        "--data-dir", str(args.data_dir),
        "--reports-dir", str(args.reports_dir),
    ]
    audit_result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if audit_result.returncode != 0:
        print("Specifications were captured, but the audit found missing fields or mismatched assumptions. Review reports/execution_spec_audit.md.")
    return audit_result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
