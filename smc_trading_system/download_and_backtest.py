# download_and_backtest.py
import sys
from config.settings import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_SYMBOL, MT5_TIMEFRAME
from integrations.mt5_connector import MT5Connector
import pandas as pd
import MetaTrader5 as mt5

print("[Download] Connecting to MT5...")
print(f"  Login: {MT5_LOGIN}")
print(f"  Server: {MT5_SERVER}")
print(f"  Symbol: {MT5_SYMBOL}")

connector = MT5Connector(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER)
if not connector.connect():
    print("[Download] ✗ Failed to connect to MT5")
    sys.exit(1)

print("[Download] ✓ Connected!")

# Get account info
account = connector.get_account_info()
if account:
    print(f"[Download] Account Balance: ${account['balance']:,.2f}")

# Select symbol
if not connector.select_symbol(MT5_SYMBOL):
    print(f"[Download] ✗ Failed to select {MT5_SYMBOL}")
    connector.disconnect()
    sys.exit(1)

# Convert timeframe
timeframe_map = {
    1: mt5.TIMEFRAME_M1,
    5: mt5.TIMEFRAME_M5,
    15: mt5.TIMEFRAME_M15,
    30: mt5.TIMEFRAME_M30,
    60: mt5.TIMEFRAME_H1,
    240: mt5.TIMEFRAME_H4,
    1440: mt5.TIMEFRAME_D1,
}
mt5_tf = timeframe_map.get(MT5_TIMEFRAME, mt5.TIMEFRAME_M5)

# Fetch candles
print(f"[Download] Fetching 500 candles from MT5...")
candles = connector.get_candles(MT5_SYMBOL, mt5_tf, num_candles=500)

if not candles:
    print("[Download] ✗ No candles retrieved")
    connector.disconnect()
    sys.exit(1)

# Convert to CSV
data = []
for candle in candles:
    data.append({
        'timestamp': str(candle.timestamp),
        'open': candle.open,
        'high': candle.high,
        'low': candle.low,
        'close': candle.close,
        'volume': candle.volume,
    })

df = pd.DataFrame(data)
csv_path = f'data/{MT5_SYMBOL}_{MT5_TIMEFRAME}m.csv'
df.to_csv(csv_path, index=False)

print(f"[Download] ✓ Saved {len(candles)} candles to {csv_path}")
print(f"[Download] Time range: {candles[0].timestamp} → {candles[-1].timestamp}")

connector.disconnect()
print("[Download] Disconnected from MT5\n")

# Now run backtest
print("[Backtest] Starting backtest on downloaded data...")
import os
os.system(f'python main.py --data "{csv_path}"')
