"""SMC_CONFLUENCE_V1 Strategy Candidate for GoldFlow.

Systematic XAU/USD trading strategy integrating:
1. Higher-Timeframe Order Flow (D1 + H4 alignment)
2. Session Liquidity Windows (London & New York high-volume hours)
3. High-Impact USD News Protection (pre- and post-release blackout)
4. Dynamic ATR stop management and breakeven capital protection

Preserves the frozen baseline SMC detector completely and provides independent
filter toggles for controlled ablation research.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from src.backtesting.engine import (
    BacktestConfig,
    BacktestResult,
    _make_exit_from_values,
    _make_time_exit_from_values,
    _prepare_bars,
    _skipped_trade,
    _spread_usd_from_raw,
    run_event_backtest,
)
from src.risk.engine import RiskConfig, RiskEngine
from src.risk.trade_management import (
    adjust_candidate_with_atr,
    check_breakeven_trigger,
    compute_atr,
)
from src.smc.engine import analyze_smc, SMCConfig
from src.smc.models import SMCAnalysisResult, SMCDirection
from src.strategy.htf_bias import HTFBiasResult, HTFDirectionalBiasEngine
from src.strategy.news_filter import HighImpactNewsFilter, NewsFilterConfig
from src.strategy.session_filter import SessionFilterConfig, SessionLiquidityFilter
from src.strategy.smc_setups import (
    SMCSetupCandidate,
    SMCSetupConfig,
    detect_smc_setups_with_funnel,
)


@dataclass(frozen=True)
class SMCConfluenceConfig:
    """Configuration for SMC_CONFLUENCE_V1 strategy."""
    enable_htf_bias: bool = True
    enable_session_filter: bool = True
    enable_news_filter: bool = True
    enable_atr_stop: bool = True
    enable_breakeven: bool = True

    # Risk & execution parameters
    risk_per_trade_pct: float = 0.005  # 0.5% risk
    max_daily_drawdown_pct: float = 0.02  # 2.0% daily limit
    max_concurrency: int = 1
    max_spread_dollars: float = 0.35  # $0.35 max spread
    min_atr_multiple: float = 1.5
    breakeven_r_trigger: float = 1.5
    breakeven_buffer_usd: float = 0.05
    fixed_rr: float = 2.0


class SMCConfluenceStrategy:
    """Encapsulates the complete confluence evaluation pipeline."""

    def __init__(
        self,
        h4_df: Optional[pd.DataFrame] = None,
        *,
        news_calendar_source: Optional[Union[str, Path, pd.DataFrame]] = None,
        config: Optional[SMCConfluenceConfig] = None,
        setup_config: Optional[SMCSetupConfig] = None,
        smc_config: Optional[SMCConfig] = None,
    ) -> None:
        self.config = config or SMCConfluenceConfig()
        self.setup_config = setup_config or SMCSetupConfig()
        self.smc_config = smc_config or SMCConfig()

        # 1. HTF Bias Engine
        self.htf_engine: Optional[HTFDirectionalBiasEngine] = None
        if h4_df is not None:
            self.htf_engine = HTFDirectionalBiasEngine(h4_df)

        # 2. Session Liquidity Filter
        self.session_filter = SessionLiquidityFilter()

        # 3. High-Impact News Filter
        self.news_filter = HighImpactNewsFilter(calendar_source=news_calendar_source)

        # 4. Risk Engine
        self.risk_engine = RiskEngine(
            RiskConfig(
                risk_per_trade_pct=self.config.risk_per_trade_pct,
                max_daily_drawdown_pct=self.config.max_daily_drawdown_pct,
                max_concurrency=self.config.max_concurrency,
                max_spread_dollars=self.config.max_spread_dollars,
            )
        )

    def generate_candidates(
        self,
        df: pd.DataFrame,
        timeframe: str,
        smc_result: Optional[SMCAnalysisResult] = None,
    ) -> tuple[list[SMCSetupCandidate], dict[str, Any], list[dict[str, Any]]]:
        """Detect baseline SMC candidates and apply enabled confluence filters."""
        # Step 1: Detect baseline candidates
        if smc_result is None:
            smc_result = analyze_smc(df, symbol="XAUUSD", timeframe=timeframe, config=self.smc_config)

        raw_candidates, raw_funnel = detect_smc_setups_with_funnel(df, smc_result, self.setup_config)

        # Step 2: Compute ATR series for volatility-based stops
        atr_series = compute_atr(df, period=14) if self.config.enable_atr_stop else None

        accepted: list[SMCSetupCandidate] = []
        audit_rows: list[dict[str, Any]] = []
        rejection_counter: Counter[str] = Counter()

        for ordinal, cand in enumerate(raw_candidates, start=1):
            entry_time = cand.next_bar_time
            if entry_time is None:
                rejection_counter["no_next_bar"] += 1
                audit_rows.append({
                    "candidate_ordinal": ordinal,
                    "signal_time": pd.Timestamp(cand.signal_time).isoformat(),
                    "entry_time": None,
                    "direction": cand.direction.value,
                    "accepted": False,
                    "rejection_reason": "no_next_bar",
                })
                continue

            # Volatility-adjusted stop expansion
            working_cand = cand
            if self.config.enable_atr_stop and atr_series is not None:
                sig_idx = int(cand.signal_index)
                if 0 <= sig_idx < len(atr_series):
                    atr_val = float(atr_series.iloc[sig_idx])
                    working_cand = adjust_candidate_with_atr(
                        cand,
                        atr_val,
                        min_atr_multiple=self.config.min_atr_multiple,
                        fixed_rr=self.config.fixed_rr,
                    )

            # Filter 1: Higher-Timeframe Bias
            htf_bias_res: Optional[HTFBiasResult] = None
            if self.config.enable_htf_bias:
                if self.htf_engine is None:
                    reason = "htf_engine_uninitialized"
                    rejection_counter[reason] += 1
                    audit_rows.append({
                        "candidate_ordinal": ordinal,
                        "signal_time": pd.Timestamp(cand.signal_time).isoformat(),
                        "entry_time": pd.Timestamp(entry_time).isoformat(),
                        "direction": cand.direction.value,
                        "accepted": False,
                        "rejection_reason": reason,
                    })
                    continue

                htf_bias_res = self.htf_engine.evaluate_bias(entry_time)
                if not htf_bias_res.is_aligned:
                    reason = htf_bias_res.rejection_reason or "htf_not_aligned"
                    rejection_counter[reason] += 1
                    audit_rows.append({
                        "candidate_ordinal": ordinal,
                        "signal_time": pd.Timestamp(cand.signal_time).isoformat(),
                        "entry_time": pd.Timestamp(entry_time).isoformat(),
                        "direction": cand.direction.value,
                        "htf_bias": htf_bias_res.bias.value,
                        "accepted": False,
                        "rejection_reason": reason,
                    })
                    continue

                if working_cand.direction != htf_bias_res.bias:
                    reason = "candidate_direction_mismatch"
                    rejection_counter[reason] += 1
                    audit_rows.append({
                        "candidate_ordinal": ordinal,
                        "signal_time": pd.Timestamp(cand.signal_time).isoformat(),
                        "entry_time": pd.Timestamp(entry_time).isoformat(),
                        "direction": cand.direction.value,
                        "htf_bias": htf_bias_res.bias.value,
                        "accepted": False,
                        "rejection_reason": reason,
                    })
                    continue

            # Filter 2: Session Liquidity
            matched_session = None
            if self.config.enable_session_filter:
                session_ok, matched_session, s_reason = self.session_filter.evaluate_timestamp(entry_time)
                if not session_ok:
                    rejection_counter[s_reason or "session_rejected"] += 1
                    audit_rows.append({
                        "candidate_ordinal": ordinal,
                        "signal_time": pd.Timestamp(cand.signal_time).isoformat(),
                        "entry_time": pd.Timestamp(entry_time).isoformat(),
                        "direction": cand.direction.value,
                        "htf_bias": htf_bias_res.bias.value if htf_bias_res else None,
                        "session": matched_session,
                        "accepted": False,
                        "rejection_reason": s_reason,
                    })
                    continue

            # Filter 3: High-Impact News Blackout
            nearest_event = None
            minutes_to_event = None
            if self.config.enable_news_filter:
                blocked, nearest_event, n_reason, minutes_to_event = self.news_filter.evaluate_timestamp(entry_time)
                if blocked:
                    rejection_counter["news_blackout"] += 1
                    audit_rows.append({
                        "candidate_ordinal": ordinal,
                        "signal_time": pd.Timestamp(cand.signal_time).isoformat(),
                        "entry_time": pd.Timestamp(entry_time).isoformat(),
                        "direction": cand.direction.value,
                        "htf_bias": htf_bias_res.bias.value if htf_bias_res else None,
                        "session": matched_session,
                        "nearest_event": nearest_event,
                        "minutes_to_event": round(minutes_to_event, 1) if minutes_to_event else None,
                        "accepted": False,
                        "rejection_reason": n_reason,
                    })
                    continue

            # Candidate passed all active filters!
            accepted.append(working_cand)
            audit_rows.append({
                "candidate_ordinal": ordinal,
                "signal_time": pd.Timestamp(cand.signal_time).isoformat(),
                "entry_time": pd.Timestamp(entry_time).isoformat(),
                "direction": cand.direction.value,
                "htf_bias": htf_bias_res.bias.value if htf_bias_res else None,
                "session": matched_session,
                "nearest_event": nearest_event,
                "minutes_to_event": round(minutes_to_event, 1) if minutes_to_event else None,
                "risk_distance": working_cand.risk_distance,
                "target_source": working_cand.target_source,
                "accepted": True,
                "rejection_reason": None,
            })

        funnel = {
            "raw_candidates_input": len(raw_candidates),
            "confluence_accepted": len(accepted),
            "confluence_rejected": len(raw_candidates) - len(accepted),
            "rejection_breakdown": dict(sorted(rejection_counter.items())),
            "active_filters": {
                "htf_bias": self.config.enable_htf_bias,
                "session_filter": self.config.enable_session_filter,
                "news_filter": self.config.enable_news_filter,
                "atr_stop": self.config.enable_atr_stop,
                "breakeven": self.config.enable_breakeven,
            },
        }
        return accepted, funnel, audit_rows


def run_confluence_backtest(
    df: pd.DataFrame,
    candidates: Sequence[SMCSetupCandidate],
    config: Optional[BacktestConfig] = None,
    *,
    timeframe: str = "M15",
    enable_breakeven: bool = False,
    breakeven_r_trigger: float = 1.5,
    breakeven_buffer_usd: float = 0.05,
    max_daily_drawdown_pct: float = 0.02,
    max_spread_dollars: float = 0.35,
) -> BacktestResult:
    """Execute backtest for confluence candidates with optional trailing breakeven.

    When enable_breakeven is False, executes through canonical run_event_backtest.
    When enable_breakeven is True, runs bar-by-bar execution tracking intrabar
    favorable excursion: when high/low touches +1.5R, stop loss is moved to
    entry + breakeven_buffer_usd, locking in risk-free trade status.
    Also enforces daily drawdown circuit breaker (2%) and max spread ($0.35).
    """
    config = config or BacktestConfig()
    if not enable_breakeven:
        return run_event_backtest(df, candidates, config, timeframe=timeframe)

    # Custom execution pass with Breakeven and Daily Drawdown circuit breaker
    frame = _prepare_bars(df)
    bar_times = list(frame["time"])
    time_iso_values = [timestamp.isoformat() for timestamp in bar_times]
    opens = frame["open"].to_numpy(dtype=float, copy=False)
    highs = frame["high"].to_numpy(dtype=float, copy=False)
    lows = frame["low"].to_numpy(dtype=float, copy=False)
    closes = frame["close"].to_numpy(dtype=float, copy=False)
    has_spread = "spread" in frame.columns
    spreads = frame["spread"].to_numpy(dtype=float, copy=False) if has_spread else None

    # Sort candidates
    normalized = []
    for ord_idx, c in enumerate(candidates, start=1):
        sig_i = int(c.signal_index)
        entry_i = sig_i + 1
        stop = float(c.stop_loss_reference)
        target = float(c.take_profit_reference)
        cid = f"{timeframe}_{ord_idx:04d}"
        sig_time = pd.Timestamp(c.signal_time).isoformat()
        direction = c.direction.value
        audit_fields = {
            "setup_id": cid,
            "timeframe": timeframe,
            "direction": direction,
            "target_source": c.target_source,
            "signal_time": sig_time,
            "stop_loss_reference": stop,
            "take_profit_reference": target,
        }
        normalized.append({
            "candidate": c, "candidate_id": cid, "signal_index": sig_i,
            "signal_time": sig_time, "entry_index": entry_i, "stop": stop,
            "target": target, "direction": direction, "audit_fields": audit_fields,
        })
    normalized.sort(key=lambda item: (item["entry_index"], item["signal_index"], item["candidate_id"]))

    candidates_by_entry: dict[int, list[dict[str, Any]]] = {}
    no_next_bar_items = []
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
    realized_equity_curve: list[dict[str, Any]] = []

    # Daily drawdown tracker
    tracker = RiskEngine(RiskConfig(account_equity=equity, max_daily_drawdown_pct=max_daily_drawdown_pct)).tracker

    for bar_index in range(len(frame)):
        bar_time = bar_times[bar_index]
        raw_spread = spreads[bar_index] if spreads is not None else None
        current_spread, current_spread_source = _spread_usd_from_raw(raw_spread, has_spread, config)
        sizing_equity_at_open = equity
        active_at_open = list(active)
        survivors: list[dict[str, Any]] = []

        # Check exits on existing active positions
        for position in active_at_open:
            # First, check if breakeven trigger was touched during this bar before exit evaluation
            fired, new_sl = check_breakeven_trigger(
                position,
                highs[bar_index],
                lows[bar_index],
                be_r_trigger=breakeven_r_trigger,
                be_buffer_usd=breakeven_buffer_usd,
            )
            if fired:
                position["stop_loss"] = new_sl
                position["breakeven_active"] = True

            event = _make_exit_from_values(
                position, bar_index, opens[bar_index], highs[bar_index], lows[bar_index],
                current_spread, current_spread_source, config,
            )
            if event is None:
                event = _make_time_exit_from_values(
                    position, bar_index, closes[bar_index], current_spread,
                    current_spread_source, config,
                )
            if event is None:
                survivors.append(position)
            else:
                trade, equity = _finalize_confluence_trade(
                    position, event, frame, equity, config, time_iso_values
                )
                trades.append(trade)
                tracker.on_trade_closed(bar_time, trade["net_pnl"], equity)
                realized_equity_curve.append({
                    "bar_index": bar_index,
                    "time": time_iso_values[bar_index],
                    "equity": equity,
                })
        active = survivors

        # New entries
        slots_this_open = max(0, config.max_concurrent_positions - len(active_at_open))
        entered_this_open = 0
        new_positions: list[dict[str, Any]] = []

        # Check circuit breaker
        is_breaker_active = tracker.is_circuit_breaker_active(bar_time, equity)

        for item in candidates_by_entry.get(bar_index, []):
            cand, cid = item["candidate"], item["candidate_id"]
            sig_i, sig_time, entry_i = item["signal_index"], item["signal_time"], item["entry_index"]
            if entry_i >= len(frame):
                trades.append(_skipped_trade(cand, cid, "no_next_bar", sig_i, sig_time))
                continue
            if entered_this_open >= slots_this_open:
                trades.append(_skipped_trade(cand, cid, "max_concurrent_positions", sig_i, sig_time))
                continue
            if is_breaker_active:
                trades.append(_skipped_trade(cand, cid, "daily_drawdown_circuit_breaker", sig_i, sig_time))
                continue

            entry_spread_raw = spreads[entry_i] if spreads is not None else None
            spread, spread_source = _spread_usd_from_raw(entry_spread_raw, has_spread, config)

            if spread > max_spread_dollars:
                trades.append(_skipped_trade(cand, cid, "spread_exceeds_threshold", sig_i, sig_time))
                continue

            bid_open = float(opens[entry_i])
            direction = item["direction"]
            side = "LONG" if direction in {"BULLISH", "LONG"} else "SHORT"
            ask_open = bid_open + spread
            if side == "LONG":
                entry_price = ask_open + config.slippage_per_side_usd
                stop_exit_estimate = item["stop"] - config.slippage_per_side_usd
                valid = item["stop"] < bid_open and entry_price < item["target"]
            else:
                entry_price = bid_open - config.slippage_per_side_usd
                stop_exit_estimate = item["stop"] + config.slippage_per_side_usd
                valid = item["target"] < entry_price and item["stop"] > ask_open
            if not valid:
                trades.append(_skipped_trade(cand, cid, "invalid_stop_or_target_after_fill_costs", sig_i, sig_time))
                continue

            risk_per_lot = abs(entry_price - stop_exit_estimate) * config.contract_size_oz + 2.0 * config.commission_per_lot_per_side
            if not math.isfinite(risk_per_lot) or risk_per_lot <= 0:
                trades.append(_skipped_trade(cand, cid, "invalid_risk_distance", sig_i, sig_time))
                continue
            risk_budget = sizing_equity_at_open * config.risk_fraction
            unrounded_lots = min(config.max_lots, risk_budget / risk_per_lot)
            lots = math.floor((unrounded_lots + 1e-12) / config.lot_step) * config.lot_step
            lots = round(lots, 8)
            if lots < config.min_lot:
                trades.append(_skipped_trade(cand, cid, "risk_budget_below_min_lot", sig_i, sig_time))
                continue

            estimated_stop_risk = risk_per_lot * lots
            pos = {
                "audit_fields": item["audit_fields"],
                "side": side,
                "signal_index": sig_i,
                "signal_time": sig_time,
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
                "breakeven_active": False,
            }
            entered_this_open += 1
            new_positions.append(pos)

        # Intrabar exits for same-bar entries
        for position in new_positions:
            entry_bar_idx = position["entry_index"]
            entry_sp_raw = spreads[entry_bar_idx] if spreads is not None else None
            entry_sp, entry_sp_src = _spread_usd_from_raw(entry_sp_raw, has_spread, config)
            event = _make_exit_from_values(
                position, entry_bar_idx, opens[entry_bar_idx], highs[entry_bar_idx],
                lows[entry_bar_idx], entry_sp, entry_sp_src, config,
            )
            if event is None:
                active.append(position)
            else:
                trade, equity = _finalize_confluence_trade(
                    position, event, frame, equity, config, time_iso_values
                )
                trades.append(trade)
                tracker.on_trade_closed(bar_time, trade["net_pnl"], equity)
                realized_equity_curve.append({
                    "bar_index": entry_bar_idx,
                    "time": time_iso_values[entry_bar_idx],
                    "equity": equity,
                })

        mark_to_market_curve.append({
            "bar_index": bar_index,
            "time": time_iso_values[bar_index],
            "equity": equity,
        })

    # Close remaining positions at end of data
    if active:
        last_idx = len(frame) - 1
        last_time = time_iso_values[last_idx]
        for position in active:
            trade, equity = _finalize_confluence_trade(
                position,
                {
                    "exit_index": last_idx,
                    "exit_price": opens[last_idx],
                    "raw_exit_price": opens[last_idx],
                    "exit_reason": "END_OF_DATA",
                    "exit_spread_usd": current_spread,
                    "exit_spread_source": current_spread_source,
                },
                frame,
                equity,
                config,
                time_iso_values,
            )
            trades.append(trade)

    from src.backtesting.engine import _metrics
    metrics = _metrics(trades, config.initial_capital, mark_to_market_curve, realized_equity_curve, config.max_concurrent_positions)
    return BacktestResult(
        trades=trades,
        metrics=metrics,
        equity_curve=mark_to_market_curve,
        realized_equity_curve=realized_equity_curve,
        config=config.__dict__,
    )


def _finalize_confluence_trade(
    position: dict[str, Any],
    exit_event: Mapping[str, Any],
    frame: pd.DataFrame,
    equity: float,
    config: BacktestConfig,
    time_iso_values: Optional[Sequence[str]] = None,
) -> tuple[dict[str, Any], float]:
    """Helper to finalize trade P&L with breakeven annotations."""
    from src.backtesting.engine import _finalize_trade
    trade, new_equity = _finalize_trade(position, exit_event, frame, equity, config, time_iso_values)
    trade["breakeven_active"] = position.get("breakeven_active", False)
    return trade, new_equity
