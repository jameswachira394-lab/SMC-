# engines/structure_engine.py
# ─────────────────────────────────────────────────────────────────────────────
# MODULE 1: REAL-TIME STRUCTURE ENGINE
# ─────────────────────────────────────────────────────────────────────────────
# Design rules:
#   - NO pivot/fractal windows (those look N bars ahead)
#   - Swing high/low confirmed only when:
#       1. Price closes BEYOND the previous extreme
#       2. The close exceeds threshold (ATR-based)
#   - Rolling tracking: we track the highest high and lowest low
#     since the last confirmed directional break
#   - Structure state transitions:
#       UNDEFINED  → BULLISH  (first BOS up or CHoCH up)
#       BULLISH    → BEARISH  (CHoCH down confirmed)
#       BEARISH    → BULLISH  (CHoCH up confirmed)
#       Any state → TRANSITIONAL (brief window after CHoCH, before BOS)
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime
from typing import Optional, Tuple

from core.candle import Candle
from core.state import MarketState, StructureState, SwingLevel
from config.settings import ATR_SWING_THRESHOLD_MULT, BODY_DOMINANCE_RATIO


class StructureEngine:
    """
    Processes one confirmed closed candle at a time.
    Updates swing highs/lows and structure state.
    Never accesses future candles.
    """

    def __init__(self):
        # Rolling extremes since last confirmed swing
        self._candidate_high: float = float('-inf')
        self._candidate_high_ts: Optional[datetime] = None
        self._candidate_low: float = float('inf')
        self._candidate_low_ts: Optional[datetime] = None
        self._initialized = False

    def update(self, candle: Candle, state: MarketState) -> bool:
        """
        Process one closed candle. Mutates state.structure,
        state.last_confirmed_swing_high/low.
        Returns True if a new swing was confirmed this bar.
        """
        if not state.is_ready if hasattr(state, 'is_ready') else False:
            return False

        atr = state.current_atr
        if atr <= 0:
            self._update_candidates(candle)
            return False

        threshold = atr * ATR_SWING_THRESHOLD_MULT
        new_swing = False

        # ── Check for new swing HIGH confirmation ─────────────────────────────
        # A new swing high is confirmed when:
        #   • We have a candidate high
        #   • Current close breaks ABOVE candidate high + threshold
        #   • The candle body is dominant (displacement confirmation)
        if (
            self._candidate_high > float('-inf')
            and candle.close > self._candidate_high + threshold
            and candle.is_bullish
            and candle.body_ratio >= BODY_DOMINANCE_RATIO
        ):
            # Confirm candidate high as a new swing high
            new_swing_high = SwingLevel(
                price=self._candidate_high,
                timestamp=self._candidate_high_ts,
                is_high=True,
            )
            state.prev_swing_high = state.last_confirmed_swing_high
            state.last_confirmed_swing_high = new_swing_high

            # Reset candidate tracking from this point
            self._candidate_high = candle.high
            self._candidate_high_ts = candle.timestamp
            self._candidate_low = candle.low
            self._candidate_low_ts = candle.timestamp
            new_swing = True

        # ── Check for new swing LOW confirmation ──────────────────────────────
        elif (
            self._candidate_low < float('inf')
            and candle.close < self._candidate_low - threshold
            and candle.is_bearish
            and candle.body_ratio >= BODY_DOMINANCE_RATIO
        ):
            new_swing_low = SwingLevel(
                price=self._candidate_low,
                timestamp=self._candidate_low_ts,
                is_high=False,
            )
            state.prev_swing_low = state.last_confirmed_swing_low
            state.last_confirmed_swing_low = new_swing_low

            self._candidate_low = candle.low
            self._candidate_low_ts = candle.timestamp
            self._candidate_high = candle.high
            self._candidate_high_ts = candle.timestamp
            new_swing = True

        else:
            # No confirmation: update rolling candidates
            self._update_candidates(candle)

        # ── Update structure state from confirmed swings ───────────────────────
        self._infer_structure(state)

        return new_swing

    def _update_candidates(self, candle: Candle):
        """Track rolling high/low candidates without confirming anything."""
        if candle.high > self._candidate_high:
            self._candidate_high = candle.high
            self._candidate_high_ts = candle.timestamp
        if candle.low < self._candidate_low:
            self._candidate_low = candle.low
            self._candidate_low_ts = candle.timestamp

    def _infer_structure(self, state: MarketState):
        """
        Determine structural bias from confirmed swings only.
        Bullish HH + HL sequence → BULLISH
        Bearish LL + LH sequence → BEARISH
        Mixed → TRANSITIONAL
        """
        sh = state.last_confirmed_swing_high
        sl = state.last_confirmed_swing_low
        psh = state.prev_swing_high
        psl = state.prev_swing_low

        if sh and sl and psh and psl:
            hh = sh.price > psh.price
            hl = sl.price > psl.price
            ll = sl.price < psl.price
            lh = sh.price < psh.price

            if hh and hl:
                state.structure = StructureState.BULLISH
            elif ll and lh:
                state.structure = StructureState.BEARISH
            else:
                state.structure = StructureState.TRANSITIONAL
        elif sh and psh:
            if sh.price > psh.price:
                state.structure = StructureState.BULLISH
            else:
                state.structure = StructureState.BEARISH

    def reset(self):
        self._candidate_high = float('-inf')
        self._candidate_high_ts = None
        self._candidate_low = float('inf')
        self._candidate_low_ts = None
