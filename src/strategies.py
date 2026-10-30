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
SUPPORTED_STRATEGIES = ("Momentum", "Bollinger_Squeeze")


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

    return signals
