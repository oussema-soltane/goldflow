try:
    import MetaTrader5 as mt5
    print("MT5 package is installed.")
    init_res = mt5.initialize()
    if init_res:
        print("MT5 terminal connected successfully!")
        t_info = mt5.terminal_info()
        print("Terminal:", t_info.name if t_info else "None")
        print("Connected to broker:", t_info.connected if t_info else "False")
        # Check XAUUSD rates
        rates = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M15, 0, 10)
        if rates is not None and len(rates) > 0:
            print(f"Successfully copied {len(rates)} M15 rates from MT5 terminal!")
            print(f"Latest rate time: {rates[-1]['time']}")
        mt5.shutdown()
    else:
        print(f"MT5 initialize returned False. Last error: {mt5.last_error()}")
except ImportError:
    print("MetaTrader5 python package not installed.")
except Exception as e:
    print(f"MT5 check error: {e}")

