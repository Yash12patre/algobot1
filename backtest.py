import argparse

import yfinance as yf
import pandas as pd

from strategies import available_strategies, get_strategy

SYMBOL = "^NSEI"
COST_PER_TRADE = 0.001   # 0.1% per buy or sell; placeholder, adjust to your real charges


def build_backtest(close, signals):
    df = close.to_frame("Close").copy()
    direction = signals.apply(lambda value: int(value > 0) - int(value < 0))
    df["position"] = direction.shift(1).fillna(0)
    df["ret"] = df["Close"].pct_change().fillna(0)
    df["trade"] = df["position"].diff().abs().fillna(0)
    df["strat_ret"] = df["position"] * df["ret"] - df["trade"] * COST_PER_TRADE
    df["equity"] = (1 + df["strat_ret"]).cumprod()
    df["buy_hold"] = (1 + df["ret"]).cumprod()
    return df


def main():
    parser = argparse.ArgumentParser(description="Backtest a strategy on NIFTY history.")
    parser.add_argument(
        "--strategy",
        choices=available_strategies(),
        default="ema_crossover",
        help="strategy to backtest",
    )
    args = parser.parse_args()

    df = yf.Ticker(SYMBOL).history(period="5y", interval="1d")[["Close"]].dropna()
    signals = get_strategy(args.strategy)(df["Close"])
    df = build_backtest(df["Close"], signals)

    years = (df.index[-1] - df.index[0]).days / 365.25
    cagr = df["equity"].iloc[-1] ** (1 / years) - 1
    max_dd = (df["equity"] / df["equity"].cummax() - 1).min()
    buy_hold_max_dd = (df["buy_hold"] / df["buy_hold"].cummax() - 1).min()
    fraction_in_market = df["position"].ne(0).mean()

    print(f"Symbol:           {SYMBOL}")
    print(f"Strategy:         {args.strategy}")
    print(f"Strategy return:  {df['equity'].iloc[-1] - 1:.1%}  (CAGR {cagr:.1%})")
    print(f"Buy & hold:       {df['buy_hold'].iloc[-1] - 1:.1%}")
    print(f"Max drawdown:     {max_dd:.1%}")
    print(f"Buy & hold max DD: {buy_hold_max_dd:.1%}")
    print(f"Fraction in market: {fraction_in_market:.1%}")
    print(f"Number of trades: {int(df['trade'].sum())}")


if __name__ == "__main__":
    main()