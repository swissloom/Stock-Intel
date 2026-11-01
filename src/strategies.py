"""Signal generation library.

Each strategy function consumes a pre-fetched OHLCV ``pandas.DataFrame`` and
returns a DataFrame with a single ``Signal`` column (1 = Long, 0 = Flat/Cash).

The functions are intentionally pure: they never perform network access, so
they can be unit-tested offline with synthetic price data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Public names recognised by :func:`apply_strategy`.
SUPPORTED_STRATEGIES = ("Momentum", "Bollinger_Squeeze", "MultiFactor")

# --- MultiFactor model parameters -----------------------------------------
# 126-day (~6-month) momentum lookback minus the most recent 21-day pullback.
MF_MOMENTUM_LOOKBACK = 126
MF_PULLBACK_LOOKBACK = 21
# Trend filter: price must be strictly above its 200-day SMA.
MF_TREND_SMA = 200
# Volatility filter: exclude bars whose 21-day annualized volatility exceeds
# this threshold (extreme tail-risk regime).
MF_VOL_LOOKBACK = 21
MF_VOL_CAP = 0.50
MF_TRADING_DAYS = 252


def multifactor_score(data: pd.DataFrame) -> pd.DataFrame:
    """Compute the raw multi-factor components for ``data``.

    Returns a DataFrame (indexed like ``data``) with columns:

    * ``momentum`` - 126-day price rate-of-change minus the most recent 21-day
      rate-of-change (``ROC_126 - ROC_21``), i.e. 6-month momentum net of the
      latest 1-month pullback.
    * ``above_sma`` - boolean, ``Close`` strictly greater than its 200-day SMA.
    * ``vol_ann`` - 21-day annualized volatility of daily returns.
    * ``vol_ok`` - boolean, ``vol_ann`` at or below :data:`MF_VOL_CAP`.

    Pure / offline. Used by :func:`apply_strategy` for the ``MultiFactor``
    signal and exposed separately so the factor math is directly testable.
    """
    close = data["Close"]
    roc_126 = close.pct_change(periods=MF_MOMENTUM_LOOKBACK)
    roc_21 = close.pct_change(periods=MF_PULLBACK_LOOKBACK)
    momentum = roc_126 - roc_21

    sma_200 = close.rolling(MF_TREND_SMA).mean()
    above_sma = close > sma_200

    daily_ret = close.pct_change()
    vol_ann = daily_ret.rolling(MF_VOL_LOOKBACK).std() * np.sqrt(MF_TRADING_DAYS)
    vol_ok = vol_ann <= MF_VOL_CAP

    out = pd.DataFrame(index=data.index)
    out["momentum"] = momentum
    out["above_sma"] = above_sma
    out["vol_ann"] = vol_ann
    out["vol_ok"] = vol_ok
    return out


def apply_strategy(data: pd.DataFrame, strategy_name: str) -> pd.DataFrame:
    """Generate long/flat signals based on the selected strategy logic.

    Parameters
    ----------
    data:
        OHLCV DataFrame containing at least a ``Close`` column.
    strategy_name:
        One of :data:`SUPPORTED_STRATEGIES`.

    Returns
    -------
    pandas.DataFrame
        DataFrame indexed like ``data`` with a single integer ``Signal`` column
        (1 = Long, 0 = Flat/Cash).
    """
    signals = pd.DataFrame(index=data.index)
    signals["Signal"] = 0

    if strategy_name == "Momentum":
        # 20-period rate-of-change trend follower.
        signals["Signal"] = np.where(data["Close"].pct_change(periods=20) > 0, 1, 0)
    elif strategy_name == "Bollinger_Squeeze":
        # Mean-reversion triggered on a lower-band touch/breakout.
        sma_20 = data["Close"].rolling(20).mean()
        std_20 = data["Close"].rolling(20).std()
        bb_lower = sma_20 - (2 * std_20)
        signals["Signal"] = np.where(
            (data["Close"] < bb_lower)
            & (data["Close"].shift(1) >= bb_lower.shift(1)),
            1,
            0,
        )
    elif strategy_name == "MultiFactor":
        # Combined multi-factor long/flat rule (per-asset):
        #   LONG (1) when ALL hold, else FLAT (0):
        #     * momentum factor (ROC_126 - ROC_21) is strictly positive, AND
        #     * price strictly above its 200-day SMA (trend filter), AND
        #     * 21-day annualized volatility <= 50% (tail-risk filter).
        factors = multifactor_score(data)
        long_mask = (
            (factors["momentum"] > 0)
            & factors["above_sma"].astype(bool)
            & factors["vol_ok"].astype(bool)
        )
        # NaN factor rows (warmup) are treated as flat.
        signals["Signal"] = np.where(long_mask.fillna(False), 1, 0)

    return signals
