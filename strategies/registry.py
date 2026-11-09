"""Lookup table for strategies used by paper trading and backtests."""

from collections.abc import Callable

import pandas as pd

from strategies.ema_crossover import generate_signals as ema_crossover

Strategy = Callable[[pd.Series], pd.Series]

STRATEGIES: dict[str, Strategy] = {
    "ema_crossover": ema_crossover,
}


def available_strategies() -> tuple[str, ...]:
    return tuple(STRATEGIES)


def get_strategy(name: str) -> Strategy:
    try:
        return STRATEGIES[name]
    except KeyError as error:
        available = ", ".join(available_strategies())
        raise ValueError(f"Unknown strategy {name!r}. Available strategies: {available}") from error
