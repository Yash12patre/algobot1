import unittest

import pandas as pd

from strategies import available_strategies, get_strategy


class StrategyTests(unittest.TestCase):
    def test_ema_crossover_returns_expected_directions(self):
        rising = pd.Series(range(100, 200), dtype=float)
        falling = pd.Series(range(200, 100, -1), dtype=float)
        flat = pd.Series([100.0] * 60)

        self.assertEqual(get_strategy("ema_crossover")(rising).iloc[-1], 1)
        self.assertEqual(get_strategy("ema_crossover")(falling).iloc[-1], -1)
        self.assertEqual(get_strategy("ema_crossover")(flat).iloc[-1], 0)

    def test_registry_lists_ema_crossover(self):
        self.assertIn("ema_crossover", available_strategies())


if __name__ == "__main__":
    unittest.main()
