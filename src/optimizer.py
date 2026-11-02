"""Walk-forward optimization engine.

:func:`run_walk_forward` keeps the spec's public signature. It fetches data via
:mod:`src.data_fetcher` and then delegates to :func:`walk_forward_optimize`,
which is a pure function operating on a pre-fetched DataFrame. That separation
lets the windowing / scoring logic be unit-tested offline (no network).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data_fetcher import DEFAULT_UNIVERSE, fetch_market_data, fetch_universe
from src.portfolio import (
    build_portfolio,
    compounded_equity_curve,
    daily_strategy_returns,
    equal_weights,
    geometric_cagr,
    inverse_volatility_weights,
    portfolio_metrics,
    total_return_compounded,
)
from src.risk_engine import (
    MIN_PROFIT_FACTOR,
    apply_trailing_stop,
    cagr_pct,
    calculate_metrics,
    compute_atr,
    compute_trade_stats,
    dynamic_slippage,
    dynamic_slippage_atr,
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

    # ATR (14) and a 21-day average volume power the ATR/volume-scaled cost
    # model and the 3x-ATR trailing stop. Computed once over the full frame so
    # each window can slice its aligned segment cheaply.
    atr_series = compute_atr(data, period=14)
    avg_volume_series = (
        data["Volume"].rolling(21).mean()
        if "Volume" in data.columns
        else pd.Series(np.nan, index=data.index)
    )

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

                # ATR- and volume-scaled dynamic slippage at the window open.
                atr_at = atr_series.iloc[train_end]
                price_at = data["Close"].iloc[train_end]
                vol_at = avg_volume_series.iloc[train_end]
                cur_volume = (
                    data["Volume"].iloc[train_end]
                    if "Volume" in data.columns
                    else np.nan
                )
                if np.isfinite(atr_at) and np.isfinite(price_at):
                    slip = dynamic_slippage_atr(
                        atr=float(atr_at),
                        price=float(price_at),
                        volume=float(cur_volume) if np.isfinite(cur_volume) else 0.0,
                        avg_volume=float(vol_at) if np.isfinite(vol_at) else 0.0,
                        base_slippage=base_slippage,
                    )
                else:
                    # Warmup fallback: volatility-scaled cost (legacy model).
                    slip = dynamic_slippage(current_vol, base_slippage=base_slippage)

                raw_signals = apply_strategy(test_data, strategy)

                # 3x-ATR trailing stop applied to the signal to produce the
                # actually-held position path (close-to-close trailing exit).
                test_atr = atr_series.iloc[train_end:test_end]
                test_atr.index = test_data.index
                held_position = apply_trailing_stop(
                    raw_signals["Signal"],
                    test_data["Close"],
                    test_atr,
                    atr_multiple=3.0,
                )
                # Persist the stop-adjusted position for downstream trade stats.
                test_signals = raw_signals.copy()
                test_signals["Signal"] = held_position.astype(int).values

                returns = test_signals["Signal"] * test_data["Close"].pct_change()
                returns = returns - slip

                # Apply the swept stop-loss to the realized return path: cap any
                # single-period adverse move at ``-sl`` so the stop-loss level
                # actually affects P&L (and therefore the scored metrics). This
                # per-bar floor complements the trailing stop above.
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

                # Profitability guardrail: never select an unprofitable config
                # (Total Return % <= 0).
                if unprofitable:
                    continue

                # Profit-factor guardrail: disqualify any config whose profit
                # factor is below the institutional minimum (PF < 1.3).
                if profit_factor < MIN_PROFIT_FACTOR:
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


def optimize_universe(
    tickers=DEFAULT_UNIVERSE,
    strategy_names=None,
    stop_loss_range=None,
    train_window_years: int = 2,
    test_window_years: int = 1,
    *,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    base_slippage: float = DEFAULT_BASE_SLIPPAGE,
    max_drawdown_limit: float = DEFAULT_MAX_DRAWDOWN_LIMIT,
    latency_base_delay: float = DEFAULT_LATENCY_BASE_DELAY,
    latency_jitter: float = DEFAULT_LATENCY_JITTER,
    frames: dict | None = None,
):
    """Scan a basket of tickers and select the single best configuration.

    Runs :func:`walk_forward_optimize` independently for every ticker in
    ``tickers`` (each with its own aligned OHLCV frame) and then selects the
    globally best ``(ticker, strategy, stop_loss)`` configuration by the same
    objective used per-window: ``(CAGR% * ProfitFactor) / (MaxDrawdown + 1e-5)``.
    The institutional guardrails (max-drawdown limit, Total Return > 0, and
    Profit Factor >= :data:`~src.risk_engine.MIN_PROFIT_FACTOR`) are enforced
    inside :func:`walk_forward_optimize`, so a ticker that qualifies nowhere
    simply contributes nothing to the winner (but still appears in the
    leaderboard with its best sweep rows).

    Parameters
    ----------
    frames:
        Optional pre-fetched ``{ticker: OHLCV DataFrame}`` mapping. When
        provided no network access occurs (used for offline tests). Otherwise
        the universe is downloaded via :func:`fetch_universe` (reusing the 429
        backoff + alignment logic).

    Returns
    -------
    tuple(best_config, equity_curve, details)
        ``best_config`` is the winning 8-key config dict augmented with the
        winning ``ticker`` (already a key), or ``None`` when nothing qualifies
        across the whole basket. ``equity_curve`` is the winning config's
        additive cumulative-return series (or ``None``). ``details`` is the
        winning ticker's details payload, additionally carrying:

        * ``universe`` - list of tickers actually evaluated;
        * ``universe_sweep`` - every tested config across all tickers (each row
          carries its ``ticker``); and
        * ``top10`` - that combined sweep ranked by Profit Factor (desc) then
          Sharpe (desc), truncated to 10 (a genuine cross-ticker leaderboard).

        When nothing qualifies, ``details`` is still returned with the combined
        ``universe_sweep`` / ``top10`` so the dashboard can render the honest
        empty state alongside the full leaderboard.
    """
    if strategy_names is None:
        strategy_names = ["MultiFactor", "Momentum", "Bollinger_Squeeze"]
    if stop_loss_range is None:
        stop_loss_range = [0.02, 0.05, 0.08]

    if frames is None:
        print(f"[*] Downloading universe: {list(tickers)}...")
        frames = fetch_universe(tickers, start=start, end=end)

    print("[*] Initiating multi-ticker Walk-Forward Optimization...")

    combined_sweep: list[dict] = []
    best_objective = -np.inf
    best_config = None
    best_equity_curve = None
    best_details = None
    evaluated: list[str] = []

    for ticker, data in frames.items():
        if data is None or len(data) == 0:
            continue
        evaluated.append(ticker)
        cfg, equity_curve, details = walk_forward_optimize(
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
            return_details=True,
        )
        # Collect this ticker's sweep rows (each already carries 'ticker').
        combined_sweep.extend(details.get("sweep", []))

        # A qualifying winner for this ticker competes for the global title.
        if cfg is not None and details is not None:
            obj = details.get("objective", -np.inf)
            if obj > best_objective:
                best_objective = obj
                best_config = cfg
                best_equity_curve = equity_curve
                best_details = details

    # Build the genuine cross-ticker leaderboard.
    ranked = sorted(
        combined_sweep,
        key=lambda e: (e["profit_factor"], e["sharpe"]),
        reverse=True,
    )
    top10 = ranked[:10]

    if best_details is None:
        details = {
            "universe": evaluated,
            "universe_sweep": combined_sweep,
            "sweep": combined_sweep,
            "top10": top10,
        }
    else:
        details = dict(best_details)
        details["universe"] = evaluated
        details["universe_sweep"] = combined_sweep
        details["top10"] = top10  # cross-ticker leaderboard overrides per-ticker

    print("\n==========================================")
    print(" UNIVERSE OPTIMIZATION RESULTS")
    print("==========================================")
    print(f" - Tickers evaluated: {evaluated}")
    if best_config:
        for k, v in best_config.items():
            print(f" - {k.replace('_', ' ').title()}: {v}")
    else:
        print(" No configuration satisfied the profitability / risk guardrails")
        print(" across the entire universe. Reporting the honest empty state.")
    print("==========================================\n")

    return best_config, best_equity_curve, details


# Default portfolio construction parameters.
DEFAULT_TOP_N = 3
DEFAULT_WEIGHTING = "inverse_vol"
DEFAULT_BENCHMARK = "SPY"


def _best_qualifying_per_ticker(combined_sweep: list) -> dict:
    """Pick each ticker's single best *qualifying* sweep row.

    A row qualifies when it is not flagged ``unprofitable`` and clears the
    profit-factor guardrail (``profit_factor >= MIN_PROFIT_FACTOR``). Among a
    ticker's qualifying rows the one with the highest ``objective`` is kept.

    Returns ``{ticker: sweep_row}`` for every ticker with at least one
    qualifying configuration.
    """
    best: dict = {}
    for row in combined_sweep:
        if row.get("unprofitable"):
            continue
        if row.get("profit_factor", 0.0) < MIN_PROFIT_FACTOR:
            continue
        t = row["ticker"]
        if t not in best or row.get("objective", -np.inf) > best[t].get(
            "objective", -np.inf
        ):
            best[t] = row
    return best


def allocate_portfolio(
    tickers=DEFAULT_UNIVERSE,
    strategy_names=None,
    stop_loss_range=None,
    train_window_years: int = 2,
    test_window_years: int = 1,
    *,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    base_slippage: float = DEFAULT_BASE_SLIPPAGE,
    max_drawdown_limit: float = DEFAULT_MAX_DRAWDOWN_LIMIT,
    latency_base_delay: float = DEFAULT_LATENCY_BASE_DELAY,
    latency_jitter: float = DEFAULT_LATENCY_JITTER,
    top_n: int = DEFAULT_TOP_N,
    weighting: str = DEFAULT_WEIGHTING,
    benchmark: str = DEFAULT_BENCHMARK,
    frames: dict | None = None,
):
    """Rank the universe, select the top-N qualifying assets, and allocate.

    This is the multi-asset portfolio allocator. It:

    1. Runs :func:`optimize_universe` to rank every ticker (reusing the
       walk-forward guardrails: max-drawdown limit, Total Return > 0, and
       Profit Factor >= :data:`~src.risk_engine.MIN_PROFIT_FACTOR`).
    2. Selects up to ``top_n`` qualifying assets (by the walk-forward
       objective). Fewer are held when fewer qualify; none means an honest
       empty portfolio.
    3. Builds each selected asset's **daily** ``MultiFactor`` strategy returns
       on the shared (aligned) calendar, net of dynamic slippage.
    4. Weights them by ``inverse_vol`` (volatility parity) or ``equal``.
    5. Combines them into a single **geometrically compounded** portfolio
       equity curve ``(1 + r).cumprod()`` and computes the geometric CAGR,
       Sharpe/Sortino and max drawdown, alongside a benchmark curve.

    Parameters
    ----------
    frames:
        Optional pre-fetched, aligned ``{ticker: OHLCV DataFrame}`` mapping for
        offline testing. Otherwise the universe is downloaded + aligned via
        :func:`optimize_universe` -> :func:`fetch_universe`.
    benchmark:
        A ticker symbol (e.g. ``"SPY"``) or ``"equal_weight"`` for an
        equal-weight Buy & Hold basket of the full evaluated universe.

    Returns
    -------
    dict
        A ``portfolio`` payload (see keys inline) including the compounded
        ``equity_curve``, ``benchmark_equity_curve``, headline metrics, the
        per-asset ``allocation`` breakdown (weight, individual Sharpe,
        contribution to total return), plus the underlying universe ``details``
        (leaderboard etc.) for the dashboard.
    """
    if strategy_names is None:
        strategy_names = ["MultiFactor", "Momentum", "Bollinger_Squeeze"]
    if stop_loss_range is None:
        stop_loss_range = [0.02, 0.05, 0.08]

    # Fetch + align once; reuse for both ranking and portfolio construction.
    if frames is None:
        print(f"[*] Downloading universe for portfolio: {list(tickers)}...")
        frames = fetch_universe(tickers, start=start, end=end)

    # Step 1-2: rank the universe and read the per-ticker qualifying winners.
    _, _, details = optimize_universe(
        tickers=tickers,
        strategy_names=strategy_names,
        stop_loss_range=stop_loss_range,
        train_window_years=train_window_years,
        test_window_years=test_window_years,
        base_slippage=base_slippage,
        max_drawdown_limit=max_drawdown_limit,
        latency_base_delay=latency_base_delay,
        latency_jitter=latency_jitter,
        frames=frames,
    )

    qualifying = _best_qualifying_per_ticker(details.get("universe_sweep", []))
    # Rank qualifying tickers by objective (desc) and take the top N.
    ranked_tickers = sorted(
        qualifying.keys(),
        key=lambda t: qualifying[t].get("objective", -np.inf),
        reverse=True,
    )
    selected = ranked_tickers[:top_n]

    print(
        f"[*] Portfolio selection: {selected or 'NONE'} "
        f"(top {top_n} of {len(qualifying)} qualifying; weighting={weighting})"
    )

    # Step 3: per-asset daily strategy returns on the shared calendar. The
    # MultiFactor model is the portfolio's signal engine. Dynamic slippage is
    # approximated per-asset by the config's best sweep row's modelled cost.
    returns_by_asset: dict = {}
    per_asset_slippage: dict = {}
    for ticker in selected:
        data = frames.get(ticker)
        if data is None or len(data) == 0:
            continue
        signal = apply_strategy(data, "MultiFactor")["Signal"]
        # Volatility-scaled slippage proxy from the asset's realized vol.
        asset_vol = (
            data["Close"].pct_change().rolling(21).std().mean() * np.sqrt(252)
        )
        slip = dynamic_slippage(
            float(asset_vol) if np.isfinite(asset_vol) else 0.15,
            base_slippage=base_slippage,
        )
        per_asset_slippage[ticker] = slip
        returns_by_asset[ticker] = daily_strategy_returns(data, signal, slippage=slip)

    # Step 4: weights.
    if weighting == "equal":
        weights = equal_weights(list(returns_by_asset.keys()))
    else:
        weighting = "inverse_vol"
        weights = inverse_volatility_weights(returns_by_asset)

    # Step 5: compounded portfolio + benchmark.
    portfolio_df = build_portfolio(returns_by_asset, weights)
    evaluated = details.get("universe", list(frames.keys()))

    if portfolio_df.empty:
        equity_curve = []
        port_rets = pd.Series(dtype=float)
    else:
        port_rets = portfolio_df["portfolio_return"]
        equity_curve = compounded_equity_curve(port_rets)

    # Benchmark: a named ticker's Buy & Hold, or an equal-weight basket.
    bench_curve = _benchmark_curve(frames, benchmark, evaluated, port_rets)

    # Headline portfolio metrics (geometric).
    if len(port_rets):
        pm = portfolio_metrics(port_rets)
        n_periods = int(len(port_rets))
        eq_series = compounded_equity_curve(port_rets)
        cagr = geometric_cagr(eq_series, n_periods=n_periods)
        total_ret = total_return_compounded(eq_series)
    else:
        pm = {"sharpe": 0.0, "sortino": 0.0, "max_drawdown": 0.0}
        cagr = 0.0
        total_ret = 0.0

    # Per-asset allocation breakdown: weight, individual Sharpe, contribution.
    allocation = []
    for ticker in selected:
        if ticker not in returns_by_asset:
            continue
        r = returns_by_asset[ticker]
        ind = portfolio_metrics(r)
        asset_eq = compounded_equity_curve(r)
        # Contribution to portfolio total return: compounded contribution column.
        contrib_series = (
            portfolio_df[f"contrib_{ticker}"]
            if f"contrib_{ticker}" in portfolio_df.columns
            else pd.Series(dtype=float)
        )
        contrib_pct = (
            total_return_compounded(compounded_equity_curve(contrib_series))
            if len(contrib_series)
            else 0.0
        )
        allocation.append(
            {
                "ticker": ticker,
                "weight_pct": round(weights.get(ticker, 0.0) * 100.0, 2),
                "sharpe": round(ind["sharpe"], 3),
                "individual_total_return_pct": round(
                    total_return_compounded(asset_eq), 2
                ),
                "contribution_pct": round(contrib_pct, 2),
                "slippage_pct": round(per_asset_slippage.get(ticker, 0.0) * 100, 5),
            }
        )

    bench_total_return = (
        total_return_compounded(pd.Series(bench_curve)) if len(bench_curve) else 0.0
    )

    idx = portfolio_df.index if not portfolio_df.empty else []
    portfolio = {
        "selected": selected,
        "weighting": weighting,
        "weights": {t: round(weights.get(t, 0.0), 4) for t in selected},
        "top_n": top_n,
        "n_qualifying": len(qualifying),
        "equity_curve": list(equity_curve) if len(equity_curve) else [],
        "benchmark": benchmark,
        "benchmark_equity_curve": list(bench_curve),
        "benchmark_total_return_pct": round(bench_total_return, 2),
        "cagr_pct": round(cagr, 3),
        "total_return_pct": round(total_ret, 3),
        "sharpe": round(pm["sharpe"], 3),
        "sortino": round(pm["sortino"], 3),
        "max_drawdown": round(pm["max_drawdown"], 4),
        "allocation": allocation,
        "period_start": str(idx[0].date()) if len(idx) else None,
        "period_end": str(idx[-1].date()) if len(idx) else None,
        "n_periods": int(len(port_rets)),
        "details": details,
    }

    print("\n==========================================")
    print(" PORTFOLIO ALLOCATION RESULTS")
    print("==========================================")
    print(f" - Selected: {selected or 'NONE (honest empty portfolio)'}")
    print(f" - Weighting: {weighting}")
    if selected:
        print(f" - Portfolio CAGR %: {portfolio['cagr_pct']}")
        print(f" - Portfolio Total Return %: {portfolio['total_return_pct']}")
        print(f" - Sharpe: {portfolio['sharpe']}  Sortino: {portfolio['sortino']}")
        print(f" - Max Drawdown: {portfolio['max_drawdown']}")
        print(f" - Benchmark ({benchmark}) Total Return %: "
              f"{portfolio['benchmark_total_return_pct']}")
    print("==========================================\n")

    return portfolio


def _benchmark_curve(frames, benchmark, evaluated, port_rets):
    """Build a compounded benchmark equity curve aligned to the portfolio.

    ``benchmark`` may be a ticker symbol (Buy & Hold of that asset) or
    ``"equal_weight"`` (an equal-weight Buy & Hold basket of ``evaluated``).
    The curve is aligned to the portfolio return index when available.
    """
    index = port_rets.index if len(port_rets) else None

    if benchmark != "equal_weight" and benchmark in frames:
        rets = frames[benchmark]["Close"].pct_change().fillna(0.0)
        if index is not None:
            rets = rets.reindex(index).fillna(0.0)
        return list(compounded_equity_curve(rets))

    # Equal-weight basket of the evaluated universe.
    basket = [t for t in evaluated if t in frames]
    if not basket:
        return []
    cols = {}
    for t in basket:
        r = frames[t]["Close"].pct_change().fillna(0.0)
        if index is not None:
            r = r.reindex(index).fillna(0.0)
        cols[t] = r
    basket_rets = pd.DataFrame(cols).mean(axis=1)
    return list(compounded_equity_curve(basket_rets))
