# core/candle.py
# ─────────────────────────────────────────────────────────────────────────────
# Immutable OHLCV candle model. All engines consume Candle objects.
# ─────────────────────────────────────────────────────────────────────────────
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    # ── Derived properties (computed from confirmed close, no lookahead) ───────

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def range_size(self) -> float:
        return self.high - self.low

    @property
    def body_ratio(self) -> float:
        """Body as fraction of total range. 1.0 = full marubozu."""
        if self.range_size == 0:
            return 0.0
        return self.body_size / self.range_size

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2

    def __repr__(self) -> str:
        direction = "▲" if self.is_bullish else "▼"
        return (
            f"Candle[{self.timestamp.strftime('%Y-%m-%d %H:%M')} "
            f"{direction} O:{self.open:.5f} H:{self.high:.5f} "
            f"L:{self.low:.5f} C:{self.close:.5f}]"
        )


def candles_from_dataframe(df) -> list:
    """
    Convert a pandas DataFrame with columns
    [timestamp/datetime, open, high, low, close, volume] into Candle list.
    Sorts ascending by timestamp.
    """
    candles = []
    for _, row in df.sort_values(df.columns[0]).iterrows():
        ts = row.iloc[0]
        if not isinstance(ts, datetime):
            ts = datetime.fromisoformat(str(ts))
        candles.append(Candle(
            timestamp=ts,
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row.get('volume', 0)),
        ))
    return candles
