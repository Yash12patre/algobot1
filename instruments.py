import io
from datetime import date
from pathlib import Path

import requests
import pandas as pd
import yfinance as yf

# Dhan's public instrument file (verify the current URL in the DhanHQ docs)
SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
CACHE_FILE = Path(__file__).resolve().parent / ".cache" / "scrip_master.csv"

def load_master() -> pd.DataFrame:
    if CACHE_FILE.exists() and date.fromtimestamp(CACHE_FILE.stat().st_mtime) == date.today():
        return pd.read_csv(CACHE_FILE, low_memory=False)

    r = requests.get(SCRIP_MASTER_URL, timeout=60)
    r.raise_for_status()
    master = pd.read_csv(io.StringIO(r.text), low_memory=False)
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(CACHE_FILE, index=False)
    return master

def nifty_spot(history=None) -> float:
    # Delayed, fine for paper mode. Switch to Dhan's Data API for live use.
    if history is None:
        history = yf.Ticker("^NSEI").history(period="1d")
    return float(history["Close"].dropna().iloc[-1])

def find_option(master, expiry_rank=0, option_type="CE",
                strikes_from_atm=0, min_days=3, spot=None):
    df = master[
        (master["SEM_EXM_EXCH_ID"] == "NSE")
        & (master["SEM_INSTRUMENT_NAME"] == "OPTIDX")
        & (master["SEM_TRADING_SYMBOL"].str.startswith("NIFTY-"))
        & (master["SEM_OPTION_TYPE"] == option_type)
    ].copy()
    df["SEM_EXPIRY_DATE"] = pd.to_datetime(df["SEM_EXPIRY_DATE"])
    cutoff = pd.Timestamp.today().normalize() + pd.Timedelta(days=min_days)
    df = df[df["SEM_EXPIRY_DATE"].dt.normalize() >= cutoff]

    expiry = sorted(df["SEM_EXPIRY_DATE"].unique())[expiry_rank]
    df = df[df["SEM_EXPIRY_DATE"] == expiry]

    if spot is None:
        spot = nifty_spot()
    atm = round(spot / 50) * 50
    target = atm + strikes_from_atm * 50
    row = df.iloc[(df["SEM_STRIKE_PRICE"] - target).abs().argsort().iloc[0]]
    return row, spot

if __name__ == "__main__":
    m = load_master()
    print(m.columns.tolist())          # confirm column names first
    row, spot = find_option(m, expiry_rank=0, option_type="CE")
    print(f"Spot: {spot:.0f}")
    print(row[["SEM_SMST_SECURITY_ID", "SEM_TRADING_SYMBOL",
               "SEM_EXPIRY_DATE", "SEM_STRIKE_PRICE", "SEM_LOT_UNITS"]])