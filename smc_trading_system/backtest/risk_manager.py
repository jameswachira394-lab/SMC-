# backtest/risk_manager.py
# ─────────────────────────────────────────────────────────────────────────────
# MODULE 8: RISK MANAGEMENT MODULE
# ─────────────────────────────────────────────────────────────────────────────
# Hard constraints:
#   • Fixed % risk per trade
#   • Max daily loss limit (% of account)
#   • Max consecutive losses → halt trading
#   • Minimum RR requirement enforced in entry engine
#   • Position sizing: risk_amount / (entry - stop_loss)
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime, date
from typing import Optional

from core.state import MarketState, TradeSignal
from engines.exit_engine import ExitResult
from config.settings import (
    RISK_PER_TRADE_PCT,
    MAX_DAILY_LOSS_PCT,
    MAX_CONSECUTIVE_LOSSES,
    ACCOUNT_SIZE,
)


class RiskManager:

    def __init__(self):
        self._daily_start_balance: float = ACCOUNT_SIZE
        self._current_day: Optional[date] = None
        self._daily_pnl: float = 0.0
        self._halted: bool = False
        self._halt_reason: str = ""

    def can_trade(self, state: MarketState, timestamp: datetime) -> tuple:
        """
        Returns (allowed: bool, reason: str).
        Checks all hard risk constraints before allowing a trade.
        """
        # ── Day rollover ──────────────────────────────────────────────────────
        today = timestamp.date()
        if self._current_day != today:
            self._daily_start_balance = state.account_balance
            self._daily_pnl = 0.0
            self._current_day = today
            self._halted = False   # Reset daily halt
            self._halt_reason = ""

        if self._halted:
            return False, self._halt_reason

        # ── Max consecutive losses ────────────────────────────────────────────
        if state.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            self._halted = True
            self._halt_reason = f"Max consecutive losses ({MAX_CONSECUTIVE_LOSSES}) reached"
            return False, self._halt_reason

        # ── Max daily loss ────────────────────────────────────────────────────
        daily_loss_pct = (
            (self._daily_start_balance - state.account_balance)
            / self._daily_start_balance * 100
            if self._daily_start_balance > 0 else 0
        )
        if daily_loss_pct >= MAX_DAILY_LOSS_PCT:
            self._halted = True
            self._halt_reason = (
                f"Daily loss limit ({MAX_DAILY_LOSS_PCT}%) reached. "
                f"Lost {daily_loss_pct:.2f}%"
            )
            return False, self._halt_reason

        return True, "ok"

    def size_position(self, signal: TradeSignal, state: MarketState) -> float:
        """
        Calculate position size (units) based on fixed % risk.
        position_size = risk_amount / |entry - stop_loss|
        """
        risk_amount = state.account_balance * (RISK_PER_TRADE_PCT / 100)
        price_risk = abs(signal.entry_price - signal.stop_loss)
        if price_risk <= 0:
            return 0.0
        return risk_amount / price_risk

    def process_exit(self, result: ExitResult, signal: TradeSignal, state: MarketState):
        """
        Update account balance and risk counters after a trade closes.
        pnl_r is in R-multiples; convert to currency using position_size * price_risk.
        """
        price_risk = abs(signal.entry_price - signal.stop_loss)
        pnl_currency = result.pnl_r * price_risk * signal.position_size

        state.account_balance += pnl_currency
        state.daily_loss_pct = (
            (self._daily_start_balance - state.account_balance)
            / self._daily_start_balance * 100
        )
        self._daily_pnl += pnl_currency

        if result.exit_type == "SL_HIT":
            state.consecutive_losses += 1
        elif result.exit_type == "TP_HIT":
            state.consecutive_losses = 0  # Reset on win

    def reset(self):
        self._daily_start_balance = ACCOUNT_SIZE
        self._current_day = None
        self._daily_pnl = 0.0
        self._halted = False
        self._halt_reason = ""
