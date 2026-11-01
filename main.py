"""Stock-Intel quantitative strategy optimization & execution pipeline.

Primary CLI entrypoint. The real logic lives in the :mod:`src` package; this
module re-exports the public functions so the historical reference API is
preserved with a single source of truth:

    apply_strategy, calculate_metrics, dynamic_slippage,
    simulate_latency, regime_filter, run_walk_forward

Running ``python main.py`` loads ``config/settings.yaml`` (falling back to the
spec defaults), performs a live walk-forward optimization for AAPL and renders a
self-contained HTML dashboard to ``output/index.html``.
"""

from __future__ import annotations

import os

import numpy as np  # noqa: F401 - kept for API/back-compat parity with the spec
import pandas as pd  # noqa: F401 - kept for API/back-compat parity with the spec
import yaml

# Single source of truth: delegate to the src/ package modules.
from src.dashboard_generator import generate_dashboard
from src.data_fetcher import DataFetchError
from src.optimizer import (
    DEFAULT_BASE_SLIPPAGE,
    DEFAULT_MAX_DRAWDOWN_LIMIT,
    allocate_portfolio,
    optimize_universe,
    run_walk_forward,
    walk_forward_optimize,  # noqa: F401 - exposed for testing/import parity
)
from src.risk_engine import (
    calculate_metrics,
    dynamic_slippage,
    regime_filter,
    simulate_latency,
)
from src.strategies import apply_strategy

__all__ = [
    "apply_strategy",
    "calculate_metrics",
    "dynamic_slippage",
    "simulate_latency",
    "regime_filter",
    "run_walk_forward",
    "optimize_universe",
    "allocate_portfolio",
    "load_settings",
    "main",
]

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "settings.yaml")

# Spec defaults used when config/settings.yaml is missing or incomplete.
_DEFAULTS = {
    "ticker": "AAPL",
    "assets": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "SPY"],
    "strategies": ["MultiFactor", "Momentum", "Bollinger_Squeeze"],
    "stop_loss_range": [0.02, 0.05, 0.08],
    "train_window_years": 2,
    "test_window_years": 1,
    "date_range": {"start": "2020-01-01", "end": "2026-11-01"},
    "risk": {"max_drawdown_limit": DEFAULT_MAX_DRAWDOWN_LIMIT, "risk_free_rate": 0.0},
    "base_slippage": DEFAULT_BASE_SLIPPAGE,
    "latency": {"base_delay": 0.1, "jitter": 0.05},
    "portfolio": {"top_n": 3, "weighting": "inverse_vol", "benchmark": "SPY"},
}


def load_settings(path: str = CONFIG_PATH) -> dict:
    """Load pipeline settings from YAML, falling back to the spec defaults."""
    settings = dict(_DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        settings.update(loaded)
    except FileNotFoundError:
        print(f"[!] Config not found at {path}; using built-in defaults.")
    return settings


def main() -> int:
    """Run the end-to-end optimization pipeline and render the dashboard."""
    settings = load_settings()
    date_range = settings.get("date_range", _DEFAULTS["date_range"])
    risk = settings.get("risk", _DEFAULTS["risk"])
    latency = settings.get("latency", _DEFAULTS["latency"])

    # The multi-ticker universe is driven by `assets` (falling back to the
    # single `ticker` for backward compatibility).
    universe = settings.get("assets") or [settings.get("ticker", "AAPL")]
    portfolio_cfg = settings.get("portfolio", _DEFAULTS["portfolio"])

    try:
        portfolio = allocate_portfolio(
            tickers=universe,
            strategy_names=settings["strategies"],
            stop_loss_range=settings["stop_loss_range"],
            train_window_years=settings["train_window_years"],
            test_window_years=settings["test_window_years"],
            start=date_range.get("start", "2020-01-01"),
            end=date_range.get("end", "2026-11-01"),
            base_slippage=settings.get("base_slippage", DEFAULT_BASE_SLIPPAGE),
            max_drawdown_limit=risk.get(
                "max_drawdown_limit", DEFAULT_MAX_DRAWDOWN_LIMIT
            ),
            latency_base_delay=latency.get("base_delay", 0.1),
            latency_jitter=latency.get("jitter", 0.05),
            top_n=portfolio_cfg.get("top_n", 3),
            weighting=portfolio_cfg.get("weighting", "inverse_vol"),
            benchmark=portfolio_cfg.get("benchmark", "SPY"),
        )
        # The universe leaderboard / best-config details ride along inside the
        # portfolio payload so the dashboard keeps rendering the sweep table.
        details = portfolio.get("details")
        best_config = _portfolio_best_config(portfolio, details)
        equity_curve = portfolio.get("equity_curve")
    except DataFetchError as exc:
        # Graceful handling: a transient Yahoo rate-limit / network failure must
        # not crash with an unhandled stack trace from a None DataFrame.
        print(f"[x] Market data unavailable: {exc}")
        print("[x] Skipping optimization; no dashboard generated.")
        return 1
    except Exception as exc:  # noqa: BLE001 - defensive top-level guard
        # Any non-fetch failure raised from inside the optimization (bad config,
        # unexpected data shape, etc.) is surfaced cleanly rather than as a raw
        # traceback, keeping the CLI robust end-to-end.
        print(f"[x] Optimization failed: {type(exc).__name__}: {exc}")
        return 1

    # Pass the winning configuration's cumulative-return (equity) curve plus the
    # institutional-metrics details (Total Return/CAGR/Profit Factor/Win Rate,
    # Buy & Hold benchmark return + equity curve, period start/end, latency ms,
    # dynamic slippage %, and the top-10 sweep) so the self-contained dashboard
    # renders the full institutional report. latency_ms and dynamic_slippage_pct
    # are already converted inside the optimizer's details channel
    # (latency_ms = execution_delay_sec * 1000, dynamic_slippage_pct =
    # estimated_slippage * 100). The benchmark equity curve is sourced from
    # details['benchmark_equity_curve'] by generate_dashboard.
    # The portfolio supplies its own compounded benchmark curve; the dashboard
    # renders the multi-asset portfolio grid, allocation table and the
    # portfolio-vs-benchmark equity chart from the `portfolio` payload.
    benchmark_curve = portfolio.get("benchmark_equity_curve")
    dashboard_path = generate_dashboard(
        best_config,
        equity_curve=equity_curve,
        details=details,
        benchmark_curve=benchmark_curve,
        portfolio=portfolio,
    )
    print(f"[+] Dashboard written to: {dashboard_path}")
    return 0


def _portfolio_best_config(portfolio: dict, details: dict | None) -> dict | None:
    """Synthesize a best-config-shaped dict for the dashboard header.

    The portfolio is multi-asset, so there is no single "best config". When the
    universe optimizer still identified a per-ticker champion we reuse it;
    otherwise we synthesize a minimal portfolio-level config so the dashboard's
    existing config-driven sections (Sharpe/Sortino/drawdown cards, cost model)
    render for the portfolio as a whole.
    """
    if not portfolio or not portfolio.get("selected"):
        return None
    selected = portfolio["selected"]
    return {
        "ticker": " + ".join(selected),
        "strategy": "MultiFactor Portfolio ({})".format(portfolio.get("weighting")),
        "stop_loss": 0.0,
        "sharpe": portfolio.get("sharpe", 0.0),
        "sortino": portfolio.get("sortino", 0.0),
        "max_drawdown": portfolio.get("max_drawdown", 0.0),
        "execution_delay_sec": 0.0,
        "estimated_slippage": (
            portfolio["allocation"][0]["slippage_pct"] / 100.0
            if portfolio.get("allocation")
            else 0.0
        ),
    }


if __name__ == "__main__":
    # Scan the universe over the multi-year regime window, allocate a top-N
    # multi-asset portfolio, and render the institutional dashboard.
    raise SystemExit(main())
