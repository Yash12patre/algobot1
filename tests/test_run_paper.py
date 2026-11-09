import contextlib
import io
import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd

import run_paper


class FixedDateTime:
    current = datetime(2026, 11, 10, 10, 0)

    @classmethod
    def now(cls):
        return cls.current

    @staticmethod
    def fromisoformat(value):
        return datetime.fromisoformat(value)


class PaperRunnerTests(unittest.TestCase):
    def setUp(self):
        FixedDateTime.current = datetime(2026, 11, 10, 10, 0)

    def test_call_signal_fills_at_most_one_long_call_slot(self):
        state = {"positions": [], "day": "2026-11-10", "day_pnl": 0.0, "orders_today": 0}
        history = pd.DataFrame(
            {"Close": [25000]},
            index=pd.DatetimeIndex([FixedDateTime.current.date()]),
        )
        row = {
            "SEM_EXPIRY_DATE": pd.Timestamp("2026-11-12"),
            "SEM_STRIKE_PRICE": 25000,
            "SEM_TRADING_SYMBOL": "NIFTY-25000-CE",
            "SEM_SMST_SECURITY_ID": 123,
            "SEM_LOT_UNITS": 10,
        }
        with (
            patch.object(run_paper, "datetime", FixedDateTime),
            patch.object(run_paper.pb, "load_state", return_value=state),
            patch.object(run_paper.pb, "can_trade", return_value=(True, "")),
            patch.object(run_paper.pb, "save_state"),
            patch.object(run_paper.pb, "open_position") as open_position,
            patch.object(run_paper, "signal", return_value="CE"),
            patch.object(run_paper, "nifty_history", return_value=history) as history_loader,
            patch.object(run_paper, "india_vix", return_value=0.15),
            patch.object(run_paper, "load_master", return_value=object()),
            patch.object(run_paper, "find_option", return_value=(row, 25000)),
            patch.object(run_paper, "bs_price", return_value=100),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            run_paper.run_cycle("ema_crossover")

        open_position.assert_called_once()
        self.assertEqual(open_position.call_args.args[3], "CE")
        self.assertEqual(open_position.call_args.args[-1], "ema_crossover")
        history_loader.assert_called_once()

    def test_after_cutoff_runner_sells_only_to_close_open_positions(self):
        FixedDateTime.current = datetime(2026, 11, 10, 15, 16)
        position = {
            "symbol": "NIFTY-25000-PE",
            "type": "PE",
            "strike": 25000,
            "expiry": "2026-11-12T15:30:00",
            "qty": 10,
            "entry_price": 100,
        }
        state = {
            "positions": [position],
            "day": "2026-11-10",
            "day_pnl": 0.0,
            "orders_today": 1,
        }
        history = pd.DataFrame(
            {"Close": [25000]},
            index=pd.DatetimeIndex([FixedDateTime.current.date()]),
        )
        with (
            patch.object(run_paper, "datetime", FixedDateTime),
            patch.object(run_paper.pb, "load_state", return_value=state),
            patch.object(run_paper.pb, "can_trade", return_value=(True, "")),
            patch.object(run_paper.pb, "save_state"),
            patch.object(run_paper.pb, "close_position") as close_position,
            patch.object(run_paper, "signal", return_value="PE"),
            patch.object(run_paper, "nifty_history", return_value=history),
            patch.object(run_paper, "india_vix", return_value=0.15),
            patch.object(run_paper, "nifty_spot", return_value=25000),
            patch.object(run_paper, "bs_price", return_value=105),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            run_paper.run_cycle("ema_crossover")

        close_position.assert_called_once()
        self.assertIs(close_position.call_args.args[1], position)
        self.assertEqual(close_position.call_args.args[3], "intraday square-off")


if __name__ == "__main__":
    unittest.main()
