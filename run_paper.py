import argparse
from datetime import datetime, time
import time as time_module

import pandas as pd
import yfinance as yf

import config
import paper_broker as pb
from instruments import find_option, load_master, nifty_spot
from pricing import bs_price
from strategies import available_strategies, get_strategy


def nifty_history():
    return yf.Ticker("^NSEI").history(period="1y", interval="1d")


def _bar_date(history):
    return pd.Timestamp(history.index[-1]).date()


def signal(strategy_name="ema_crossover", history=None, today=None):
    """Map the latest completed daily strategy direction to an option type."""
    history = nifty_history() if history is None else history
    close = history["Close"].dropna()
    today = today or datetime.now().date()
    if not close.empty and _bar_date(close) == today:
        close = close.iloc[:-1]
    if close.empty:
        return None
    direction = get_strategy(strategy_name)(close).iloc[-1]
    if direction > 0:
        return "CE"
    if direction < 0:
        return "PE"
    return None


def traded_today(history=None, today=None):
    """Return whether the latest daily NIFTY bar is dated today."""
    history = nifty_history() if history is None else history
    today = today or datetime.now().date()
    return not history.empty and _bar_date(history) == today


def india_vix():
    try:
        return float(yf.Ticker("^INDIAVIX").history(period="5d")["Close"].iloc[-1]) / 100
    except Exception:
        return 0.15


def run_cycle(strategy_name, history=None, now=None):
    state = pb.load_state()
    positions = pb.get_positions(state)
    now = now or datetime.now()
    today = now.date().isoformat()
    history = nifty_history() if history is None else history

    if positions and state.get("day") not in (None, today):
        print("Previous-day position found; forcing a safety exit before today's trading.")
        pb.roll_day(state, today)
        iv = india_vix()
        spot = nifty_spot(history)
        for position in positions[:]:
            expiry = datetime.fromisoformat(position["expiry"])
            premium = bs_price(spot, position["strike"], expiry, iv, position["type"])
            pb.close_position(state, position, premium, "previous-day safety square-off")
        pb.save_state(state)
        return

    can_open, reason = pb.can_trade(state)
    current_signal = signal(strategy_name, history, now.date())
    iv = india_vix()
    print(f"Signal: {current_signal or 'flat'} | IV used: {iv:.1%}")

    square_off = time.fromisoformat(config.SQUARE_OFF_BY)
    trade_start = time.fromisoformat(config.TRADE_START)
    square_off_due = now.time() >= square_off
    is_trading_day = now.weekday() < 5 and traded_today(history, now.date())
    closed_any = False

    if positions:
        spot = nifty_spot(history)
        for position in positions[:]:
            expiry = datetime.fromisoformat(position["expiry"])
            premium = bs_price(spot, position["strike"], expiry, iv, position["type"])
            unrealized = (premium - position["entry_price"]) * position["qty"]
            print(
                f"Holding bought {position['symbol']}: est. premium {premium:.2f}, "
                f"unrealised ₹{unrealized:,.0f}"
            )
            close_reason = None
            if square_off_due:
                close_reason = "intraday square-off"
            elif unrealized <= -config.MAX_LOSS_PER_TRADE:
                close_reason = "stop loss"
            elif current_signal != position["type"]:
                close_reason = "signal reversed" if current_signal else "signal off"
            elif (expiry - now).days < 1:
                close_reason = "near expiry"
            if close_reason:
                pb.close_position(state, position, premium, close_reason)
                closed_any = True

    if square_off_due:
        print("Square-off time reached; no new positions will be opened.")
    elif closed_any:
        print("Position closed; no replacement position will be opened this cycle.")
    elif now.weekday() >= 5:
        print("No new position: the market is closed for the weekend.")
    elif not is_trading_day:
        print("No new position: today is not confirmed as an NSE trading day.")
    elif not trade_start <= now.time() < square_off:
        print("No new position: outside the configured intraday entry window.")
    elif current_signal in ("CE", "PE") and can_open:
        positions = pb.get_positions(state)
        type_limit = config.MAX_OPEN_CALLS if current_signal == "CE" else config.MAX_OPEN_PUTS
        open_of_type = sum(position["type"] == current_signal for position in positions)
        available_orders = max(config.MAX_ORDERS_PER_DAY - state["orders_today"], 0)
        slots = min(type_limit - open_of_type, available_orders)
        if slots > 0:
            row, spot = find_option(
                load_master(), 0, current_signal, 0, config.MIN_DAYS_TO_EXPIRY, spot=nifty_spot(history)
            )
            expiry = pd.Timestamp(row["SEM_EXPIRY_DATE"]).normalize() + pd.Timedelta(
                hours=15, minutes=30
            )
            premium = bs_price(
                spot, row["SEM_STRIKE_PRICE"], expiry.to_pydatetime(), iv, current_signal
            )
            pb.open_position(
                state,
                row["SEM_TRADING_SYMBOL"],
                row["SEM_SMST_SECURITY_ID"],
                current_signal,
                row["SEM_STRIKE_PRICE"],
                expiry.to_pydatetime(),
                row["SEM_LOT_UNITS"],
                premium,
                strategy_name,
            )
        else:
            print(f"Maximum long {current_signal} positions already open ({type_limit}).")
    elif not can_open:
        print(f"Not trading: {reason}")
    else:
        print("No eligible long-option entry signal or outside the intraday trading window.")

    pb.save_state(state)


def main():
    parser = argparse.ArgumentParser(description="Run the long-options paper-trading strategy.")
    parser.add_argument(
        "--strategy",
        choices=available_strategies(),
        default="ema_crossover",
        help="strategy to use",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="keep checking during the session and square off at the configured cutoff",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="seconds between cycles when --loop is enabled",
    )
    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval must be a positive number of seconds")
    if not args.loop:
        run_cycle(args.strategy)
        return

    trade_start = time.fromisoformat(config.TRADE_START)
    square_off = time.fromisoformat(config.SQUARE_OFF_BY)
    if datetime.now().weekday() >= 5:
        history = nifty_history()
        run_cycle(args.strategy, history=history)
        print("Today is not an NSE trading day; exiting loop mode.")
        return
    while datetime.now().time() < trade_start:
        time_module.sleep(min(args.interval, 30))

    history = nifty_history()
    if not traded_today(history):
        run_cycle(args.strategy, history=history)
        print("Today is not an NSE trading day; exiting loop mode.")
        return

    run_cycle(args.strategy, history=history)
    while True:
        if datetime.now().time() >= square_off:
            break
        time_module.sleep(args.interval)
        run_cycle(args.strategy)


if __name__ == "__main__":
    main()
