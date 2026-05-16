# engines/liquidity_engine.py
# ─────────────────────────────────────────────────────────────────────────────
# MODULE 3: LIQUIDITY MODEL
# ─────────────────────────────────────────────────────────────────────────────
# Design rules:
#   • Equal highs/lows detected when two or more swing extremes are within
#     ATR × tolerance of each other (no fuzzy clustering, strict tolerance)
#   • Sweep definition:
#       - Wick TAKES the liquidity level (wick extends through it)
#       - Candle CLOSES BACK inside the prior range (rejection)
#       - Both conditions must be true on the same candle close
#   • Outputs:
#       LIQUIDITY_SWEEP_BUY_SIDE  (equal highs swept)
#       LIQUIDITY_SWEEP_SELL_SIDE (equal lows swept)
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime
from typing import List, Optional

from core.candle import Candle
from core.state import (
    MarketState, StructureEvent, EventType, LiquidityLevel
)
from config.settings import ATR_LIQUIDITY_TOLERANCE_MULT


class LiquidityEngine:

    def __init__(self):
        self._swing_highs_history: List[tuple] = []  # (price, timestamp)
        self._swing_lows_history: List[tuple] = []
        self._max_levels = 20

    def update(self, candle: Candle, state: MarketState) -> List[StructureEvent]:
        """
        1. Register newly confirmed swings as liquidity candidates.
        2. Check for sweeps on the current closed candle.
        Returns sweep events.
        """
        events: List[StructureEvent] = []
        atr = state.current_atr
        if atr <= 0:
            return events

        # ── Register new swing extremes into liquidity pool ───────────────────
        sh = state.last_confirmed_swing_high
        sl = state.last_confirmed_swing_low

        if sh and not any(ts == sh.timestamp for _, ts in self._swing_highs_history):
            self._swing_highs_history.append((sh.price, sh.timestamp))
            if len(self._swing_highs_history) > self._max_levels:
                self._swing_highs_history.pop(0)
            # Build equal highs liquidity levels
            self._refresh_liquidity_levels(state, atr)

        if sl and not any(ts == sl.timestamp for _, ts in self._swing_lows_history):
            self._swing_lows_history.append((sl.price, sl.timestamp))
            if len(self._swing_lows_history) > self._max_levels:
                self._swing_lows_history.pop(0)
            self._refresh_liquidity_levels(state, atr)

        # ── Check for sweeps on this closed candle ────────────────────────────
        tolerance = atr * ATR_LIQUIDITY_TOLERANCE_MULT

        for liq in state.liquidity_levels:
            if liq.swept:
                continue

            if liq.is_buy_side:
                # Buy-side (equal highs): wick breaks above level, close back below
                swept = candle.high > liq.price and candle.close < liq.price
                if swept:
                    liq.swept = True
                    liq.sweep_timestamp = candle.timestamp
                    event = StructureEvent(
                        event_type=EventType.LIQUIDITY_SWEEP_BUY_SIDE,
                        price=liq.price,
                        timestamp=candle.timestamp,
                        atr=atr,
                        details={
                            "swept_level": liq.price,
                            "wick_high": candle.high,
                            "close": candle.close,
                            "rejection": liq.price - candle.close,
                        },
                    )
                    events.append(event)
                    state.push_event(event)
                    state.last_sweep = event
            else:
                # Sell-side (equal lows): wick breaks below level, close back above
                swept = candle.low < liq.price and candle.close > liq.price
                if swept:
                    liq.swept = True
                    liq.sweep_timestamp = candle.timestamp
                    event = StructureEvent(
                        event_type=EventType.LIQUIDITY_SWEEP_SELL_SIDE,
                        price=liq.price,
                        timestamp=candle.timestamp,
                        atr=atr,
                        details={
                            "swept_level": liq.price,
                            "wick_low": candle.low,
                            "close": candle.close,
                            "rejection": candle.close - liq.price,
                        },
                    )
                    events.append(event)
                    state.push_event(event)
                    state.last_sweep = event

        return events

    def _refresh_liquidity_levels(self, state: MarketState, atr: float):
        """
        Identify equal highs / equal lows within ATR tolerance and create
        liquidity levels if not already tracked.
        """
        tolerance = atr * ATR_LIQUIDITY_TOLERANCE_MULT

        # ── Equal highs → buy-side liquidity ──────────────────────────────────
        new_buy_side = self._find_clusters(self._swing_highs_history, tolerance, is_high=True)
        existing_buy = {l.price for l in state.liquidity_levels if l.is_buy_side and not l.swept}

        for cluster_price, cluster_ts in new_buy_side:
            if not any(abs(cluster_price - ep) < tolerance for ep in existing_buy):
                state.liquidity_levels.append(LiquidityLevel(
                    price=cluster_price,
                    timestamp=cluster_ts,
                    is_buy_side=True,
                ))
                existing_buy.add(cluster_price)

        # ── Equal lows → sell-side liquidity ──────────────────────────────────
        new_sell_side = self._find_clusters(self._swing_lows_history, tolerance, is_high=False)
        existing_sell = {l.price for l in state.liquidity_levels if not l.is_buy_side and not l.swept}

        for cluster_price, cluster_ts in new_sell_side:
            if not any(abs(cluster_price - ep) < tolerance for ep in existing_sell):
                state.liquidity_levels.append(LiquidityLevel(
                    price=cluster_price,
                    timestamp=cluster_ts,
                    is_buy_side=False,
                ))
                existing_sell.add(cluster_price)

        # Prune swept levels older than 100 entries
        if len(state.liquidity_levels) > 100:
            state.liquidity_levels = [l for l in state.liquidity_levels if not l.swept][-100:]

    def _find_clusters(
        self,
        history: List[tuple],
        tolerance: float,
        is_high: bool,
    ) -> List[tuple]:
        """
        Find pairs (or groups) of price levels within tolerance.
        Returns (average_price, latest_timestamp) for each cluster.
        """
        clusters = []
        used = set()

        for i, (p1, t1) in enumerate(history):
            if i in used:
                continue
            group = [(p1, t1)]
            for j, (p2, t2) in enumerate(history):
                if j <= i or j in used:
                    continue
                if abs(p1 - p2) <= tolerance:
                    group.append((p2, t2))
                    used.add(j)
            if len(group) >= 2:
                avg_price = sum(p for p, _ in group) / len(group)
                latest_ts = max(t for _, t in group)
                clusters.append((avg_price, latest_ts))
                used.add(i)

        return clusters

    def reset(self):
        self._swing_highs_history.clear()
        self._swing_lows_history.clear()
