from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.capture_mt5_execution_specs import attach_execution_spec_to_sidecars


def _write_sidecar(root: Path, *, symbol: str = "XAUUSD", server: str | None = "MetaQuotes-Demo", synthetic: bool = False) -> Path:
    sidecar = root / f"{symbol}_M5_clean.meta.json"
    metadata = {
        "symbol": symbol,
        "timeframe": "M5",
        "broker_server": server,
        "broker_company": "MetaQuotes Ltd.",
        "is_synthetic": synthetic,
        "source": "MetaTrader 5 API" if not synthetic else "synthetic generator",
    }
    sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    return sidecar


def _spec(symbol: str = "XAUUSD") -> dict:
    return {
        "status": "captured_complete",
        "source": "MetaTrader5.symbol_info",
        "symbol": symbol,
        "captured_at_utc": "2026-10-20T00:00:00+00:00",
        "digits": 2,
        "point": 0.01,
        "trade_contract_size": 100.0,
        "volume_min": 0.01,
        "volume_step": 0.01,
        "volume_max": 100.0,
        "trade_tick_size": 0.01,
        "trade_tick_value": 1.0,
        "trade_calc_mode": 3,
        "trade_calc_mode_name": "SYMBOL_CALC_MODE_CFD",
        "trade_calc_mode_name_source": "MetaTrader5 module constants",
        "trade_calc_mode_constant_values": {"SYMBOL_CALC_MODE_CFD": 3},
    }


def test_capture_updates_only_sidecar_and_leaves_ohlc_csv_untouched(tmp_path):
    sidecar = _write_sidecar(tmp_path)
    csv_path = tmp_path / "XAUUSD_M5_clean.csv"
    original_csv = b"time,open,high,low,close\n2026-01-01,100,101,99,100\n"
    csv_path.write_bytes(original_csv)

    updated = attach_execution_spec_to_sidecars(
        tmp_path,
        symbol="XAUUSD",
        specification=_spec(),
        broker_server="MetaQuotes-Demo",
        broker_company="MetaQuotes Ltd.",
    )

    assert updated == [sidecar]
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta["execution_specification"]["trade_contract_size"] == 100.0
    assert meta["execution_specification_capture"]["ohlc_csv_modified"] is False
    assert meta["execution_specification_capture"]["same_broker_server_as_data"] is True
    assert csv_path.read_bytes() == original_csv


def test_capture_rejects_known_broker_mismatch_without_partial_update(tmp_path):
    good = _write_sidecar(tmp_path)
    other = tmp_path / "XAUUSD_H1_clean.meta.json"
    other.write_text(json.dumps({
        "symbol": "XAUUSD", "timeframe": "H1", "broker_server": "Other-Broker", "is_synthetic": False
    }), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Broker server mismatch"):
        attach_execution_spec_to_sidecars(
            tmp_path,
            symbol="XAUUSD",
            specification=_spec(),
            broker_server="MetaQuotes-Demo",
            broker_company="MetaQuotes Ltd.",
        )

    assert "execution_specification" not in json.loads(good.read_text(encoding="utf-8"))
    assert "execution_specification" not in json.loads(other.read_text(encoding="utf-8"))


def test_capture_requires_exact_symbol_match(tmp_path):
    _write_sidecar(tmp_path, symbol="XAUUSD")
    with pytest.raises(RuntimeError, match="exact symbol"):
        attach_execution_spec_to_sidecars(
            tmp_path,
            symbol="XAUUSD.a",
            specification=_spec("XAUUSD.a"),
            broker_server="MetaQuotes-Demo",
            broker_company="MetaQuotes Ltd.",
        )


def test_capture_refuses_synthetic_data(tmp_path):
    _write_sidecar(tmp_path, synthetic=True)
    with pytest.raises(RuntimeError, match="synthetic dataset"):
        attach_execution_spec_to_sidecars(
            tmp_path,
            symbol="XAUUSD",
            specification=_spec(),
            broker_server="MetaQuotes-Demo",
            broker_company="MetaQuotes Ltd.",
        )


def test_capture_missing_server_is_refused(tmp_path):
    _write_sidecar(tmp_path, server=None)
    with pytest.raises(RuntimeError, match="Cannot prove broker server matches"):
        attach_execution_spec_to_sidecars(
            tmp_path,
            symbol="XAUUSD",
            specification=_spec(),
            broker_server="MetaQuotes-Demo",
            broker_company="MetaQuotes Ltd.",
        )


def test_capture_account_info_none_is_refused_without_updates(tmp_path):
    sidecar = _write_sidecar(tmp_path)
    original = sidecar.read_bytes()
    with pytest.raises(RuntimeError, match="Cannot prove broker server matches"):
        attach_execution_spec_to_sidecars(
            tmp_path,
            symbol="XAUUSD",
            specification=_spec(),
            broker_server=None,
            broker_company=None,
        )
    assert sidecar.read_bytes() == original


def test_capture_rolls_back_on_os_error_during_second_write(tmp_path, monkeypatch):
    """A failure on a later sidecar must restore earlier files byte-for-byte."""
    m5 = _write_sidecar(tmp_path)
    h1 = tmp_path / "XAUUSD_H1_clean.meta.json"
    h1.write_text(json.dumps({
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "broker_server": "MetaQuotes-Demo",
        "broker_company": "MetaQuotes Ltd.",
        "is_synthetic": False,
        "source": "MetaTrader 5 API",
    }), encoding="utf-8")
    before = {path: path.read_bytes() for path in (m5, h1)}

    import scripts.capture_mt5_execution_specs as cap_mod
    real_write = cap_mod._atomic_json_write
    calls = {"count": 0}

    def failing_write(path, value):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated disk full")
        real_write(path, value)

    monkeypatch.setattr(cap_mod, "_atomic_json_write", failing_write)
    with pytest.raises(OSError, match="simulated disk full"):
        attach_execution_spec_to_sidecars(
            tmp_path,
            symbol="XAUUSD",
            specification=_spec(),
            broker_server="MetaQuotes-Demo",
            broker_company="MetaQuotes Ltd.",
        )

    assert {path: path.read_bytes() for path in (m5, h1)} == before
    assert not list(tmp_path.glob("*.rollback.*.tmp"))


def test_capture_rolls_back_if_writer_raises_after_replacing_second_sidecar(tmp_path, monkeypatch):
    """A writer that raises after its atomic replace must also be rolled back."""
    m5 = _write_sidecar(tmp_path)
    h1 = tmp_path / "XAUUSD_H1_clean.meta.json"
    h1.write_text(json.dumps({
        "symbol": "XAUUSD", "timeframe": "H1", "broker_server": "MetaQuotes-Demo",
        "broker_company": "MetaQuotes Ltd.", "is_synthetic": False, "source": "MetaTrader 5 API",
    }), encoding="utf-8")
    before = {path: path.read_bytes() for path in (m5, h1)}

    import scripts.capture_mt5_execution_specs as cap_mod
    real_write = cap_mod._atomic_json_write
    calls = {"count": 0}

    def write_then_raise_on_second(path, value):
        calls["count"] += 1
        real_write(path, value)
        if calls["count"] == 2:
            raise OSError("simulated post-replace error")

    monkeypatch.setattr(cap_mod, "_atomic_json_write", write_then_raise_on_second)
    with pytest.raises(OSError, match="post-replace error"):
        attach_execution_spec_to_sidecars(
            tmp_path, symbol="XAUUSD", specification=_spec(),
            broker_server="MetaQuotes-Demo", broker_company="MetaQuotes Ltd.",
        )

    assert {path: path.read_bytes() for path in (m5, h1)} == before
    assert not list(tmp_path.glob("*.rollback.*.tmp"))


def test_capture_preserves_recovery_copy_if_rollback_itself_fails(tmp_path, monkeypatch):
    """Do not delete the only recovery copy if an OS rollback replace fails."""
    m5 = _write_sidecar(tmp_path)
    h1 = tmp_path / "XAUUSD_H1_clean.meta.json"
    h1.write_text(json.dumps({
        "symbol": "XAUUSD", "timeframe": "H1", "broker_server": "MetaQuotes-Demo",
        "broker_company": "MetaQuotes Ltd.", "is_synthetic": False, "source": "MetaTrader 5 API",
    }), encoding="utf-8")

    import os as real_os
    import types
    import scripts.capture_mt5_execution_specs as cap_mod
    real_write = cap_mod._atomic_json_write
    real_replace = real_os.replace
    write_calls = {"count": 0}
    replace_calls = {"count": 0}

    def write_then_raise_on_second(path, value):
        write_calls["count"] += 1
        real_write(path, value)
        if write_calls["count"] == 2:
            raise OSError("simulated post-replace error")

    def fail_first_rollback_replace(src, dst):
        replace_calls["count"] += 1
        # First two calls commit M5 and H1; fail the following rollback replace.
        if replace_calls["count"] == 3:
            raise OSError("simulated rollback disk error")
        return real_replace(src, dst)

    monkeypatch.setattr(cap_mod, "_atomic_json_write", write_then_raise_on_second)
    # Use a module-local OS proxy so the injected replace failure affects only
    # the capture module, not tempfile or unrelated library internals.
    monkeypatch.setattr(
        cap_mod, "os", types.SimpleNamespace(
            replace=fail_first_rollback_replace, fsync=real_os.fsync, chmod=real_os.chmod
        )
    )
    with pytest.raises(RuntimeError, match="rollback was incomplete") as exc_info:
        attach_execution_spec_to_sidecars(
            tmp_path, symbol="XAUUSD", specification=_spec(),
            broker_server="MetaQuotes-Demo", broker_company="MetaQuotes Ltd.",
        )

    recovery_files = list(tmp_path.glob("*.rollback.*.tmp"))
    assert recovery_files, "The rollback-failed original must remain available for manual recovery"
    assert str(recovery_files[0]) in str(exc_info.value)
    # Sidecars are processed in sorted path order (H1, then M5), so the
    # simulated rollback failure affects M5. H1 is restored; M5's original
    # bytes remain available in the preserved recovery copy.
    assert "execution_specification" not in json.loads(h1.read_text(encoding="utf-8"))
    assert "execution_specification" in json.loads(m5.read_text(encoding="utf-8"))
