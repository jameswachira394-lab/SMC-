# utils/atr.py
# ─────────────────────────────────────────────────────────────────────────────
# Real-time ATR calculator. Updated on each candle CLOSE. No lookahead.
# Uses Wilder's smoothing (same as TradingView default).
# ─────────────────────────────────────────────────────────────────────────────
from collections import deque
from typing import Optional
from core.candle import Candle


class ATRCalculator:
    """
    Wilder-smoothed ATR. Processes one candle at a time in sequence.
    Never touches future candles.
    """

    def __init__(self, period: int = 14):
        self.period = period
        self._true_ranges: deque = deque(maxlen=period)
        self._atr: Optional[float] = None
        self._prev_close: Optional[float] = None
        self._bars_seen: int = 0

    def update(self, candle: Candle) -> Optional[float]:
        """
        Feed the CLOSED candle and return the current ATR (or None if warming up).
        Called AFTER candle closes — no future data involved.
        """
        if self._prev_close is None:
            # First candle: TR = range only
            tr = candle.high - candle.low
        else:
            tr = max(
                candle.high - candle.low,
                abs(candle.high - self._prev_close),
                abs(candle.low - self._prev_close),
            )

        self._prev_close = candle.close
        self._true_ranges.append(tr)
        self._bars_seen += 1

        if self._bars_seen < self.period:
            return None  # Still warming up

        if self._atr is None:
            # Initial ATR: simple average of first `period` TRs
            self._atr = sum(self._true_ranges) / self.period
        else:
            # Wilder smoothing
            self._atr = (self._atr * (self.period - 1) + tr) / self.period

        return self._atr

    @property
    def value(self) -> Optional[float]:
        return self._atr

    @property
    def is_ready(self) -> bool:
        return self._atr is not None

    def reset(self):
        self._true_ranges.clear()
        self._atr = None
        self._prev_close = None
        self._bars_seen = 0
