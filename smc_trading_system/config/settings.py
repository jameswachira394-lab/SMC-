# config/settings.py
# ─────────────────────────────────────────────────────────────────────────────
# All system-wide parameters. Tune these without touching engine logic.
# ─────────────────────────────────────────────────────────────────────────────

# ── ATR ──────────────────────────────────────────────────────────────────────
ATR_PERIOD = 14                   # Lookback for ATR calculation
ATR_DISPLACEMENT_MULT = 1.0       # Minimum ATR multiple for BOS/CHoCH displacement
ATR_SWING_THRESHOLD_MULT = 0.5    # ATR fraction to confirm a new swing
ATR_LIQUIDITY_TOLERANCE_MULT = 0.1  # ATR fraction for equal high/low detection

# ── Structure Engine ─────────────────────────────────────────────────────────
BODY_DOMINANCE_RATIO = 0.5        # Min body/range ratio to qualify as impulse candle
MIN_SWING_BREAK_MULT = 0.25       # ATR multiple price must close beyond to confirm swing

# ── Order Blocks ─────────────────────────────────────────────────────────────
MAX_ACTIVE_OBS = 10               # Max OB zones stored per direction
OB_MIN_BODY_RATIO = 0.4           # Min body/range for OB candle

# ── FVG ──────────────────────────────────────────────────────────────────────
MIN_FVG_SIZE_MULT = 0.1           # Min ATR multiple for FVG to be stored
MAX_ACTIVE_FVGS = 20

# ── Session Filter ────────────────────────────────────────────────────────────
# Times in UTC
LONDON_OPEN_HOUR = 7
LONDON_CLOSE_HOUR = 16
NY_OPEN_HOUR = 12
NY_CLOSE_HOUR = 21
SESSION_FILTER_ENABLED = True

# ── Entry ─────────────────────────────────────────────────────────────────────
REQUIRE_SWEEP_BEFORE_ENTRY = True
REQUIRE_REJECTION_CANDLE = True   # Confirmation candle after return to OB/FVG
HTF_BIAS_ENABLED = False          # Set True to require HTF trend alignment

# ── Risk Management ───────────────────────────────────────────────────────────
RISK_PER_TRADE_PCT = 1.0          # % of account risked per trade
MAX_DAILY_LOSS_PCT = 3.0          # Daily loss limit as % of account
MAX_CONSECUTIVE_LOSSES = 4        # Stop trading after N consecutive losses
MIN_RR_RATIO = 2.0                # Minimum required reward:risk
ACCOUNT_SIZE = 10_000             # Starting account size (USD)

# ── Backtest ──────────────────────────────────────────────────────────────────
PARTIAL_TP_ENABLED = True
PARTIAL_TP_AT_R = 1.0             # Take partial profit at 1R
PARTIAL_TP_PCT = 0.5              # Close 50% of position at partial TP

# ── Consolidation Filter ──────────────────────────────────────────────────────
CONSOLIDATION_ATR_MULT = 0.5      # If range < this × ATR over N bars → no trade
CONSOLIDATION_LOOKBACK = 10

# ── MT5 Live Trading ──────────────────────────────────────────────────────────
# Configure these to enable live trading mode
MT5_LOGIN = None                  # Your MT5 account login (e.g., 123456789)
MT5_PASSWORD = None               # Your MT5 account password
MT5_SERVER = "ICMarketsSC-Demo"   # Demo: "ICMarketsSC-Demo" | Live: "ICMarkets-Live"
MT5_SYMBOL = "EURUSD"             # Trading pair
MT5_TIMEFRAME = 60                # Timeframe in minutes (60 = 1H, 240 = 4H, etc)
MT5_MAGIC_NUMBER = 123456         # Unique identifier for orders placed by this system
MT5_LOT_SIZE = 0.1                # Fixed lot size for live trading
MT5_CHECK_INTERVAL = 60           # Seconds between candle checks
