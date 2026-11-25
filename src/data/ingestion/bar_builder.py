"""
Deterministic M1 Bar Synthesis from Raw Ticks for GoldFlow.

Aggregates continuous raw tick observations into [T, T+60s) 1-minute bars without
artificial candle interpolation, preserving granular spread distributions and volume metrics.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from src.data.ingestion.models import AggregatedBar, RawTickObservation


class M1BarBuilder:
    """
    Constructs deterministic M1 candlestick bars from raw tick streams.
    
    Adheres strictly to the [T, T+60s) left-closed, right-open interval standard:
    a tick at 12:00:00.000 belongs to the 12:00 bar;
    a tick at 12:00:59.999 belongs to the 12:00 bar;
    a tick at 12:01:00.000 belongs to the 12:01 bar.
    """

    def __init__(self, price_source: str = "bid", symbol: str = "XAUUSD") -> None:
        if price_source not in ("bid", "mid", "ask"):
            raise ValueError(f"Invalid price_source '{price_source}'. Allowed: 'bid', 'mid', 'ask'.")
        self.price_source = price_source
        self.symbol = symbol

    def synthesize_bars(
        self,
        ticks: Union[List[RawTickObservation], pd.DataFrame],
        exclude_incomplete_trailing_bar: bool = False,
    ) -> Tuple[List[AggregatedBar], pd.DataFrame]:
        """
        Aggregate raw ticks into M1 bars.

        Parameters
        ----------
        ticks : List[RawTickObservation] or pd.DataFrame
            Validated tick observations with 'timestamp_utc'.
        exclude_incomplete_trailing_bar : bool
            If True, drops the final bar if it has fewer ticks or is still forming.

        Returns
        -------
        Tuple[List[AggregatedBar], pd.DataFrame]
            List of AggregatedBar objects and equivalent pandas DataFrame.
        """
        if isinstance(ticks, list):
            if not ticks:
                return [], self._empty_bar_df()
            records = [{
                "timestamp_utc": t.timestamp_utc,
                "symbol": t.symbol,
                "bid": t.bid,
                "ask": t.ask,
                "spread": t.spread,
                "mid": t.mid,
                "volume": t.volume,
                "sequence_id": t.sequence_id,
                "provider": t.provider,
            } for t in ticks]
            df = pd.DataFrame(records)
        elif isinstance(ticks, pd.DataFrame):
            if ticks.empty:
                return [], self._empty_bar_df()
            df = ticks.copy()
        else:
            raise TypeError(f"Unsupported ticks type: {type(ticks)}")

        if "timestamp_utc" not in df.columns:
            if "time" in df.columns:
                df["timestamp_utc"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
            else:
                raise ValueError("Ticks dataframe must contain 'timestamp_utc' or 'time' column.")
        else:
            df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True, format="ISO8601")

        # Sort monotonically
        df = df.sort_values("timestamp_utc").reset_index(drop=True)

        # Price source selection
        if self.price_source == "bid":
            price_series = df["bid"]
        elif self.price_source == "ask":
            price_series = df["ask"]
        else:
            price_series = df["mid"] if "mid" in df.columns else (df["bid"] + df["ask"]) / 2.0

        spread_series = df["spread"] if "spread" in df.columns else (df["ask"] - df["bid"])
        volume_series = df["volume"] if "volume" in df.columns else pd.Series(1.0, index=df.index)

        df["_target_price"] = price_series
        df["_spread"] = spread_series
        df["_volume"] = volume_series

        # Assign bar interval [T, T+60s) via floor
        df["bar_time"] = df["timestamp_utc"].dt.floor("1min")

        grouped = df.groupby("bar_time", sort=True)

        bars: List[AggregatedBar] = []
        rows: List[Dict[str, Any]] = []

        total_groups = len(grouped)
        group_idx = 0

        for bar_time, group in grouped:
            group_idx += 1
            is_last = (group_idx == total_groups)
            is_incomplete = False

            if is_last and exclude_incomplete_trailing_bar:
                continue

            prices = group["_target_price"].to_numpy()
            spreads = group["_spread"].to_numpy()
            vols = group["_volume"].to_numpy()

            open_p = float(prices[0])
            high_p = float(np.max(prices))
            low_p = float(np.min(prices))
            close_p = float(prices[-1])

            spread_open = float(spreads[0])
            spread_close = float(spreads[-1])
            spread_min = float(np.min(spreads))
            spread_max = float(np.max(spreads))
            spread_mean = float(np.mean(spreads))

            tick_count = len(group)
            real_vol = float(np.sum(vols))

            seq_series = group["sequence_id"].dropna() if "sequence_id" in group.columns else pd.Series([], dtype=float)
            first_seq = int(seq_series.iloc[0]) if len(seq_series) > 0 else None
            last_seq = int(seq_series.iloc[-1]) if len(seq_series) > 0 else None

            bar = AggregatedBar(
                timestamp_utc=bar_time,
                symbol=self.symbol,
                timeframe="M1",
                open=round(open_p, 2),
                high=round(high_p, 2),
                low=round(low_p, 2),
                close=round(close_p, 2),
                tick_volume=tick_count,
                volume=round(real_vol, 2),
                spread_open=round(spread_open, 5),
                spread_close=round(spread_close, 5),
                spread_min=round(spread_min, 5),
                spread_max=round(spread_max, 5),
                spread_mean=round(spread_mean, 5),
                tick_count=tick_count,
                is_incomplete=is_incomplete,
                first_sequence_id=first_seq,
                last_sequence_id=last_seq,
                price_source=self.price_source,
            )
            bars.append(bar)
            rows.append(bar.to_dict())

        if not rows:
            return [], self._empty_bar_df()

        bar_df = pd.DataFrame(rows)
        bar_df["time"] = pd.to_datetime(bar_df["time"], utc=True)
        return bars, bar_df

    def _empty_bar_df(self) -> pd.DataFrame:
        df = pd.DataFrame(
            columns=[
                "time", "symbol", "timeframe", "open", "high", "low", "close",
                "tick_volume", "real_volume", "spread", "spread_open",
                "spread_close", "spread_min", "spread_max", "spread_mean",
                "tick_count", "is_incomplete",
            ]
        )
        df["time"] = pd.to_datetime(df["time"], utc=True)
        return df


def synthesize_m1_bars(
    ticks: Union[List[RawTickObservation], pd.DataFrame],
    price_source: str = "bid",
    symbol: str = "XAUUSD",
    exclude_incomplete_trailing_bar: bool = False,
) -> Tuple[List[AggregatedBar], pd.DataFrame]:
    """
    Convenience function to synthesize M1 bars from raw ticks.
    """
    builder = M1BarBuilder(price_source=price_source, symbol=symbol)
    return builder.synthesize_bars(ticks, exclude_incomplete_trailing_bar=exclude_incomplete_trailing_bar)
