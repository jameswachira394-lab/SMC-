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
        description="SMC Non-Repainting Trading System Backtest"
    )
    parser.add_argument("--data",            help="Path to OHLCV CSV (LTF)")
    parser.add_argument("--htf",             help="Path to HTF OHLCV CSV (optional bias)")
    parser.add_argument("--output",          default="output", help="Output directory")
    parser.add_argument("--generate-sample", action="store_true",
                        help="Generate synthetic sample data and run on it")
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
