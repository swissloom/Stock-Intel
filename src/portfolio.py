"""Multi-asset portfolio construction & performance.

This module builds a unified, **geometrically compounded** portfolio equity
curve from the daily returns of a selected basket of assets. It is deliberately
separate from the per-ticker additive walk-forward engine (``src/optimizer.py``,
``src/risk_engine.py``) so that:

* the existing single-ticker additive-return convention (``returns.cumsum()``)
  and its test contract are left completely untouched; and
* the portfolio layer uses the institutionally-correct compounding convention
  (``(1 + r).cumprod()``) with the geometric CAGR formula
  ``CAGR = (Ending / Beginning) ** (1 / Years) - 1``.

All functions are pure (no network, no global state) so they are directly
unit-testable offline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def daily_strategy_returns(
    data: pd.DataFrame,
    signal: pd.Series,
    slippage: float = 0.0,
) -> pd.Series:
    """Per-bar strategy returns for one asset on its shared-calendar frame.

    ``return_t = position_{t} * pct_change(Close)_t - slippage_on_turnover``

    The signal is treated as the position held into bar ``t`` (shifted by one
    bar to avoid look-ahead: you trade on the *next* bar after a signal). A
    per-unit ``slippage`` cost is charged on each change in position
    (turnover), so entering/exiting incurs the modelled transaction cost.

    Returns a Series aligned to ``data.index`` with NaNs filled to 0.0.
    """
    close = data["Close"]
    pct = close.pct_change()
    pos = pd.Series(signal).reindex(data.index).fillna(0.0).astype(float)
    # Trade on the bar AFTER the signal (no look-ahead).
    held = pos.shift(1).fillna(0.0)
    gross = held * pct
    # Transaction cost charged on turnover (|change in position|).
    turnover = held.diff().abs().fillna(held.abs())
    net = gross - turnover * slippage
    return net.fillna(0.0)


def inverse_volatility_weights(
    returns_by_asset: dict,
    lookback: int | None = None,
    min_weight: float = 0.0,
) -> dict:
    """Volatility-parity (inverse-volatility) weights.

    Each asset's weight is proportional to ``1 / volatility`` (so lower-vol
    assets get more capital), normalized to sum to 1. Volatility is the stdev
    of the asset's daily returns over the most recent ``lookback`` bars (or the
    full series when ``lookback`` is ``None``).

    Degenerate cases:
    * an asset with zero/NaN volatility is floored to a tiny epsilon so it
      still receives a (large) finite weight rather than dividing by zero;
    * if every asset is degenerate the function falls back to equal weights.
    """
    inv = {}
    for ticker, rets in returns_by_asset.items():
        series = pd.Series(rets).dropna()
        if lookback is not None and len(series) > lookback:
            series = series.iloc[-lookback:]
        vol = float(series.std()) if len(series) > 1 else 0.0
        if not np.isfinite(vol) or vol <= 1e-9:
            vol = 1e-9
        inv[ticker] = 1.0 / vol

    total = sum(inv.values())
    if total <= 0 or not np.isfinite(total):
        return equal_weights(list(returns_by_asset.keys()))
    weights = {t: v / total for t, v in inv.items()}

    if min_weight > 0:
        weights = {t: max(w, min_weight) for t, w in weights.items()}
        norm = sum(weights.values())
        weights = {t: w / norm for t, w in weights.items()}
    return weights


def equal_weights(tickers) -> dict:
    """Equal-weight allocation across ``tickers`` (sums to 1)."""
    tickers = list(tickers)
    if not tickers:
        return {}
    w = 1.0 / len(tickers)
    return {t: w for t in tickers}


def build_portfolio(
    returns_by_asset: dict,
    weights: dict,
) -> pd.DataFrame:
    """Combine per-asset daily returns into a weighted portfolio return series.

    Parameters
    ----------
    returns_by_asset:
        ``{ticker: daily-return Series}`` all sharing the same DatetimeIndex.
    weights:
        ``{ticker: weight}`` (need not be pre-normalized; it is re-normalized
        here to sum to 1 over the assets present in ``returns_by_asset``).

    Returns
    -------
    pandas.DataFrame
        Columns: ``portfolio_return`` (weighted daily return) plus one
        ``contrib_<ticker>`` column per asset (``weight * asset_return``) so the
        dashboard can attribute each asset's contribution. Indexed on the shared
        calendar.
    """
    assets = [t for t in weights if t in returns_by_asset]
    if not assets:
        return pd.DataFrame()

    # Align all asset return series on the shared index.
    aligned = pd.DataFrame(
        {t: pd.Series(returns_by_asset[t]) for t in assets}
    ).fillna(0.0)

    # Re-normalize weights over the present assets.
    w_total = sum(weights[t] for t in assets)
    norm_w = {t: (weights[t] / w_total if w_total else 0.0) for t in assets}

    out = pd.DataFrame(index=aligned.index)
    for t in assets:
        out[f"contrib_{t}"] = aligned[t] * norm_w[t]
    out["portfolio_return"] = out[[f"contrib_{t}" for t in assets]].sum(axis=1)
    return out


def compounded_equity_curve(returns: pd.Series) -> pd.Series:
    """Geometrically compounded equity curve, base 1.0.

    ``equity_t = prod_{k<=t} (1 + return_k)`` via ``(1 + r).cumprod()``.
    NaNs are treated as 0.0 (no move).
    """
    r = pd.Series(returns).fillna(0.0).astype(float)
    return (1.0 + r).cumprod()


def geometric_cagr(equity_curve: pd.Series, n_periods: int | None = None) -> float:
    """Annualized CAGR from a compounded equity curve (percent).

    ``CAGR = (Ending / Beginning) ** (1 / Years) - 1`` expressed as a
    percentage, where ``Years = n_periods / 252`` and ``n_periods`` defaults to
    the length of the curve. Guards:

    * fewer than 2 points, non-positive beginning/ending, or ``Years <= 0``
      return ``0.0``;
    * a fully wiped-out curve (ending <= 0) returns ``-100.0``.
    """
    eq = pd.Series(equity_curve).dropna().astype(float)
    if len(eq) < 2:
        return 0.0
    ending = float(eq.iloc[-1])
    # The compounded curve from :func:`compounded_equity_curve` has one point
    # per return (the first point is already ``1 + r_0``, not the base 1.0), so
    # the true starting capital is the implied base 1.0 and the curve spans
    # ``len(eq)`` periods of growth. Measuring from the literal first point would
    # silently drop the first period's return, understating multi-year CAGR, so
    # anchor the "beginning" at 1.0 and span the full period count.
    beginning = 1.0
    if n_periods is None:
        n_periods = len(eq)
    years = n_periods / TRADING_DAYS_PER_YEAR
    if years <= 0 or beginning <= 0:
        return 0.0
    if ending <= 0:
        return -100.0
    return float(((ending / beginning) ** (1.0 / years) - 1.0) * 100.0)


def total_return_compounded(equity_curve: pd.Series) -> float:
    """Total return (%) of a compounded equity curve: ``(end/start - 1)*100``."""
    eq = pd.Series(equity_curve).dropna().astype(float)
    if len(eq) < 1:
        return 0.0
    # Anchored at the implied base capital 1.0 (see geometric_cagr), so the
    # first period's return is included and total return is consistent with
    # CAGR built from the same curve.
    return float((eq.iloc[-1] / 1.0 - 1.0) * 100.0)


def portfolio_metrics(
    portfolio_returns: pd.Series,
    risk_free_rate: float = 0.0,
) -> dict:
    """Sharpe, Sortino and Max Drawdown for a compounded return stream.

    Sharpe/Sortino annualize by ``sqrt(252)``. Max drawdown is computed on the
    **compounded** equity curve (peak-to-trough as a fraction of the peak),
    consistent with the portfolio's geometric convention.
    """
    r = pd.Series(portfolio_returns).fillna(0.0).astype(float)
    excess = r - risk_free_rate
    std = r.std()
    downside = r[r < 0].std()

    _EPS = 1e-12
    sharpe = (excess.mean() / std * np.sqrt(252)) if std > _EPS else 0.0
    sortino = (excess.mean() / downside * np.sqrt(252)) if downside > _EPS else 0.0

    equity = compounded_equity_curve(r)
    running_max = equity.cummax()
    drawdown = (running_max - equity) / running_max
    max_dd = float(drawdown.max()) if len(drawdown) else 0.0

    return {
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": max_dd,
    }
