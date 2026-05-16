# SMC Trading System — Non-Repainting, Event-Driven

A deterministic Smart Money Concepts (SMC) trading system that replicates
BOS, CHoCH, Order Blocks, FVGs, and Liquidity Sweeps **without**:
- future-candle dependency
- pivot-based repainting
- retrospective zone construction
- visually deceptive structure labeling

---

## Core Design Rule

> "If the market stopped at the current candle, the system must still produce the same output."

All signals are confirmed by **candle close only**. No lookahead. No repainting.

---

## Architecture

```
smc_trading_system/
│
├── config/
│   └── settings.py              # ATR periods, thresholds, session times, risk params
│
├── core/
│   ├── candle.py                # OHLCV candle model
│   └── state.py                 # Global market state container
│
├── engines/
│   ├── structure_engine.py      # Module 1: Real-time swing detection (no pivots)
│   ├── bos_choch_engine.py      # Module 2: BOS / CHoCH event engine
│   ├── liquidity_engine.py      # Module 3: Liquidity sweep detection
│   ├── orderblock_engine.py     # Module 4: Forward-only OB construction
│   ├── fvg_engine.py            # Module 5: Fair Value Gap (strict 3-candle)
│   ├── entry_engine.py          # Module 6: Confluence entry logic
│   └── exit_engine.py           # Module 7: Exit / TP / SL engine
│
├── backtest/
│   ├── simulator.py             # Candle-by-candle backtest simulator
│   ├── risk_manager.py          # Module 8: Risk management constraints
│   └── reporter.py              # Backtest output: win rate, expectancy, drawdown
│
├── utils/
│   ├── atr.py                   # ATR calculator (real-time, no lookahead)
│   └── session.py               # London / New York session filter
│
├── tests/
│   └── test_engines.py          # Unit tests for all engines
│
├── main.py                      # Entry point: run backtest or live feed
└── README.md
```

---

## Event Flow

```
New Candle Close
       │
       ▼
[ATR Update] ──────────────────────────────────────────────┐
       │                                                   │
       ▼                                                   │
[Structure Engine]                                         │
  • Update rolling swing high/low                         │
  • Confirm swing only on close + displacement            │
       │                                                   │
       ▼                                                   │
[BOS/CHoCH Engine]                                        │
  • BOS_UP / BOS_DOWN / CHOCH_UP / CHOCH_DOWN            │
       │                                                   │
       ▼                                                   │
[Liquidity Engine]                                        │
  • Detect equal highs/lows within ATR tolerance          │
  • Confirm sweep: wick takes level + close inside        │
       │                                                   │
       ▼                                                   │
[Order Block Engine]                                      │
  • On BOS/CHoCH: store last opposite candle before       │
    displacement as immutable OB zone                     │
       │                                                   │
       ▼                                                   │
[FVG Engine]                                              │
  • Check 3-candle model on every close                   │
  • Store new FVGs immediately; track mitigation          │
       │                                                   │
       ▼                                                   │
[Entry Engine]                                            │
  • Require ALL confluence conditions                     │
  • Session filter (London / NY only)                     │
       │                                                   │
       ▼                                                   │
[Exit Engine]                                             │
  • TP = opposing liquidity / swing                       │
  • SL = beyond OB or sweep origin                        │
       │                                                   │
       ▼                                                   │
[Risk Manager]                                            │
  • Size position; enforce daily loss / consec. limits    │
       │                                                   │
       ▼                                                   │
[Trade Log / Backtest Reporter]
```

---

## Modules Summary

| # | Module | No Repainting? | Confirmed by Close? |
|---|--------|:--------------:|:-------------------:|
| 1 | Structure Engine | ✅ | ✅ |
| 2 | BOS/CHoCH Engine | ✅ | ✅ |
| 3 | Liquidity Engine | ✅ | ✅ |
| 4 | Order Block Engine | ✅ | ✅ |
| 5 | FVG Engine | ✅ | ✅ |
| 6 | Entry Engine | ✅ | ✅ |
| 7 | Exit Engine | ✅ | ✅ |
| 8 | Risk Manager | ✅ | ✅ |

---

## Usage

```bash
# Install dependencies
pip install pandas numpy

# Run backtest on sample/custom OHLCV CSV
python main.py --data data/sample.csv --timeframe 15m

# Run with HTF bias
python main.py --data data/eurusd_15m.csv --htf data/eurusd_1h.csv
```

Output: `output/backtest_report.json` + `output/trades.csv`
