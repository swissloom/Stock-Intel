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


# Sentinel returned by :func:`compute_trade_stats` for profit factor when there
# are winning trades but zero losing trades (division by zero). A large finite
# value keeps downstream arithmetic (ranking / objective) well-defined while
# still signalling "no losses". Documented here so callers/tests can rely on it.
PROFIT_FACTOR_NO_LOSS = 1.0e9


def compute_trade_stats(signal: pd.Series, period_returns: pd.Series) -> dict:
    """Compute trade-level statistics from a signal and its realized returns.

    Trades are derived from ``signal`` transitions where ``signal`` is the
    per-bar position (1 = long, 0 = flat):

    * a ``0 -> 1`` transition is an **entry**;
    * the matching ``1 -> 0`` transition (or the end of the series while still
      long) is the **exit**.

    The per-trade P&L is the **sum of the realized per-period returns** while
    the position is held. This is consistent with the optimizer's equity curve,
    which is built additively (``returns.cumsum()``), so a trade's contribution
    equals the additive change in the equity curve over its holding window.

    Parameters
    ----------
    signal:
        Per-bar position series (values in ``{0, 1}``).
    period_returns:
        Per-bar realized strategy returns aligned with ``signal`` (already net
        of slippage / stop-loss clipping / regime masking). ``NaN`` values are
        treated as ``0.0``.

    Returns
    -------
    dict
        ``total_trades`` (int), ``win_rate_pct`` (float, winning / total * 100),
        ``avg_trade_duration_days`` (float, mean bars held per trade),
        ``gross_profit`` (float, sum of positive trade P&L),
        ``gross_loss`` (float, absolute sum of negative trade P&L),
        ``profit_factor`` (float).

    Edge cases
    ----------
    * **Zero trades** -> ``win_rate_pct=0.0``, ``avg_trade_duration_days=0.0``,
      ``gross_profit=0.0``, ``gross_loss=0.0``, ``profit_factor=0.0``.
    * **Zero losses but >0 trades** -> ``profit_factor`` is the documented
      sentinel :data:`PROFIT_FACTOR_NO_LOSS` (``1e9``).
    """
    sig = pd.Series(signal).fillna(0.0).astype(float).reset_index(drop=True)
    rets = pd.Series(period_returns).fillna(0.0).astype(float).reset_index(drop=True)
    n = min(len(sig), len(rets))
    sig = sig.iloc[:n]
    rets = rets.iloc[:n]

    # Treat anything > 0.5 as "long" so float signals are handled robustly.
    pos = (sig > 0.5).to_numpy()

    trade_pnls: list[float] = []
    trade_durations: list[int] = []
    in_trade = False
    entry_i = 0
    for i in range(n):
        if pos[i] and not in_trade:
            in_trade = True
            entry_i = i
        elif not pos[i] and in_trade:
            # Exit at bar i: the position was held for bars [entry_i, i-1].
            pnl = float(rets.iloc[entry_i:i].sum())
            trade_pnls.append(pnl)
            trade_durations.append(i - entry_i)
            in_trade = False
    if in_trade:
        # Still long at the end of the series: close at the last bar.
        pnl = float(rets.iloc[entry_i:n].sum())
        trade_pnls.append(pnl)
        trade_durations.append(n - entry_i)

    total_trades = len(trade_pnls)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "avg_trade_duration_days": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "profit_factor": 0.0,
        }

    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]
    gross_profit = float(sum(wins))
    gross_loss = float(abs(sum(losses)))
    win_rate_pct = len(wins) / total_trades * 100.0
    avg_trade_duration_days = float(np.mean(trade_durations))

    if gross_loss > 1e-12:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 1e-12:
        profit_factor = PROFIT_FACTOR_NO_LOSS
    else:
        # Trades exist but net zero gross profit and zero gross loss.
        profit_factor = 0.0

    return {
        "total_trades": total_trades,
        "win_rate_pct": win_rate_pct,
        "avg_trade_duration_days": avg_trade_duration_days,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
    }


def total_return_pct(period_returns: pd.Series) -> float:
    """Total return (%) using the **additive** convention.

    Consistent with the optimizer's equity curve (``returns.cumsum()``), total
    return is the sum of per-period returns expressed as a percentage:
    ``sum(returns) * 100``. ``NaN`` values are treated as ``0.0``.
    """
    rets = pd.Series(period_returns).fillna(0.0).astype(float)
    return float(rets.sum() * 100.0)


def cagr_pct(total_ret_pct: float, n_periods: int) -> float:
    """Annualized return (CAGR %) from a total return % and a period count.

    ``CAGR = ((1 + total_return) ** (252 / n_periods) - 1) * 100`` where
    ``total_return`` is the fractional total return (``total_ret_pct / 100``)
    and 252 is the trading-days-per-year convention.

    Guards
    ------
    * ``n_periods <= 0`` -> returns ``0.0``.
    * ``1 + total_return <= 0`` (total loss of 100%+ ) -> returns ``-100.0``
      (a full wipeout) since the fractional power is otherwise undefined.
    """
    if n_periods <= 0:
        return 0.0
    total_ret = total_ret_pct / 100.0
    base = 1.0 + total_ret
    if base <= 0:
        return -100.0
    return float((base ** (252.0 / n_periods) - 1.0) * 100.0)


def dynamic_slippage(volatility: float, base_slippage: float = 0.001) -> float:
    """Dynamically scale transaction costs based on underlying volatility.

    ``slippage = base_slippage * (1 + 10 * volatility)``
    """
    return base_slippage * (1.0 + volatility * 10.0)


# Minimum profit factor a configuration must clear to be eligible for
# selection. Configs below this are disqualified (institutional guardrail).
MIN_PROFIT_FACTOR = 1.3


def compute_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """True-range based Average True Range (ATR).

    Uses the classic True Range definition
    ``max(high-low, |high-prev_close|, |low-prev_close|)`` smoothed by a simple
    rolling mean over ``period`` bars. Pure / offline.
    """
    high = data["High"]
    low = data["Low"]
    prev_close = data["Close"].shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def dynamic_slippage_atr(
    atr: float,
    price: float,
    volume: float,
    avg_volume: float,
    base_slippage: float = 0.001,
) -> float:
    """ATR- and volume-scaled transaction-cost model.

    Slippage widens with relative ATR (volatility of the bar as a fraction of
    price) and with thin liquidity (current volume below its average):

        ``atr_frac   = atr / price``                     (0 when price <= 0)
        ``liq_factor = clip(avg_volume / volume, 1, 5)`` (thin -> up to 5x)
        ``slippage   = base_slippage * (1 + 10 * atr_frac) * liq_factor``

    Lower-than-average volume increases cost (harder to fill); higher volume is
    floored at the base (``liq_factor`` >= 1) so ample liquidity never discounts
    below the base cost. All inputs are scalars so the function stays pure and
    directly testable. Non-finite / degenerate inputs fall back safely.
    """
    atr_frac = (atr / price) if (price and price > 0 and np.isfinite(atr)) else 0.0
    if atr_frac < 0 or not np.isfinite(atr_frac):
        atr_frac = 0.0

    if volume and volume > 0 and avg_volume and avg_volume > 0:
        liq_factor = float(np.clip(avg_volume / volume, 1.0, 5.0))
    else:
        liq_factor = 1.0

    return base_slippage * (1.0 + 10.0 * atr_frac) * liq_factor


def atr_position_size(
    equity: float,
    atr: float,
    price: float,
    risk_per_trade: float = 0.01,
    max_fraction: float = 1.0,
) -> float:
    """ATR-based volatility position sizing, returned as a fraction of equity.

    Risks a fixed fraction of ``equity`` (``risk_per_trade``) against a stop set
    at ``atr`` distance, then expresses the resulting notional as a fraction of
    equity (``0 <= fraction <= max_fraction``):

        ``units          = (equity * risk_per_trade) / atr``
        ``notional       = units * price``
        ``fraction       = clip(notional / equity, 0, max_fraction)``

    Higher ATR (more volatile) -> smaller position; lower ATR -> larger (capped
    at ``max_fraction``). Degenerate inputs (non-positive atr/price/equity)
    return ``0.0``. Pure / offline.
    """
    if not (atr and atr > 0 and price and price > 0 and equity and equity > 0):
        return 0.0
    units = (equity * risk_per_trade) / atr
    notional = units * price
    fraction = notional / equity
    return float(np.clip(fraction, 0.0, max_fraction))


def apply_trailing_stop(
    signal: pd.Series,
    close: pd.Series,
    atr: pd.Series,
    atr_multiple: float = 3.0,
) -> pd.Series:
    """Apply a 3x-ATR (configurable) trailing stop to a long/flat signal.

    While the input ``signal`` is long (1), a trailing stop is maintained at
    ``peak_close - atr_multiple * ATR`` where ``peak_close`` is the highest
    close seen since entry. When ``Close`` closes at or below that stop the
    position is forced flat (0) from the next bar onward and stays flat until
    the original signal exits and re-enters (a fresh 0 -> 1 transition), which
    re-arms the stop for the new trade.

    Returns a new integer position series (1 = long, 0 = flat) aligned with the
    inputs. Pure / offline; the trailing stop is evaluated on a close-to-close
    basis (no intra-bar trigger), consistent with the project's per-bar P&L
    convention.
    """
    sig = pd.Series(signal).fillna(0).astype(int).to_numpy()
    px = pd.Series(close).astype(float).to_numpy()
    atr_arr = pd.Series(atr).astype(float).to_numpy()
    n = min(len(sig), len(px), len(atr_arr))

    out = np.zeros(n, dtype=int)
    in_trade = False
    peak = -np.inf
    stopped_this_trade = False

    for i in range(n):
        want_long = sig[i] == 1

        if not want_long:
            # Signal flat -> definitely flat; reset trade state.
            in_trade = False
            stopped_this_trade = False
            out[i] = 0
            continue

        # Signal wants long.
        if not in_trade and not stopped_this_trade:
            # Fresh entry: arm the stop.
            in_trade = True
            peak = px[i]
            out[i] = 1
            continue

        if stopped_this_trade:
            # Stopped out earlier within this same signal-long run; stay flat
            # until the signal exits (handled by the `not want_long` branch).
            out[i] = 0
            continue

        # Continuing an active trade: update peak and test the trailing stop.
        if np.isfinite(px[i]):
            peak = max(peak, px[i])
        stop_level = (
            peak - atr_multiple * atr_arr[i]
            if np.isfinite(atr_arr[i])
            else -np.inf
        )
        if np.isfinite(px[i]) and px[i] <= stop_level:
            # Trailing stop hit: exit (flat from this bar).
            in_trade = False
            stopped_this_trade = True
            out[i] = 0
        else:
            out[i] = 1

    return pd.Series(out, index=pd.Series(close).index[:n])


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
