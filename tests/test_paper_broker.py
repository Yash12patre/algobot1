import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import paper_broker


class PaperBrokerPositionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.trades_file = Path(self.temp_dir.name) / "trades.csv"
        self.state_file = Path(self.temp_dir.name) / "state.json"
        self.patches = (
            patch.object(paper_broker, "LOG_FILE", str(self.trades_file)),
            patch.object(paper_broker, "STATE_FILE", str(self.state_file)),
        )
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.temp_dir.cleanup)
        self.state = {"positions": [], "orders_today": 0, "day_pnl": 0.0, "day": None}

    def open(self, opt_type):
        return paper_broker.open_position(
            self.state,
            f"NIFTY-25000-{opt_type}",
            123,
            opt_type,
            25000,
            datetime(2026, 11, 12, 15, 30),
            1,
            100,
            "ema_crossover",
        )

    def test_only_one_put_and_one_call_can_be_opened(self):
        put = self.open("PE")
        call = self.open("CE")

        with self.assertRaisesRegex(ValueError, "Maximum open CE"):
            self.open("CE")
        with self.assertRaisesRegex(ValueError, "Maximum open PE"):
            self.open("PE")

        self.assertEqual(paper_broker.get_positions(self.state), [put, call])

    def test_sell_action_requires_and_removes_an_open_bought_position(self):
        position = self.open("CE")
        paper_broker.close_position(self.state, position, 110, "intraday square-off")

        self.assertEqual(paper_broker.get_positions(self.state), [])
        with self.assertRaisesRegex(ValueError, "not open"):
            paper_broker.close_position(self.state, position, 110, "duplicate exit")

        with self.trades_file.open(newline="", encoding="utf-8") as file:
            trades = list(csv.DictReader(file))
        self.assertEqual([trade["action"] for trade in trades], ["BUY", "SELL"])
        self.assertEqual(trades[1]["reason"], "intraday square-off")

    def test_legacy_single_position_state_migrates_to_long_positions_list(self):
        legacy = {"symbol": "NIFTY-25000-PE", "type": "PE", "qty": 1}
        state = {"position": legacy, "day": "2026-11-10"}

        positions = paper_broker.get_positions(state)

        self.assertEqual(positions, [legacy])
        self.assertNotIn("position", state)
        self.assertEqual(state["day"], "2026-11-10")

    def test_invalid_option_type_cannot_be_opened(self):
        with self.assertRaisesRegex(ValueError, "Only long CE and PE"):
            self.open("FUT")


if __name__ == "__main__":
    unittest.main()
