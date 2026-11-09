"""20/50 EMA trend strategy."""

import pandas as pd

FAST_PERIOD = 20
SLOW_PERIOD = 50
NEUTRAL_BAND = 0.001


def generate_signals(close: pd.Series) -> pd.Series:
    """Return trend direction after EMA warm-up and neutral-band filtering."""
    fast = close.ewm(span=FAST_PERIOD, adjust=False).mean()
    slow = close.ewm(span=SLOW_PERIOD, adjust=False).mean()
    signals = (fast > slow).astype(int) - (fast < slow).astype(int)
    relative_spread = (fast - slow).abs().div(close.where(close != 0))
    signals = signals.mask((relative_spread < NEUTRAL_BAND) | close.eq(0), 0)
    signals.iloc[:SLOW_PERIOD] = 0
    return signals
