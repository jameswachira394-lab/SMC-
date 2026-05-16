# utils/session.py
# ─────────────────────────────────────────────────────────────────────────────
# Trading session filter. London and New York sessions only (UTC times).
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime, time
from config.settings import (
    LONDON_OPEN_HOUR, LONDON_CLOSE_HOUR,
    NY_OPEN_HOUR, NY_CLOSE_HOUR,
    SESSION_FILTER_ENABLED,
)


LONDON_OPEN  = time(LONDON_OPEN_HOUR, 0)
LONDON_CLOSE = time(LONDON_CLOSE_HOUR, 0)
NY_OPEN      = time(NY_OPEN_HOUR, 0)
NY_CLOSE     = time(NY_CLOSE_HOUR, 0)


def is_london_session(ts: datetime) -> bool:
    t = ts.time()
    return LONDON_OPEN <= t < LONDON_CLOSE


def is_ny_session(ts: datetime) -> bool:
    t = ts.time()
    return NY_OPEN <= t < NY_CLOSE


def is_tradeable_session(ts: datetime) -> bool:
    """
    Returns True if timestamp falls within London or New York session (UTC).
    If session filter is disabled in settings, always returns True.
    """
    if not SESSION_FILTER_ENABLED:
        return True
    return is_london_session(ts) or is_ny_session(ts)


def session_name(ts: datetime) -> str:
    if is_london_session(ts) and is_ny_session(ts):
        return "London/NY Overlap"
    if is_london_session(ts):
        return "London"
    if is_ny_session(ts):
        return "New York"
    return "Off-Session"
