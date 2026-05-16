# engines/orderblock_engine.py
# ─────────────────────────────────────────────────────────────────────────────
# MODULE 4: ORDER BLOCK ENGINE — FORWARD-ONLY LOGIC
# ─────────────────────────────────────────────────────────────────────────────
# Rules:
#   • OB is created ONLY AFTER a BOS or CHoCH event is confirmed
#   • OB = the last opposite-color candle BEFORE the displacement move
#   • "Last opposite candle" = the most recent candle before BOS/CHoCH close
#     that is opposite in direction to the BOS/CHoCH candle
#   • OB zone = [low, high] of that candle (immutable after creation)
#   • Validation:
#       - Body dominance (OB_MIN_BODY_RATIO)
#       - Preceded a strong impulse move (displacement ≥ ATR_DISPLACEMENT_MULT)
#   • Invalidation: a candle CLOSES fully through the OB zone
#   • Retroactive modification: NOT ALLOWED
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from core.candle import Candle
from core.state import (
    MarketState, StructureEvent, EventType, OrderBlock
)
from config.settings import OB_MIN_BODY_RATIO, MAX_ACTIVE_OBS


class OrderBlockEngine:

    def __init__(self):
        # Sliding window of recent closed candles (we need last N to find OB candle)
        self._candle_buffer: List[Candle] = []
        self._buffer_size = 30

    def update(
        self,
        candle: Candle,
        state: MarketState,
        new_events: List[StructureEvent],
    ) -> List[OrderBlock]:
        """
        1. Store the current closed candle in buffer.
        2. On BOS/CHoCH events: find and register the OB candle.
        3. Invalidate any OBs fully broken by this candle's close.
        Returns list of newly created OBs.
        """
        # Add candle to buffer BEFORE processing events
        self._candle_buffer.append(candle)
        if len(self._candle_buffer) > self._buffer_size:
            self._candle_buffer.pop(0)

        new_obs: List[OrderBlock] = []

        # ── Create OBs from structure events ──────────────────────────────────
        for event in new_events:
            if event.event_type in (EventType.BOS_UP, EventType.CHOCH_UP):
                ob = self._find_ob_candle(is_bullish_break=True, atr=state.current_atr)
                if ob:
                    state.order_blocks.append(ob)
                    new_obs.append(ob)

            elif event.event_type in (EventType.BOS_DOWN, EventType.CHOCH_DOWN):
                ob = self._find_ob_candle(is_bullish_break=False, atr=state.current_atr)
                if ob:
                    state.order_blocks.append(ob)
                    new_obs.append(ob)

        # ── Invalidate broken OBs ─────────────────────────────────────────────
        for ob in state.order_blocks:
            if ob.active and ob.invalidated_by(candle.close):
                ob.active = False

        # ── Prune excess OBs (keep most recent MAX_ACTIVE_OBS per direction) ──
        self._prune(state)

        return new_obs

    def _find_ob_candle(self, is_bullish_break: bool, atr: float) -> Optional[OrderBlock]:
        """
        Scan back through the candle buffer (EXCLUDING current candle which IS the break)
        and find the last candle opposite to the break direction.

        Bullish break (BOS_UP / CHOCH_UP):
          → OB = last BEARISH candle before the displacement → Bullish OB (demand)
        Bearish break (BOS_DOWN / CHOCH_DOWN):
          → OB = last BULLISH candle before the displacement → Bearish OB (supply)
        """
        # Exclude the current (last) candle — it IS the break candle
        search_window = self._candle_buffer[:-1]

        for c in reversed(search_window):
            if is_bullish_break:
                # Looking for last bearish candle → becomes bullish OB
                if c.is_bearish and c.body_ratio >= OB_MIN_BODY_RATIO:
                    return OrderBlock(
                        zone_high=c.high,
                        zone_low=c.low,
                        timestamp=c.timestamp,
                        is_bullish=True,
                        active=True,
                        id=str(uuid4())[:8],
                    )
            else:
                # Looking for last bullish candle → becomes bearish OB
                if c.is_bullish and c.body_ratio >= OB_MIN_BODY_RATIO:
                    return OrderBlock(
                        zone_high=c.high,
                        zone_low=c.low,
                        timestamp=c.timestamp,
                        is_bullish=False,
                        active=True,
                        id=str(uuid4())[:8],
                    )
        return None

    def _prune(self, state: MarketState):
        """Keep only the most recent MAX_ACTIVE_OBS active OBs per direction."""
        for direction in (True, False):
            active = [ob for ob in state.order_blocks if ob.active and ob.is_bullish == direction]
            if len(active) > MAX_ACTIVE_OBS:
                # Mark oldest as inactive
                to_remove = sorted(active, key=lambda ob: ob.timestamp)[:len(active) - MAX_ACTIVE_OBS]
                for ob in to_remove:
                    ob.active = False

    def reset(self):
        self._candle_buffer.clear()
