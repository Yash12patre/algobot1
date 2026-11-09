import csv
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import backtest
import config
import paper_broker
import run_paper
from strategies.ema_crossover import NEUTRAL_BAND, SLOW_PERIOD, generate_signals


class PaperRequirementsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_file = Path(self.temp_dir.name) / "paper_trades.csv"
        self.state_file = Path(self.temp_dir.name) / "paper_state.json"
        self.patches = (
            patch.object(paper_broker, "LOG_FILE", str(self.log_file)),
            patch.object(paper_broker, "STATE_FILE", str(self.state_file)),
        )
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def open_position(self, state, opt_type="CE", strategy="ema_crossover"):
        return paper_broker.open_position(
            state,
            f"NIFTY-25000-{opt_type}",
            123,
            opt_type,
            25000,
            datetime.now() + timedelta(days=2),
            1,
            100,
            strategy,
        )

    def test_ema_warmup_bars_are_neutral(self):
        rising = pd.Series(range(100, 200), dtype=float)

        signals = generate_signals(rising)

        self.assertEqual(signals.iloc[:SLOW_PERIOD].tolist(), [0] * SLOW_PERIOD)
        self.assertNotEqual(signals.iloc[SLOW_PERIOD], 0)

    def test_neutral_band_filters_near_equal_emas(self):
        gentle_rise = pd.Series([100 + index * 0.001 for index in range(100)])

        signals = generate_signals(gentle_rise)

        self.assertEqual(NEUTRAL_BAND, 0.001)
        self.assertEqual(signals.iloc[SLOW_PERIOD:].tolist(), [0] * (len(signals) - SLOW_PERIOD))

    def test_backtest_shifts_signed_positions_and_charges_two_cost_units_on_flip(self):
        close = pd.Series([100.0, 101.0, 100.0])
        signals = pd.Series([1, -1, -1])

        result = backtest.build_backtest(close, signals)

        self.assertEqual(result["position"].tolist(), [0, 1, -1])
        self.assertEqual(result["trade"].tolist(), [0, 1, 2])
        expected_flip_return = (
            result["position"].iloc[2] * result["ret"].iloc[2]
            - 2 * backtest.COST_PER_TRADE
        )
        self.assertAlmostEqual(result["strat_ret"].iloc[2], expected_flip_return)

    def test_open_position_enforces_one_call_and_one_put_and_logs_strategy(self):
        state = {"positions": [], "day": None, "day_pnl": 0.0, "orders_today": 0}
        self.assertEqual(config.MAX_OPEN_CALLS, 1)
        self.assertEqual(config.MAX_OPEN_PUTS, 1)
        call = self.open_position(state, "CE", "test_strategy")
        put = self.open_position(state, "PE", "test_strategy")

        with self.assertRaisesRegex(ValueError, "Maximum open CE"):
            self.open_position(state, "CE")
        with self.assertRaisesRegex(ValueError, "Maximum open PE"):
            self.open_position(state, "PE")

        self.assertEqual(call["strategy"], "test_strategy")
        self.assertEqual(put["strategy"], "test_strategy")
        with self.log_file.open(newline="", encoding="utf-8") as file:
            trades = list(csv.DictReader(file))
        self.assertEqual([trade["strategy"] for trade in trades], ["test_strategy", "test_strategy"])

    def test_legacy_trade_log_is_backed_up_before_new_schema_is_written(self):
        self.log_file.write_text(
            "time,action,symbol,qty,price,pnl_net,reason\n"
            "2026-11-10T09:30:00,BUY,NIFTY-25000-CE,1,100,,signal\n",
            encoding="utf-8",
        )
        state = {"positions": [], "day": None, "day_pnl": 0.0, "orders_today": 0}

        self.open_position(state)

        backup = self.log_file.with_name("paper_trades.old.csv")
        self.assertTrue(backup.exists())
        with self.log_file.open(newline="", encoding="utf-8") as file:
            header = next(csv.reader(file))
        self.assertIn("strategy", header)

    def test_stop_loss_sets_same_day_reentry_cooldown(self):
        state = {"positions": [], "day": None, "day_pnl": 0.0, "orders_today": 0}
        position = self.open_position(state)

        paper_broker.close_position(state, position, 50, "stop loss")

        self.assertEqual(state["no_entry_day"], datetime.now().date().isoformat())
        can_trade, reason = paper_broker.can_trade(state)
        self.assertFalse(can_trade)
        self.assertIn("cooldown", reason)

    def test_signal_uses_only_completed_daily_bars(self):
        today = datetime.now().date()
        history = pd.DataFrame(
            {"Close": [100.0, 200.0]},
            index=pd.DatetimeIndex([today - timedelta(days=1), today]),
        )
        received = []

        with patch.object(
            run_paper,
            "get_strategy",
            return_value=lambda close: received.append(close.copy()) or pd.Series([1], index=close.index),
        ):
            run_paper.signal("ema_crossover", history, today)

        self.assertEqual(received[0].tolist(), [100.0])

    def test_traded_today_requires_latest_daily_bar_date_to_match(self):
        today = datetime.now().date()
        current_bar = pd.DataFrame(
            {"Close": [100.0]},
            index=pd.DatetimeIndex([today]),
        )
        previous_bar = pd.DataFrame(
            {"Close": [100.0]},
            index=pd.DatetimeIndex([today - timedelta(days=1)]),
        )

        self.assertTrue(run_paper.traded_today(current_bar, today))
        self.assertFalse(run_paper.traded_today(previous_bar, today))

    def test_stale_exit_books_pnl_to_current_day(self):
        now = datetime.now()
        position = {
            "symbol": "NIFTY-25000-PE",
            "security_id": 123,
            "type": "PE",
            "strike": 25000,
            "expiry": (now + timedelta(days=2)).isoformat(),
            "qty": 10,
            "entry_price": 100.0,
            "strategy": "test_strategy",
        }
        state = {
            "positions": [position],
            "day": (now.date() - timedelta(days=1)).isoformat(),
            "day_pnl": 1234.0,
            "orders_today": 4,
        }
        history = pd.DataFrame(
            {"Close": [25000.0]},
            index=pd.DatetimeIndex([now.date()]),
        )
        with (
            patch.object(run_paper, "datetime") as clock,
            patch.object(run_paper.pb, "load_state", return_value=state),
            patch.object(run_paper.pb, "save_state"),
            patch.object(run_paper, "india_vix", return_value=0.15),
            patch.object(run_paper, "nifty_spot", return_value=25000),
            patch.object(run_paper, "bs_price", return_value=200),
        ):
            clock.now.return_value = now
            clock.fromisoformat = datetime.fromisoformat
            run_paper.run_cycle("test_strategy", history=history, now=now)

        expected_pnl = (200 * (1 - config.SLIPPAGE_PCT) - position["entry_price"]) * position["qty"]
        expected_pnl -= 2 * config.PAPER_COST_PER_ORDER
        self.assertEqual(state["day"], now.date().isoformat())
        self.assertEqual(state["day_pnl"], round(expected_pnl, 2))
        self.assertEqual(state["orders_today"], 1)
        self.assertEqual(state["positions"], [])


if __name__ == "__main__":
    unittest.main()
