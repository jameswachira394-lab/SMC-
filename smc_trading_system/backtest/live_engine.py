# backtest/live_engine.py
# ─────────────────────────────────────────────────────────────────────────────
# LIVE TRADING ENGINE
# ─────────────────────────────────────────────────────────────────────────────
# Extends the simulator logic to execute trades in real-time on MT5
# Processes candles as they close and places/manages orders accordingly
# ─────────────────────────────────────────────────────────────────────────────

import time
from typing import List, Optional
from datetime import datetime, timedelta

from core.candle import Candle
from core.state import MarketState, TradeSignal
from utils.atr import ATRCalculator
from engines.structure_engine import StructureEngine
from engines.bos_choch_engine import BOSCHoCHEngine
from engines.liquidity_engine import LiquidityEngine
from engines.orderblock_engine import OrderBlockEngine
from engines.fvg_engine import FVGEngine
from engines.entry_engine import EntryEngine
from engines.exit_engine import ExitEngine, ExitResult
from backtest.risk_manager import RiskManager
from config.settings import ACCOUNT_SIZE, ATR_PERIOD

from integrations.mt5_connector import MT5Connector
from integrations.mt5_trader import MT5Trader, OrderResult


class LiveTradeRecord:
    """Record of a live trade executed on MT5."""

    def __init__(self, signal: TradeSignal, order_result: OrderResult):
        self.signal = signal
        self.order_result = order_result
        self.entry_time = datetime.now()
        self.status = "OPEN"


class LiveTradingEngine:
    """
    Real-time SMC trading system that executes on MT5.
    Monitors candles and places orders based on SMC signals.
    """

    def __init__(
        self,
        connector: MT5Connector,
        symbol: str,
        timeframe: int,
        lot_size: float = 0.1,
        magic_number: int = 123456,
    ):
        """
        Initialize live trading engine.

        Args:
            connector: Connected MT5Connector instance
            symbol: Trading pair (e.g., "EURUSD")
            timeframe: Timeframe in minutes (60 = 1H, 240 = 4H, etc)
            lot_size: Fixed position size in lots
            magic_number: Unique order identifier
        """
        self.connector = connector
        self.trader = MT5Trader(connector, symbol, magic_number)
        self.symbol = symbol
        self.timeframe = timeframe
        self.lot_size = lot_size

        # State management
        self.state = MarketState(account_balance=ACCOUNT_SIZE)
        self.last_candle_time: Optional[datetime] = None
        self.trade_records: List[LiveTradeRecord] = []

        # Engines (same as backtester)
        self.atr_calc = ATRCalculator(period=ATR_PERIOD)
        self.structure_eng = StructureEngine()
        self.bos_choch_eng = BOSCHoCHEngine()
        self.liquidity_eng = LiquidityEngine()
        self.ob_eng = OrderBlockEngine()
        self.fvg_eng = FVGEngine()
        self.entry_eng = EntryEngine()
        self.exit_eng = ExitEngine()
        self.risk_mgr = RiskManager()

        self._open_signal: Optional[TradeSignal] = None
        self._current_position_ticket: Optional[int] = None

    def get_mt5_timeframe(self) -> int:
        """Convert timeframe in minutes to MT5 constant."""
        import MetaTrader5 as mt5

        timeframe_map = {
            1: mt5.TIMEFRAME_M1,
            5: mt5.TIMEFRAME_M5,
            15: mt5.TIMEFRAME_M15,
            30: mt5.TIMEFRAME_M30,
            60: mt5.TIMEFRAME_H1,
            240: mt5.TIMEFRAME_H4,
            1440: mt5.TIMEFRAME_D1,
            10080: mt5.TIMEFRAME_W1,
            43200: mt5.TIMEFRAME_MN1,
        }
        return timeframe_map.get(self.timeframe, mt5.TIMEFRAME_H1)

    def fetch_historical_candles(self, num_candles: int = 500) -> List[Candle]:
        """
        Fetch historical candles to warm up indicators.

        Args:
            num_candles: Number of candles to fetch

        Returns:
            List of Candle objects
        """
        print(f"[Live Engine] Fetching {num_candles} historical candles...")
        mt5_tf = self.get_mt5_timeframe()
        candles = self.connector.get_candles(self.symbol, mt5_tf, num_candles)

        if candles:
            self.last_candle_time = candles[-1].timestamp
            print(f"[Live Engine] Loaded {len(candles)} candles (last: {self.last_candle_time})")
        else:
            print("[Live Engine] Failed to load historical candles")

        return candles

    def warm_up_indicators(self, candles: List[Candle]):
        """
        Process historical candles through all engines to prepare state.

        Args:
            candles: List of historical Candle objects
        """
        print("[Live Engine] Warming up indicators...")

        for candle in candles:
            # Update ATR
            atr = self.atr_calc.update(candle)
            if atr:
                self.state.current_atr = atr

            # Skip if warming up
            if not self.atr_calc.is_ready:
                continue

            # Run through all engines (without entry/exit)
            self.structure_eng.update(candle, self.state)
            new_events = self.bos_choch_eng.update(candle, self.state)
            sweep_events = self.liquidity_eng.update(candle, self.state)
            new_events.extend(sweep_events)
            self.ob_eng.update(candle, self.state, new_events)
            self.fvg_eng.update(candle, self.state)

        print("[Live Engine] Warm-up complete. Ready for live trading.")

    def process_candle(self, candle: Candle) -> bool:
        """
        Process a single candle and execute trading logic.

        Args:
            candle: New closed candle

        Returns:
            True if signal was processed, False otherwise
        """
        # Skip if same candle time
        if self.last_candle_time and candle.timestamp <= self.last_candle_time:
            return False

        self.last_candle_time = candle.timestamp
        print(f"\n[Live Engine] Processing candle: {candle.timestamp}")

        # Update ATR
        atr = self.atr_calc.update(candle)
        if atr:
            self.state.current_atr = atr

        if not self.atr_calc.is_ready:
            print("[Live Engine] ATR still warming up...")
            return False

        # Check for exits first
        if self.state.open_trade and self._current_position_ticket:
            exit_result = self.exit_eng.update(candle, self.state)
            if exit_result:
                self._process_exit(exit_result, candle)
                return False

        # Run through all engines
        self.structure_eng.update(candle, self.state)
        new_events = self.bos_choch_eng.update(candle, self.state)
        sweep_events = self.liquidity_eng.update(candle, self.state)
        new_events.extend(sweep_events)
        self.ob_eng.update(candle, self.state, new_events)
        self.fvg_eng.update(candle, self.state)

        # Check for entries
        if not self.state.open_trade:
            allowed, reason = self.risk_mgr.can_trade(self.state, candle.timestamp)
            if allowed:
                signal = self.entry_eng.update(candle, self.state)
                if signal:
                    # Size position
                    signal.position_size = self.risk_mgr.size_position(signal, self.state)
                    self._process_entry(signal, candle)
                    return True

        return False

    def _process_entry(self, signal: TradeSignal, candle: Candle):
        """
        Place entry order on MT5.

        Args:
            signal: TradeSignal from entry engine
            candle: Current candle
        """
        print(f"[Live Engine] Entry signal: {signal.direction} | "
              f"Price: {signal.entry_price} | SL: {signal.stop_loss} | TP: {signal.take_profit}")

        # Place order on MT5
        if signal.direction == "BUY":
            result = self.trader.place_buy_order(signal, self.lot_size)
        else:
            result = self.trader.place_sell_order(signal, self.lot_size)

        if result.success:
            self.state.open_trade = signal
            self._open_signal = signal
            self._current_position_ticket = result.order_id

            record = LiveTradeRecord(signal, result)
            self.trade_records.append(record)

            print(f"[Live Engine] ✓ Order placed successfully: {result.order_id}")
        else:
            print(f"[Live Engine] ✗ Order failed: {result.error}")

    def _process_exit(self, exit_result: ExitResult, candle: Candle):
        """
        Close position on MT5.

        Args:
            exit_result: ExitResult from exit engine
            candle: Current candle
        """
        if not self._current_position_ticket:
            return

        print(f"[Live Engine] Exit signal: {exit_result.exit_type} | "
              f"Price: {exit_result.exit_price} | P&L: {exit_result.pnl_r}R")

        result = self.trader.close_position(self._current_position_ticket)

        if result.success:
            print(f"[Live Engine] ✓ Position closed successfully")
            self.state.open_trade = None
            self._open_signal = None
            self._current_position_ticket = None
            self.risk_mgr.process_exit(exit_result, self._open_signal, self.state)
        else:
            print(f"[Live Engine] ✗ Close failed: {result.error}")

    def get_active_positions(self):
        """Get all active positions from MT5."""
        return self.trader.get_positions()

    def get_account_info(self):
        """Get current account info from MT5."""
        return self.connector.get_account_info()

    def run(self, check_interval: int = 60, max_duration_hours: int = 24):
        """
        Main live trading loop.

        Args:
            check_interval: Seconds between candle checks
            max_duration_hours: Maximum runtime (safety limit)
        """
        print(f"[Live Engine] Starting live trading loop ({max_duration_hours}h max)")
        print(f"[Live Engine] Symbol: {self.symbol} | Timeframe: {self.timeframe}m | Interval: {check_interval}s")

        # Load and warm up
        if not self.connector.check_connection():
            print("[Live Engine] Cannot connect to MT5")
            return

        if not self.connector.select_symbol(self.symbol):
            print("[Live Engine] Failed to select symbol")
            return

        candles = self.fetch_historical_candles(num_candles=200)
        if not candles:
            print("[Live Engine] Cannot warm up without historical data")
            return

        self.warm_up_indicators(candles)

        # Main loop
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=max_duration_hours)
        loop_count = 0

        try:
            while datetime.now() < end_time:
                # Verify connection
                if not self.connector.check_connection():
                    print("[Live Engine] Connection lost, reconnecting...")
                    time.sleep(5)
                    continue

                # Fetch latest candle
                latest = self.connector.get_latest_candle(
                    self.symbol, self.get_mt5_timeframe()
                )

                if latest:
                    self.process_candle(latest)

                # Update account info periodically
                if loop_count % 10 == 0:
                    info = self.get_account_info()
                    if info:
                        print(f"[Live Engine] Account Balance: ${info['balance']:,.2f} | "
                              f"Equity: ${info['equity']:,.2f} | "
                              f"Margin: {info['margin_level']:.1f}%")

                    positions = self.get_active_positions()
                    if positions:
                        for pos in positions:
                            print(f"  Open {pos.direction}: Volume {pos.volume} @ {pos.open_price} "
                                  f"| Profit: ${pos.profit:,.2f}")

                loop_count += 1
                time.sleep(check_interval)

        except KeyboardInterrupt:
            print("\n[Live Engine] Stopping...")
        except Exception as e:
            print(f"[Live Engine] Error: {e}")
        finally:
            self.connector.disconnect()
            print("[Live Engine] Disconnected")

    def report(self):
        """Print trading summary."""
        print("\n" + "=" * 80)
        print("LIVE TRADING SESSION SUMMARY")
        print("=" * 80)

        account_info = self.get_account_info()
        if account_info:
            print(f"Final Balance: ${account_info['balance']:,.2f}")
            print(f"Final Equity: ${account_info['equity']:,.2f}")
            print(f"Total Profit/Loss: ${account_info['profit']:,.2f}")

        print(f"Total Trades: {len(self.trade_records)}")
        for i, record in enumerate(self.trade_records, 1):
            print(f"  Trade {i}: {record.signal.direction} | "
                  f"Entry: {record.signal.entry_price} | Status: {record.status}")
