# Stock-Intel

A Python **quantitative strategy optimization & backtesting workstation**. It
evaluates multi-strategy execution, runs walk-forward analysis, dynamically
models transaction costs/slippage, filters for market regimes, simulates order
execution latency, tracks risk limits, and renders a self-contained HTML
report.

## Overview

The pipeline downloads historical OHLCV data, sweeps a set of strategies and
stop-loss levels across rolling train/test windows (walk-forward), scores each
configuration by `Sharpe + Sortino`, disqualifies any configuration that breaks
the max-drawdown limit, and writes the winning configuration (together with its
cumulative-return / equity curve) to a self-contained HTML dashboard.

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
│   ├── strategies.py                    # Signal library (Momentum, Bollinger)
│   ├── risk_engine.py                   # Slippage, latency, regime, metrics
│   ├── optimizer.py                     # Walk-forward optimization engine
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
ticker (default **AAPL**), runs the walk-forward optimization, prints the
`OPTIMIZATION RESULTS` block, and writes `output/index.html`.

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
