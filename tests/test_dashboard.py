import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import dashboard


class DashboardDataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.trades_file = Path(self.temp_dir.name) / "trades.csv"
        self.state_file = Path(self.temp_dir.name) / "state.json"
        self.today = date(2026, 11, 10)
        self.files = (
            patch.object(dashboard, "TRADES_FILE", self.trades_file),
            patch.object(dashboard, "STATE_FILE", self.state_file),
        )
        for file_patch in self.files:
            file_patch.start()
            self.addCleanup(file_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def write_trades(self, rows):
        with self.trades_file.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["time", "action", "symbol", "qty", "price", "pnl_net", "reason", "strategy"])
            writer.writerows(rows)

    def write_state(self, position):
        self.state_file.write_text(json.dumps({"position": position}), encoding="utf-8")

    def test_closed_position_drives_realized_summary_and_intraday_curve(self):
        self.write_trades([
            ["2026-11-10T09:35:00", "BUY", "NIFTY-25000-CE", 10, 300, "", "signal"],
            ["2026-11-10T10:15:00", "SELL", "NIFTY-25000-CE", 10, 350, 420, "signal reversed"],
        ])
        self.write_state(None)

        data = dashboard.load_dashboard_data(self.today)

        self.assertEqual(data["realized_pnl"], 420)
        self.assertEqual(data["trade_count"], 1)
        self.assertEqual(data["closed_positions"], 1)
        self.assertEqual(data["wins"], 1)
        self.assertEqual(data["positions"][0]["status"], "CLOSED")
        self.assertEqual(data["positions"][0]["entry_time"], "09:35:00")
        self.assertEqual(data["positions"][0]["exit_time"], "10:15:00")
        self.assertEqual(data["positions"][0]["pnl_pct"], 14)
        self.assertEqual(data["pnl_curve"], [{"time": "10:15:00", "pnl": 420}])
        self.assertEqual(data["strategy_pnl"][0]["name"], "Unattributed")

    def test_dashboard_attributes_position_from_trade_log(self):
        self.write_trades([
            ["2026-11-10T09:35:00", "BUY", "NIFTY-25000-CE", 10, 300, "", "signal", "ema_crossover"],
            ["2026-11-10T10:15:00", "SELL", "NIFTY-25000-CE", 10, 350, 420, "signal reversed", "ema_crossover"],
        ])
        self.write_state(None)

        data = dashboard.load_dashboard_data(self.today)

        self.assertEqual(data["positions"][0]["strategy"], "ema_crossover")
        self.assertEqual(data["strategy_pnl"][0]["name"], "ema_crossover")

    def test_open_position_shows_available_stop_but_not_fake_live_pnl(self):
        position = {
            "symbol": "NIFTY-25000-PE",
            "type": "PE",
            "strike": 25000,
            "expiry": "2026-11-17T15:30:00",
            "qty": 10,
            "entry_price": 300,
        }
        self.write_trades([
            ["2026-11-10T09:40:00", "BUY", position["symbol"], 10, 300, "", "signal"],
        ])
        self.write_state(position)

        data = dashboard.load_dashboard_data(self.today)

        self.assertFalse(data["live_pnl_available"])
        self.assertEqual(data["open_positions"], 1)
        self.assertEqual(data["positions"][0]["status"], "OPEN")
        self.assertIsNone(data["positions"][0]["current_price"])
        self.assertIsNone(data["positions"][0]["pnl"])
        self.assertEqual(data["positions"][0]["stop_loss_price"], 100)
        self.assertIsNone(data["positions"][0]["target_price"])
        self.assertEqual(data["positions"][0]["entry_time"], "09:40:00")

    def test_state_only_position_is_included_without_invented_entry_time(self):
        position = {
            "symbol": "NIFTY-25000-CE",
            "type": "CE",
            "strike": 25000,
            "expiry": "2026-11-17T15:30:00",
            "qty": 10,
            "entry_price": 300,
        }
        self.write_state(position)

        data = dashboard.load_dashboard_data(self.today)

        self.assertEqual(len(data["positions"]), 1)
        self.assertIsNone(data["positions"][0]["entry_time"])
        self.assertEqual(data["positions"][0]["status"], "OPEN")

    def test_dashboard_includes_all_three_long_positions(self):
        open_positions = [
            {"symbol": "NIFTY-25000-PE", "type": "PE", "strike": 25000,
             "expiry": "2026-11-17T15:30:00", "qty": 10, "entry_price": 100},
            {"symbol": "NIFTY-25100-CE", "type": "CE", "strike": 25100,
             "expiry": "2026-11-17T15:30:00", "qty": 10, "entry_price": 110},
            {"symbol": "NIFTY-25200-CE", "type": "CE", "strike": 25200,
             "expiry": "2026-11-17T15:30:00", "qty": 10, "entry_price": 120},
        ]
        self.write_state(None)
        self.state_file.write_text(json.dumps({"positions": open_positions}), encoding="utf-8")

        data = dashboard.load_dashboard_data(self.today)

        self.assertEqual(data["open_positions"], 3)
        self.assertEqual([position["type"] for position in data["positions"]], ["PE", "CE", "CE"])
        self.assertTrue(all(position["status"] == "OPEN" for position in data["positions"]))

    def test_previous_day_position_is_flagged_for_safety_exit(self):
        position = {
            "symbol": "NIFTY-25000-PE",
            "type": "PE",
            "strike": 25000,
            "expiry": "2026-11-17T15:30:00",
            "qty": 10,
            "entry_price": 100,
        }
        self.state_file.write_text(
            json.dumps({"positions": [position], "day": "2026-11-09"}),
            encoding="utf-8",
        )

        data = dashboard.load_dashboard_data(self.today)

        self.assertEqual(data["stale_positions"], 1)
        self.assertEqual(data["open_positions"], 1)
        self.assertEqual(data["positions"][0]["status"], "STALE")


if __name__ == "__main__":
    unittest.main()
