# backtest/simulator.py
# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST ENGINE — CANDLE-BY-CANDLE SIMULATION
# ─────────────────────────────────────────────────────────────────────────────
# Design rules:
#   • Process candles in strict chronological order
#   • Each engine receives ONLY the current candle (and prior confirmed state)
#   • No lookahead: engines never see future candles
#   • Trade log is built from confirmed exit events only
# ─────────────────────────────────────────────────────────────────────────────
from typing import List, Optional
from datetime import datetime

from core.candle import Candle
from core.state import MarketState, StructureState, TradeSignal
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


class TradeRecord:
    """Immutable trade record written after exit."""
    def __init__(
        self,
        signal: TradeSignal,
        exit_result: ExitResult,
        session: str,
    ):
        self.direction      = signal.direction
        self.entry_price    = signal.entry_price
        self.stop_loss      = signal.stop_loss
        self.take_profit    = signal.take_profit
        self.position_size  = signal.position_size
        self.entry_time     = signal.timestamp
        self.exit_time      = exit_result.timestamp
        self.exit_price     = exit_result.exit_price
        self.exit_type      = exit_result.exit_type
        self.pnl_r          = exit_result.pnl_r
        self.rr_ratio       = signal.rr_ratio
        self.reason         = signal.reason
        self.session        = session

    def to_dict(self) -> dict:
        return {
            "direction":     self.direction,
            "entry_price":   self.entry_price,
            "stop_loss":     self.stop_loss,
            "take_profit":   self.take_profit,
            "position_size": self.position_size,
            "entry_time":    str(self.entry_time),
            "exit_time":     str(self.exit_time),
            "exit_price":    self.exit_price,
            "exit_type":     self.exit_type,
            "pnl_r":         round(self.pnl_r, 4),
            "rr_ratio":      round(self.rr_ratio, 2),
            "reason":        self.reason,
            "session":       self.session,
        }


class Simulator:
    """
    Orchestrates all engines in strict candle-by-candle order.
    No engine is ever given a future candle.
    """

    def __init__(self):
        self.state = MarketState(account_balance=ACCOUNT_SIZE)

        # Engines
        self.atr_calc       = ATRCalculator(period=ATR_PERIOD)
        self.structure_eng  = StructureEngine()
        self.bos_choch_eng  = BOSCHoCHEngine()
        self.liquidity_eng  = LiquidityEngine()
        self.ob_eng         = OrderBlockEngine()
        self.fvg_eng        = FVGEngine()
        self.entry_eng      = EntryEngine()
        self.exit_eng       = ExitEngine()
        self.risk_mgr       = RiskManager()

        # Output
        self.trade_log: List[TradeRecord] = []
        self.equity_curve: List[dict] = []
        self._open_signal: Optional[TradeSignal] = None
        self._bars_processed: int = 0

    def run(self, candles: List[Candle]) -> List[TradeRecord]:
        """
        Main backtest loop. Process each candle exactly once, in order.
        Returns list of completed TradeRecords.
        """
        print(f"[Simulator] Starting backtest: {len(candles)} candles")
        print(f"[Simulator] Account: ${self.state.account_balance:,.2f} | "
              f"Risk/trade: {__import__('config.settings', fromlist=['RISK_PER_TRADE_PCT']).RISK_PER_TRADE_PCT}%")

        for i, candle in enumerate(candles):
            self._process_candle(candle)
            self._bars_processed += 1

            if i % 500 == 0 and i > 0:
                print(f"  [{i}/{len(candles)}] Balance: ${self.state.account_balance:,.2f} | "
                      f"Trades: {len(self.trade_log)}")

        print(f"[Simulator] Done. {len(self.trade_log)} trades completed.")
        return self.trade_log

    def _process_candle(self, candle: Candle):
        """Process a single closed candle through all engines in sequence."""

        # ── 1. Update ATR (must be first — all engines depend on it) ──────────
        atr = self.atr_calc.update(candle)
        if atr:
            self.state.current_atr = atr
        if not self.atr_calc.is_ready:
            return   # Warming up

        # ── 2. Exit check (before entry — protects against same-bar entry/exit)
        if self.state.open_trade:
            exit_result = self.exit_eng.update(candle, self.state)
            if exit_result:
                self._record_exit(exit_result, candle)

        # ── 3. Structure Engine ───────────────────────────────────────────────
        self.structure_eng.update(candle, self.state)

        # ── 4. BOS / CHoCH Engine ─────────────────────────────────────────────
        new_events = self.bos_choch_eng.update(candle, self.state)

        # ── 5. Liquidity Engine ───────────────────────────────────────────────
        sweep_events = self.liquidity_eng.update(candle, self.state)
        new_events.extend(sweep_events)

        # ── 6. Order Block Engine ─────────────────────────────────────────────
        self.ob_eng.update(candle, self.state, new_events)

        # ── 7. FVG Engine ─────────────────────────────────────────────────────
        self.fvg_eng.update(candle, self.state)

        # ── 8. Entry Engine ───────────────────────────────────────────────────
        if not self.state.open_trade:
            allowed, reason = self.risk_mgr.can_trade(self.state, candle.timestamp)
            if allowed:
                signal = self.entry_eng.update(candle, self.state)
                if signal:
                    # Size the position
                    signal.position_size = self.risk_mgr.size_position(signal, self.state)
                    self.state.open_trade = signal
                    self._open_signal = signal

        # ── 9. Record equity ──────────────────────────────────────────────────
        self.equity_curve.append({
            "timestamp": str(candle.timestamp),
            "balance": round(self.state.account_balance, 2),
            "structure": self.state.structure.name,
            "in_trade": self.state.open_trade is not None,
        })

    def _record_exit(self, result: ExitResult, candle: Candle):
        """Write completed trade to log and update risk manager."""
        if self._open_signal is None:
            return

        if result.partial:
            # Don't close trade record yet — just log partial
            self.risk_mgr.process_exit(result, self._open_signal, self.state)
            return

        from utils.session import session_name
        record = TradeRecord(
            signal=self._open_signal,
            exit_result=result,
            session=session_name(candle.timestamp),
        )
        self.trade_log.append(record)
        self.risk_mgr.process_exit(result, self._open_signal, self.state)
        self._open_signal = None

    def reset(self):
        """Full reset for re-running with different parameters."""
        self.state = MarketState(account_balance=ACCOUNT_SIZE)
        self.atr_calc.reset()
        self.structure_eng.reset()
        self.bos_choch_eng.reset()
        self.liquidity_eng.reset()
        self.ob_eng.reset()
        self.fvg_eng.reset()
        self.entry_eng.reset()
        self.exit_eng.reset()
        self.risk_mgr.reset()
        self.trade_log.clear()
        self.equity_curve.clear()
        self._open_signal = None
        self._bars_processed = 0
