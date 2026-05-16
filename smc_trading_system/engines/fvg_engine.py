# engines/fvg_engine.py
# ─────────────────────────────────────────────────────────────────────────────
# MODULE 5: FAIR VALUE GAP ENGINE — STRICT 3-CANDLE MODEL
# ─────────────────────────────────────────────────────────────────────────────
# Rules:
#   Bullish FVG: candle[1].low > candle[-1].high   (gap between candle[i-2] high
#                                                    and candle[i].low)
#   Bearish FVG: candle[1].high < candle[-1].low
#
#   Where:
#       candle[-1] = 2 bars ago (confirmed)
#       candle[0]  = 1 bar ago  (confirmed)
#       candle[1]  = current closed candle
#
#   • Confirmed ONLY on current candle close (3 candles all closed)
#   • FVG stored immediately and immutably when formed
#   • Mitigation tracked on each subsequent close:
#       untouched → partial → filled (inactive)
#   • No retroactive resizing
#   • Minimum FVG size filter: gap ≥ ATR × MIN_FVG_SIZE_MULT
# ─────────────────────────────────────────────────────────────────────────────
from collections import deque
from typing import List, Optional
from uuid import uuid4

from core.candle import Candle
from core.state import MarketState, FairValueGap
from config.settings import MIN_FVG_SIZE_MULT, MAX_ACTIVE_FVGS


class FVGEngine:

    def __init__(self):
        # Rolling 3-candle window (all confirmed closed candles)
        self._window: deque = deque(maxlen=3)

    def update(self, candle: Candle, state: MarketState) -> List[FairValueGap]:
        """
        Add current closed candle to window.
        Check for new FVG formation.
        Update mitigation on all active FVGs.
        Returns list of newly created FVGs.
        """
        self._window.append(candle)
        new_fvgs: List[FairValueGap] = []

        atr = state.current_atr
        if atr <= 0 or len(self._window) < 3:
            return new_fvgs

        min_size = atr * MIN_FVG_SIZE_MULT

        c_prev2 = self._window[0]   # 2 bars ago
        # c_prev1 = self._window[1] # 1 bar ago (middle candle — not needed for detection)
        c_curr  = self._window[2]   # current (just closed)

        # ── Bullish FVG: current low > prev2 high ─────────────────────────────
        if c_curr.low > c_prev2.high:
            gap_low  = c_prev2.high
            gap_high = c_curr.low
            gap_size = gap_high - gap_low
            if gap_size >= min_size:
                fvg = FairValueGap(
                    gap_high=gap_high,
                    gap_low=gap_low,
                    timestamp=c_curr.timestamp,
                    is_bullish=True,
                    mitigation="untouched",
                    active=True,
                    id=str(uuid4())[:8],
                )
                state.fair_value_gaps.append(fvg)
                new_fvgs.append(fvg)

        # ── Bearish FVG: current high < prev2 low ────────────────────────────
        elif c_curr.high < c_prev2.low:
            gap_low  = c_curr.high
            gap_high = c_prev2.low
            gap_size = gap_high - gap_low
            if gap_size >= min_size:
                fvg = FairValueGap(
                    gap_high=gap_high,
                    gap_low=gap_low,
                    timestamp=c_curr.timestamp,
                    is_bullish=False,
                    mitigation="untouched",
                    active=True,
                    id=str(uuid4())[:8],
                )
                state.fair_value_gaps.append(fvg)
                new_fvgs.append(fvg)

        # ── Update mitigation on ALL active FVGs ──────────────────────────────
        for fvg in state.fair_value_gaps:
            if fvg.active:
                fvg.update_mitigation(
                    current_low=candle.low,
                    current_high=candle.high,
                )

        # ── Prune excess ──────────────────────────────────────────────────────
        self._prune(state)

        return new_fvgs

    def _prune(self, state: MarketState):
        """Remove oldest filled FVGs if we exceed MAX_ACTIVE_FVGS."""
        active = [f for f in state.fair_value_gaps if f.active]
        if len(active) > MAX_ACTIVE_FVGS:
            # Deactivate the oldest (earliest timestamp) ones
            sorted_fvgs = sorted(active, key=lambda f: f.timestamp)
            for f in sorted_fvgs[:len(active) - MAX_ACTIVE_FVGS]:
                f.active = False

    def reset(self):
        self._window.clear()
