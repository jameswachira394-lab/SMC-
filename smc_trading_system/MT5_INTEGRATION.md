# MT5 Live Trading Integration

This document covers how to use the SMC Trading System with MetaTrader 5 (MT5) for live trading.

## Installation

### 1. Install MetaTrader5 Python Package

```bash
pip install MetaTrader5
```

### 2. Update Python Dependencies

Add to your `requirements.txt`:
```
MetaTrader5>=5.0.0
pandas>=1.3.0
numpy>=1.20.0
```

Then install:
```bash
pip install -r requirements.txt
```

## Configuration

### Option 1: Configure in Code (Recommended for Testing)

Update `config/settings.py` with your MT5 credentials:

```python
MT5_LOGIN = 123456789          # Your MT5 account number
MT5_PASSWORD = "your_password"  # Your MT5 password
MT5_SERVER = "ICMarketsSC-Demo" # Demo: "ICMarketsSC-Demo" | Live: "ICMarkets-Live"
MT5_SYMBOL = "EURUSD"           # Trading pair
MT5_TIMEFRAME = 60              # 60 = 1 hour, 240 = 4 hours, etc
MT5_LOT_SIZE = 0.1              # Position size in lots
MT5_MAGIC_NUMBER = 123456       # Unique order identifier
MT5_CHECK_INTERVAL = 60         # Seconds between candle checks
```

### Option 2: Use Command Line Arguments (More Secure)

Pass credentials directly to the CLI:

```bash
python main.py --mode live \
    --login 123456789 \
    --password "your_password" \
    --server "ICMarketsSC-Demo" \
    --symbol EURUSD \
    --timeframe 60 \
    --lot-size 0.1 \
    --interval 60 \
    --duration 24
```

## Usage

### Run Backtest (Default)

```bash
# Use sample data
python main.py --generate-sample

# Use CSV data
python main.py --data data/eurusd_1h.csv

# With higher timeframe bias
python main.py --data data/eurusd_15m.csv --htf data/eurusd_1h.csv
```

### Run Live Trading on MT5

**Important: Always test with a demo account first!**

```bash
# Start live trading
python main.py --mode live \
    --login YOUR_LOGIN \
    --password YOUR_PASSWORD \
    --server ICMarketsSC-Demo \
    --symbol EURUSD \
    --timeframe 60

# With custom settings
python main.py --mode live \
    --login YOUR_LOGIN \
    --password YOUR_PASSWORD \
    --server ICMarketsSC-Demo \
    --symbol EURUSD \
    --timeframe 240 \
    --lot-size 0.2 \
    --interval 60 \
    --duration 48
```

## API Reference

### MT5Connector

Manages connection to MetaTrader5.

**Methods:**
- `connect()` - Establish MT5 connection
- `disconnect()` - Close MT5 connection
- `get_account_info()` - Fetch account balance, equity, margin
- `get_candles(symbol, timeframe, num_candles)` - Fetch OHLC data
- `get_latest_candle(symbol, timeframe)` - Get most recent closed candle
- `get_symbol_info(symbol)` - Get spread, bid/ask, digits
- `select_symbol(symbol)` - Enable symbol for trading
- `check_connection()` - Verify connection is still alive

### MT5Trader

Executes trades on MT5.

**Methods:**
- `place_buy_order(signal, volume, comment)` - Place BUY limit order
- `place_sell_order(signal, volume, comment)` - Place SELL limit order
- `close_position(ticket, comment)` - Close open position
- `modify_position(ticket, new_sl, new_tp)` - Adjust stop loss / take profit
- `get_positions()` - List all active positions
- `cancel_order(order_id)` - Cancel pending order

### LiveTradingEngine

Main orchestrator for real-time trading.

**Methods:**
- `run(check_interval, max_duration_hours)` - Start live trading loop
- `process_candle(candle)` - Process single candle
- `warm_up_indicators(candles)` - Initialize indicators with historical data
- `fetch_historical_candles(num_candles)` - Load history from MT5
- `get_active_positions()` - List current trades
- `get_account_info()` - Current account status

## Trading Flow

1. **Initialization**
   - Connect to MT5
   - Select trading symbol
   - Load 200 historical candles
   - Warm up all indicators (ATR, structure, liquidity, etc.)

2. **Main Loop** (Every `check_interval` seconds)
   - Fetch latest closed candle from MT5
   - Run through all SMC engines
   - If entry signal → Place BUY/SELL order on MT5
   - If exit signal + open position → Close position

3. **Position Management**
   - Automatic stop loss and take profit placement
   - Risk-managed position sizing based on account balance
   - Real-time P&L tracking

4. **Safety Features**
   - Automatic reconnection on MT5 connection loss
   - Daily loss limits (configurable in `config/settings.py`)
   - Maximum consecutive losses halt
   - Order magic number for tracking only this system's trades

## Important Notes

⚠️ **Safety Precautions:**
- **Always test with a demo account first** (server: "ICMarketsSC-Demo")
- Start with small lot sizes (0.01 - 0.1 lots)
- Set `MAX_DAILY_LOSS_PCT` in settings to limit daily losses
- Monitor the first few trades closely
- Keep your MT5 password secure (use environment variables in production)

📊 **Performance Considerations:**
- Real-time candle fetching depends on MT5 server latency
- `check_interval` of 60 seconds (1 min) is safe for 1H+ timeframes
- Faster timeframes may require lower intervals (but increases load)
- Each interval check queries MT5, use responsibly

🔧 **Debugging:**
- Check console output for [MT5] and [Live Engine] messages
- `get_account_info()` shows current balance and margin level
- Active positions are logged with entry price, SL, TP
- All orders use magic number for identification in MT5 terminal

## Demo Account Setup

1. Download MetaTrader 5
2. Create demo account on broker (e.g., IC Markets)
3. Note your login number and password
4. Find the demo server name in MT5 (Help → About)
5. Use credentials in configuration

## Troubleshooting

**"Initialize failed" error:**
- Verify login, password, and server name are correct
- Check MT5 is installed and running
- Ensure internet connection is stable

**"Symbol not found" error:**
- Verify symbol name is correct (EURUSD not EUR/USD)
- Symbol may be named differently on your broker
- Check symbol is available for trading on your account

**"Order failed" error:**
- Check account has sufficient margin
- Verify lot size is valid for the symbol
- Check trading hours (not during market close)
- Review daily loss limits if hit

**Candles not updating:**
- Verify MT5 connection is alive
- Check symbol is selected with `select_symbol()`
- Increase `check_interval` if too frequent
- Verify timeframe is correct (60 = 1H, not minutes)

## Example: Full Live Trading Session

```bash
# 1. Configure settings.py with your MT5 demo account

# 2. Run live trading on EURUSD 1H timeframe
python main.py --mode live \
    --login 123456789 \
    --password mypassword \
    --server "ICMarketsSC-Demo" \
    --symbol EURUSD \
    --timeframe 60 \
    --lot-size 0.1

# 3. System will:
#    - Connect to MT5
#    - Load 200 historical candles
#    - Warm up all indicators
#    - Begin monitoring for entry signals
#    - Execute trades based on SMC logic
#    - Update every 60 seconds

# 4. To stop: Press Ctrl+C in terminal
#    - Prints trading session summary
#    - Positions remain open (close manually in MT5)
```

## Environment Variables (Production)

For production deployments, use environment variables to store credentials:

```bash
# Linux/Mac
export MT5_LOGIN=123456789
export MT5_PASSWORD=mypassword
export MT5_SERVER="ICMarketsSC-Demo"

# Windows PowerShell
$env:MT5_LOGIN = "123456789"
$env:MT5_PASSWORD = "mypassword"
$env:MT5_SERVER = "ICMarketsSC-Demo"

# Then modify main.py to read from env:
login = os.getenv("MT5_LOGIN")
password = os.getenv("MT5_PASSWORD")
server = os.getenv("MT5_SERVER")
```

## Next Steps

1. ✅ Install MetaTrader5 package
2. ✅ Set up demo account on a broker
3. ✅ Configure MT5 credentials
4. ✅ Test with `--generate-sample` backtest
5. ✅ Test live mode with demo account
6. ✅ Monitor trades for 1-2 weeks
7. ✅ Move to live account (optional)

---

**Questions?** Check the main README.md or review the engine code in `/engines/`
