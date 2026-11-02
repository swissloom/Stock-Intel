# Stock-Intel

A Python **quantitative strategy optimization & backtesting workstation**. It
evaluates multi-strategy execution, runs walk-forward analysis, dynamically
models transaction costs/slippage, filters for market regimes, simulates order
execution latency, tracks risk limits, and renders a self-contained HTML
report.

## Overview

The pipeline downloads historical OHLCV data for a **basket of liquid benchmark
tickers** (`AAPL, MSFT, NVDA, AMZN, GOOGL, META, SPY`), aligns them onto a
shared trading calendar, and sweeps a set of strategies and stop-loss levels
across rolling train/test windows (walk-forward) **for every ticker**. It
scores each configuration by `(CAGR% x ProfitFactor) / (MaxDrawdown + 1e-5)`,
disqualifies any configuration that breaks the max-drawdown limit, is
unprofitable (Total Return <= 0), or has a Profit Factor below **1.3**, and
writes the globally winning `(ticker, strategy, stop_loss)` configuration
(together with its cumulative-return / equity curve and a cross-ticker
leaderboard) to a self-contained HTML dashboard.

### Multi-factor alpha model (`MultiFactor`)

The flagship strategy combines three factors into a binary long/flat signal
(long only when **all** hold):

* **Momentum:** 126-day (6-month) rate-of-change minus the most recent 21-day
  rate-of-change (momentum net of the latest pullback) must be positive.
* **Trend filter:** price strictly above its 200-day SMA.
* **Volatility filter:** 21-day annualized volatility at or below 50% (extreme
  tail-risk regimes are excluded).

### Institutional risk engine

* **ATR/volume-scaled slippage:** transaction costs widen with relative ATR and
  with thin liquidity (volume below its 21-day average).
* **ATR position sizing & 3x-ATR trailing stop:** volatility-based sizing and a
  close-to-close trailing stop that forces flat on a 3x-ATR adverse excursion.
* **Performance guardrails:** any permutation with a negative Total Return or a
  Profit Factor below 1.3 is disqualified from selection.

### Multi-year regime window & multi-asset portfolio

The default backtest spans a **5+ year multi-year regime window**
(`2020-01-01` -> `2026-11-01`): the 2020 COVID crash, the 2022 bear market /
rate-hike cycle, and the 2023-2024 bull run. The 200-day SMA trend gate and the
21-day annualized-volatility gate are what carry the multi-factor model through
those regime shifts.

Rather than concentrating 100% in a single ticker, the allocator (
`allocate_portfolio` in `src/optimizer.py`) **ranks the universe, selects the
top-N qualifying assets** (default N=3, by the walk-forward objective after the
PF >= 1.3 / drawdown / profitability guardrails), and builds a diversified
portfolio:

* **Weighting:** `inverse_vol` (volatility parity - lower-vol assets get more
  capital) or `equal`, configurable under `portfolio.weighting`.
* **Compounded equity curve:** the portfolio uses the institutionally-correct
  **geometric** convention (`(1 + r).cumprod()`) with
  `CAGR = (Ending / Beginning) ** (1 / Years) - 1`. This is intentionally
  separate (in `src/portfolio.py`) from the per-ticker *additive* walk-forward
  engine, whose convention and test contract are left untouched.
* **Benchmark:** a compounded Buy & Hold of `portfolio.benchmark` (default
  `SPY`) or an `equal_weight` basket of the whole universe.

The dashboard adds a **Portfolio Summary Grid** (Portfolio CAGR, Total Return,
Sharpe, Sortino, Max Drawdown, benchmark comparison), an **Allocation
Breakdown** table (each asset's weight, individual Sharpe, individual total
return, and contribution), and plots the **portfolio cumulative return vs. the
benchmark**.

### Honesty note

The engine is **not** tuned to produce green reports. Guardrails only ever
*reject* configurations; they never fabricate a winner or a basket. If no asset
in the universe clears the profitability / risk bar, the dashboard renders an
honest empty portfolio state alongside the full leaderboard. The numbers shown
reflect the exact mathematical reality of the downloaded data.

### Stop-loss handling

The swept `stop_loss` level is **applied to the realized return path**: within
each test window, any single-period adverse move worse than `-stop_loss` is
capped at `-stop_loss` (a simple per-bar stop). This means different stop-loss
levels produce genuinely different P&L and scored metrics, so the "optimal"
stop-loss reflects an effect that was actually simulated.

> **Deviation from the bare reference.** The spec's verbatim reference records
> the stop-loss level but never applies it to the return series, so every
> stop-loss value would score identically. We intentionally apply the stop to
> the return path (a per-period clip at `-stop_loss`) so the advertised exit
> rule matches the backtested P&L. The stop is modeled as a per-bar return
> floor rather than an intra-bar price trigger; a path-dependent intraday stop
> (exit mid-bar, flatten the position for the remainder of the window) is a
> known simplification left as future work.

## Architecture

```
Stock-Intel/
├── .github/workflows/run_pipeline.yml   # CI: tests (hard gate) + live run
├── config/settings.yaml                 # Model parameters, assets, thresholds
├── src/
│   ├── __init__.py
│   ├── data_fetcher.py                  # Download + validate (429 backoff)
│   ├── strategies.py                    # Signal library (MultiFactor, Momentum, Bollinger)
│   ├── risk_engine.py                   # ATR slippage, trailing stop, latency, regime, metrics
│   ├── optimizer.py                     # Walk-forward + universe + portfolio allocator
│   ├── portfolio.py                     # Compounded multi-asset portfolio (CAGR, weighting)
│   └── dashboard_generator.py           # Self-contained HTML report
├── tests/test_pipeline.py               # Offline unit tests
├── main.py                              # CLI entrypoint
├── requirements.txt
└── .env.example
```

`main.py` re-exports and delegates to the `src/` modules, so the public API
(`apply_strategy`, `calculate_metrics`, `dynamic_slippage`, `simulate_latency`,
`regime_filter`, `run_walk_forward`) has a single source of truth.

## Setup

A virtual environment is required (dependencies are not available on the global
interpreter).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the pipeline

```bash
python main.py
```

This reads `config/settings.yaml`, downloads live market data for the configured
`assets` universe, runs the multi-ticker walk-forward optimization, prints the
`UNIVERSE OPTIMIZATION RESULTS` block, and writes both `output/dashboard.html`
(the institutional report artifact) and `output/index.html` (kept identical; the
CI artifact-verify guard and Cloudflare Pages deploy depend on it).

> **Live data vs. offline tests.** `python main.py` fetches live data from
> Yahoo Finance and therefore requires internet access. Yahoo intermittently
> returns **HTTP 429** rate-limit errors; `src/data_fetcher.py` automatically
> retries with **exponential backoff**. If data remains unavailable the run
> exits gracefully with a clear message (no dashboard is produced). The unit
> tests, by contrast, run **fully offline** against synthetic price data.

## Running the tests

```bash
pytest tests/ -v
```

Set `SIMULATE_LATENCY=0` to skip the simulated execution-latency sleeps so the
suite runs fast (CI does this automatically):

```bash
SIMULATE_LATENCY=0 pytest tests/ -v
```

## Configuration (`config/settings.yaml`)

| Key | Meaning |
| --- | --- |
| `ticker` | Primary symbol optimized by the default run |
| `assets` | Broader asset universe the workstation targets |
| `strategies` | Strategies to sweep (`Momentum`, `Bollinger_Squeeze`) |
| `stop_loss_range` | Stop-loss levels swept out-of-sample |
| `train_window_years` / `test_window_years` | Walk-forward window sizing (×252 trading days) |
| `date_range.start` / `date_range.end` | Historical download range |
| `risk.max_drawdown_limit` | Configs exceeding this drawdown are disqualified |
| `risk.risk_free_rate` | Per-period risk-free rate for excess returns |
| `base_slippage` | Base transaction cost; scaled by volatility |
| `latency.base_delay` / `latency.jitter` | Simulated execution-latency parameters |

## Environment variables

See `.env.example`. The key one is `SIMULATE_LATENCY` (set to `0` to disable the
latency sleep in CI/tests).
