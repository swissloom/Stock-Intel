"""Stock-Intel quantitative strategy optimization & execution pipeline.

Primary CLI entrypoint. The real logic lives in the :mod:`src` package; this
module re-exports the public functions so the historical reference API is
preserved with a single source of truth:

    apply_strategy, calculate_metrics, dynamic_slippage,
    simulate_latency, regime_filter, run_walk_forward

Running ``python main.py`` loads ``config/settings.yaml`` (falling back to the
spec defaults), performs a live walk-forward optimization for AAPL and renders a
self-contained HTML dashboard to ``output/dashboard.html``.
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
    "load_settings",
    "main",
]

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "settings.yaml")

# Spec defaults used when config/settings.yaml is missing or incomplete.
_DEFAULTS = {
    "ticker": "AAPL",
    "strategies": ["Momentum", "Bollinger_Squeeze"],
    "stop_loss_range": [0.02, 0.05, 0.08],
    "train_window_years": 2,
    "test_window_years": 1,
    "date_range": {"start": "2020-01-01", "end": "2026-01-01"},
    "risk": {"max_drawdown_limit": DEFAULT_MAX_DRAWDOWN_LIMIT, "risk_free_rate": 0.0},
    "base_slippage": DEFAULT_BASE_SLIPPAGE,
    "latency": {"base_delay": 0.1, "jitter": 0.05},
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

    try:
        best_config, equity_curve = run_walk_forward(
            ticker=settings["ticker"],
            strategy_names=settings["strategies"],
            stop_loss_range=settings["stop_loss_range"],
            train_window_years=settings["train_window_years"],
            test_window_years=settings["test_window_years"],
            start=date_range.get("start", "2020-01-01"),
            end=date_range.get("end", "2026-01-01"),
            base_slippage=settings.get("base_slippage", DEFAULT_BASE_SLIPPAGE),
            max_drawdown_limit=risk.get(
                "max_drawdown_limit", DEFAULT_MAX_DRAWDOWN_LIMIT
            ),
            latency_base_delay=latency.get("base_delay", 0.1),
            latency_jitter=latency.get("jitter", 0.05),
            return_equity_curve=True,
        )
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

    # Pass the winning configuration's cumulative-return (equity) curve so the
    # self-contained dashboard renders the spec-required return curve.
    dashboard_path = generate_dashboard(best_config, equity_curve=equity_curve)
    print(f"[+] Dashboard written to: {dashboard_path}")
    return 0


if __name__ == "__main__":
    # Mirror the spec reference entrypoint: optimize AAPL across the two
    # strategies and the stop-loss sweep, then render the dashboard.
    raise SystemExit(main())
