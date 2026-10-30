"""Risk, regime and execution simulation engine.

This module contains the pure quantitative helpers used by the walk-forward
optimizer:

* :func:`calculate_metrics` - Sharpe / Sortino / Max Drawdown.
* :func:`dynamic_slippage` - volatility-scaled transaction costs.
* :func:`simulate_latency` - order-routing latency jitter (sleep skippable
  under tests).
* :func:`regime_filter` - 200-SMA trend + ATR expansion market-regime filter.

All functions accept in-memory data (DataFrame / Series / floats) and perform
no network access, so they are directly unit-testable offline.
"""

from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd

# Environment flag used by CI / the test-suite to skip the real ``time.sleep``
# so pytest runs fast. Set ``SIMULATE_LATENCY=0`` to disable sleeping.
_LATENCY_ENV_VAR = "SIMULATE_LATENCY"


def calculate_metrics(returns: pd.Series, risk_free_rate: float = 0.0):
    """Calculate annualized Sharpe Ratio, Sortino Ratio and Max Drawdown.

    Parameters
    ----------
    returns:
        Per-period strategy returns.
    risk_free_rate:
        Per-period risk-free rate subtracted from ``returns`` for the excess
        return calculation.

    Returns
    -------
    tuple(float, float, float)
        ``(sharpe, sortino, max_drawdown)``. Sharpe/Sortino are 0.0 when the
        corresponding standard deviation is non-positive (divide-by-zero guard).
    """
    excess_returns = returns - risk_free_rate
    downside_returns = returns[returns < 0]

    std_dev = returns.std()
    downside_std = downside_returns.std()

    # Guard against degenerate dispersion. A mathematically-constant return
    # stream can still yield a tiny non-zero std (~1e-18) from floating-point
    # accumulation, which would otherwise pass a strict ``> 0`` check and blow
    # up the ratio, so treat anything at or below the float tolerance as zero.
    _STD_EPS = 1e-12

    sharpe = (
        (excess_returns.mean() / std_dev * np.sqrt(252))
        if std_dev > _STD_EPS
        else 0.0
    )
    sortino = (
        (excess_returns.mean() / downside_std * np.sqrt(252))
        if downside_std > _STD_EPS
        else 0.0
    )

    cum_returns = returns.cumsum()
    max_drawdown = (cum_returns.cummax() - cum_returns).max()

    return sharpe, sortino, max_drawdown


def dynamic_slippage(volatility: float, base_slippage: float = 0.001) -> float:
    """Dynamically scale transaction costs based on underlying volatility.

    ``slippage = base_slippage * (1 + 10 * volatility)``
    """
    return base_slippage * (1.0 + volatility * 10.0)


def simulate_latency(base_delay: float = 0.5, jitter: float = 0.2) -> float:
    """Simulate real-world execution delay between signal and order routing.

    A random jitter in ``[-jitter, +jitter]`` is added to ``base_delay`` and the
    process sleeps for the resulting duration, returning the actual delay.

    The real ``time.sleep`` is skipped when the ``SIMULATE_LATENCY`` environment
    variable is set to a falsy value (``0``/``false``/``no``). The computed
    delay is still returned so numerical behaviour is unchanged. This keeps the
    default (production) behaviour identical while allowing the test-suite and
    CI to run fast.
    """
    actual_delay = base_delay + np.random.uniform(-jitter, jitter)
    if _sleep_enabled() and actual_delay > 0:
        time.sleep(actual_delay)
    return actual_delay


def _sleep_enabled() -> bool:
    """Return whether :func:`simulate_latency` should actually sleep."""
    raw = os.environ.get(_LATENCY_ENV_VAR)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def regime_filter(data: pd.DataFrame) -> pd.Series:
    """Identify favorable market regimes using a 200-SMA and ATR expansion.

    Returns a boolean Series that is ``True`` when price is above its 200-period
    SMA *and* the 14-period ATR is expanding (above its own 14-period mean).
    """
    sma_200 = data["Close"].rolling(200).mean()
    high_low_range = data["High"] - data["Low"]
    atr_14 = high_low_range.rolling(14).mean()
    atr_condition = atr_14 > atr_14.rolling(14).mean()
    return (data["Close"] > sma_200) & atr_condition
