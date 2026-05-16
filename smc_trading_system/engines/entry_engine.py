# engines/entry_engine.py
# ─────────────────────────────────────────────────────────────────────────────
# MODULE 6: ENTRY LOGIC ENGINE — CONFLUENCE ONLY
# ─────────────────────────────────────────────────────────────────────────────
# LONG ENTRY requires ALL of:
#   1. Bullish structure confirmed (BOS_UP or CHoCH_UP in recent events)
#   2. Sell-side liquidity sweep occurred (below price, recent)
#   3. Price is currently trading at / inside a bullish OB or bullish FVG
#   4. Rejection confirmation candle present (current candle closes bullish
#      after touching the zone)
#   5. Session filter: London or NY only
#   6. No consolidation (range not compressed)
#   7. (Optional) HTF bias is bullish
#
# SHORT ENTRY: inverse of all above
#
# Output: TradeSignal or None
# ─────────────────────────────────────────────────────────────────────────────
from typing import Optional, List
from datetime import datetime

from core.candle import Candle
from core.state import (
    MarketState, StructureState, EventType,
    TradeSignal, OrderBlock, FairValueGap
)
from utils.session import is_tradeable_session
from config.settings import (
    REQUIRE_SWEEP_BEFORE_ENTRY,
    REQUIRE_REJECTION_CANDLE,
    HTF_BIAS_ENABLED,
    CONSOLIDATION_ATR_MULT,
    CONSOLIDATION_LOOKBACK,
    MIN_RR_RATIO,
    PARTIAL_TP_ENABLED,
    PARTIAL_TP_AT_R,
)


class EntryEngine:

    def __init__(self):
        # Store recent candle ranges to detect consolidation
        self._recent_ranges: List[float] = []
        self._lookback = CONSOLIDATION_LOOKBACK

    def update(
        self,
        candle: Candle,
        state: MarketState,
        exit_engine=None,  # injected to calculate TP/SL
    ) -> Optional[TradeSignal]:
        """
        Evaluate all confluence conditions on this closed candle.
        Returns a TradeSignal if all conditions met, else None.
        No lookahead — all decisions based on closed candle only.
        """
        # Update consolidation tracker
        self._recent_ranges.append(candle.range_size)
        if len(self._recent_ranges) > self._lookback:
            self._recent_ranges.pop(0)

        # Skip if already in a trade
        if state.open_trade is not None:
            return None

        # ── Pre-checks ────────────────────────────────────────────────────────
        if not state.current_atr or state.current_atr <= 0:
            return None

        if not is_tradeable_session(candle.timestamp):
            return None

        if self._is_consolidating(state.current_atr):
            return None

        # ── Try LONG ──────────────────────────────────────────────────────────
        if self._long_conditions_met(candle, state):
            signal = self._build_long_signal(candle, state)
            if signal and signal.rr_ratio >= MIN_RR_RATIO:
                return signal

        # ── Try SHORT ─────────────────────────────────────────────────────────
        if self._short_conditions_met(candle, state):
            signal = self._build_short_signal(candle, state)
            if signal and signal.rr_ratio >= MIN_RR_RATIO:
                return signal

        return None

    # ── LONG CONDITIONS ───────────────────────────────────────────────────────

    def _long_conditions_met(self, candle: Candle, state: MarketState) -> bool:
        # 1. Bullish structure
        if state.structure not in (StructureState.BULLISH, StructureState.TRANSITIONAL):
            return False

        # 2. Recent BOS_UP or CHOCH_UP in events
        bullish_break = state.last_event_of_type(EventType.BOS_UP, EventType.CHOCH_UP)
        if not bullish_break:
            return False

        # 3. Sell-side sweep occurred after (or with) the bullish break
        if REQUIRE_SWEEP_BEFORE_ENTRY:
            sweep = state.last_event_of_type(EventType.LIQUIDITY_SWEEP_SELL_SIDE)
            if not sweep:
                return False
            # Sweep must be recent (after last bearish structure event)
            bearish_break = state.last_event_of_type(EventType.BOS_DOWN, EventType.CHOCH_DOWN)
            if bearish_break and sweep.timestamp < bearish_break.timestamp:
                return False

        # 4. Price inside bullish OB or bullish FVG
        zone = self._touching_bullish_zone(candle, state)
        if zone is None:
            return False

        # 5. Rejection candle (current candle closes bullish after touching zone)
        if REQUIRE_REJECTION_CANDLE:
            if not candle.is_bullish:
                return False
            if candle.close <= candle.open:
                return False

        # 6. HTF bias (optional)
        if HTF_BIAS_ENABLED and state.htf_bias != StructureState.BULLISH:
            return False

        return True

    def _short_conditions_met(self, candle: Candle, state: MarketState) -> bool:
        if state.structure not in (StructureState.BEARISH, StructureState.TRANSITIONAL):
            return False

        bearish_break = state.last_event_of_type(EventType.BOS_DOWN, EventType.CHOCH_DOWN)
        if not bearish_break:
            return False

        if REQUIRE_SWEEP_BEFORE_ENTRY:
            sweep = state.last_event_of_type(EventType.LIQUIDITY_SWEEP_BUY_SIDE)
            if not sweep:
                return False
            bullish_break = state.last_event_of_type(EventType.BOS_UP, EventType.CHOCH_UP)
            if bullish_break and sweep.timestamp < bullish_break.timestamp:
                return False

        zone = self._touching_bearish_zone(candle, state)
        if zone is None:
            return False

        if REQUIRE_REJECTION_CANDLE:
            if not candle.is_bearish:
                return False

        if HTF_BIAS_ENABLED and state.htf_bias != StructureState.BEARISH:
            return False

        return True

    # ── ZONE DETECTION ────────────────────────────────────────────────────────

    def _touching_bullish_zone(self, candle: Candle, state: MarketState):
        """Returns first bullish OB or FVG that the current candle is touching."""
        for ob in state.active_obs(bullish=True):
            if ob.zone_low <= candle.low <= ob.zone_high or \
               ob.zone_low <= candle.close <= ob.zone_high:
                return ob
        for fvg in state.active_fvgs(bullish=True):
            if fvg.gap_low <= candle.low <= fvg.gap_high or \
               fvg.gap_low <= candle.close <= fvg.gap_high:
                return fvg
        return None

    def _touching_bearish_zone(self, candle: Candle, state: MarketState):
        """Returns first bearish OB or FVG that the current candle is touching."""
        for ob in state.active_obs(bullish=False):
            if ob.zone_low <= candle.high <= ob.zone_high or \
               ob.zone_low <= candle.close <= ob.zone_high:
                return ob
        for fvg in state.active_fvgs(bullish=False):
            if fvg.gap_low <= candle.high <= fvg.gap_high or \
               fvg.gap_low <= candle.close <= fvg.gap_high:
                return fvg
        return None

    # ── SIGNAL BUILDERS ───────────────────────────────────────────────────────

    def _build_long_signal(self, candle: Candle, state: MarketState) -> Optional[TradeSignal]:
        zone = self._touching_bullish_zone(candle, state)
        if zone is None:
            return None

        entry = candle.close
        stop_loss = self._long_stop(zone, state)
        if stop_loss is None or stop_loss >= entry:
            return None

        risk = entry - stop_loss
        tp1 = self._nearest_opposing_liquidity(entry, state, is_long=True)
        if tp1 is None:
            tp1 = entry + risk * MIN_RR_RATIO

        rr = (tp1 - entry) / risk if risk > 0 else 0
        partial_tp = (entry + risk * PARTIAL_TP_AT_R) if PARTIAL_TP_ENABLED else None

        return TradeSignal(
            direction="long",
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=tp1,
            partial_tp=partial_tp,
            timestamp=candle.timestamp,
            reason=f"LONG confluence @ {zone}",
            rr_ratio=rr,
        )

    def _build_short_signal(self, candle: Candle, state: MarketState) -> Optional[TradeSignal]:
        zone = self._touching_bearish_zone(candle, state)
        if zone is None:
            return None

        entry = candle.close
        stop_loss = self._short_stop(zone, state)
        if stop_loss is None or stop_loss <= entry:
            return None

        risk = stop_loss - entry
        tp1 = self._nearest_opposing_liquidity(entry, state, is_long=False)
        if tp1 is None:
            tp1 = entry - risk * MIN_RR_RATIO

        rr = (entry - tp1) / risk if risk > 0 else 0
        partial_tp = (entry - risk * PARTIAL_TP_AT_R) if PARTIAL_TP_ENABLED else None

        return TradeSignal(
            direction="short",
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=tp1,
            partial_tp=partial_tp,
            timestamp=candle.timestamp,
            reason=f"SHORT confluence @ {zone}",
            rr_ratio=rr,
        )

    # ── STOP LOSS HELPERS ─────────────────────────────────────────────────────

    def _long_stop(self, zone, state: MarketState) -> Optional[float]:
        """SL = below OB/FVG zone low OR below sweep origin (whichever is lower)."""
        zone_sl = zone.zone_low if hasattr(zone, 'zone_low') else zone.gap_low
        sl = zone_sl - state.current_atr * 0.1  # small buffer below zone

        # If sweep occurred, optionally place SL below sweep origin
        sweep = state.last_event_of_type(EventType.LIQUIDITY_SWEEP_SELL_SIDE)
        if sweep:
            sweep_sl = sweep.details.get("wick_low", zone_sl) - state.current_atr * 0.1
            sl = min(sl, sweep_sl)

        return sl

    def _short_stop(self, zone, state: MarketState) -> Optional[float]:
        """SL = above OB/FVG zone high OR above sweep origin."""
        zone_sl = zone.zone_high if hasattr(zone, 'zone_high') else zone.gap_high
        sl = zone_sl + state.current_atr * 0.1

        sweep = state.last_event_of_type(EventType.LIQUIDITY_SWEEP_BUY_SIDE)
        if sweep:
            sweep_sl = sweep.details.get("wick_high", zone_sl) + state.current_atr * 0.1
            sl = max(sl, sweep_sl)

        return sl

    # ── TAKE PROFIT HELPERS ───────────────────────────────────────────────────

    def _nearest_opposing_liquidity(
        self, entry: float, state: MarketState, is_long: bool
    ) -> Optional[float]:
        """Find nearest opposing liquidity pool or swing level above/below entry."""
        targets = []

        # Opposing swing levels
        if is_long and state.last_confirmed_swing_high:
            if state.last_confirmed_swing_high.price > entry:
                targets.append(state.last_confirmed_swing_high.price)
        if not is_long and state.last_confirmed_swing_low:
            if state.last_confirmed_swing_low.price < entry:
                targets.append(state.last_confirmed_swing_low.price)

        # Opposing liquidity pools (unswept)
        for liq in state.liquidity_levels:
            if liq.swept:
                continue
            if is_long and liq.is_buy_side and liq.price > entry:
                targets.append(liq.price)
            elif not is_long and not liq.is_buy_side and liq.price < entry:
                targets.append(liq.price)

        if not targets:
            return None

        if is_long:
            return min(targets)   # nearest above
        else:
            return max(targets)   # nearest below

    # ── CONSOLIDATION FILTER ──────────────────────────────────────────────────

    def _is_consolidating(self, atr: float) -> bool:
        if len(self._recent_ranges) < self._lookback:
            return False
        avg_range = sum(self._recent_ranges) / len(self._recent_ranges)
        return avg_range < atr * CONSOLIDATION_ATR_MULT

    def reset(self):
        self._recent_ranges.clear()
