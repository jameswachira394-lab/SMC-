# tests/test_engines.py
# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS — All engines tested in isolation
# Run: python -m pytest tests/ -v  OR  python tests/test_engines.py
# ─────────────────────────────────────────────────────────────────────────────
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
from core.candle import Candle
from core.state import MarketState, StructureState
from utils.atr import ATRCalculator
from engines.structure_engine import StructureEngine
from engines.bos_choch_engine import BOSCHoCHEngine
from engines.fvg_engine import FVGEngine
from engines.orderblock_engine import OrderBlockEngine
from engines.liquidity_engine import LiquidityEngine
from core.state import EventType


# ── Helpers ───────────────────────────────────────────────────────────────────

BASE_TIME = datetime(2024, 1, 15, 9, 0, 0)

def make_candle(i, open_, high, low, close, vol=1000):
    return Candle(
        timestamp=BASE_TIME + timedelta(minutes=15 * i),
        open=open_, high=high, low=low, close=close, volume=vol
    )

def warm_atr(atr_calc, state, n=14):
    """Feed N candles to warm up ATR."""
    for i in range(n):
        c = make_candle(i, 1.1000, 1.1010, 1.0990, 1.1005)
        atr = atr_calc.update(c)
        if atr:
            state.current_atr = atr
    return n


# ── ATR Tests ─────────────────────────────────────────────────────────────────

def test_atr_warmup():
    calc = ATRCalculator(period=3)
    c1 = make_candle(0, 1.10, 1.12, 1.09, 1.11)
    c2 = make_candle(1, 1.11, 1.13, 1.10, 1.12)
    assert calc.update(c1) is None   # Not ready yet
    assert calc.update(c2) is None
    c3 = make_candle(2, 1.12, 1.14, 1.11, 1.13)
    result = calc.update(c3)
    assert result is not None
    assert result > 0
    print(f"  ATR after 3 candles: {result:.6f}")

def test_atr_no_lookahead():
    """ATR must not access future candles — purely sequential."""
    calc = ATRCalculator(period=5)
    values = []
    for i in range(10):
        c = make_candle(i, 1.10 + i*0.001, 1.101 + i*0.001, 1.099 + i*0.001, 1.1005 + i*0.001)
        v = calc.update(c)
        values.append(v)
    # First 4 should be None (warming up)
    assert all(v is None for v in values[:4])
    # After period, should have values
    assert all(v is not None for v in values[5:])
    print(f"  ATR sequence (last 5): {[round(v, 6) for v in values[5:]]}")


# ── Candle Tests ──────────────────────────────────────────────────────────────

def test_candle_properties():
    bull = make_candle(0, 1.1000, 1.1020, 1.0990, 1.1015)
    assert bull.is_bullish
    assert not bull.is_bearish
    assert bull.body_size == abs(1.1015 - 1.1000)
    assert bull.range_size == 1.1020 - 1.0990
    assert 0 < bull.body_ratio <= 1.0

    bear = make_candle(1, 1.1015, 1.1020, 1.0980, 1.0990)
    assert bear.is_bearish
    assert bear.upper_wick > 0
    assert bear.lower_wick > 0
    print(f"  Bull body_ratio: {bull.body_ratio:.3f} | Bear body_ratio: {bear.body_ratio:.3f}")


# ── FVG Tests ─────────────────────────────────────────────────────────────────

def test_fvg_bullish_detection():
    """Bullish FVG: candle[i].low > candle[i-2].high"""
    engine = FVGEngine()
    state = MarketState()
    state.current_atr = 0.0010

    c1 = make_candle(0, 1.1000, 1.1010, 1.0990, 1.1005)  # high = 1.1010
    c2 = make_candle(1, 1.1010, 1.1020, 1.1005, 1.1015)  # middle candle
    c3 = make_candle(2, 1.1020, 1.1035, 1.1015, 1.1030)  # low=1.1015 > c1.high=1.1010 → FVG

    engine.update(c1, state)
    engine.update(c2, state)
    result = engine.update(c3, state)

    assert len(result) == 1, f"Expected 1 FVG, got {len(result)}"
    fvg = result[0]
    assert fvg.is_bullish
    assert fvg.gap_low == c1.high
    assert fvg.gap_high == c3.low
    assert fvg.mitigation == "untouched"
    print(f"  Bullish FVG: {fvg}")

def test_fvg_bearish_detection():
    """Bearish FVG: candle[i].high < candle[i-2].low"""
    engine = FVGEngine()
    state = MarketState()
    state.current_atr = 0.0010

    c1 = make_candle(0, 1.1010, 1.1015, 1.1000, 1.1005)  # low = 1.1000
    c2 = make_candle(1, 1.1005, 1.1010, 1.0990, 1.0995)
    c3 = make_candle(2, 1.0990, 1.0995, 1.0975, 1.0980)  # high=1.0995 < c1.low=1.1000 → FVG

    engine.update(c1, state)
    engine.update(c2, state)
    result = engine.update(c3, state)

    assert len(result) == 1
    fvg = result[0]
    assert not fvg.is_bullish
    assert fvg.gap_low == c3.high
    assert fvg.gap_high == c1.low
    print(f"  Bearish FVG: {fvg}")

def test_fvg_mitigation():
    """FVG should transition untouched → partial → filled."""
    engine = FVGEngine()
    state = MarketState()
    state.current_atr = 0.0010

    c1 = make_candle(0, 1.1000, 1.1010, 1.0990, 1.1005)
    c2 = make_candle(1, 1.1010, 1.1020, 1.1005, 1.1015)
    c3 = make_candle(2, 1.1020, 1.1035, 1.1015, 1.1030)
    engine.update(c1, state)
    engine.update(c2, state)
    engine.update(c3, state)

    fvg = state.fair_value_gaps[0]
    assert fvg.mitigation == "untouched"

    # Partial fill: candle dips into FVG but doesn't go below gap_low
    c4 = make_candle(3, 1.1030, 1.1035, 1.1012, 1.1025)  # low=1.1012 inside FVG
    engine.update(c4, state)
    assert fvg.mitigation == "partial"

    # Full fill: candle goes below gap_low
    c5 = make_candle(4, 1.1025, 1.1030, 1.1008, 1.1020)  # low=1.1008 < gap_low=1.1010
    engine.update(c5, state)
    assert fvg.mitigation == "filled"
    assert not fvg.active
    print(f"  FVG mitigation cycle: untouched → partial → filled ✓")

def test_fvg_no_retroactive_resize():
    """FVG boundaries must never change after creation."""
    engine = FVGEngine()
    state = MarketState()
    state.current_atr = 0.0010

    c1 = make_candle(0, 1.1000, 1.1010, 1.0990, 1.1005)
    c2 = make_candle(1, 1.1010, 1.1025, 1.1008, 1.1020)
    c3 = make_candle(2, 1.1025, 1.1040, 1.1018, 1.1035)

    engine.update(c1, state)
    engine.update(c2, state)
    engine.update(c3, state)

    if state.fair_value_gaps:
        fvg = state.fair_value_gaps[0]
        original_low  = fvg.gap_low
        original_high = fvg.gap_high

        # Feed more candles — boundaries must not change
        for i in range(4, 10):
            c = make_candle(i, 1.1035 + i*0.0001, 1.1040 + i*0.0001,
                            1.1030 + i*0.0001, 1.1038 + i*0.0001)
            engine.update(c, state)

        assert fvg.gap_low  == original_low,  "FVG low was retroactively modified!"
        assert fvg.gap_high == original_high, "FVG high was retroactively modified!"
        print(f"  FVG boundaries immutable: [{original_low}, {original_high}] ✓")


# ── BOS/CHoCH Tests ───────────────────────────────────────────────────────────

def test_bos_requires_close_not_wick():
    """BOS must be triggered by CLOSE beyond level, not wick."""
    engine = BOSCHoCHEngine()
    state = MarketState()
    state.current_atr = 0.0010
    state.structure = StructureState.BULLISH

    from core.state import SwingLevel
    state.last_confirmed_swing_high = SwingLevel(
        price=1.1020, timestamp=BASE_TIME, is_high=True
    )

    # Wick breaks above but close is below — should NOT trigger BOS
    wick_break = make_candle(1, 1.1010, 1.1025, 1.1008, 1.1015)  # close < 1.1020
    events = engine.update(wick_break, state)
    assert len(events) == 0, "BOS fired on wick-only break!"

    # Close breaks above — should trigger BOS
    close_break = make_candle(2, 1.1015, 1.1035, 1.1013, 1.1032)
    events = engine.update(close_break, state)
    assert len(events) == 1
    assert events[0].event_type == EventType.BOS_UP
    print(f"  BOS correctly requires close confirmation: {events[0]}")


# ── Order Block Tests ─────────────────────────────────────────────────────────

def test_ob_created_after_bos_only():
    """OB should only be created AFTER a confirmed BOS/CHoCH event."""
    from core.state import StructureEvent, EventType
    engine = OrderBlockEngine()
    state = MarketState()
    state.current_atr = 0.0010

    # Feed candles without any events — no OB should form
    candles = [
        make_candle(i, 1.1000 + i*0.0001, 1.1010 + i*0.0001,
                    1.0990 + i*0.0001, 1.1005 + i*0.0001)
        for i in range(10)
    ]
    for c in candles:
        new_obs = engine.update(c, state, [])
        assert len(new_obs) == 0, "OB created without a BOS event!"

    # Pre-fill buffer with a clearly bearish candle (will become the OB)
    # We feed it WITHOUT an event so it lands in the buffer first
    bearish = make_candle(10, 1.1010, 1.1012, 1.0993, 1.0997)  # bearish, strong body
    state.current_atr = 0.0010
    engine.update(bearish, state, [])  # no event — just fills buffer

    # Now fire a BOS_UP event on the NEXT candle (displacement candle)
    bos_event = StructureEvent(
        event_type=EventType.BOS_UP,
        price=1.1025,
        timestamp=BASE_TIME + timedelta(minutes=15 * 11),
        atr=0.0010,
    )
    displacement = make_candle(11, 1.1000, 1.1030, 1.0999, 1.1025)  # bullish displacement
    new_obs = engine.update(displacement, state, [bos_event])

    assert len(new_obs) == 1
    assert new_obs[0].is_bullish
    assert new_obs[0].active
    print(f"  OB created after BOS: {new_obs[0]}")

def test_ob_invalidation():
    """OB must be invalidated when price closes fully through it."""
    from core.state import StructureEvent, EventType
    engine = OrderBlockEngine()
    state = MarketState()
    state.current_atr = 0.0010

    # Create a bearish OB manually in state
    from core.state import OrderBlock
    ob = OrderBlock(
        zone_high=1.1020, zone_low=1.1010,
        timestamp=BASE_TIME, is_bullish=False, active=True, id="test"
    )
    state.order_blocks.append(ob)

    # Close above the OB zone → should invalidate bearish OB
    c = make_candle(0, 1.1015, 1.1030, 1.1013, 1.1025)  # close=1.1025 > zone_high=1.1020
    engine.update(c, state, [])

    assert not ob.active, "Bearish OB was not invalidated after close through zone!"
    print(f"  OB invalidation on close-through: ✓")


# ── Liquidity Tests ───────────────────────────────────────────────────────────

def test_liquidity_sweep_requires_close_inside():
    """Sweep must have wick through level AND close back inside."""
    engine = LiquidityEngine()
    state = MarketState()
    state.current_atr = 0.0010

    # Inject a buy-side liquidity level
    from core.state import LiquidityLevel
    state.liquidity_levels.append(LiquidityLevel(
        price=1.1020, timestamp=BASE_TIME, is_buy_side=True, swept=False
    ))

    # Candle wicks above but CLOSES above too — NOT a sweep
    no_sweep = make_candle(0, 1.1015, 1.1025, 1.1013, 1.1022)  # close > 1.1020
    events = engine.update(no_sweep, state)
    assert len(events) == 0, "False sweep detected (close stayed above level)!"

    # Candle wicks above AND closes BELOW → valid sweep
    state.liquidity_levels[0].swept = False  # reset
    real_sweep = make_candle(1, 1.1015, 1.1025, 1.1012, 1.1017)  # close < 1.1020
    events = engine.update(real_sweep, state)
    assert len(events) == 1
    assert events[0].event_type == EventType.LIQUIDITY_SWEEP_BUY_SIDE
    print(f"  Liquidity sweep correctly requires close-back: {events[0]}")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all():
    tests = [
        ("ATR warmup",                   test_atr_warmup),
        ("ATR no lookahead",             test_atr_no_lookahead),
        ("Candle properties",            test_candle_properties),
        ("FVG bullish detection",        test_fvg_bullish_detection),
        ("FVG bearish detection",        test_fvg_bearish_detection),
        ("FVG mitigation cycle",         test_fvg_mitigation),
        ("FVG no retroactive resize",    test_fvg_no_retroactive_resize),
        ("BOS requires close not wick",  test_bos_requires_close_not_wick),
        ("OB created after BOS only",    test_ob_created_after_bos_only),
        ("OB invalidation",              test_ob_invalidation),
        ("Liquidity sweep close-back",   test_liquidity_sweep_requires_close_inside),
    ]

    passed = 0
    failed = 0
    print("\n" + "=" * 60)
    print("  SMC ENGINE TEST SUITE")
    print("=" * 60)

    for name, fn in tests:
        try:
            print(f"\n▶ {name}")
            fn()
            print(f"  ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"  ❌ FAIL: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}\n")
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
