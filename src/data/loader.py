"""
MetaTrader 5 Data Loader & Symbol Discovery for GoldFlow.

Handles MT5 terminal connection diagnostics, gold instrument discovery,
historical candle extraction for H4, H1, M15, M5 timeframes, raw CSV storage,
and offline fallback utilities.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Try importing MetaTrader5 safely
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False


# Canonical timeframe mapping
TIMEFRAME_MAP: Dict[str, Any] = {
    "M5": getattr(mt5, "TIMEFRAME_M5", 5) if MT5_AVAILABLE else 5,
    "M15": getattr(mt5, "TIMEFRAME_M15", 15) if MT5_AVAILABLE else 15,
    "H1": getattr(mt5, "TIMEFRAME_H1", 16385) if MT5_AVAILABLE else 60,
    "H4": getattr(mt5, "TIMEFRAME_H4", 16388) if MT5_AVAILABLE else 240,
}

TIMEFRAME_MINUTES: Dict[str, int] = {
    "M5": 5,
    "M15": 15,
    "H1": 60,
    "H4": 240,
}

TIMESTAMP_MODES = ("posix_utc", "server_wall_clock")

# MT5 symbol fields needed to reconcile research execution assumptions with the
# terminal's actual instrument specification. Missing values are recorded as null;
# they are never inferred from OHLC precision or silently filled with defaults.
SYMBOL_EXECUTION_SPEC_FIELDS: Dict[str, str] = {
    "digits": "digits",
    "point": "point",
    "trade_contract_size": "trade_contract_size",
    "volume_min": "volume_min",
    "volume_step": "volume_step",
    "volume_max": "volume_max",
    "trade_tick_size": "trade_tick_size",
    "trade_tick_value": "trade_tick_value",
    "trade_tick_value_profit": "trade_tick_value_profit",
    "trade_tick_value_loss": "trade_tick_value_loss",
    "currency_base": "currency_base",
    "currency_profit": "currency_profit",
    "currency_margin": "currency_margin",
    "trade_calc_mode": "trade_calc_mode",
    "trade_stops_level": "trade_stops_level",
    "trade_freeze_level": "trade_freeze_level",
    "spread": "spread",
    "spread_float": "spread_float",
}
SYMBOL_EXECUTION_SPEC_CORE_FIELDS = (
    "digits", "point", "trade_contract_size", "volume_min", "volume_step",
    "volume_max", "trade_tick_size", "trade_tick_value", "trade_calc_mode",
    "trade_calc_mode_name", "trade_calc_mode_name_source", "trade_calc_mode_constant_values",
)


def _plain_mt5_scalar(value: Any) -> Any:
    """Convert a real MT5 scalar to JSON-safe data; ignore mocks/opaque objects."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, str):
        return value
    return None


def _mt5_calc_mode_constant_values() -> Dict[str, int]:
    """Snapshot symbolic calc-mode IDs from the installed MT5 Python package."""
    if mt5 is None:
        return {}
    constants: Dict[str, int] = {}
    for name in dir(mt5):
        if not name.startswith("SYMBOL_CALC_MODE_"):
            continue
        try:
            value = _plain_mt5_scalar(getattr(mt5, name, None))
        except Exception:
            continue
        if isinstance(value, int) and not isinstance(value, bool):
            constants[name] = value
    return constants


def _resolve_mt5_calc_mode_name(value: Any, constants: Dict[str, int]) -> Optional[str]:
    """Resolve a mode name through the active MT5 package constants, never guessed IDs."""
    mode_value = _plain_mt5_scalar(value)
    if isinstance(mode_value, bool) or not isinstance(mode_value, int):
        return None
    matches = [name for name, constant_value in constants.items() if constant_value == mode_value]
    return matches[0] if len(matches) == 1 else None


def inquire_mt5_symbol_execution_reconciliation(symbol: str, info: Any = None) -> Optional[Dict[str, Any]]:
    """Inquire live MT5 order_calc_profit to empirically verify tick value and contract scaling.

    This function performs calculation inquiries only using mt5.order_calc_profit.
    It does not place orders, alter positions, or enable automated execution.
    """
    if mt5 is None:
        return None
    try:
        if info is None:
            info = mt5.symbol_info(symbol)
        if info is None:
            return None

        tick_size = getattr(info, "trade_tick_size", None)
        contract_size = getattr(info, "trade_contract_size", None)
        reported_tick_value = getattr(info, "trade_tick_value", None)
        if tick_size is None or contract_size is None or tick_size <= 0 or contract_size <= 0:
            return None

        tick = mt5.symbol_info_tick(symbol)
        ref_price = getattr(tick, "ask", None) if tick is not None else None
        if ref_price is None or ref_price <= 0:
            ref_price = 2650.0  # Reference gold price for inquiry

        test_volumes = [1.0, 0.5, 0.1, 0.05, 0.01]
        inquiries = []
        for vol in test_volumes:
            p_buy_fav = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, vol, ref_price, ref_price + tick_size)
            p_buy_adv = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, vol, ref_price, ref_price - tick_size)
            p_sell_fav = mt5.order_calc_profit(mt5.ORDER_TYPE_SELL, symbol, vol, ref_price, ref_price - tick_size)
            p_sell_adv = mt5.order_calc_profit(mt5.ORDER_TYPE_SELL, symbol, vol, ref_price, ref_price + tick_size)
            expected_p = round(vol * contract_size * tick_size, 6)
            inquiries.append({
                "volume": vol,
                "buy_favorable_1tick": round(p_buy_fav, 6) if p_buy_fav is not None else None,
                "buy_adverse_1tick": round(p_buy_adv, 6) if p_buy_adv is not None else None,
                "sell_favorable_1tick": round(p_sell_fav, 6) if p_sell_fav is not None else None,
                "sell_adverse_1tick": round(p_sell_adv, 6) if p_sell_adv is not None else None,
                "expected_linear_profit": expected_p,
            })

        one_lot_buy = inquiries[0]["buy_favorable_1tick"]
        expected_1lot = round(contract_size * tick_size, 6)
        discrepancy = bool(reported_tick_value is not None and abs(reported_tick_value - expected_1lot) > 0.001)

        is_verified = (
            one_lot_buy is not None
            and abs(one_lot_buy - expected_1lot) < 1e-4
            and inquiries[0]["buy_adverse_1tick"] is not None
            and abs(inquiries[0]["buy_adverse_1tick"] - (-expected_1lot)) < 1e-4
            and inquiries[0]["sell_favorable_1tick"] is not None
            and abs(inquiries[0]["sell_favorable_1tick"] - expected_1lot) < 1e-4
            and inquiries[0]["sell_adverse_1tick"] is not None
            and abs(inquiries[0]["sell_adverse_1tick"] - (-expected_1lot)) < 1e-4
        )

        return {
            "reconciliation_status": "linear_contract_size_verified_by_terminal_api" if is_verified else "verification_failed",
            "authoritative_calculation_method": "contract_size_linear_formula_verified_by_order_calc_profit",
            "contract_size": float(contract_size),
            "tick_size": float(tick_size),
            "reported_property_tick_value": float(reported_tick_value) if reported_tick_value is not None else None,
            "formula_expected_tick_value": float(expected_1lot),
            "inquired_order_calc_profit_1lot": float(one_lot_buy) if one_lot_buy is not None else None,
            "discrepancy_detected": discrepancy,
            "discrepancy_fields": ["symbol_info.trade_tick_value"] if discrepancy else [],
            "inquiry_evidence": inquiries,
            "reconciliation_explanation": (
                f"MT5 symbol_info.trade_tick_value reports {reported_tick_value} (broker-configured table property), "
                f"while MT5 order_calc_profit returns {one_lot_buy} USD per {tick_size} tick for 1.0 lot, "
                f"matching the contract formula (contract_size {contract_size} * tick_size {tick_size} = {expected_1lot} USD/tick)."
            ),
            "conversion_limitations": (
                "Live order_calc_profit inquiry applies to USD account currency and current broker margins; "
                "historical P&L requires profit currency = account currency = USD."
            ),
        }
    except Exception as exc:
        return {
            "reconciliation_status": "error",
            "error": str(exc),
        }


def capture_symbol_execution_specification(symbol: str) -> Dict[str, Any]:
    """Capture instrument properties from MT5 without inventing missing values."""
    captured_at = dt.datetime.now(dt.timezone.utc).isoformat()
    info = None
    if mt5 is not None:
        try:
            info = mt5.symbol_info(symbol)
        except Exception as exc:
            return {
                "status": "unavailable",
                "source": "MetaTrader5.symbol_info",
                "symbol": symbol,
                "captured_at_utc": captured_at,
                "error": str(exc),
                **{key: None for key in SYMBOL_EXECUTION_SPEC_FIELDS},
                "trade_calc_mode_name": None,
                "trade_calc_mode_name_source": None,
                "trade_calc_mode_constant_values": None,
                "tick_value_reconciliation": None,
            }

    values = {
        key: _plain_mt5_scalar(getattr(info, attr, None)) if info is not None else None
        for key, attr in SYMBOL_EXECUTION_SPEC_FIELDS.items()
    }
    mode_constants = _mt5_calc_mode_constant_values()
    values["trade_calc_mode_constant_values"] = mode_constants
    values["trade_calc_mode_name"] = _resolve_mt5_calc_mode_name(
        values.get("trade_calc_mode"), mode_constants
    )
    values["trade_calc_mode_name_source"] = (
        "MetaTrader5 module constants" if values["trade_calc_mode_name"] is not None else None
    )
    reconciliation = inquire_mt5_symbol_execution_reconciliation(symbol, info) if info is not None else None
    values["tick_value_reconciliation"] = reconciliation

    populated_core = [
        key for key in SYMBOL_EXECUTION_SPEC_CORE_FIELDS
        if (bool(values.get(key)) if key == "trade_calc_mode_constant_values" else values.get(key) is not None)
    ]
    if info is None:
        # Module constants alone are not an instrument capture. Preserve the
        # distinction between a terminal without this symbol and partial specs.
        status = "unavailable"
    elif all(
        bool(values.get(key)) if key == "trade_calc_mode_constant_values"
        else values.get(key) is not None
        for key in SYMBOL_EXECUTION_SPEC_CORE_FIELDS
    ):
        status = "captured_complete"
    elif populated_core:
        status = "captured_incomplete"
    else:
        status = "unavailable"
    return {
        "status": status,
        "source": "MetaTrader5.symbol_info",
        "symbol": symbol,
        "captured_at_utc": captured_at,
        "required_core_fields": list(SYMBOL_EXECUTION_SPEC_CORE_FIELDS),
        **values,
    }


def convert_mt5_epoch_times(
    values: Any,
    *,
    timestamp_mode: str = "posix_utc",
    server_timezone: Optional[str] = None,
) -> Tuple[pd.Series, pd.Series]:
    """
    Convert MT5 integer timestamps to UTC-aware timestamps.

    `posix_utc` follows the official MT5 Python API contract: integers are Unix
    epoch seconds and must not be offset-adjusted.

    `server_wall_clock` is an explicit compatibility mode for a feed empirically
    shown to encode server-local wall-clock values as if they were epoch seconds.
    It interprets the UTC-rendered wall-clock components in `server_timezone`,
    then converts those localized times to UTC. This is DST-aware and deliberately
    raises on ambiguous/nonexistent local times rather than silently guessing.

    Returns (UTC timestamps, correction seconds applied to each timestamp).
    """
    if timestamp_mode not in TIMESTAMP_MODES:
        raise ValueError(
            f"Unsupported timestamp_mode={timestamp_mode!r}; "
            f"choose one of {TIMESTAMP_MODES}."
        )

    as_utc = pd.Series(pd.to_datetime(values, unit="s", utc=True, errors="raise"))
    if timestamp_mode == "posix_utc":
        return as_utc, pd.Series(0, index=as_utc.index, dtype="int64")

    if not server_timezone:
        raise ValueError(
            "server_timezone is required when timestamp_mode='server_wall_clock'."
        )

    # Treat the displayed UTC components as the server's local wall-clock reading.
    # Do NOT use tz_convert here: the source values are not valid UTC instants in
    # this mode. Localize the naive wall-clock values, then convert to true UTC.
    wall_clock = as_utc.dt.tz_localize(None)
    try:
        localized = wall_clock.dt.tz_localize(
            server_timezone, ambiguous="raise", nonexistent="raise"
        )
    except Exception as exc:
        raise ValueError(
            "Could not safely localize server-wall-clock timestamps. The data "
            "contains an ambiguous/nonexistent local time or the timezone is invalid. "
            "Resolve the source timezone/transition explicitly; no guess was applied."
        ) from exc

    utc_times = localized.dt.tz_convert("UTC")
    correction_seconds = (
        (utc_times - as_utc).dt.total_seconds().round().astype("int64")
    )
    return utc_times, correction_seconds


def _as_utc_datetime(value: Union[dt.datetime, str]) -> dt.datetime:
    """Convert a date input to aware UTC; naive inputs are explicitly treated as UTC."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


COMMON_MT5_PATHS = [
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
]


def find_mt5_executable() -> Optional[Path]:
    """Search for the MT5 terminal64.exe executable in running processes and common Windows directories."""
    # 1. Check running processes first to find the exact executable if already launched
    try:
        import psutil
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                name = proc.info.get("name")
                if name and "terminal64" in name.lower():
                    exe = proc.info.get("exe")
                    if exe and Path(exe).is_file():
                        return Path(exe)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass

    # 2. Check standard common paths
    for p_str in COMMON_MT5_PATHS:
        p = Path(p_str)
        if p.exists() and p.is_file():
            return p

    # 3. Search Program Files directories for broker-specific MT5 installations
    for base in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        base_p = Path(base)
        if base_p.exists():
            try:
                for candidate in base_p.glob("*MetaTrader 5*/terminal64.exe"):
                    if candidate.is_file():
                        return candidate
            except Exception:
                pass

    return None


def is_terminal_running() -> bool:
    """Check whether the MetaTrader 5 terminal64 process is currently active."""
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info.get("name")
                if name and "terminal64" in name.lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return False


def check_mt5_status(timeout_sec: float = 2.0, require_running_process: bool = True) -> Dict[str, Any]:
    """
    Check whether MT5 package is installed, terminal is present, open, and accessible.
    
    Parameters
    ----------
    timeout_sec : float, default 2.0
        Maximum time to wait for connection response.
    require_running_process : bool, default True
        If True, requires MT5 to be already open in Windows before attempting IPC.
        This prevents launching unwanted background/headless terminal processes.
    
    Returns a diagnostic dictionary without requiring or storing broker passwords.
    """
    terminal_path = find_mt5_executable()
    running = is_terminal_running()

    status: Dict[str, Any] = {
        "package_installed": MT5_AVAILABLE,
        "package_version": getattr(mt5, "__version__", None) if MT5_AVAILABLE else None,
        "terminal_installed": terminal_path is not None,
        "terminal_path": str(terminal_path) if terminal_path else None,
        "terminal_running": running,
        "connected": False,
        "terminal_info": None,
        "account_info": None,
        "error_code": None,
        "error_description": None,
        "actionable_message": "",
    }

    if not MT5_AVAILABLE:
        status["actionable_message"] = (
            "MetaTrader5 Python library is not installed. Run: pip install MetaTrader5"
        )
        return status

    if not terminal_path and not running:
        status["actionable_message"] = (
            "MetaTrader 5 terminal was not detected in standard directories. "
            "Please ensure MetaTrader 5 desktop is installed."
        )
        return status

    if require_running_process and not running:
        term_desc = f"installed at '{terminal_path}'" if terminal_path else "installed"
        status["actionable_message"] = (
            f"MetaTrader 5 is {term_desc} but is NOT currently open. "
            "Please launch the MetaTrader 5 desktop application and log in to your Demo account."
        )
        return status

    # Attempt safe initialization with strict timeout via threading
    import threading

    init_result: Dict[str, Any] = {"success": False, "error": None}

    def _do_init():
        try:
            init_kwargs: Dict[str, Any] = {}
            if terminal_path:
                init_kwargs["path"] = str(terminal_path)
            res = mt5.initialize(**init_kwargs)
            init_result["success"] = bool(res)
            if not res:
                init_result["error"] = mt5.last_error()
        except Exception as ex:
            init_result["error"] = str(ex)

    init_thread = threading.Thread(target=_do_init, daemon=True)
    init_thread.start()
    init_thread.join(timeout=timeout_sec)

    if init_thread.is_alive():
        status["actionable_message"] = (
            "MT5 terminal did not respond within timeout. "
            "Please verify that the MT5 application is open and logged in."
        )
        return status

    if not init_result["success"]:
        err = init_result["error"]
        status["error_code"] = err[0] if isinstance(err, tuple) else err
        status["error_description"] = err[1] if isinstance(err, tuple) and len(err) > 1 else str(err)
        status["actionable_message"] = (
            "Could not connect to MT5 terminal. Please launch MetaTrader 5 desktop, "
            "ensure your Demo account is logged in, and verify 'Allow automated trading' is enabled."
        )
        return status

    # Connected successfully
    try:
        status["connected"] = True
        t_info = mt5.terminal_info()
        if t_info:
            status["terminal_info"] = {
                "community_account": getattr(t_info, "community_account", False),
                "connected": getattr(t_info, "connected", True),
                "trade_allowed": getattr(t_info, "trade_allowed", False),
                "name": getattr(t_info, "name", "MetaTrader 5"),
                "path": getattr(t_info, "path", ""),
            }

        acc_info = mt5.account_info()
        if acc_info:
            status["account_info"] = {
                "login": getattr(acc_info, "login", None),
                "server": getattr(acc_info, "server", None),
                "currency": getattr(acc_info, "currency", "USD"),
                "leverage": getattr(acc_info, "leverage", None),
                "balance": getattr(acc_info, "balance", None),
                "equity": getattr(acc_info, "equity", None),
                "trade_mode": "Demo" if getattr(acc_info, "trade_mode", 0) == 0 else "Live/Contest",
            }
            status["actionable_message"] = (
                f"Connected to MT5 ({status['account_info']['server']}, "
                f"Account #{status['account_info']['login']}). Ready for data extraction."
            )
        else:
            status["actionable_message"] = (
                "Terminal initialized, but no active account is logged in. "
                "Please log into your MT5 demo account in the terminal window."
            )
    except Exception as exc:
        status["error_description"] = str(exc)
        status["actionable_message"] = f"Error querying MT5 account status: {exc}"

    return status


def shutdown_mt5() -> None:
    """Safely shut down the MT5 Python IPC connection if active."""
    if MT5_AVAILABLE:
        try:
            mt5.shutdown()
        except Exception:
            pass


def discover_gold_symbols() -> List[Dict[str, Any]]:
    """
    Query all symbols available in the connected MT5 terminal and identify gold candidates.
    
    Brokers use varying tickers: XAUUSD, XAUUSD.a, XAUUSDm, GOLD, GOLD.pro, etc.
    Returns candidate symbols with descriptive metadata to allow transparent user confirmation.
    """
    if not MT5_AVAILABLE:
        return []

    try:
        symbols = mt5.symbols_get()
        if symbols is None:
            return []

        gold_candidates = []
        for s in symbols:
            name_upper = s.name.upper()
            desc_upper = (s.description or "").upper()
            if "XAU" in name_upper or "GOLD" in name_upper or "GOLD" in desc_upper:
                gold_candidates.append({
                    "name": s.name,
                    "description": s.description,
                    "currency_base": getattr(s, "currency_base", None),
                    "currency_profit": getattr(s, "currency_profit", None),
                    "digits": getattr(s, "digits", None),
                    "spread": getattr(s, "spread", None),
                    "point": getattr(s, "point", None),
                    "trade_contract_size": getattr(s, "trade_contract_size", None),
                    "volume_min": getattr(s, "volume_min", None),
                    "volume_step": getattr(s, "volume_step", None),
                    "volume_max": getattr(s, "volume_max", None),
                    "trade_tick_size": getattr(s, "trade_tick_size", None),
                    "trade_tick_value": getattr(s, "trade_tick_value", None),
                    "trade_tick_value_profit": getattr(s, "trade_tick_value_profit", None),
                    "trade_tick_value_loss": getattr(s, "trade_tick_value_loss", None),
                    "currency_margin": getattr(s, "currency_margin", None),
                    "trade_stops_level": getattr(s, "trade_stops_level", None),
                    "trade_freeze_level": getattr(s, "trade_freeze_level", None),
                    "spread_float": getattr(s, "spread_float", None),
                    "visible": getattr(s, "visible", False),
                })
        return gold_candidates
    except Exception as exc:
        logger.error(f"Error querying symbols from MT5: {exc}")
        return []


def sanitize_symbol_for_filename(symbol: str) -> str:
    """
    Sanitize a broker trading symbol for safe cross-platform (specifically Windows) filesystem usage.
    
    Replaces characters illegal in Windows file paths (/ \\ : * ? " < > |) with underscores.
    Preserves original symbol string in metadata and data structures.
    """
    if not symbol or not isinstance(symbol, str):
        return "UNKNOWN_SYMBOL"
    
    # Windows reserved characters: < > : " / \ | ? *
    illegal_chars = r'<>:"/\|?*'
    safe = symbol.strip()
    for char in illegal_chars:
        safe = safe.replace(char, "_")
    
    # Remove control characters (ASCII 0-31) and strip trailing dots/spaces
    safe = "".join(c for c in safe if ord(c) >= 32).strip(". ")
    return safe or "UNKNOWN_SYMBOL"


def fetch_historical_bars(
    symbol: str,
    timeframe: str,
    n_bars: Optional[int] = 2000,
    start_date: Optional[Union[dt.datetime, str]] = None,
    end_date: Optional[Union[dt.datetime, str]] = None,
    exclude_incomplete: bool = True,
    timestamp_mode: str = "posix_utc",
    server_timezone: Optional[str] = None,
    timestamp_mode_verified: bool = False,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Retrieve historical OHLCV bars from MT5 for a specified symbol and timeframe.

    COMPLETED-CANDLE HANDLING & TIMESTAMP CONVENTION:
    -------------------------------------------------
    MT5 position 0 is the current/forming bar; position 1 is the latest completed
    bar. When `exclude_incomplete=True`, position 1 is used for position-based
    retrieval.

    MT5's documented default is POSIX UTC timestamps. The default `timestamp_mode`
    therefore leaves epoch timestamps unshifted. Use `timestamp_mode="server_wall_clock"`
    only when a live diagnostic has demonstrated that this particular feed encodes
    server-local wall-clock values as epoch-like integers. In that mode, provide an
    IANA `server_timezone` such as "Europe/Athens"; historical DST offsets are applied
    per timestamp, not as a fixed current offset. Ambiguous/nonexistent local times
    raise an error rather than being silently guessed.

    Parameters
    ----------
    symbol : str
        Trading symbol (e.g. 'XAUUSD', 'GOLD').
    timeframe : str
        Timeframe key ('H4', 'H1', 'M15', 'M5').
    n_bars : int, optional
        Number of historical bars to fetch if start_date is not specified.
    start_date : datetime or str, optional
        Start datetime.
    end_date : datetime or str, optional
        End datetime (defaults to current time if start_date is provided).
    exclude_incomplete : bool, default True
        If True, returns only fully completed historical candles.
    timestamp_mode : {"posix_utc", "server_wall_clock"}
        Timestamp representation observed for this feed. Default follows MT5 docs.
    server_timezone : str, optional
        IANA timezone required for server_wall_clock mode, e.g. "Europe/Athens".
    timestamp_mode_verified : bool, default False
        Explicit operator confirmation that a live diagnostic was reviewed. Without
        this, metadata remains unverified and research readiness stays blocked.

    Returns
    -------
    Tuple[pd.DataFrame, Dict[str, Any]]
        The extracted dataframe and retrieval metadata dictionary.
    """
    # Check the active module reference rather than the import-time flag so callers
    # can safely inject a mock MT5 client in offline unit tests. In production this
    # remains None when MetaTrader5 could not be imported.
    if mt5 is None:
        raise RuntimeError("MetaTrader5 library is not available in the current Python environment.")

    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(f"Invalid timeframe '{timeframe}'. Allowed: {list(TIMEFRAME_MAP.keys())}")

    tf_const = getattr(mt5, f"TIMEFRAME_{timeframe}", TIMEFRAME_MAP[timeframe])

    # Ensure symbol is selected in Market Watch
    if not mt5.symbol_select(symbol, True):
        raise ValueError(
            f"Symbol '{symbol}' could not be selected in MT5 Market Watch. "
            f"Check if the broker symbol name is exact."
        )

    if timestamp_mode not in TIMESTAMP_MODES:
        raise ValueError(f"timestamp_mode must be one of {TIMESTAMP_MODES}")
    if timestamp_mode == "server_wall_clock" and not server_timezone:
        raise ValueError(
            "Pass server_timezone (IANA timezone) when using server_wall_clock mode."
        )

    retrieval_time = dt.datetime.now(dt.timezone.utc)
    bars_count = n_bars if n_bars and n_bars > 0 else 2000

    # Fetch rates from MT5
    if start_date is not None:
        start_date = _as_utc_datetime(start_date)
        if end_date is None:
            end_date = dt.datetime.now(dt.timezone.utc)
        else:
            end_date = _as_utc_datetime(end_date)

        rates = mt5.copy_rates_range(symbol, tf_const, start_date, end_date)
    else:
        # Documented MT5 behavior: start_pos=1 gives completed bars; start_pos=0 includes open bar
        start_pos = 1 if exclude_incomplete else 0
        rates = mt5.copy_rates_from_pos(symbol, tf_const, start_pos, bars_count)

    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        raise RuntimeError(
            f"MT5 returned 0 bars for {symbol} ({timeframe}). MT5 error: {err}"
        )

    # Preserve the integer returned by MT5 for auditability before conversion.
    df = pd.DataFrame(rates)
    if "time" not in df.columns:
        raise ValueError("MT5 rates do not contain the required 'time' field.")
    df["time_raw_epoch"] = pd.to_numeric(df["time"], errors="raise").astype("int64")
    converted_times, correction_seconds = convert_mt5_epoch_times(
        df["time_raw_epoch"],
        timestamp_mode=timestamp_mode,
        server_timezone=server_timezone,
    )
    df["time"] = converted_times
    # Store per-row correction for raw provenance; cleaned output drops this helper.
    df["timestamp_correction_applied_seconds"] = correction_seconds.to_numpy()

    # Rename / standardise columns
    expected_cols = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = 0

    # Keep raw epoch and correction columns in the raw export; cleaning removes them.
    audit_cols = ["time_raw_epoch", "timestamp_correction_applied_seconds"]
    df = df[expected_cols + audit_cols].copy()
    df = df.sort_values("time").reset_index(drop=True)

    # If copy_rates_range was used and exclude_incomplete is True, verify trailing bar.
    # The tick time integer is also a server-local timestamp, so correct it too.
    if start_date is not None and exclude_incomplete and len(df) > 0:
        tick_info = mt5.symbol_info_tick(symbol)
        if tick_info is not None and tick_info.time:
            tick_series, _tick_correction = convert_mt5_epoch_times(
                [int(tick_info.time)],
                timestamp_mode=timestamp_mode,
                server_timezone=server_timezone,
            )
            latest_tick_dt = tick_series.iloc[0].to_pydatetime()
            last_candle_t = df["time"].iloc[-1].to_pydatetime()
            duration = dt.timedelta(minutes=TIMEFRAME_MINUTES.get(timeframe, 15))
            if last_candle_t + duration > latest_tick_dt:
                df = df.iloc[:-1].copy()

    server_offset_at_retrieval = None
    if server_timezone:
        try:
            from zoneinfo import ZoneInfo
            offset = dt.datetime.now(ZoneInfo(server_timezone)).utcoffset()
            server_offset_at_retrieval = (
                float(offset.total_seconds() / 3600) if offset is not None else None
            )
        except Exception as exc:
            raise ValueError(f"Invalid IANA server_timezone {server_timezone!r}.") from exc

    broker_server = None
    broker_company = None
    broker_account_currency = None
    if mt5 is not None:
        try:
            acc = mt5.account_info()
            if acc is not None:
                srv = getattr(acc, "server", None)
                if isinstance(srv, str):
                    broker_server = srv
                currency = getattr(acc, "currency", None)
                if isinstance(currency, str):
                    broker_account_currency = currency
            term = mt5.terminal_info()
            if term is not None:
                comp = getattr(term, "company", None)
                if isinstance(comp, str):
                    broker_company = comp
        except Exception:
            pass

    execution_specification = capture_symbol_execution_specification(symbol)
    execution_specification["account_currency"] = broker_account_currency
    metadata: Dict[str, Any] = {
        "symbol": symbol,
        "account_currency": broker_account_currency,
        "execution_specification": execution_specification,
        "execution_specification_status": execution_specification["status"],
        "timeframe": timeframe,
        "retrieval_date_utc": retrieval_time.isoformat(),
        "row_count": len(df),
        "requested_bars": bars_count,
        "actual_rows_received": len(df),
        "start_time": df["time"].iloc[0].isoformat() if len(df) > 0 else None,
        "end_time": df["time"].iloc[-1].isoformat() if len(df) > 0 else None,
        "timezone_convention": "UTC (UTC-aware pandas timestamps)",
        "source": "MetaTrader 5 API",
        "is_synthetic": False,
        "broker_server": broker_server,
        "broker_company": broker_company,
        "source_verification_status": "declared_not_independently_verified",
        "raw_timestamp_epoch_preserved": True,
        "incomplete_bar_excluded": exclude_incomplete,
        "timestamp_mode": timestamp_mode,
        "timestamp_representation": (
            "POSIX epoch seconds in UTC"
            if timestamp_mode == "posix_utc"
            else "server-local wall-clock encoded as epoch-like seconds"
        ),
        "server_timezone": server_timezone,
        "timestamp_mode_verified": bool(timestamp_mode_verified),
        "timestamp_integrity_status": "verified" if timestamp_mode_verified else "normalized_by_explicit_mode",
        "timestamp_correction_applied_seconds": (
            int(correction_seconds.iloc[0])
            if correction_seconds.nunique() == 1 and len(correction_seconds)
            else (0 if len(correction_seconds) == 0 else None)
        ),
        "timestamp_correction_applied_seconds_min": (
            int(correction_seconds.min()) if len(correction_seconds) else None
        ),
        "timestamp_correction_applied_seconds_max": (
            int(correction_seconds.max()) if len(correction_seconds) else None
        ),
        "server_utc_offset_hours": server_offset_at_retrieval,
    }

    return df, metadata


def save_raw_data(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    output_dir: Union[str, Path] = "data/raw",
) -> Path:
    """
    Save the extracted dataframe with original MT5 epoch integers and normalized UTC
    timestamps for auditability. The `time_raw_epoch` column preserves the API value.
    Uses a sanitized filename while preserving the original symbol in metadata.

    DATA SAFETY: Written atomically via a temp file. If the write fails, any existing
    valid dataset at the target path is preserved.
    """
    import tempfile
    import os
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    safe_symbol = sanitize_symbol_for_filename(symbol)
    filename = f"{safe_symbol}_{timeframe}_raw.csv"
    full_path = out_path / filename

    # Write to temp file first; only rename when complete and non-empty.
    fd, tmp_name = tempfile.mkstemp(dir=out_path, prefix=f"{filename}.tmp.", suffix=".csv")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
            df.to_csv(fh, index=False)
        tmp_path = Path(tmp_name)
        if tmp_path.stat().st_size == 0:
            raise RuntimeError("Temp file written for {full_path} has zero bytes; aborting atomic swap.")
        # os.replace is atomic on POSIX; on Windows it uses MoveFileEx which is close enough.
        os.replace(tmp_name, full_path)
    except Exception:
        # Clean up temp file but do not clobber the existing target.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return full_path


def load_local_data(filepath: Union[str, Path]) -> pd.DataFrame:
    """
    Load a local CSV dataset (raw or processed) and parse timestamps as UTC-aware.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    df = pd.read_csv(path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def generate_synthetic_gold_data(
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    n_bars: int = 500,
    base_price: float = 2650.0,
    seed: int = 42,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Generate realistic synthetic XAU/USD market data strictly for testing and offline development.
    
    This synthetic dataset respects gold price scales, volatility regimes,
    and valid OHLC boundaries with explicit UTC-aware timestamps.
    """
    if n_bars <= 0:
        empty_df = pd.DataFrame(
            columns=["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
        )
        empty_df["time"] = pd.to_datetime(empty_df["time"], utc=True)
        metadata = {
            "symbol": symbol,
            "timeframe": timeframe,
            "retrieval_date_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "row_count": 0,
            "start_time": None,
            "end_time": None,
            "timezone_convention": "UTC (UTC-aware pd.Timestamp)",
            "source": "Synthetic Benchmark Generator (Unit Testing / Offline Mode)",
            "source_verification_status": "synthetic_generator",
            "raw_timestamp_epoch_preserved": False,
            "is_synthetic": True,
            "timestamp_mode": "posix_utc",
            "timestamp_representation": "synthetic UTC-aware timestamps",
            "server_timezone": None,
            "server_utc_offset_hours": None,
            "timestamp_correction_applied_seconds": 0,
            "timestamp_correction_applied_seconds_min": 0,
            "timestamp_correction_applied_seconds_max": 0,
            "timestamp_integrity_status": "normalized_by_explicit_mode",
        }
        return empty_df, metadata

    rng = np.random.default_rng(seed)
    minutes = TIMEFRAME_MINUTES.get(timeframe, 15)

    # Generate UTC-aware business hour timestamps
    end_time = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    timestamps = [end_time - dt.timedelta(minutes=minutes * i) for i in range(n_bars)]
    timestamps.reverse()

    prices = [base_price]
    for _ in range(n_bars - 1):
        delta = rng.normal(0, 1.8)
        prices.append(max(100.0, prices[-1] + delta))

    rows = []
    for t, p in zip(timestamps, prices):
        candle_range = abs(rng.normal(1.2, 0.8))
        half_range = candle_range / 2.0
        open_price = round(p, 2)
        close_price = round(p + rng.uniform(-half_range, half_range), 2)
        high_price = round(max(open_price, close_price) + abs(rng.uniform(0.1, 0.9)), 2)
        low_price = round(min(open_price, close_price) - abs(rng.uniform(0.1, 0.9)), 2)
        tick_vol = int(rng.integers(120, 1500))
        spread = int(rng.integers(12, 35))

        rows.append({
            "time": t,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "tick_volume": tick_vol,
            "spread": spread,
            "real_volume": 0,
        })

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    metadata = {
        "symbol": symbol,
        "timeframe": timeframe,
        "retrieval_date_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "row_count": len(df),
        "start_time": df["time"].iloc[0].isoformat(),
        "end_time": df["time"].iloc[-1].isoformat(),
        "timezone_convention": "UTC (UTC-aware pd.Timestamp)",
        "source": "Synthetic Benchmark Generator (Unit Testing / Offline Mode)",
        "source_verification_status": "synthetic_generator",
        "raw_timestamp_epoch_preserved": False,
        "is_synthetic": True,
        "timestamp_mode": "posix_utc",
        "timestamp_representation": "synthetic UTC-aware timestamps",
        "server_timezone": None,
        "server_utc_offset_hours": None,
        "timestamp_correction_applied_seconds": 0,
        "timestamp_correction_applied_seconds_min": 0,
        "timestamp_correction_applied_seconds_max": 0,
        "timestamp_integrity_status": "normalized_by_explicit_mode",
    }
    return df, metadata
