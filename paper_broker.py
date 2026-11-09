import csv
import json
import os
from datetime import datetime
import config

STATE_FILE = "paper_state.json"
LOG_FILE = "paper_trades.csv"
TRADE_HEADER = ["time", "action", "symbol", "qty", "price", "pnl_net", "reason", "strategy"]

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
    else:
        state = {"positions": [], "day": None, "day_pnl": 0.0, "orders_today": 0}
    _ensure_positions(state)
    return state

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2)

def _roll_day(s, today=None):
    today = today or datetime.now().date().isoformat()
    if s["day"] != today:
        s.update(day=today, day_pnl=0.0, orders_today=0)


def roll_day(s, today=None):
    _roll_day(s, today)


def _ensure_positions(s):
    positions = s.get("positions")
    if positions is None:
        legacy_position = s.pop("position", None)
        positions = [legacy_position] if legacy_position else []
        s["positions"] = positions
    elif not isinstance(positions, list):
        raise ValueError("Paper state positions must be a list.")
    s.pop("position", None)
    return positions


def get_positions(s):
    return _ensure_positions(s)


def can_trade(s):
    _roll_day(s)
    if s["day_pnl"] <= -config.MAX_LOSS_PER_DAY:
        return False, "daily loss limit hit"
    if s["orders_today"] >= config.MAX_ORDERS_PER_DAY:
        return False, "max orders per day hit"
    if s.get("no_entry_day") == s["day"]:
        return False, "same-day re-entry cooldown after exit"
    return True, ""

def _log(row):
    log_path = os.path.abspath(LOG_FILE)
    old_path = os.path.join(os.path.dirname(log_path), "paper_trades.old.csv")
    if os.path.exists(log_path) and os.path.getsize(log_path):
        with open(log_path, newline="", encoding="utf-8") as file:
            header = next(csv.reader(file), [])
        if header and "strategy" not in header:
            if os.path.exists(old_path):
                raise FileExistsError(
                    f"Cannot migrate {LOG_FILE}: backup already exists at {old_path}."
                )
            os.replace(log_path, old_path)
        elif header and header != TRADE_HEADER:
            raise ValueError(f"Unexpected paper trade CSV header in {LOG_FILE}: {header!r}")

    new = not os.path.exists(log_path) or os.path.getsize(log_path) == 0
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(TRADE_HEADER)
        w.writerow(row)


def open_position(s, symbol, security_id, opt_type, strike, expiry, lot_units, premium, strategy):
    if opt_type not in ("CE", "PE"):
        raise ValueError("Only long CE and PE positions can be opened.")
    allowed, reason = can_trade(s)
    if not allowed:
        raise ValueError(f"Cannot open position: {reason}.")
    positions = _ensure_positions(s)
    type_limit = config.MAX_OPEN_CALLS if opt_type == "CE" else config.MAX_OPEN_PUTS
    if sum(position["type"] == opt_type for position in positions) >= type_limit:
        raise ValueError(f"Maximum open {opt_type} buying positions reached.")

    fill = round(premium * (1 + config.SLIPPAGE_PCT), 2)
    qty = int(lot_units) * config.MAX_LOTS
    position = {
        "symbol": symbol,
        "security_id": int(security_id),
        "type": opt_type,
        "strike": float(strike),
        "expiry": expiry.isoformat(),
        "qty": qty,
        "entry_price": fill,
        "entry_time": datetime.now().isoformat(timespec="seconds"),
        "strategy": strategy,
    }
    positions.append(position)
    s["orders_today"] += 1
    _log([
        datetime.now().isoformat(timespec="seconds"),
        "BUY",
        symbol,
        qty,
        fill,
        "",
        "signal",
        strategy,
    ])
    print(f"PAPER BUY {symbol} qty={qty} @ {fill}")
    return position


def close_position(s, position, premium, reason):
    positions = _ensure_positions(s)
    if position not in positions:
        raise ValueError("Cannot sell to close a position that is not open.")
    roll_day(s)
    p = position
    fill = round(premium * (1 - config.SLIPPAGE_PCT), 2)
    pnl = (fill - p["entry_price"]) * p["qty"] - 2 * config.PAPER_COST_PER_ORDER
    s["day_pnl"] += pnl
    s["orders_today"] += 1
    if reason in ("stop loss", "signal reversed", "signal off"):
        s["no_entry_day"] = s["day"]
    _log([datetime.now().isoformat(timespec="seconds"), "SELL", p["symbol"],
          p["qty"], fill, round(pnl, 2), reason, p.get("strategy", "")])
    print(f"PAPER SELL TO CLOSE {p['symbol']} @ {fill}  net P&L INR {pnl:,.0f}  ({reason})")
    positions.remove(p)