"""Walk-forward optimization engine.

:func:`run_walk_forward` keeps the spec's public signature. It fetches data via
:mod:`src.data_fetcher` and then delegates to :func:`walk_forward_optimize`,
which is a pure function operating on a pre-fetched DataFrame. That separation
lets the windowing / scoring logic be unit-tested offline (no network).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data_fetcher import fetch_market_data
from src.risk_engine import (
    calculate_metrics,
    dynamic_slippage,
    regime_filter,
    simulate_latency,
)
from src.strategies import apply_strategy

# Trading days per calendar year used to size the walk-forward windows.
TRADING_DAYS_PER_YEAR = 252

# Default parameters (mirror config/settings.yaml and the spec reference).
DEFAULT_START = "2020-01-01"
DEFAULT_END = "2026-01-01"
DEFAULT_MAX_DRAWDOWN_LIMIT = 0.25
DEFAULT_BASE_SLIPPAGE = 0.001
DEFAULT_LATENCY_BASE_DELAY = 0.1
DEFAULT_LATENCY_JITTER = 0.05


def walk_forward_optimize(
    data: pd.DataFrame,
    ticker: str,
    strategy_names: list,
    stop_loss_range: list,
    train_window_years: int = 2,
    test_window_years: int = 1,
    *,
    base_slippage: float = DEFAULT_BASE_SLIPPAGE,
    max_drawdown_limit: float = DEFAULT_MAX_DRAWDOWN_LIMIT,
    latency_base_delay: float = DEFAULT_LATENCY_BASE_DELAY,
    latency_jitter: float = DEFAULT_LATENCY_JITTER,
):
    """Run the walk-forward sweep over a pre-fetched OHLCV ``data`` frame.

    This is the pure, network-free core of the optimizer. It computes rolling
    annualized volatility and the market-regime mask, then iterates
    train/test windows sweeping strategies x stop-loss levels, applying dynamic
    slippage + simulated latency, scoring ``sharpe + sortino`` and disqualifying
    any configuration whose max drawdown exceeds ``max_drawdown_limit``.

    Returns the best configuration dict (or ``None`` when nothing qualifies).
    """
    volatility = data["Close"].pct_change().rolling(21).std() * np.sqrt(252)
    regime = regime_filter(data)

    train_days = train_window_years * TRADING_DAYS_PER_YEAR
    test_days = test_window_years * TRADING_DAYS_PER_YEAR

    best_overall_score = -np.inf
    best_config = None

    for start_idx in range(0, len(data) - train_days - test_days, test_days):
        train_end = start_idx + train_days
        test_end = train_end + test_days

        test_data = data.iloc[train_end:test_end]

        for strategy in strategy_names:
            for sl in stop_loss_range:
                delay = simulate_latency(
                    base_delay=latency_base_delay, jitter=latency_jitter
                )
                current_vol = (
                    volatility.iloc[train_end]
                    if not np.isnan(volatility.iloc[train_end])
                    else 0.15
                )
                slip = dynamic_slippage(current_vol, base_slippage=base_slippage)

                test_signals = apply_strategy(test_data, strategy)
                returns = test_signals["Signal"] * test_data["Close"].pct_change()
                returns = returns - slip

                valid_regime = regime.iloc[train_end:test_end]
                returns = returns * valid_regime.astype(int)

                sharpe, sortino, mdd = calculate_metrics(returns)

                # Risk filter: disqualify configs exceeding the drawdown limit.
                if mdd > max_drawdown_limit:
                    continue

                score = sharpe + sortino
                if score > best_overall_score:
                    best_overall_score = score
                    best_config = {
                        "ticker": ticker,
                        "strategy": strategy,
                        "stop_loss": sl,
                        "sharpe": round(sharpe, 3),
                        "sortino": round(sortino, 3),
                        "max_drawdown": round(mdd, 4),
                        "execution_delay_sec": round(delay, 3),
                        "estimated_slippage": round(slip, 5),
                    }

    return best_config


def run_walk_forward(
    ticker: str,
    strategy_names: list,
    stop_loss_range: list,
    train_window_years: int = 2,
    test_window_years: int = 1,
    *,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    base_slippage: float = DEFAULT_BASE_SLIPPAGE,
    max_drawdown_limit: float = DEFAULT_MAX_DRAWDOWN_LIMIT,
    latency_base_delay: float = DEFAULT_LATENCY_BASE_DELAY,
    latency_jitter: float = DEFAULT_LATENCY_JITTER,
    data: pd.DataFrame | None = None,
):
    """Download market data and run the walk-forward optimization pipeline.

    Keeps the spec's public signature. A pre-fetched ``data`` frame may be
    injected (bypassing the network) for offline testing.

    Returns the best configuration dict, or ``None`` when no configuration
    satisfies the risk constraints.
    """
    if data is None:
        print(f"[*] Downloading market data for ticker: {ticker}...")
        data = fetch_market_data(ticker, start=start, end=end)

    print("[*] Initiating Walk-Forward Optimization pipeline...")

    best_config = walk_forward_optimize(
        data,
        ticker=ticker,
        strategy_names=strategy_names,
        stop_loss_range=stop_loss_range,
        train_window_years=train_window_years,
        test_window_years=test_window_years,
        base_slippage=base_slippage,
        max_drawdown_limit=max_drawdown_limit,
        latency_base_delay=latency_base_delay,
        latency_jitter=latency_jitter,
    )

    print("\n==========================================")
    print(" OPTIMIZATION RESULTS")
    print("==========================================")
    if best_config:
        for k, v in best_config.items():
            print(f" - {k.replace('_', ' ').title()}: {v}")
    else:
        print("No strategy configuration satisfied risk constraints.")
    print("==========================================\n")

    return best_config
