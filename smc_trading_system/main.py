# main.py
# ─────────────────────────────────────────────────────────────────────────────
# SMC TRADING SYSTEM — ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
# Usage:
#   python main.py --data data/sample.csv
#   python main.py --data data/eurusd_15m.csv --htf data/eurusd_1h.csv
#   python main.py --generate-sample    # generates a synthetic OHLCV dataset
# ─────────────────────────────────────────────────────────────────────────────
import argparse
import os
import sys

# ── Make sure project root is on path ────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_csv(path: str):
    """Load an OHLCV CSV into a list of Candle objects."""
    try:
        import pandas as pd
    except ImportError:
        print("ERROR: pandas is required. Run: pip install pandas numpy")
        sys.exit(1)

    df = pd.read_csv(path)

    # Normalise column names (case-insensitive)
    df.columns = [c.lower().strip() for c in df.columns]

    # Accept 'date', 'time', 'datetime', or 'timestamp' as the time column
    ts_cols = [c for c in df.columns if c in ("date", "time", "datetime", "timestamp")]
    if not ts_cols:
        print(f"ERROR: CSV must have a timestamp column (date/time/datetime/timestamp). "
              f"Found: {list(df.columns)}")
        sys.exit(1)

    df = df.rename(columns={ts_cols[0]: "timestamp"})

    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        print(f"ERROR: CSV missing columns: {missing}")
        sys.exit(1)

    from core.candle import candles_from_dataframe
    return candles_from_dataframe(df)


def generate_sample_data(n: int = 2000, path: str = "data/sample.csv"):
    """
    Generate a synthetic OHLCV dataset with realistic price action
    for testing purposes only.
    """
    import random
    import math
    from datetime import datetime, timedelta
    import csv
    import os

    os.makedirs(os.path.dirname(path), exist_ok=True)
    random.seed(42)

    price = 1.10000
    ts = datetime(2023, 1, 2, 7, 0, 0)  # Start at London open

    rows = []
    trend = 1  # 1 = up, -1 = down
    trend_bars = 0

    for i in range(n):
        # Occasional trend reversals
        if trend_bars > random.randint(20, 60):
            trend *= -1
            trend_bars = 0

        # Build candle
        atr_sim = price * 0.0008
        body    = random.uniform(0.0001, atr_sim * 1.2) * trend
        wick_up = random.uniform(0, atr_sim * 0.8)
        wick_dn = random.uniform(0, atr_sim * 0.8)

        open_  = price
        close_ = price + body
        high_  = max(open_, close_) + wick_up
        low_   = min(open_, close_) - wick_dn
        vol    = random.randint(100, 5000)

        rows.append({
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "open":      round(open_, 5),
            "high":      round(high_, 5),
            "low":       round(low_, 5),
            "close":     round(close_, 5),
            "volume":    vol,
        })

        price = close_
        ts += timedelta(minutes=15)
        trend_bars += 1

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"[Sample] Generated {n} candles → {path}")
    return path


def main():
    parser = argparse.ArgumentParser(
        description="SMC Non-Repainting Trading System (Backtest & Live)"
    )
    
    # Mode selection
    parser.add_argument("--mode", choices=["backtest", "live"], default="backtest",
                        help="Run mode: backtest or live trading")
    
    # Backtest arguments
    parser.add_argument("--data",            help="Path to OHLCV CSV (LTF)")
    parser.add_argument("--htf",             help="Path to HTF OHLCV CSV (optional bias)")
    parser.add_argument("--output",          default="output", help="Output directory")
    parser.add_argument("--generate-sample", action="store_true",
                        help="Generate synthetic sample data and run on it")
    
    # Live trading arguments
    parser.add_argument("--login",           type=int, help="MT5 account login")
    parser.add_argument("--password",        help="MT5 account password")
    parser.add_argument("--server",          help="MT5 server name")
    parser.add_argument("--symbol",          help="Trading pair (e.g., EURUSD)")
    parser.add_argument("--timeframe",       type=int, default=60,
                        help="Timeframe in minutes (60=1H, 240=4H, etc)")
    parser.add_argument("--lot-size",        type=float, default=0.1,
                        help="Position size in lots")
    parser.add_argument("--interval",        type=int, default=60,
                        help="Seconds between candle checks")
    parser.add_argument("--duration",        type=int, default=24,
                        help="Maximum trading duration in hours")
    
    args = parser.parse_args()

    # ── BACKTEST MODE ──────────────────────────────────────────────────────
    if args.mode == "backtest":
        run_backtest(args)

    # ── LIVE TRADING MODE ──────────────────────────────────────────────────
    elif args.mode == "live":
        run_live_trading(args)


def run_backtest(args):
    """Execute backtest mode."""
    # ── Generate sample if requested ─────────────────────────────────────────
    if args.generate_sample or not args.data:
        sample_path = generate_sample_data(n=3000)
        args.data = sample_path

    # ── Load candles ──────────────────────────────────────────────────────────
    print(f"[Main] Loading data: {args.data}")
    candles = load_csv(args.data)
    print(f"[Main] Loaded {len(candles)} candles "
          f"({candles[0].timestamp} → {candles[-1].timestamp})")

    # ── Optional HTF bias ─────────────────────────────────────────────────────
    htf_candles = None
    if args.htf:
        print(f"[Main] Loading HTF data: {args.htf}")
        htf_candles = load_csv(args.htf)
        print(f"[Main] HTF: {len(htf_candles)} candles")

    # ── Run backtest ──────────────────────────────────────────────────────────
    from backtest.simulator import Simulator
    from backtest.reporter import BacktestReporter

    sim = Simulator()
    trades = sim.run(candles)

    # ── Report ────────────────────────────────────────────────────────────────
    reporter = BacktestReporter(output_dir=args.output)
    reporter.generate(trades, sim.equity_curve)


def run_live_trading(args):
    """Execute live trading mode."""
    from integrations.mt5_connector import MT5Connector
    from backtest.live_engine import LiveTradingEngine
    from config.settings import (
        MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_SYMBOL, 
        MT5_TIMEFRAME, MT5_MAGIC_NUMBER, MT5_LOT_SIZE, MT5_CHECK_INTERVAL
    )
    
    # Use CLI args if provided, otherwise use config
    login = args.login or MT5_LOGIN
    password = args.password or MT5_PASSWORD
    server = args.server or MT5_SERVER
    symbol = args.symbol or MT5_SYMBOL
    timeframe = args.timeframe or MT5_TIMEFRAME
    lot_size = args.lot_size or MT5_LOT_SIZE
    magic = 123456  # Can be made configurable
    interval = args.interval or MT5_CHECK_INTERVAL
    duration = args.duration or 24
    
    # Validate MT5 credentials
    if not login or not password or not server:
        print("[Main] ERROR: MT5 credentials required")
        print("  Usage: python main.py --mode live --login YOUR_LOGIN --password YOUR_PASS --server YOUR_SERVER")
        print("  Or set MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in config/settings.py")
        sys.exit(1)
    
    print(f"[Main] Starting live trading mode")
    print(f"[Main] Symbol: {symbol} | Timeframe: {timeframe}m")
    
    # Connect to MT5
    connector = MT5Connector(login, password, server)
    if not connector.connect():
        print("[Main] Failed to connect to MT5")
        sys.exit(1)
    
    # Create and run live engine
    engine = LiveTradingEngine(
        connector,
        symbol=symbol,
        timeframe=timeframe,
        lot_size=lot_size,
        magic_number=magic,
    )
    
    try:
        engine.run(check_interval=interval, max_duration_hours=duration)
        engine.report()
    except Exception as e:
        print(f"[Main] Live trading error: {e}")
        connector.disconnect()
        sys.exit(1)


if __name__ == "__main__":
    main()
