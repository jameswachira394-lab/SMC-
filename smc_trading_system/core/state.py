# core/state.py
# ─────────────────────────────────────────────────────────────────────────────
# MarketState is the single shared state object threaded through all engines.
# Each engine reads it and emits events / mutations — never raw lookahead data.
# ─────────────────────────────────────────────────────────────────────────────
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, List


# ── Enums ─────────────────────────────────────────────────────────────────────

class StructureState(Enum):
    BULLISH = auto()
    BEARISH = auto()
    TRANSITIONAL = auto()
    UNDEFINED = auto()


class EventType(Enum):
    BOS_UP = "BOS_UP"
    BOS_DOWN = "BOS_DOWN"
    CHOCH_UP = "CHOCH_UP"
    CHOCH_DOWN = "CHOCH_DOWN"
    LIQUIDITY_SWEEP_BUY_SIDE = "LIQUIDITY_SWEEP_BUY_SIDE"
    LIQUIDITY_SWEEP_SELL_SIDE = "LIQUIDITY_SWEEP_SELL_SIDE"
    LONG_ENTRY = "LONG_ENTRY"
    SHORT_ENTRY = "SHORT_ENTRY"
    TP_HIT = "TP_HIT"
    SL_HIT = "SL_HIT"
    PARTIAL_TP = "PARTIAL_TP"


# ── Zone dataclasses ──────────────────────────────────────────────────────────

@dataclass
class SwingLevel:
    price: float
    timestamp: datetime
    is_high: bool           # True = swing high; False = swing low

    def __repr__(self):
        kind = "SwingHigh" if self.is_high else "SwingLow"
        return f"{kind}[{self.price:.5f} @ {self.timestamp}]"


@dataclass
class OrderBlock:
    zone_high: float
    zone_low: float
    timestamp: datetime
    is_bullish: bool        # True = demand OB; False = supply OB
    active: bool = True
    id: str = ""

    def contains(self, price: float) -> bool:
        return self.zone_low <= price <= self.zone_high

    def invalidated_by(self, candle_close: float) -> bool:
        if self.is_bullish:
            return candle_close < self.zone_low
        else:
            return candle_close > self.zone_high

    def __repr__(self):
        kind = "Bullish" if self.is_bullish else "Bearish"
        status = "ACTIVE" if self.active else "INVALID"
        return f"OB[{kind} {self.zone_low:.5f}-{self.zone_high:.5f} {status}]"


@dataclass
class FairValueGap:
    gap_high: float
    gap_low: float
    timestamp: datetime
    is_bullish: bool
    mitigation: str = "untouched"   # untouched | partial | filled
    active: bool = True
    id: str = ""

    @property
    def size(self) -> float:
        return self.gap_high - self.gap_low

    def update_mitigation(self, current_low: float, current_high: float):
        """Update fill state based on candle range (no lookahead)."""
        if self.is_bullish:
            if current_low <= self.gap_low:
                self.mitigation = "filled"
                self.active = False
            elif current_low < self.gap_high:
                self.mitigation = "partial"
        else:
            if current_high >= self.gap_high:
                self.mitigation = "filled"
                self.active = False
            elif current_high > self.gap_low:
                self.mitigation = "partial"

    def __repr__(self):
        kind = "Bull" if self.is_bullish else "Bear"
        return f"FVG[{kind} {self.gap_low:.5f}-{self.gap_high:.5f} {self.mitigation}]"


@dataclass
class LiquidityLevel:
    price: float
    timestamp: datetime
    is_buy_side: bool       # True = equal highs (buy-side liquidity)
    swept: bool = False
    sweep_timestamp: Optional[datetime] = None


@dataclass
class StructureEvent:
    event_type: EventType
    price: float
    timestamp: datetime
    atr: float
    details: dict = field(default_factory=dict)

    def __repr__(self):
        return f"Event[{self.event_type.value} @ {self.price:.5f} {self.timestamp}]"


@dataclass
class TradeSignal:
    direction: str              # "long" | "short"
    entry_price: float
    stop_loss: float
    take_profit: float
    partial_tp: Optional[float]
    timestamp: datetime
    reason: str
    rr_ratio: float
    position_size: float = 0.0  # filled by risk manager


# ── Master state ──────────────────────────────────────────────────────────────

@dataclass
class MarketState:
    # Structure
    structure: StructureState = StructureState.UNDEFINED
    last_confirmed_swing_high: Optional[SwingLevel] = None
    last_confirmed_swing_low: Optional[SwingLevel] = None
    prev_swing_high: Optional[SwingLevel] = None
    prev_swing_low: Optional[SwingLevel] = None

    # Tracking for swing construction (rolling, no pivots)
    rolling_high: float = float('-inf')
    rolling_low: float = float('inf')
    rolling_high_ts: Optional[datetime] = None
    rolling_low_ts: Optional[datetime] = None
    bars_since_last_break: int = 0

    # ATR
    current_atr: float = 0.0

    # Events (last N)
    recent_events: List[StructureEvent] = field(default_factory=list)

    # Zones
    order_blocks: List[OrderBlock] = field(default_factory=list)
    fair_value_gaps: List[FairValueGap] = field(default_factory=list)
    liquidity_levels: List[LiquidityLevel] = field(default_factory=list)

    # Last sweep
    last_sweep: Optional[StructureEvent] = None

    # Open trade
    open_trade: Optional[TradeSignal] = None

    # Risk counters
    consecutive_losses: int = 0
    daily_loss_pct: float = 0.0
    account_balance: float = 10_000.0

    # HTF bias (optional)
    htf_bias: Optional[StructureState] = None

    def push_event(self, event: StructureEvent):
        self.recent_events.append(event)
        if len(self.recent_events) > 50:
            self.recent_events.pop(0)

    def last_event_of_type(self, *types: EventType) -> Optional[StructureEvent]:
        for ev in reversed(self.recent_events):
            if ev.event_type in types:
                return ev
        return None

    def active_obs(self, bullish: bool) -> List[OrderBlock]:
        return [ob for ob in self.order_blocks if ob.active and ob.is_bullish == bullish]

    def active_fvgs(self, bullish: bool) -> List[FairValueGap]:
        return [f for f in self.fair_value_gaps if f.active and f.is_bullish == bullish]
