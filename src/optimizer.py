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
    cagr_pct,
    calculate_metrics,
    compute_trade_stats,
    dynamic_slippage,
    regime_filter,
    simulate_latency,
    total_return_pct,
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
    return_details: bool = False,
):
    """Run the walk-forward sweep over a pre-fetched OHLCV ``data`` frame.

    This is the pure, network-free core of the optimizer. It computes rolling
    annualized volatility and the market-regime mask, then iterates
    train/test windows sweeping strategies x stop-loss levels, applying dynamic
    slippage + simulated latency, computing institutional performance metrics
    and disqualifying any configuration whose max drawdown exceeds
    ``max_drawdown_limit``.

    Selection objective
    --------------------
    Among candidates the winner maximizes
    ``(cagr_pct * profit_factor) / (max_drawdown + 1e-5)``.

    Profitability guardrail
    -----------------------
    Any configuration whose **Total Return % <= 0** is flagged ``UNPROFITABLE``
    and can never become ``best_config`` regardless of its objective score.
    The existing ``max_drawdown > max_drawdown_limit`` risk filter is also kept.

    The swept stop-loss level is applied to the per-period return path: any
    single-period loss worse than ``-sl`` is capped at ``-sl`` (a simple
    per-bar stop), so different stop-loss levels genuinely change the realized
    P&L and the scored metrics rather than merely being recorded.

    Conventions
    -----------
    Equity curves (strategy and benchmark) are built additively via
    ``returns.fillna(0.0).cumsum()``. Total Return % is therefore the additive
    ``sum(returns) * 100`` (see :func:`src.risk_engine.total_return_pct`) and
    CAGR annualizes it with ``TRADING_DAYS_PER_YEAR`` = 252.

    Returns
    -------
    When ``return_details`` is ``False`` (default):
        ``(best_config, equity_curve)`` where ``best_config`` holds exactly the
        original 8 keys and ``equity_curve`` is the winning config's additive
        cumulative-return series (list of floats), or ``(None, None)`` when
        nothing qualifies.

    When ``return_details`` is ``True``:
        ``(best_config, equity_curve, details)``. ``details`` is a dict with:

        * ``total_return_pct``, ``cagr_pct``, ``profit_factor``,
          ``win_rate_pct``, ``total_trades``, ``avg_trade_duration_days`` for
          the winning config;
        * ``benchmark_total_return_pct`` and ``benchmark_equity_curve`` (list,
          length-aligned with ``equity_curve``) for Buy & Hold over the winning
          test window;
        * ``latency_ms`` (execution delay in milliseconds) and
          ``dynamic_slippage_pct`` (estimated slippage as a percentage);
        * ``period_start`` / ``period_end`` ISO date strings from the winning
          test-window index;
        * ``objective`` (the winning objective score);
        * ``sweep`` - the full list of every tested configuration's result
          dicts; and ``top10`` - that list ranked by profit factor (desc) then
          sharpe (desc), truncated to 10.

        When nothing qualifies ``best_config`` and ``equity_curve`` are ``None``
        but ``details`` is still returned (with ``sweep``/``top10`` populated
        from all tested configs, including UNPROFITABLE ones).
    """
    volatility = data["Close"].pct_change().rolling(21).std() * np.sqrt(252)
    regime = regime_filter(data)

    train_days = train_window_years * TRADING_DAYS_PER_YEAR
    test_days = test_window_years * TRADING_DAYS_PER_YEAR

    best_overall_score = -np.inf
    best_config = None
    best_equity_curve = None
    best_details = None

    sweep: list[dict] = []

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

                # Apply the swept stop-loss to the realized return path: cap any
                # single-period adverse move at ``-sl`` so the stop-loss level
                # actually affects P&L (and therefore the scored metrics).
                returns = returns.clip(lower=-sl)

                valid_regime = regime.iloc[train_end:test_end]
                returns = (returns * valid_regime.astype(int)).fillna(0.0)

                sharpe, sortino, mdd = calculate_metrics(returns)

                # Institutional metrics on the realized return path.
                tr_pct = total_return_pct(returns)
                n_periods = int(returns.shape[0])
                c_pct = cagr_pct(tr_pct, n_periods)
                trade_stats = compute_trade_stats(test_signals["Signal"], returns)
                profit_factor = trade_stats["profit_factor"]
                unprofitable = tr_pct <= 0.0

                # Objective: (CAGR% * ProfitFactor) / (MaxDrawdown + 1e-5).
                objective = (c_pct * profit_factor) / (mdd + 1e-5)

                # Benchmark (Buy & Hold) over the SAME test window, additive.
                bench_returns = test_data["Close"].pct_change().fillna(0.0)
                bench_total_return_pct = total_return_pct(bench_returns)
                bench_equity_curve = (
                    bench_returns.cumsum().astype(float).tolist()
                )

                equity_curve = returns.cumsum().astype(float).tolist()

                sweep_entry = {
                    "ticker": ticker,
                    "strategy": strategy,
                    "stop_loss": sl,
                    "sharpe": round(sharpe, 3),
                    "sortino": round(sortino, 3),
                    "max_drawdown": round(mdd, 4),
                    "total_return_pct": round(tr_pct, 3),
                    "cagr_pct": round(c_pct, 3),
                    "profit_factor": round(profit_factor, 3),
                    "win_rate_pct": round(trade_stats["win_rate_pct"], 2),
                    "total_trades": trade_stats["total_trades"],
                    "avg_trade_duration_days": round(
                        trade_stats["avg_trade_duration_days"], 2
                    ),
                    "unprofitable": bool(unprofitable),
                    "objective": round(objective, 4),
                }
                sweep.append(sweep_entry)

                # Risk filter: disqualify configs exceeding the drawdown limit.
                if mdd > max_drawdown_limit:
                    continue

                # Profitability guardrail: never select an unprofitable config.
                if unprofitable:
                    continue

                if objective > best_overall_score:
                    best_overall_score = objective
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
                    # Retain the winning config's additive cumulative-return
                    # (equity) curve so the dashboard can render the return
                    # curve.
                    best_equity_curve = equity_curve

                    idx = test_data.index
                    best_details = {
                        "total_return_pct": round(tr_pct, 3),
                        "cagr_pct": round(c_pct, 3),
                        "profit_factor": round(profit_factor, 3),
                        "win_rate_pct": round(trade_stats["win_rate_pct"], 2),
                        "total_trades": trade_stats["total_trades"],
                        "avg_trade_duration_days": round(
                            trade_stats["avg_trade_duration_days"], 2
                        ),
                        "benchmark_total_return_pct": round(
                            bench_total_return_pct, 3
                        ),
                        "benchmark_equity_curve": bench_equity_curve,
                        "latency_ms": round(delay * 1000.0, 2),
                        "dynamic_slippage_pct": round(slip * 100.0, 5),
                        "period_start": (
                            str(idx[0].date())
                            if len(idx) and hasattr(idx[0], "date")
                            else (str(idx[0]) if len(idx) else None)
                        ),
                        "period_end": (
                            str(idx[-1].date())
                            if len(idx) and hasattr(idx[-1], "date")
                            else (str(idx[-1]) if len(idx) else None)
                        ),
                        "objective": round(objective, 4),
                    }

    if not return_details:
        return best_config, best_equity_curve

    # Rank every tested config by Profit Factor (desc) then Sharpe (desc).
    ranked = sorted(
        sweep,
        key=lambda e: (e["profit_factor"], e["sharpe"]),
        reverse=True,
    )
    top10 = ranked[:10]

    if best_details is None:
        details = {"sweep": sweep, "top10": top10}
    else:
        details = dict(best_details)
        details["sweep"] = sweep
        details["top10"] = top10

    return best_config, best_equity_curve, details


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
    return_equity_curve: bool = False,
    return_details: bool = False,
):
    """Download market data and run the walk-forward optimization pipeline.

    Keeps the spec's public signature. A pre-fetched ``data`` frame may be
    injected (bypassing the network) for offline testing.

    By default returns the best configuration dict (or ``None`` when no
    configuration satisfies the risk constraints), preserving the spec's
    documented behaviour. When ``return_equity_curve=True`` the function
    instead returns a ``(best_config, equity_curve)`` tuple so callers (such as
    the dashboard renderer) can draw the winning configuration's return curve.

    When ``return_details=True`` is combined with ``return_equity_curve=True``
    the function returns ``(best_config, equity_curve, details)`` where
    ``details`` is the opt-in structure documented on
    :func:`walk_forward_optimize` (metrics, benchmark, latency_ms,
    dynamic_slippage_pct, period dates, full sweep and top-10 ranking). Default
    behaviour is unchanged.
    """
    if data is None:
        print(f"[*] Downloading market data for ticker: {ticker}...")
        data = fetch_market_data(ticker, start=start, end=end)

    print("[*] Initiating Walk-Forward Optimization pipeline...")

    opt_result = walk_forward_optimize(
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
        return_details=return_details,
    )
    if return_details:
        best_config, equity_curve, details = opt_result
    else:
        best_config, equity_curve = opt_result
        details = None

    print("\n==========================================")
    print(" OPTIMIZATION RESULTS")
    print("==========================================")
    if best_config:
        for k, v in best_config.items():
            print(f" - {k.replace('_', ' ').title()}: {v}")
    else:
        print("No strategy configuration satisfied risk constraints.")
    print("==========================================\n")

    if return_equity_curve and return_details:
        return best_config, equity_curve, details
    if return_equity_curve:
        return best_config, equity_curve
    if return_details:
        return best_config, details
    return best_config
