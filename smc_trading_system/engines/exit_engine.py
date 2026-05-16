# engines/exit_engine.py
# ─────────────────────────────────────────────────────────────────────────────
# MODULE 7: EXIT ENGINE
# ─────────────────────────────────────────────────────────────────────────────
# Rules:
#   Take Profit:
#     • Primary TP = nearest opposing liquidity pool or previous swing H/L
#     • (Optional) Partial TP at 1R, runner to full TP
#   Stop Loss:
#     • Fixed at entry: beyond OB invalidation level or sweep origin
#     • No trailing unless explicitly configured
#   Exit triggers (evaluated each closed candle):
#     • TP_HIT    : candle high/low reaches TP
#     • SL_HIT    : candle low/high reaches SL
#     • PARTIAL_TP: candle reaches partial TP level (50% close)
# ─────────────────────────────────────────────────────────────────────────────
from dataclasses import dataclass
from typing import Optional, Tuple
from core.candle import Candle
from core.state import MarketState, TradeSignal, EventType, StructureEvent
from config.settings import PARTIAL_TP_ENABLED, PARTIAL_TP_PCT


@dataclass
class ExitResult:
    exit_type: str          # "TP_HIT" | "SL_HIT" | "PARTIAL_TP" | None
    exit_price: float
    pnl_r: float            # P&L in R-multiples
    timestamp: object
    partial: bool = False   # True if only partial close


class ExitEngine:

    def __init__(self):
        self._partial_tp_triggered: bool = False

    def update(self, candle: Candle, state: MarketState) -> Optional[ExitResult]:
        """
        Check if the current closed candle hits TP or SL on the open trade.
        Returns ExitResult if an exit occurred, None otherwise.
        All checks use confirmed candle high/low — no lookahead.
        """
        trade = state.open_trade
        if trade is None:
            return None

        is_long = trade.direction == "long"
        risk = abs(trade.entry_price - trade.stop_loss)
        if risk <= 0:
            return None

        # ── Partial TP check (first, before full TP/SL) ──────────────────────
        if (
            PARTIAL_TP_ENABLED
            and trade.partial_tp is not None
            and not self._partial_tp_triggered
        ):
            if is_long and candle.high >= trade.partial_tp:
                self._partial_tp_triggered = True
                pnl_r = (trade.partial_tp - trade.entry_price) / risk * PARTIAL_TP_PCT
                return ExitResult(
                    exit_type="PARTIAL_TP",
                    exit_price=trade.partial_tp,
                    pnl_r=pnl_r,
                    timestamp=candle.timestamp,
                    partial=True,
                )
            elif not is_long and candle.low <= trade.partial_tp:
                self._partial_tp_triggered = True
                pnl_r = (trade.entry_price - trade.partial_tp) / risk * PARTIAL_TP_PCT
                return ExitResult(
                    exit_type="PARTIAL_TP",
                    exit_price=trade.partial_tp,
                    pnl_r=pnl_r,
                    timestamp=candle.timestamp,
                    partial=True,
                )

        # ── SL check (uses candle close for body-based SL, wick for hard SL) ──
        if is_long:
            sl_hit = candle.low <= trade.stop_loss
        else:
            sl_hit = candle.high >= trade.stop_loss

        if sl_hit:
            exit_price = trade.stop_loss
            pnl_r = -1.0  # Always -1R on SL
            if PARTIAL_TP_ENABLED and self._partial_tp_triggered:
                # If partial was taken, net loss is reduced
                pnl_r = -1.0 * (1 - PARTIAL_TP_PCT)
            self._partial_tp_triggered = False
            state.open_trade = None
            return ExitResult(
                exit_type="SL_HIT",
                exit_price=exit_price,
                pnl_r=pnl_r,
                timestamp=candle.timestamp,
            )

        # ── Full TP check ─────────────────────────────────────────────────────
        if is_long:
            tp_hit = candle.high >= trade.take_profit
        else:
            tp_hit = candle.low <= trade.take_profit

        if tp_hit:
            exit_price = trade.take_profit
            if is_long:
                gross_r = (exit_price - trade.entry_price) / risk
            else:
                gross_r = (trade.entry_price - exit_price) / risk

            # If partial was already taken, only remaining portion hits full TP
            if PARTIAL_TP_ENABLED and self._partial_tp_triggered:
                gross_r *= (1 - PARTIAL_TP_PCT)

            self._partial_tp_triggered = False
            state.open_trade = None
            return ExitResult(
                exit_type="TP_HIT",
                exit_price=exit_price,
                pnl_r=gross_r,
                timestamp=candle.timestamp,
            )

        return None

    def reset(self):
        self._partial_tp_triggered = False
