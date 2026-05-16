# integrations/mt5_connector.py
# ─────────────────────────────────────────────────────────────────────────────
# MT5 CONNECTION & DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────
# Handles MetaTrader5 initialization, account info, and real-time data retrieval
# ─────────────────────────────────────────────────────────────────────────────

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import time
import os

from core.candle import Candle


class MT5Connector:
    """
    Manages MT5 connection lifecycle and data fetching.
    Ensures account info is current and handles connection errors gracefully.
    """

    def __init__(self, login: int, password: str, server: str):
        """
        Initialize MT5 connector (does NOT connect yet).

        Args:
            login: MT5 account login number
            password: MT5 account password
            server: MT5 server name (e.g., "ICMarketsSC-Demo", "ICMarkets-Live")
        """
        self.login = login
        self.password = password
        self.server = server
        self.connected = False
        self.last_connect_time = None

    def connect(self) -> bool:
        """
        Establish connection to MT5.
        Returns True if successful, False otherwise.
        """
        try:
            if not mt5.initialize(login=self.login, password=self.password, server=self.server):
                error = mt5.last_error()
                print(f"[MT5] Initialize failed: {error}")
                return False

            # Verify connection by fetching account info
            account_info = mt5.account_info()
            if account_info is None:
                print("[MT5] Failed to fetch account info")
                mt5.shutdown()
                return False

            self.connected = True
            self.last_connect_time = datetime.now()
            print(f"[MT5] Connected to {self.server}")
            print(f"[MT5] Account: {account_info.login} | Balance: ${account_info.balance:,.2f}")
            return True

        except Exception as e:
            print(f"[MT5] Connection error: {e}")
            return False

    def disconnect(self):
        """Safely disconnect from MT5."""
        try:
            if self.connected:
                mt5.shutdown()
                self.connected = False
                print("[MT5] Disconnected")
        except Exception as e:
            print(f"[MT5] Disconnect error: {e}")

    def get_account_info(self) -> Optional[dict]:
        """
        Fetch current account information.

        Returns:
            Dict with balance, equity, margin, margin free, or None if error
        """
        if not self.connected:
            return None

        try:
            info = mt5.account_info()
            if info is None:
                print("[MT5] Failed to fetch account info")
                return None

            return {
                "login": info.login,
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin,
                "margin_free": info.margin_free,
                "profit": info.profit,
                "margin_level": info.margin_level,
            }
        except Exception as e:
            print(f"[MT5] Error fetching account info: {e}")
            return None

    def get_candles(
        self,
        symbol: str,
        timeframe: int,
        num_candles: int = 500,
        start_time: Optional[datetime] = None,
    ) -> List[Candle]:
        """
        Fetch OHLC candles from MT5.

        Args:
            symbol: Trading pair (e.g., "EURUSD", "XAUUSD")
            timeframe: MT5 timeframe constant (e.g., mt5.TIMEFRAME_H1, mt5.TIMEFRAME_M15)
            num_candles: Number of candles to fetch
            start_time: Optional start time; if None, fetches last N candles

        Returns:
            List of Candle objects, or empty list on error
        """
        if not self.connected:
            print("[MT5] Not connected")
            return []

        try:
            if start_time:
                rates = mt5.copy_rates_from(symbol, timeframe, start_time, num_candles)
            else:
                rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_candles)

            if rates is None or len(rates) == 0:
                print(f"[MT5] No candles retrieved for {symbol} on timeframe {timeframe}")
                return []

            candles = []
            for rate in rates:
                # MT5 rate structure: (time, open, high, low, close, tick_volume, spread, real_volume)
                candle = Candle(
                    timestamp=datetime.fromtimestamp(rate['time']),
                    open=rate['open'],
                    high=rate['high'],
                    low=rate['low'],
                    close=rate['close'],
                    volume=int(rate['real_volume'] if rate['real_volume'] > 0 else rate['tick_volume']),
                )
                candles.append(candle)

            print(f"[MT5] Retrieved {len(candles)} candles for {symbol}")
            return candles

        except Exception as e:
            print(f"[MT5] Error fetching candles: {e}")
            return []

    def get_latest_candle(self, symbol: str, timeframe: int) -> Optional[Candle]:
        """
        Fetch the latest closed candle for a symbol.

        Args:
            symbol: Trading pair
            timeframe: MT5 timeframe constant

        Returns:
            Latest Candle object or None if error
        """
        candles = self.get_candles(symbol, timeframe, num_candles=1)
        if candles:
            return candles[0]
        return None

    def check_connection(self) -> bool:
        """
        Check if connection is still alive; reconnect if needed.

        Returns:
            True if connected, False otherwise
        """
        if not self.connected:
            return False

        try:
            # Simple test by fetching account info
            if mt5.account_info() is None:
                print("[MT5] Connection lost, attempting reconnect...")
                self.disconnect()
                return self.connect()
            return True
        except Exception as e:
            print(f"[MT5] Connection check failed: {e}")
            self.disconnect()
            return self.connect()

    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        """
        Fetch symbol information (spread, tick size, contract size, etc.).

        Args:
            symbol: Trading pair

        Returns:
            Dict with symbol properties or None if error
        """
        if not self.connected:
            return None

        try:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                print(f"[MT5] Symbol {symbol} not found")
                return None

            return {
                "name": symbol_info.name,
                "spread": symbol_info.spread,
                "bid": symbol_info.bid,
                "ask": symbol_info.ask,
                "digits": symbol_info.digits,
                "point": symbol_info.point,
                "trade_tick_size": symbol_info.trade_tick_size,
                "trade_contract_size": symbol_info.trade_contract_size,
            }
        except Exception as e:
            print(f"[MT5] Error fetching symbol info: {e}")
            return None

    def select_symbol(self, symbol: str) -> bool:
        """
        Enable symbol for trading.

        Args:
            symbol: Trading pair

        Returns:
            True if successful
        """
        if not self.connected:
            return False

        try:
            if not mt5.symbol_select(symbol, True):
                print(f"[MT5] Failed to select symbol {symbol}")
                return False
            return True
        except Exception as e:
            print(f"[MT5] Error selecting symbol: {e}")
            return False
