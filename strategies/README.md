# Strategies

Each strategy is a separate Python module in this folder. A strategy module
should provide a `generate_signals(close)` function that accepts a pandas
Series of closing prices and returns a same-index Series of directions:

- `1`: bullish
- `-1`: bearish
- `0`: neutral

To add a strategy:

1. Add a module, for example `strategies/rsi_reversal.py`, implementing
   `generate_signals(close)`.
2. Import that function in `strategies/registry.py` and add it to
   `STRATEGIES` with a command-line name.
3. Run it in paper mode or a historical backtest:

   ```powershell
   .\venv\Scripts\python.exe run_paper.py --strategy rsi_reversal
   .\venv\Scripts\python.exe backtest.py --strategy rsi_reversal
   ```

The paper runner maps bullish signals to calls, bearish signals to puts, and
neutral signals to no new position. The index backtest uses bullish signals
for long index exposure and bearish signals for short index exposure; its
short leg is a directional proxy for the paper runner's long-put position, not
an options-writing strategy.

Paper options are buy-to-open only: `BUY` creates a long call (`CE`) or long
put (`PE`). A `SELL` is only a square-off of an existing bought position; it
cannot open a short option. The paper portfolio allows at most one open put
and one open call, and the runner stops opening positions at the configured
square-off time. Use `run_paper.py --loop` to keep running cycles and perform
the configured end-of-day square-off automatically while the process remains
running. A later run also forces a safety exit for positions left in an older
day's state. Without `--loop`, run a cycle after square-off to close any
remaining positions.
