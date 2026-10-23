"""Backtesting engines and execution models for GoldFlow."""

from .engine import BacktestConfig, BacktestResult, run_event_backtest

__all__ = ["BacktestConfig", "BacktestResult", "run_event_backtest"]
