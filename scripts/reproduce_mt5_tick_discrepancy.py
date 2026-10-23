"""
Diagnostic script to reproduce and investigate the MT5 tick-value discrepancy on live MT5 terminal.
Performs read-only calculations using mt5.order_calc_profit. No orders placed.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import MetaTrader5 as mt5


def main():
    if not mt5.initialize():
        print(f"ERROR: mt5.initialize() failed: {mt5.last_error()}")
        sys.exit(2)

    try:
        acc = mt5.account_info()
        term = mt5.terminal_info()

        acc_dict = {
            "login": getattr(acc, "login", None),
            "server": getattr(acc, "server", None),
            "company": getattr(acc, "company", None),
            "currency": getattr(acc, "currency", None),
            "leverage": getattr(acc, "leverage", None),
            "trade_mode": getattr(acc, "trade_mode", None),
        }

        term_dict = {
            "name": getattr(term, "name", None),
            "company": getattr(term, "company", None),
            "build": getattr(term, "build", None),
            "connected": getattr(term, "connected", None),
        }

        symbol = "XAUUSD"
        if not mt5.symbol_select(symbol, True):
            print(f"ERROR: Cannot select symbol {symbol}: {mt5.last_error()}")
            sys.exit(2)

        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)

        info_dict = {
            "name": getattr(info, "name", None),
            "digits": getattr(info, "digits", None),
            "point": getattr(info, "point", None),
            "spread": getattr(info, "spread", None),
            "spread_float": getattr(info, "spread_float", None),
            "trade_calc_mode": getattr(info, "trade_calc_mode", None),
            "trade_contract_size": getattr(info, "trade_contract_size", None),
            "trade_tick_size": getattr(info, "trade_tick_size", None),
            "trade_tick_value": getattr(info, "trade_tick_value", None),
            "trade_tick_value_profit": getattr(info, "trade_tick_value_profit", None),
            "trade_tick_value_loss": getattr(info, "trade_tick_value_loss", None),
            "currency_base": getattr(info, "currency_base", None),
            "currency_profit": getattr(info, "currency_profit", None),
            "currency_margin": getattr(info, "currency_margin", None),
            "volume_min": getattr(info, "volume_min", None),
            "volume_step": getattr(info, "volume_step", None),
            "volume_max": getattr(info, "volume_max", None),
            "volume_limit": getattr(info, "volume_limit", None),
        }

        tick_dict = {
            "time": getattr(tick, "time", None),
            "bid": getattr(tick, "bid", None),
            "ask": getattr(tick, "ask", None),
            "last": getattr(tick, "last", None),
            "volume": getattr(tick, "volume", None),
        }

        ref_bid = tick.bid
        ref_ask = tick.ask
        tick_size = info.trade_tick_size or 0.01

        # Test volumes
        test_volumes = [1.0, 0.5, 0.1, 0.05, 0.01]
        calc_results = []

        for vol in test_volumes:
            # BUY favorable (price goes up by 1 tick from ask)
            buy_fav = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, vol, ref_ask, ref_ask + tick_size)
            # BUY adverse (price goes down by 1 tick from ask)
            buy_adv = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, vol, ref_ask, ref_ask - tick_size)
            # SELL favorable (price goes down by 1 tick from bid)
            sell_fav = mt5.order_calc_profit(mt5.ORDER_TYPE_SELL, symbol, vol, ref_bid, ref_bid - tick_size)
            # SELL adverse (price goes up by 1 tick from bid)
            sell_adv = mt5.order_calc_profit(mt5.ORDER_TYPE_SELL, symbol, vol, ref_bid, ref_bid + tick_size)

            calc_results.append({
                "volume": vol,
                "buy_favorable_1tick": buy_fav,
                "buy_adverse_1tick": buy_adv,
                "sell_favorable_1tick": sell_fav,
                "sell_adverse_1tick": sell_adv,
                "expected_linear_formula_profit": round(tick_size * info.trade_contract_size * vol, 4),
            })

        # Test multi-tick linearity (1.0 lot, BUY, moves of 1, 2, 5, 10, 50, 100 ticks)
        multi_tick_results = []
        for n_ticks in [1, 2, 5, 10, 50, 100]:
            p_open = ref_ask
            p_close = ref_ask + n_ticks * tick_size
            profit = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, 1.0, p_open, p_close)
            expected = round(n_ticks * tick_size * info.trade_contract_size * 1.0, 4)
            multi_tick_results.append({
                "ticks": n_ticks,
                "price_diff": round(n_ticks * tick_size, 4),
                "calculated_profit": profit,
                "expected_profit": expected,
            })

        output_data = {
            "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "account_info": acc_dict,
            "terminal_info": term_dict,
            "symbol_info": info_dict,
            "tick_info": tick_dict,
            "tick_size": tick_size,
            "one_tick_calculations": calc_results,
            "multi_tick_calculations": multi_tick_results,
        }

        report_path = Path("reports/mt5_live_tick_reconciliation_inquiry.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(output_data, indent=2), encoding="utf-8")

        print("=" * 70)
        print("  LIVE MT5 TICK VALUE RECONCILIATION INQUIRY")
        print("=" * 70)
        print(f"Connected Account Server: {acc_dict['server']}")
        print(f"Account Currency: {acc_dict['currency']}")
        print(f"Symbol: {symbol} (Digits: {info_dict['digits']}, Point: {info_dict['point']})")
        print(f"Base Currency: {info_dict['currency_base']}, Profit Currency: {info_dict['currency_profit']}")
        print(f"Trade Calc Mode: {info_dict['trade_calc_mode']}")
        print(f"Trade Contract Size: {info_dict['trade_contract_size']}")
        print(f"Trade Tick Size: {info_dict['trade_tick_size']}")
        print(f"Reported Trade Tick Value: {info_dict['trade_tick_value']}")
        print(f"Reported Trade Tick Value Profit: {info_dict['trade_tick_value_profit']}")
        print(f"Reported Trade Tick Value Loss: {info_dict['trade_tick_value_loss']}")
        print(f"Reference Prices: Bid={ref_bid}, Ask={ref_ask}")
        print("\n--- One-Tick P&L Inquiries (order_calc_profit) ---")
        for res in calc_results:
            print(f"Volume: {res['volume']:<5} | BUY Fav: {res['buy_favorable_1tick']:<6} | BUY Adv: {res['buy_adverse_1tick']:<6} | "
                  f"SELL Fav: {res['sell_favorable_1tick']:<6} | SELL Adv: {res['sell_adverse_1tick']:<6} | "
                  f"Linear Formula Expected: {res['expected_linear_formula_profit']}")

        print("\n--- Multi-Tick Linearity Inquiries (1.0 Lot BUY) ---")
        for res in multi_tick_results:
            print(f"Ticks: {res['ticks']:<4} | Price Diff: {res['price_diff']:<6} | "
                  f"order_calc_profit: {res['calculated_profit']:<8} | Linear Formula Expected: {res['expected_profit']}")

        print(f"\nReport saved to: {report_path.resolve()}")
        print("=" * 70)

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
