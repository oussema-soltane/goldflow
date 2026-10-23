"""Event-driven, bar-based execution simulator for GoldFlow research.

This module models orders from completed SMC signal candles using the next
bar's open. It treats input OHLC candles as bid-side prices (MetaTrader 5's
usual FX/CFD chart convention), applies spread to buy entries and short exits,
and resolves an ambiguous stop/target collision conservatively as stop-first.
It is a research simulator, not a broker fill emulator or live-trading system.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 10_000.0
    risk_fraction: float = 0.01
    contract_size_oz: float = 100.0
    point_size: float = 0.01
    fallback_spread_usd: float = 0.20
    slippage_per_side_usd: float = 0.05
    commission_per_lot_per_side: float = 0.0
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lots: float = 100.0
    max_concurrent_positions: int = 1
    conservative_stop_first: bool = True
    # Optional maximum number of bars held, counting the entry bar as bar 1.
    # Time stops occur at the bar close only when stop/target was not hit first.
    max_holding_bars: int | None = None
    spread_multiplier: float = 1.0
    override_spread_usd: float | None = None

    def __post_init__(self) -> None:
        numeric_fields = (
            "initial_capital", "risk_fraction", "contract_size_oz", "point_size",
            "fallback_spread_usd", "slippage_per_side_usd",
            "commission_per_lot_per_side", "min_lot", "lot_step", "max_lots",
            "spread_multiplier",
        )
        for field_name in numeric_fields:
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float, np.integer, np.floating))
                or not math.isfinite(float(value))
            ):
                raise ValueError(f"{field_name} must be a finite real number")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be > 0")
        if not 0 < self.risk_fraction <= 1:
            raise ValueError("risk_fraction must be in (0, 1]")
        if self.contract_size_oz <= 0:
            raise ValueError("contract_size_oz must be > 0")
        if self.point_size <= 0:
            raise ValueError("point_size must be > 0")
        if self.fallback_spread_usd < 0 or self.slippage_per_side_usd < 0:
            raise ValueError("spread and slippage must be >= 0")
        if self.commission_per_lot_per_side < 0:
            raise ValueError("commission must be >= 0")
        if self.spread_multiplier < 0:
            raise ValueError("spread_multiplier must be >= 0")
        if self.override_spread_usd is not None:
            if (
                isinstance(self.override_spread_usd, bool)
                or not isinstance(self.override_spread_usd, (int, float, np.integer, np.floating))
                or not math.isfinite(float(self.override_spread_usd))
                or float(self.override_spread_usd) < 0
            ):
                raise ValueError("override_spread_usd must be None or a finite real number >= 0")
        if self.min_lot <= 0 or self.lot_step <= 0 or self.max_lots < self.min_lot:
            raise ValueError("invalid lot constraints")
        if (
            isinstance(self.max_concurrent_positions, bool)
            or not isinstance(self.max_concurrent_positions, int)
            or self.max_concurrent_positions < 1
        ):
            raise ValueError("max_concurrent_positions must be an integer >= 1")
        if self.max_holding_bars is not None:
            if isinstance(self.max_holding_bars, bool) or not isinstance(self.max_holding_bars, int) or self.max_holding_bars < 1:
                raise ValueError("max_holding_bars must be None or an integer >= 1")


@dataclass
class BacktestResult:
    trades: list[dict[str, Any]]
    metrics: dict[str, Any]
    equity_curve: list[dict[str, Any]]  # close-to-close mark-to-market equity
    realized_equity_curve: list[dict[str, Any]]
    config: dict[str, Any]


def _value(candidate: Any, key: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(key, default)
    return getattr(candidate, key, default)


def _direction(candidate: Any) -> str:
    raw = _value(candidate, "direction", "")
    return str(getattr(raw, "value", raw)).upper()


def _spread_usd(row: pd.Series, config: BacktestConfig) -> tuple[float, str]:
    """Convert the MT5 `spread` field from broker points to price units, or apply override/multiplier."""
    if config.override_spread_usd is not None:
        return float(config.override_spread_usd), "config_override"
    multiplier = float(config.spread_multiplier)
    if "spread" in row.index:
        raw = pd.to_numeric(pd.Series([row["spread"]]), errors="coerce").iloc[0]
        if pd.notna(raw) and math.isfinite(float(raw)) and float(raw) > 0:
            return float(raw) * config.point_size * multiplier, "bar_spread_points"
    return float(config.fallback_spread_usd) * multiplier, "fixed_fallback"


def _prepare_bars(df: pd.DataFrame) -> pd.DataFrame:
    required = {"time", "open", "high", "low", "close"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Backtest input missing required columns: {', '.join(missing)}")
    frame = df.copy().reset_index(drop=True)
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    if frame["time"].isna().any():
        raise ValueError("Backtest input has invalid timestamps")
    if not frame["time"].is_monotonic_increasing or frame["time"].duplicated().any():
        raise ValueError("Backtest timestamps must be unique and chronological")
    for col in ("open", "high", "low", "close"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
        if not np.isfinite(frame[col].to_numpy(dtype=float)).all():
            raise ValueError(f"Backtest input has invalid {col} prices")
    invalid = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    if invalid.any():
        raise ValueError(f"Backtest input has {int(invalid.sum())} invalid OHLC row(s)")
    if "spread" in frame.columns:
        spread = pd.to_numeric(frame["spread"], errors="coerce")
        observed_spread = spread.dropna().to_numpy(dtype=float)
        if observed_spread.size and not np.isfinite(observed_spread).all():
            raise ValueError("Backtest input spread values must be finite when present")
        if spread.notna().any() and (spread.dropna() < 0).any():
            raise ValueError("Backtest input spread values must be non-negative")
        frame["spread"] = spread.fillna(0.0)
    return frame


def _make_exit(
    position: dict[str, Any],
    frame: pd.DataFrame,
    index: int,
    config: BacktestConfig,
) -> Optional[dict[str, Any]]:
    """Return a deterministic exit event for one position on the current bar."""
    row = frame.iloc[index]
    side = position["side"]
    stop = position["stop_loss"]
    target = position["take_profit"]
    slip = config.slippage_per_side_usd
    spread, spread_source = _spread_usd(row, config)
    bid_open, bid_high, bid_low, bid_close = (
        float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
    )

    # Existing stop/target orders are evaluated against this bar's opening quote
    # first. Gaps through a stop receive the worse opening fill, not the stop price.
    if side == "LONG":
        if bid_open <= stop:
            return {"exit_index": index, "exit_price": bid_open - slip, "raw_exit_price": bid_open, "exit_reason": "STOP_GAP", "exit_spread_usd": spread, "exit_spread_source": spread_source}
        if bid_open >= target:
            return {"exit_index": index, "exit_price": target, "raw_exit_price": target, "exit_reason": "TAKE_PROFIT_GAP", "exit_spread_usd": spread, "exit_spread_source": spread_source}
        stop_hit = bid_low <= stop
        target_hit = bid_high >= target
    else:
        ask_open = bid_open + spread
        ask_high = bid_high + spread
        ask_low = bid_low + spread
        if ask_open >= stop:
            return {"exit_index": index, "exit_price": ask_open + slip, "raw_exit_price": ask_open, "exit_reason": "STOP_GAP", "exit_spread_usd": spread, "exit_spread_source": spread_source}
        if ask_open <= target:
            return {"exit_index": index, "exit_price": target, "raw_exit_price": target, "exit_reason": "TAKE_PROFIT_GAP", "exit_spread_usd": spread, "exit_spread_source": spread_source}
        stop_hit = ask_high >= stop
        target_hit = ask_low <= target

    if stop_hit and target_hit:
        if config.conservative_stop_first:
            exit_price = stop - slip if side == "LONG" else stop + slip
            raw_exit = stop
            reason = "STOP_FIRST_COLLISION"
        else:
            exit_price = target
            raw_exit = target
            reason = "TARGET_FIRST_COLLISION"
    elif stop_hit:
        exit_price = stop - slip if side == "LONG" else stop + slip
        raw_exit = stop
        reason = "STOP_LOSS"
    elif target_hit:
        # Take-profit is modelled as a limit order: no adverse exit slippage once
        # the level is touched. Spread remains represented by quote-side triggering.
        exit_price = target
        raw_exit = target
        reason = "TAKE_PROFIT"
    else:
        return None
    return {"exit_index": index, "exit_price": float(exit_price), "raw_exit_price": float(raw_exit), "exit_reason": reason, "exit_spread_usd": spread, "exit_spread_source": spread_source}


def _make_time_exit(
    position: dict[str, Any],
    frame: pd.DataFrame,
    index: int,
    config: BacktestConfig,
) -> Optional[dict[str, Any]]:
    """Close at this bar's executable close once the holding-bar cap is reached.

    Stop/target exits are evaluated first by the caller. The entry bar counts as
    held bar 1; for a time stop the long closes at bid close and the short at ask
    close, with adverse slippage.
    """
    if config.max_holding_bars is None:
        return None
    bars_held = index - int(position["entry_index"]) + 1
    if bars_held < config.max_holding_bars:
        return None
    row = frame.iloc[index]
    spread, spread_source = _spread_usd(row, config)
    close = float(row["close"])
    if position["side"] == "LONG":
        raw_exit = close
        exit_price = close - config.slippage_per_side_usd
    else:
        raw_exit = close + spread
        exit_price = close + spread + config.slippage_per_side_usd
    return {
        "exit_index": index,
        "exit_price": float(exit_price),
        "raw_exit_price": float(raw_exit),
        "exit_reason": "TIME_STOP",
        "exit_spread_usd": spread,
        "exit_spread_source": spread_source,
    }


def _finalize_trade(
    position: dict[str, Any],
    exit_event: Mapping[str, Any],
    frame: pd.DataFrame,
    equity: float,
    config: BacktestConfig,
) -> tuple[dict[str, Any], float]:
    exit_index = int(exit_event["exit_index"])
    exit_price = float(exit_event["exit_price"])
    raw_exit_price = float(exit_event.get("raw_exit_price", exit_price))
    direction_sign = 1.0 if position["side"] == "LONG" else -1.0
    gross_pnl = (exit_price - position["entry_price"]) * direction_sign * config.contract_size_oz * position["lots"]
    commission = 2.0 * config.commission_per_lot_per_side * position["lots"]
    net_pnl = gross_pnl - commission
    new_equity = equity + net_pnl
    exit_spread = float(exit_event.get("exit_spread_usd", 0.0))

    # Bid OHLC means spread is paid at a long entry, or at a short exit.
    spread_usd = position["entry_spread_usd"] if position["side"] == "LONG" else exit_spread
    spread_cost = spread_usd * config.contract_size_oz * position["lots"]

    entry_slip = abs(position["entry_price"] - (position["entry_reference_open"] + (position["entry_spread_usd"] if position["side"] == "LONG" else 0.0)))
    exit_slip = abs(exit_price - raw_exit_price)
    slippage_cost = (entry_slip + exit_slip) * config.contract_size_oz * position["lots"]

    raw_gross_pnl = gross_pnl + spread_cost + slippage_cost
    total_transaction_costs = spread_cost + slippage_cost + commission

    trade = {
        **position["audit_fields"],
        "status": "CLOSED",
        "side": position["side"],
        "signal_index": position["signal_index"],
        "signal_time": position["signal_time"],
        "entry_index": position["entry_index"],
        "entry_time": frame.iloc[position["entry_index"]]["time"].isoformat(),
        "entry_price": position["entry_price"],
        "entry_reference_open": position["entry_reference_open"],
        "entry_spread_usd": position["entry_spread_usd"],
        "entry_spread_source": position["entry_spread_source"],
        "stop_loss": position["stop_loss"],
        "take_profit": position["take_profit"],
        "lots": position["lots"],
        "risk_budget_cash": position["risk_budget_cash"],
        "estimated_stop_risk_cash": position["estimated_stop_risk_cash"],
        "estimated_spread_cost_usd": spread_cost,
        "spread_cost": spread_cost,
        "slippage_cost": slippage_cost,
        "total_transaction_costs": total_transaction_costs,
        "raw_gross_pnl": raw_gross_pnl,
        "exit_index": exit_index,
        "exit_time": frame.iloc[exit_index]["time"].isoformat(),
        "exit_price": exit_price,
        "raw_exit_price": raw_exit_price,
        "exit_reason": exit_event["exit_reason"],
        "exit_spread_usd": exit_spread,
        "exit_spread_source": exit_event.get("exit_spread_source", "fixed_fallback"),
        "bars_held": exit_index - position["entry_index"] + 1,
        "gross_pnl": gross_pnl,
        "commission": commission,
        "net_pnl": net_pnl,
        # R is normalized by the actual planned stop risk after lot-step rounding,
        # not by the larger pre-rounding cash risk budget.
        "R_multiple": (
            net_pnl / position["estimated_stop_risk_cash"]
            if position["estimated_stop_risk_cash"] > 0 else None
        ),
        "risk_budget_breach": bool(net_pnl < 0 and abs(net_pnl) > position["risk_budget_cash"] + 1e-8),
        "equity_after": new_equity,
    }
    return trade, new_equity


def _skipped_trade(candidate: Any, candidate_id: str, reason: str, signal_index: int, signal_time: str) -> dict[str, Any]:
    return {
        "setup_id": candidate_id,
        "timeframe": _value(candidate, "timeframe"),
        "direction": _direction(candidate),
        "signal_index": signal_index,
        "signal_time": signal_time,
        "stop_loss_reference": _value(candidate, "stop_loss_reference"),
        "take_profit_reference": _value(candidate, "take_profit_reference"),
        "target_source": _value(candidate, "target_source"),
        "status": "SKIPPED",
        "skip_reason": reason,
        "net_pnl": 0.0,
    }


def _metrics(
    trades: Sequence[Mapping[str, Any]],
    initial_capital: float,
    mark_to_market_curve: Sequence[Mapping[str, Any]],
    realized_equity_curve: Sequence[Mapping[str, Any]],
    max_concurrency: int,
) -> dict[str, Any]:
    closed = [t for t in trades if t.get("status") == "CLOSED"]
    skipped = [t for t in trades if t.get("status") == "SKIPPED"]
    end_of_data = [t for t in closed if t.get("exit_reason") == "END_OF_DATA"]
    rule_exits = [t for t in closed if t.get("exit_reason") != "END_OF_DATA"]
    wins = [t for t in rule_exits if float(t.get("net_pnl", 0.0)) > 0]
    losses = [t for t in rule_exits if float(t.get("net_pnl", 0.0)) < 0]
    breakeven = [t for t in rule_exits if float(t.get("net_pnl", 0.0)) == 0]
    all_wins = [t for t in closed if float(t.get("net_pnl", 0.0)) > 0]
    all_losses = [t for t in closed if float(t.get("net_pnl", 0.0)) < 0]
    rule_net_pnls = [float(t["net_pnl"]) for t in rule_exits]
    gross_profit = sum(float(t["net_pnl"]) for t in wins)
    gross_loss = abs(sum(float(t["net_pnl"]) for t in losses))
    all_gross_profit = sum(float(t["net_pnl"]) for t in all_wins)
    all_gross_loss = abs(sum(float(t["net_pnl"]) for t in all_losses))
    final_equity = float(realized_equity_curve[-1]["equity"]) if realized_equity_curve else initial_capital

    def drawdown(values: Sequence[float]) -> tuple[float, float]:
        peak = float(initial_capital)
        max_dd = 0.0
        max_dd_pct = 0.0
        for value in values:
            peak = max(peak, float(value))
            dd = peak - float(value)
            dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
            max_dd_pct = max(max_dd_pct, dd_pct)
        return max_dd, max_dd_pct

    mtm_values = [float(p["equity"]) for p in mark_to_market_curve]
    realized_values = [float(p["equity"]) for p in realized_equity_curve]
    max_dd, max_dd_pct = drawdown(mtm_values)
    realized_dd, realized_dd_pct = drawdown(realized_values)
    r_values = [float(t["R_multiple"]) for t in rule_exits if t.get("R_multiple") is not None]
    skipped_reasons = sorted({str(t.get("skip_reason")) for t in skipped})
    return {
        "candidate_count": len(closed) + len(skipped),
        "closed_trades": len(closed),
        "rule_exit_trades": len(rule_exits),
        "end_of_data_exits": len(end_of_data),
        "time_stop_exits": sum(1 for t in closed if t.get("exit_reason") == "TIME_STOP"),
        "end_of_data_pnl": sum(float(t.get("net_pnl", 0.0)) for t in end_of_data),
        "net_profit_from_rule_exits": sum(rule_net_pnls),
        "skipped_candidates": len(skipped),
        "skipped_by_reason": {reason: sum(1 for t in skipped if t.get("skip_reason") == reason) for reason in skipped_reasons},
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate_pct": (len(wins) / len(rule_exits) * 100.0) if rule_exits else None,
        "win_rate_all_liquidations_pct": (len(all_wins) / len(closed) * 100.0) if closed else None,
        "initial_capital": float(initial_capital),
        "final_equity": final_equity,
        "net_profit": final_equity - initial_capital,
        "return_pct": ((final_equity / initial_capital) - 1.0) * 100.0,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else (None if gross_profit == 0 else "infinite"),
        "profit_factor_all_liquidations": (all_gross_profit / all_gross_loss) if all_gross_loss > 0 else (None if all_gross_profit == 0 else "infinite"),
        "expectancy_per_rule_exit": (float(np.mean(rule_net_pnls)) if rule_net_pnls else None),
        "average_R_multiple": (float(np.mean(r_values)) if r_values else None),
        "max_drawdown_cash": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "max_realized_drawdown_cash": realized_dd,
        "max_realized_drawdown_pct": realized_dd_pct,
        "drawdown_basis": "Close-to-close mark-to-market equity; open positions are hypothetically liquidated at the executable close quote with modeled slippage and round-turn commission. OHLC cannot reveal intrabar equity minima.",
        "total_commission": sum(float(t.get("commission", 0.0)) for t in closed),
        "total_spread_cost": sum(float(t.get("spread_cost", 0.0)) for t in closed),
        "total_slippage_cost": sum(float(t.get("slippage_cost", 0.0)) for t in closed),
        "total_transaction_costs": sum(float(t.get("total_transaction_costs", t.get("commission", 0.0))) for t in closed),
        "total_raw_gross_profit": sum(float(t.get("raw_gross_pnl", t.get("gross_pnl", 0.0))) for t in closed),
        "stop_gap_exits": sum(1 for t in closed if t.get("exit_reason") == "STOP_GAP"),
        "stop_first_collisions": sum(1 for t in closed if t.get("exit_reason") == "STOP_FIRST_COLLISION"),
        "losses_beyond_risk_budget": sum(1 for t in closed if t.get("risk_budget_breach", False)),
        "mean_bars_held_rule_exits": float(np.mean([int(t["bars_held"]) for t in rule_exits])) if rule_exits else None,
        "max_concurrent_positions_configured": max_concurrency,
        "note": "Net profit and final equity include end-of-data liquidation P&L. Win rate, profit factor, expectancy, and average R exclude END_OF_DATA exits; TIME_STOP exits are rule exits. Max drawdown is close-to-close mark-to-market; realized-only drawdown is separately reported.",
    }


def replay_trade_ledger_costs(
    trades: Sequence[Mapping[str, Any]],
    *,
    spread_multiplier: float = 1.0,
    override_spread_usd: Optional[float] = None,
    slippage_per_side_usd: float = 0.05,
    commission_per_lot_per_side: float = 0.0,
    contract_size_oz: float = 100.0,
    initial_capital: float = 10_000.0,
) -> dict[str, Any]:
    """Replay transaction costs on a fixed trade ledger without changing entries, exits, or lots.

    For identical trades, this guarantees:
    - Higher spread cannot decrease spread cost.
    - Higher adverse slippage cannot decrease slippage cost.
    - Higher commission cannot decrease commission expense.
    - Net P&L = Raw Gross P&L - (Spread Cost + Slippage Cost + Commission).
    """
    replayed = []
    total_raw_gross = 0.0
    total_spread_cost = 0.0
    total_slippage_cost = 0.0
    total_commission = 0.0
    total_net = 0.0

    for t in trades:
        if t.get("status") != "CLOSED":
            replayed.append(dict(t))
            continue
        lots = float(t.get("lots", 0.0))
        raw_gross = float(t.get("raw_gross_pnl", t.get("gross_pnl", 0.0)))

        # 1. Spread cost
        if override_spread_usd is not None:
            eff_spread = float(override_spread_usd)
        else:
            base_spread = float(t.get("entry_spread_usd" if t.get("side") == "LONG" else "exit_spread_usd", 0.20))
            eff_spread = base_spread * float(spread_multiplier)
        spread_charge = eff_spread * contract_size_oz * lots

        # 2. Slippage cost: entry slippage + exit slippage (if not limit take profit)
        exit_has_slippage = t.get("exit_reason") not in ("TAKE_PROFIT", "TAKE_PROFIT_GAP")
        eff_slippage_sides = 2.0 if exit_has_slippage else 1.0
        slippage_charge = eff_slippage_sides * slippage_per_side_usd * contract_size_oz * lots

        # 3. Commission cost
        commission_charge = 2.0 * commission_per_lot_per_side * lots

        # 4. Net P&L
        tot_costs = spread_charge + slippage_charge + commission_charge
        replayed_net = raw_gross - tot_costs

        trade_copy = dict(t)
        trade_copy.update({
            "replay_raw_gross_pnl": raw_gross,
            "replay_spread_cost": spread_charge,
            "replay_slippage_cost": slippage_charge,
            "replay_commission": commission_charge,
            "replay_total_costs": tot_costs,
            "replay_net_pnl": replayed_net,
        })
        replayed.append(trade_copy)

        total_raw_gross += raw_gross
        total_spread_cost += spread_charge
        total_slippage_cost += slippage_charge
        total_commission += commission_charge
        total_net += replayed_net

    rule_trades = [t for t in replayed if t.get("status") == "CLOSED" and t.get("exit_reason") != "END_OF_DATA"]
    wins = [t for t in rule_trades if t.get("replay_net_pnl", 0.0) > 0]
    losses = [t for t in rule_trades if t.get("replay_net_pnl", 0.0) < 0]
    gp = sum(t["replay_net_pnl"] for t in wins)
    gl = abs(sum(t["replay_net_pnl"] for t in losses))
    pf = (gp / gl) if gl > 0 else (None if gp == 0 else "infinite")
    wr = (len(wins) / len(rule_trades) * 100.0) if rule_trades else None

    rule_pnls = [float(t["replay_net_pnl"]) for t in rule_trades]
    expectancy = float(np.mean(rule_pnls)) if rule_pnls else None

    r_multiples = []
    for t in rule_trades:
        planned_risk = float(t.get("estimated_stop_risk_cash", 0.0))
        if planned_risk > 0:
            r = float(t["replay_net_pnl"]) / planned_risk
            t["replay_R_multiple"] = r
            r_multiples.append(r)
    avg_r = float(np.mean(r_multiples)) if r_multiples else None

    peak = float(initial_capital)
    cum = float(initial_capital)
    max_dd = 0.0
    max_dd_pct = 0.0
    for t in replayed:
        if t.get("status") == "CLOSED":
            cum += float(t["replay_net_pnl"])
            peak = max(peak, cum)
            dd = peak - cum
            max_dd = max(max_dd, dd)
            if peak > 0:
                max_dd_pct = max(max_dd_pct, (dd / peak) * 100.0)

    return {
        "trades": replayed,
        "total_trades": len([t for t in replayed if t.get("status") == "CLOSED"]),
        "rule_exit_trades": len(rule_trades),
        "total_raw_gross_profit": total_raw_gross,
        "total_spread_cost": total_spread_cost,
        "total_slippage_cost": total_slippage_cost,
        "total_commission": total_commission,
        "total_transaction_costs": total_spread_cost + total_slippage_cost + total_commission,
        "net_profit": total_net,
        "return_pct": ((total_net / initial_capital) * 100.0) if initial_capital > 0 else 0.0,
        "win_rate_pct": wr,
        "profit_factor": pf,
        "expectancy_per_rule_exit": expectancy,
        "average_R_multiple": avg_r,
        "max_drawdown_cash": max_dd,
        "max_drawdown_pct": max_dd_pct,
    }




def run_event_backtest(
    df: pd.DataFrame,
    candidates: Iterable[Any],
    config: Optional[BacktestConfig] = None,
    *,
    timeframe: str = "UNKNOWN",
) -> BacktestResult:
    """Simulate candidates with next-bar-open fills and conservative OHLC exits.

    Each candidate must expose ``signal_index``, ``direction``,
    ``stop_loss_reference``, and ``take_profit_reference``. The entry happens at
    ``signal_index + 1``. Candidates missing a next bar are logged as skipped.
    """
    config = config or BacktestConfig()
    frame = _prepare_bars(df)
    candidates_list = list(candidates)
    normalized: list[dict[str, Any]] = []
    for ordinal, c in enumerate(candidates_list, start=1):
        try:
            signal_index = int(_value(c, "signal_index"))
        except (TypeError, ValueError):
            raise ValueError(f"Candidate {ordinal} has an invalid signal_index")
        raw_time = _value(c, "signal_time", frame.iloc[signal_index]["time"] if 0 <= signal_index < len(frame) else None)
        signal_time = pd.Timestamp(raw_time).isoformat() if raw_time is not None else ""
        direction = _direction(c)
        candidate_id = str(_value(c, "setup_id", f"{timeframe}_{ordinal:04d}"))
        if direction not in {"BULLISH", "BEARISH", "LONG", "SHORT"}:
            raise ValueError(f"Candidate {candidate_id} has unsupported direction: {direction!r}")
        if signal_index < 0 or signal_index >= len(frame):
            raise ValueError(f"Candidate {candidate_id} signal_index is out of range")
        entry_index = signal_index + 1
        try:
            stop = float(_value(c, "stop_loss_reference"))
            target = float(_value(c, "take_profit_reference"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"Candidate {candidate_id} has a non-numeric stop-loss or take-profit reference"
            ) from exc
        if not math.isfinite(stop) or not math.isfinite(target) or stop <= 0 or target <= 0:
            raise ValueError(
                f"Candidate {candidate_id} must have finite, positive stop-loss and take-profit references"
            )
        audit_fields = {
            "setup_id": candidate_id,
            "timeframe": timeframe,
            "direction": direction,
            "target_source": _value(c, "target_source"),
            "signal_time": signal_time,
            "stop_loss_reference": stop,
            "take_profit_reference": target,
        }
        normalized.append({
            "candidate": c, "candidate_id": candidate_id, "signal_index": signal_index,
            "signal_time": signal_time, "entry_index": entry_index, "stop": stop,
            "target": target, "direction": direction, "audit_fields": audit_fields,
        })
    normalized.sort(key=lambda item: (item["entry_index"], item["signal_index"], item["candidate_id"]))
    candidates_by_entry: dict[int, list[dict[str, Any]]] = {}
    no_next_bar_items: list[dict[str, Any]] = []
    for item in normalized:
        if item["entry_index"] >= len(frame):
            no_next_bar_items.append(item)
        else:
            candidates_by_entry.setdefault(item["entry_index"], []).append(item)

    equity = float(config.initial_capital)
    active: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = [
        _skipped_trade(item["candidate"], item["candidate_id"], "no_next_bar", item["signal_index"], item["signal_time"])
        for item in no_next_bar_items
    ]
    mark_to_market_curve: list[dict[str, Any]] = []
    max_open_seen = 0

    for bar_index in range(len(frame)):
        bar = frame.iloc[bar_index]
        # Entries at this bar's open must not use P&L from exits that occur later
        # within the same bar. Position sizing is based on the realized balance
        # carried into the bar.
        sizing_equity_at_open = equity
        # Positions held at the start of this bar reserve concurrency slots for
        # this entire bar, even if a stop/target is touched intrabar. This avoids
        # granting a second entry the benefit of unknown intrabar event ordering.
        active_at_open = list(active)
        survivors: list[dict[str, Any]] = []
        for position in active_at_open:
            event = _make_exit(position, frame, bar_index, config)
            if event is None:
                event = _make_time_exit(position, frame, bar_index, config)
            if event is None:
                survivors.append(position)
            else:
                trade, equity = _finalize_trade(position, event, frame, equity, config)
                trades.append(trade)
        active = survivors

        slots_this_open = max(0, config.max_concurrent_positions - len(active_at_open))
        entered_this_open = 0
        new_positions: list[dict[str, Any]] = []
        for item in candidates_by_entry.get(bar_index, []):
            cand, cid = item["candidate"], item["candidate_id"]
            signal_i, signal_time, entry_i = item["signal_index"], item["signal_time"], item["entry_index"]
            if entry_i >= len(frame):
                trades.append(_skipped_trade(cand, cid, "no_next_bar", signal_i, signal_time))
                continue
            if entered_this_open >= slots_this_open:
                trades.append(_skipped_trade(cand, cid, "max_concurrent_positions", signal_i, signal_time))
                continue

            row = frame.iloc[entry_i]
            spread, spread_source = _spread_usd(row, config)
            bid_open = float(row["open"])
            direction = item["direction"]
            side = "LONG" if direction in {"BULLISH", "LONG"} else "SHORT"
            ask_open = bid_open + spread
            if side == "LONG":
                entry_price = ask_open + config.slippage_per_side_usd
                stop_exit_estimate = item["stop"] - config.slippage_per_side_usd
                # A long stop is triggered on the Bid side. Reject an order if
                # the executable Bid quote has already reached/passed its stop.
                directionally_valid = item["stop"] < bid_open and entry_price < item["target"]
            else:
                entry_price = bid_open - config.slippage_per_side_usd
                stop_exit_estimate = item["stop"] + config.slippage_per_side_usd
                # A short stop is triggered on the Ask side. Reject an order if
                # the executable Ask quote has already reached/passed its stop.
                directionally_valid = item["target"] < entry_price and item["stop"] > ask_open
            if not directionally_valid:
                trades.append(_skipped_trade(cand, cid, "invalid_stop_or_target_after_fill_costs", signal_i, signal_time))
                continue

            risk_per_lot = abs(entry_price - stop_exit_estimate) * config.contract_size_oz + 2.0 * config.commission_per_lot_per_side
            if not math.isfinite(risk_per_lot) or risk_per_lot <= 0:
                trades.append(_skipped_trade(cand, cid, "invalid_risk_distance", signal_i, signal_time))
                continue
            risk_budget = sizing_equity_at_open * config.risk_fraction
            unrounded_lots = min(config.max_lots, risk_budget / risk_per_lot)
            lots = math.floor((unrounded_lots + 1e-12) / config.lot_step) * config.lot_step
            lots = round(lots, 8)
            if lots < config.min_lot:
                trades.append(_skipped_trade(cand, cid, "risk_budget_below_min_lot", signal_i, signal_time))
                continue
            estimated_stop_risk = risk_per_lot * lots
            pos = {
                "audit_fields": item["audit_fields"],
                "side": side,
                "signal_index": signal_i,
                "signal_time": signal_time,
                "entry_index": entry_i,
                "entry_price": entry_price,
                "entry_reference_open": bid_open,
                "entry_spread_usd": spread,
                "entry_spread_source": spread_source,
                "stop_loss": item["stop"],
                "take_profit": item["target"],
                "lots": lots,
                "risk_budget_cash": risk_budget,
                "estimated_stop_risk_cash": estimated_stop_risk,
            }
            entered_this_open += 1
            new_positions.append(pos)
            max_open_seen = max(max_open_seen, len(active_at_open) + len(new_positions))

        # A new position can be stopped or take profit on its entry bar. OHLC
        # cannot establish the path if both levels were touched; stop-first wins.
        for position in new_positions:
            event = _make_exit(position, frame, position["entry_index"], config)
            if event is None:
                event = _make_time_exit(position, frame, position["entry_index"], config)
            if event is None:
                active.append(position)
            else:
                trade, equity = _finalize_trade(position, event, frame, equity, config)
                trades.append(trade)

        # Record close-to-close mark-to-market equity. Open positions are valued
        # at a hypothetical executable liquidation quote, including exit slippage
        # and round-turn commission, so floating losses are represented in DD.
        unrealized_pnl = 0.0
        for position in active:
            mark_spread, _mark_source = _spread_usd(bar, config)
            if position["side"] == "LONG":
                liquidation_price = float(bar["close"]) - config.slippage_per_side_usd
                sign = 1.0
            else:
                liquidation_price = float(bar["close"]) + mark_spread + config.slippage_per_side_usd
                sign = -1.0
            gross_mark_pnl = (liquidation_price - position["entry_price"]) * sign * config.contract_size_oz * position["lots"]
            estimated_round_turn_commission = 2.0 * config.commission_per_lot_per_side * position["lots"]
            unrealized_pnl += gross_mark_pnl - estimated_round_turn_commission
        mark_to_market_curve.append({
            "time": bar["time"].isoformat(),
            "equity": equity + unrealized_pnl,
            "realized_equity": equity,
            "unrealized_pnl": unrealized_pnl,
            "open_positions": len(active),
        })

    # Close any remaining positions on the final available bar so reported equity
    # is realized at the sample boundary. This is an explicit end-of-data exit.
    if active:
        last_index = len(frame) - 1
        last_row = frame.iloc[last_index]
        spread, source = _spread_usd(last_row, config)
        for position in active:
            if position["side"] == "LONG":
                exit_price = float(last_row["close"]) - config.slippage_per_side_usd
            else:
                exit_price = float(last_row["close"]) + spread + config.slippage_per_side_usd
            event = {"exit_index": last_index, "exit_price": exit_price, "exit_reason": "END_OF_DATA", "exit_spread_usd": spread, "exit_spread_source": source}
            trade, equity = _finalize_trade(position, event, frame, equity, config)
            trades.append(trade)

    # Aggregate the realized cash equity by exit timestamp. The primary equity
    # curve is the mark-to-market series recorded on every completed bar.
    # Aggregate same-time exits to avoid arbitrary intra-timestamp ordering.
    pnl_by_time: dict[str, float] = {}
    count_by_time: dict[str, int] = {}
    for trade in trades:
        if trade.get("status") != "CLOSED":
            continue
        exit_time = str(trade["exit_time"])
        pnl_by_time[exit_time] = pnl_by_time.get(exit_time, 0.0) + float(trade["net_pnl"])
        count_by_time[exit_time] = count_by_time.get(exit_time, 0) + 1
    realized_equity = float(config.initial_capital)
    realized_equity_curve: list[dict[str, Any]] = []
    equity_after_by_time: dict[str, float] = {}
    for exit_time in sorted(pnl_by_time):
        net_at_time = pnl_by_time[exit_time]
        realized_equity += net_at_time
        equity_after_by_time[exit_time] = realized_equity
        realized_equity_curve.append({
            "time": exit_time,
            "equity": realized_equity,
            "net_pnl": net_at_time,
            "trades_closed": count_by_time[exit_time],
        })
    for trade in trades:
        if trade.get("status") == "CLOSED":
            trade["equity_after"] = equity_after_by_time[str(trade["exit_time"])]

    # At the sample boundary, all remaining positions were just liquidated using
    # the same quote/slippage/commission formula as the final mark. Reflect the
    # realized final state in the last mark so the curve and account balance agree.
    if mark_to_market_curve:
        mark_to_market_curve[-1].update({
            "equity": realized_equity,
            "realized_equity": realized_equity,
            "unrealized_pnl": 0.0,
            "open_positions": 0,
            "end_of_data_liquidation": bool(any(t.get("exit_reason") == "END_OF_DATA" for t in trades if t.get("status") == "CLOSED")),
        })
    equity_curve = mark_to_market_curve

    # Keep stable chronological ordering; all setup/collision/skip rows are traceable.
    trades.sort(key=lambda t: (str(t.get("entry_time", t.get("signal_time", ""))), str(t.get("setup_id", ""))))
    metrics = _metrics(trades, config.initial_capital, equity_curve, realized_equity_curve, config.max_concurrent_positions)
    metrics["max_open_positions_observed"] = max_open_seen
    metrics["max_holding_bars_configured"] = config.max_holding_bars
    return BacktestResult(
        trades=trades,
        metrics=metrics,
        equity_curve=equity_curve,
        realized_equity_curve=realized_equity_curve,
        config=asdict(config),
    )
