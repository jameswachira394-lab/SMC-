# engines/bos_choch_engine.py
# ─────────────────────────────────────────────────────────────────────────────
# MODULE 2: BOS / CHoCH EVENT ENGINE
# ─────────────────────────────────────────────────────────────────────────────
# Rules (all confirmed by candle CLOSE only):
#
#   BOS_UP   = close breaks last confirmed swing HIGH in bullish trend
#   BOS_DOWN = close breaks last confirmed swing LOW  in bearish trend
#   CHoCH_UP   = close breaks last confirmed swing HIGH against bearish structure
#   CHoCH_DOWN = close breaks last confirmed swing LOW  against bullish structure
#
# Filters:
#   • Close must exceed swing level (no wick-only breaks)
#   • Displacement filter: (close - swing level) ≥ ATR × mult
#   • Candle body must dominate range (BODY_DOMINANCE_RATIO)
# ─────────────────────────────────────────────────────────────────────────────
from typing import Optional, List

from core.candle import Candle
from core.state import (
    MarketState, StructureState, StructureEvent, EventType
)
from config.settings import ATR_DISPLACEMENT_MULT, BODY_DOMINANCE_RATIO


class BOSCHoCHEngine:

    def __init__(self):
        # Track which swing levels have already fired an event (avoid duplicates)
        self._consumed_swing_highs: set = set()
        self._consumed_swing_lows: set = set()

    def update(self, candle: Candle, state: MarketState) -> List[StructureEvent]:
        """
        Process one closed candle. Returns list of new BOS/CHoCH events (0-2).
        Events are also appended to state.recent_events.
        """
        events: List[StructureEvent] = []
        atr = state.current_atr
        if atr <= 0:
            return events

        displacement_min = atr * ATR_DISPLACEMENT_MULT

        sh = state.last_confirmed_swing_high
        sl = state.last_confirmed_swing_low

        # ── BOS UP / CHoCH UP ─────────────────────────────────────────────────
        # Condition: close > last confirmed swing high + displacement
        if (
            sh is not None
            and sh.timestamp not in self._consumed_swing_highs
            and candle.close > sh.price
            and (candle.close - sh.price) >= displacement_min
            and candle.is_bullish
            and candle.body_ratio >= BODY_DOMINANCE_RATIO
        ):
            if state.structure in (StructureState.BULLISH, StructureState.TRANSITIONAL):
                ev_type = EventType.BOS_UP
            else:
                ev_type = EventType.CHOCH_UP

            event = StructureEvent(
                event_type=ev_type,
                price=candle.close,
                timestamp=candle.timestamp,
                atr=atr,
                details={
                    "broken_level": sh.price,
                    "displacement": candle.close - sh.price,
                    "candle_body_ratio": candle.body_ratio,
                },
            )
            events.append(event)
            state.push_event(event)
            self._consumed_swing_highs.add(sh.timestamp)

            # Transition structure
            if ev_type == EventType.CHOCH_UP:
                state.structure = StructureState.TRANSITIONAL

        # ── BOS DOWN / CHoCH DOWN ─────────────────────────────────────────────
        # Condition: close < last confirmed swing low − displacement
        if (
            sl is not None
            and sl.timestamp not in self._consumed_swing_lows
            and candle.close < sl.price
            and (sl.price - candle.close) >= displacement_min
            and candle.is_bearish
            and candle.body_ratio >= BODY_DOMINANCE_RATIO
        ):
            if state.structure in (StructureState.BEARISH, StructureState.TRANSITIONAL):
                ev_type = EventType.BOS_DOWN
            else:
                ev_type = EventType.CHOCH_DOWN

            event = StructureEvent(
                event_type=ev_type,
                price=candle.close,
                timestamp=candle.timestamp,
                atr=atr,
                details={
                    "broken_level": sl.price,
                    "displacement": sl.price - candle.close,
                    "candle_body_ratio": candle.body_ratio,
                },
            )
            events.append(event)
            state.push_event(event)
            self._consumed_swing_lows.add(sl.timestamp)

            if ev_type == EventType.CHOCH_DOWN:
                state.structure = StructureState.TRANSITIONAL

        return events

    def reset(self):
        self._consumed_swing_highs.clear()
        self._consumed_swing_lows.clear()
