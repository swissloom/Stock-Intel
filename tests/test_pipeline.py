"""Offline unit tests for the quantitative pipeline.

Every test here runs fully offline: synthetic/fixture OHLCV frames are used and
``yfinance.download`` / ``time.sleep`` are stubbed so nothing touches the
network and the suite finishes in a few seconds.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from src.data_fetcher import DataFetchError, normalize_ohlcv, fetch_market_data
from src.optimizer import walk_forward_optimize
from src.risk_engine import (
    PROFIT_FACTOR_NO_LOSS,
    cagr_pct,
    calculate_metrics,
    compute_trade_stats,
    dynamic_slippage,
    regime_filter,
    simulate_latency,
    total_return_pct,
)
from src.strategies import apply_strategy

EXPECTED_CONFIG_KEYS = {
    "ticker",
    "strategy",
    "stop_loss",
    "sharpe",
    "sortino",
    "max_drawdown",
    "execution_delay_sec",
    "estimated_slippage",
}


# ---------------------------------------------------------------------------
# Global offline / fast-run guards
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _no_latency_sleep(monkeypatch):
    """Disable real latency sleeping so the suite runs fast and offline."""
    monkeypatch.setenv("SIMULATE_LATENCY", "0")
    # Belt-and-braces: also stub time.sleep in the risk engine in case the env
    # flag path is ever bypassed.
    monkeypatch.setattr("src.risk_engine.time.sleep", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Guarantee no test can reach the network via yfinance.download."""
    import src.data_fetcher as df_mod

    def _boom(*args, **kwargs):  # pragma: no cover - should never be hit
        raise AssertionError("Network access attempted via yf.download")

    if df_mod.yf is not None:
        monkeypatch.setattr(df_mod.yf, "download", _boom, raising=False)


# ---------------------------------------------------------------------------
# Synthetic data fixtures
# ---------------------------------------------------------------------------
def _ohlcv_from_close(close: np.ndarray, start: str = "2018-01-01") -> pd.DataFrame:
    """Build a plausible OHLCV frame from a close-price array."""
    idx = pd.bdate_range(start=start, periods=len(close))
    close = np.asarray(close, dtype=float)
    # Derive High/Low/Open around Close with a small, deterministic spread.
    spread = np.maximum(np.abs(close) * 0.01, 0.1)
    high = close + spread
    low = close - spread
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = np.full(len(close), 1_000_000.0)
    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )


@pytest.fixture
def uptrend_df() -> pd.DataFrame:
    """A clear, monotonically rising series (~650 trading days)."""
    n = 650
    close = 100.0 + np.arange(n) * 1.0
    return _ohlcv_from_close(close)


@pytest.fixture
def long_uptrend_df() -> pd.DataFrame:
    """A rising series long enough to enter the walk-forward loop.

    ``walk_forward_optimize`` iterates
    ``range(0, len(data) - train_days - test_days, test_days)`` with
    ``train_days = 2*252 = 504`` and ``test_days = 1*252 = 252``. A fixture of
    900 rows (``900 - 504 - 252 = 144 > 0``) therefore produces at least one
    real window, so the scoring / drawdown / best_config logic is exercised.
    """
    n = 900
    close = 100.0 + np.arange(n) * 1.0
    return _ohlcv_from_close(close)


@pytest.fixture
def downtrend_df() -> pd.DataFrame:
    """A clear, monotonically falling series (~650 trading days)."""
    n = 650
    close = 800.0 - np.arange(n) * 1.0
    return _ohlcv_from_close(close)


@pytest.fixture
def mean_reverting_df() -> pd.DataFrame:
    """A deterministic mean-reverting (oscillating) series (~650 days)."""
    n = 650
    t = np.arange(n)
    close = 100.0 + 10.0 * np.sin(t / 12.0)
    return _ohlcv_from_close(close)


# ---------------------------------------------------------------------------
# apply_strategy - Momentum
# ---------------------------------------------------------------------------
def test_momentum_long_on_uptrend(uptrend_df):
    out = apply_strategy(uptrend_df, "Momentum")
    assert "Signal" in out.columns
    assert set(np.unique(out["Signal"])).issubset({0, 1})
    # After the 20-period lookback the rate-of-change is strictly positive.
    assert (out["Signal"].iloc[20:] == 1).all()


def test_momentum_flat_on_downtrend(downtrend_df):
    out = apply_strategy(downtrend_df, "Momentum")
    assert "Signal" in out.columns
    assert set(np.unique(out["Signal"])).issubset({0, 1})
    # A falling series never has a positive 20-period ROC -> always flat.
    assert (out["Signal"] == 0).all()


# ---------------------------------------------------------------------------
# apply_strategy - Bollinger_Squeeze
# ---------------------------------------------------------------------------
def test_bollinger_long_on_lower_band_breach():
    # Flat baseline, then a single sharp dip below the lower band.
    n = 60
    close = np.full(n, 100.0)
    # Add tiny deterministic wiggle so the rolling std is non-zero.
    close = close + np.tile([0.0, 0.5, -0.5, 0.25, -0.25], n // 5)
    breach_idx = 50
    close[breach_idx] = 80.0  # sharp drop below the lower Bollinger band
    df = _ohlcv_from_close(close)

    out = apply_strategy(df, "Bollinger_Squeeze")
    assert "Signal" in out.columns
    assert set(np.unique(out["Signal"])).issubset({0, 1})
    # The breach bar must fire a long signal (crosses below lower band).
    assert out["Signal"].iloc[breach_idx] == 1


# ---------------------------------------------------------------------------
# calculate_metrics
# ---------------------------------------------------------------------------
def test_calculate_metrics_positive_returns():
    # Mostly positive drift with some noise -> positive Sharpe/Sortino.
    rng = np.random.default_rng(42)
    returns = pd.Series(0.001 + rng.normal(0, 0.0005, 300))
    sharpe, sortino, mdd = calculate_metrics(returns)
    assert np.isfinite(sharpe) and np.isfinite(sortino)
    assert sharpe > 0
    assert sortino > 0
    assert mdd >= 0


def test_calculate_metrics_negative_returns_sign():
    rng = np.random.default_rng(7)
    returns = pd.Series(-0.001 + rng.normal(0, 0.0005, 300))
    sharpe, sortino, mdd = calculate_metrics(returns)
    assert np.isfinite(sharpe) and np.isfinite(sortino)
    assert sharpe < 0
    assert mdd >= 0


def test_calculate_metrics_constant_returns_divzero_guard():
    # Zero std dev must not raise; Sharpe & Sortino guard to 0.0.
    returns = pd.Series(np.full(100, 0.01))
    sharpe, sortino, mdd = calculate_metrics(returns)
    assert sharpe == 0.0
    assert sortino == 0.0
    assert mdd >= 0


def test_calculate_metrics_max_drawdown_from_cumulative():
    # Up then down: cumulative peak then trough yields a known drawdown.
    returns = pd.Series([0.1, 0.1, -0.1, -0.1, -0.1])
    _, _, mdd = calculate_metrics(returns)
    cum = returns.cumsum()
    expected = (cum.cummax() - cum).max()
    assert mdd == pytest.approx(expected)
    assert mdd >= 0


# ---------------------------------------------------------------------------
# dynamic_slippage
# ---------------------------------------------------------------------------
def test_dynamic_slippage_zero_volatility_is_base():
    base = 0.001
    assert dynamic_slippage(0.0, base_slippage=base) == pytest.approx(base)


def test_dynamic_slippage_scales_with_volatility():
    base = 0.001
    # slippage = base * (1 + 10 * vol); vol=0.2 -> base * (1 + 2.0)
    assert dynamic_slippage(0.2, base_slippage=base) == pytest.approx(base * (1 + 2.0))
    # Monotonic increase in volatility.
    assert dynamic_slippage(0.5, base_slippage=base) > dynamic_slippage(0.1, base_slippage=base)


# ---------------------------------------------------------------------------
# simulate_latency (sleep disabled)
# ---------------------------------------------------------------------------
def test_simulate_latency_no_sleep_returns_delay():
    # With SIMULATE_LATENCY=0 (autouse fixture) this must return instantly.
    delay = simulate_latency(base_delay=0.5, jitter=0.0)
    assert delay == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# regime_filter
# ---------------------------------------------------------------------------
def test_regime_filter_returns_boolean_series(uptrend_df):
    regime = regime_filter(uptrend_df)
    assert isinstance(regime, pd.Series)
    assert len(regime) == len(uptrend_df)
    assert regime.dtype == bool


def test_regime_filter_true_in_uptrend_false_in_downtrend(uptrend_df, downtrend_df):
    up_regime = regime_filter(uptrend_df)
    down_regime = regime_filter(downtrend_df)
    # Established uptrend region (well past the 200-SMA warmup) should be
    # favorable at least somewhere.
    assert up_regime.iloc[250:].any()
    # A steady downtrend is never above its own 200-SMA -> never favorable.
    assert not down_regime.iloc[200:].any()


# ---------------------------------------------------------------------------
# walk_forward_optimize (pure, offline)
# ---------------------------------------------------------------------------
def test_walk_forward_optimize_returns_config_and_curve(long_uptrend_df):
    """A >=800-row fixture enters the loop and yields a real config + curve.

    This is the critical integration test: the 900-row fixture guarantees at
    least one train/test window runs, so the windowing, dynamic slippage,
    regime masking, scoring, drawdown filter and ``best_config`` construction
    are all genuinely exercised (not short-circuited to the ``None`` branch).
    """
    best, equity_curve = walk_forward_optimize(
        long_uptrend_df,
        ticker="SYNTH",
        strategy_names=["Momentum", "Bollinger_Squeeze"],
        stop_loss_range=[0.05, 0.1],
        train_window_years=2,
        test_window_years=1,
        latency_base_delay=0.0,
        latency_jitter=0.0,
    )
    # The loop MUST have produced a real configuration here.
    assert isinstance(best, dict), "walk-forward loop did not produce a config"
    assert set(best.keys()) == EXPECTED_CONFIG_KEYS
    assert best["ticker"] == "SYNTH"
    assert best["strategy"] in {"Momentum", "Bollinger_Squeeze"}
    assert best["stop_loss"] in {0.05, 0.1}
    # Risk filter: drawdown constraint must hold for any returned config.
    assert best["max_drawdown"] <= 0.25
    # Scoring produces finite Sharpe/Sortino numbers.
    assert np.isfinite(best["sharpe"]) and np.isfinite(best["sortino"])
    # The winning config carries a non-trivial equity (return) curve for the
    # dashboard, one value per test-window bar.
    assert isinstance(equity_curve, list)
    assert len(equity_curve) >= 2
    assert all(np.isfinite(v) for v in equity_curve)


def test_walk_forward_optimize_offline_uptrend(uptrend_df):
    best, equity_curve = walk_forward_optimize(
        uptrend_df,
        ticker="SYNTH",
        strategy_names=["Momentum", "Bollinger_Squeeze"],
        stop_loss_range=[0.05, 0.1],
        train_window_years=2,
        test_window_years=1,
        latency_base_delay=0.0,
        latency_jitter=0.0,
    )
    # Either a fully-formed config or None (if nothing qualifies).
    assert best is None or isinstance(best, dict)
    if best is None:
        assert equity_curve is None
    else:
        assert set(best.keys()) == EXPECTED_CONFIG_KEYS
        assert best["ticker"] == "SYNTH"
        assert best["strategy"] in {"Momentum", "Bollinger_Squeeze"}
        assert best["stop_loss"] in {0.05, 0.1}
        # Risk filter: drawdown constraint must hold for any returned config.
        assert best["max_drawdown"] <= 0.25


def test_walk_forward_optimize_respects_drawdown_limit(mean_reverting_df):
    best, _ = walk_forward_optimize(
        mean_reverting_df,
        ticker="OSC",
        strategy_names=["Momentum", "Bollinger_Squeeze"],
        stop_loss_range=[0.05],
        train_window_years=2,
        test_window_years=1,
        latency_base_delay=0.0,
        latency_jitter=0.0,
    )
    assert best is None or (isinstance(best, dict) and best["max_drawdown"] <= 0.25)


def test_walk_forward_optimize_stop_loss_affects_pnl():
    """Different stop-loss levels must produce different realized metrics.

    A volatile series with real adverse moves means clipping per-period losses
    at ``-sl`` changes the return path, so a tight stop and a loose stop score
    differently. This guards against the stop-loss sweep being cosmetic.
    """
    rng = np.random.default_rng(123)
    n = 900
    # Upward drift with meaningful volatility so stops actually bind.
    steps = rng.normal(0.4, 6.0, n)
    close = 300.0 + np.cumsum(steps)
    close = np.maximum(close, 10.0)  # keep prices positive
    df = _ohlcv_from_close(close)

    # Use the opt-in details channel to read the realized per-config metrics
    # from the sweep. This proves the stop-loss level materially changes the
    # realized P&L path even when the profitability guardrail (Total Return
    # <= 0 => UNPROFITABLE, never selected) prevents a losing config from
    # becoming best_config.
    _, _, tight_details = walk_forward_optimize(
        df,
        ticker="VOL",
        strategy_names=["Momentum"],
        stop_loss_range=[0.01],
        train_window_years=2,
        test_window_years=1,
        latency_base_delay=0.0,
        latency_jitter=0.0,
        max_drawdown_limit=1.0,
        return_details=True,
    )
    _, _, loose_details = walk_forward_optimize(
        df,
        ticker="VOL",
        strategy_names=["Momentum"],
        stop_loss_range=[0.5],
        train_window_years=2,
        test_window_years=1,
        latency_base_delay=0.0,
        latency_jitter=0.0,
        max_drawdown_limit=1.0,
        return_details=True,
    )
    tight_sweep = tight_details["sweep"]
    loose_sweep = loose_details["sweep"]
    assert tight_sweep and loose_sweep
    # The stop-loss level is applied to the return path, so a very tight stop
    # and a very loose stop should not yield identical realized Sharpe values.
    assert tight_sweep[0]["sharpe"] != loose_sweep[0]["sharpe"]
    # And they produce materially different total returns too.
    assert tight_sweep[0]["total_return_pct"] != loose_sweep[0]["total_return_pct"]


# ---------------------------------------------------------------------------
# data_fetcher.normalize_ohlcv (offline)
# ---------------------------------------------------------------------------
def _multiindex_frame(ticker: str, n: int = 30) -> pd.DataFrame:
    idx = pd.bdate_range(start="2020-01-01", periods=n)
    fields = ["Open", "High", "Low", "Close", "Volume"]
    cols = pd.MultiIndex.from_product([fields, [ticker]])
    data = np.column_stack(
        [
            np.full(n, 10.0),  # Open
            np.full(n, 11.0),  # High
            np.full(n, 9.0),   # Low
            np.linspace(10.0, 12.0, n),  # Close
            np.full(n, 1e6),   # Volume
        ]
    )
    return pd.DataFrame(data, index=idx, columns=cols)


def test_normalize_ohlcv_flattens_multiindex():
    raw = _multiindex_frame("AAPL")
    out = normalize_ohlcv(raw, "AAPL")
    assert not isinstance(out.columns, pd.MultiIndex)
    for col in ("Open", "High", "Low", "Close", "Volume"):
        assert col in out.columns
    assert isinstance(out.index, pd.DatetimeIndex)


def test_normalize_ohlcv_empty_raises():
    with pytest.raises(DataFetchError):
        normalize_ohlcv(pd.DataFrame(), "AAPL")


def test_normalize_ohlcv_missing_columns_raises():
    idx = pd.bdate_range(start="2020-01-01", periods=5)
    bad = pd.DataFrame({"Close": np.arange(5.0)}, index=idx)
    with pytest.raises(DataFetchError):
        normalize_ohlcv(bad, "AAPL")


def test_fetch_market_data_uses_injected_downloader_no_network():
    # Inject a fake downloader so no real network call happens.
    raw = _multiindex_frame("MSFT")

    def fake_downloader(ticker, start=None, end=None):
        return raw

    out = fetch_market_data("MSFT", downloader=fake_downloader)
    assert isinstance(out.index, pd.DatetimeIndex)
    assert set(("Open", "High", "Low", "Close", "Volume")).issubset(out.columns)


def test_fetch_market_data_retries_on_rate_limit():
    # First call raises a 429-style error, second returns valid data.
    calls = {"n": 0}
    raw = _multiindex_frame("NFLX")

    def flaky_downloader(ticker, start=None, end=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("429 Too Many Requests")
        return raw

    out = fetch_market_data(
        "NFLX",
        downloader=flaky_downloader,
        base_backoff=0.0,  # no real waiting
        max_backoff=0.0,
    )
    assert calls["n"] == 2
    assert "Close" in out.columns


# ---------------------------------------------------------------------------
# risk_engine: trade stats / total return / CAGR (institutional metrics)
# ---------------------------------------------------------------------------
def test_compute_trade_stats_known_signal_and_returns():
    # Signal: two trades. Trade 1 bars [1,2] (held, exits at index 3),
    # trade 2 bars [5,6] (held, exits at index 7).
    #   index:   0  1  2  3  4  5  6  7  8
    #   signal:  0  1  1  0  0  1  1  0  0
    signal = pd.Series([0, 1, 1, 0, 0, 1, 1, 0, 0])
    # Returns applied per bar. Trade 1 holds bars 1,2 -> 0.02 + 0.03 = 0.05 (win)
    # Trade 2 holds bars 5,6 -> -0.04 + 0.01 = -0.03 (loss)
    returns = pd.Series([0.0, 0.02, 0.03, 0.0, 0.0, -0.04, 0.01, 0.0, 0.0])
    stats = compute_trade_stats(signal, returns)
    assert stats["total_trades"] == 2
    # One winner out of two -> 50% win rate.
    assert stats["win_rate_pct"] == pytest.approx(50.0)
    # Each trade held 2 bars -> avg duration 2.0.
    assert stats["avg_trade_duration_days"] == pytest.approx(2.0)
    assert stats["gross_profit"] == pytest.approx(0.05)
    assert stats["gross_loss"] == pytest.approx(0.03)
    # Profit factor = gross profit / gross loss = 0.05 / 0.03.
    assert stats["profit_factor"] == pytest.approx(0.05 / 0.03)


def test_compute_trade_stats_zero_trades_defaults():
    signal = pd.Series([0, 0, 0, 0])
    returns = pd.Series([0.01, -0.01, 0.0, 0.02])
    stats = compute_trade_stats(signal, returns)
    assert stats["total_trades"] == 0
    assert stats["win_rate_pct"] == 0.0
    assert stats["avg_trade_duration_days"] == 0.0
    assert stats["profit_factor"] == 0.0


def test_compute_trade_stats_zero_loss_sentinel():
    # A single winning trade with no losing trades -> documented sentinel.
    signal = pd.Series([0, 1, 1, 0])
    returns = pd.Series([0.0, 0.02, 0.03, 0.0])
    stats = compute_trade_stats(signal, returns)
    assert stats["total_trades"] == 1
    assert stats["win_rate_pct"] == pytest.approx(100.0)
    assert stats["profit_factor"] == PROFIT_FACTOR_NO_LOSS


def test_compute_trade_stats_exit_at_end_of_series():
    # Still long at the end: trade spans bars [2, 4].
    signal = pd.Series([0, 0, 1, 1, 1])
    returns = pd.Series([0.0, 0.0, 0.01, 0.01, 0.01])
    stats = compute_trade_stats(signal, returns)
    assert stats["total_trades"] == 1
    assert stats["avg_trade_duration_days"] == pytest.approx(3.0)
    assert stats["gross_profit"] == pytest.approx(0.03)


def test_total_return_pct_additive():
    returns = pd.Series([0.01, 0.02, -0.01])
    # Additive convention: sum * 100 = (0.02) * 100 = 2.0.
    assert total_return_pct(returns) == pytest.approx(2.0)


def test_cagr_pct_hand_computed():
    # Total return 20% over 126 periods (half a year of trading days).
    # CAGR = ((1.2) ** (252/126) - 1) * 100 = (1.2**2 - 1) * 100 = 44.0.
    assert cagr_pct(20.0, 126) == pytest.approx(44.0)


def test_cagr_pct_guards():
    assert cagr_pct(10.0, 0) == 0.0
    # Total loss beyond -100% -> full wipeout sentinel.
    assert cagr_pct(-150.0, 252) == -100.0


# ---------------------------------------------------------------------------
# walk_forward_optimize: details channel, guardrail, objective, benchmark
# ---------------------------------------------------------------------------
def test_walk_forward_optimize_without_details_keeps_contract(long_uptrend_df):
    """Regression guard: default call shape and exact 8-key contract hold."""
    best, equity_curve = walk_forward_optimize(
        long_uptrend_df,
        ticker="SYNTH",
        strategy_names=["Momentum", "Bollinger_Squeeze"],
        stop_loss_range=[0.05, 0.1],
        train_window_years=2,
        test_window_years=1,
        latency_base_delay=0.0,
        latency_jitter=0.0,
    )
    assert isinstance(best, dict)
    assert set(best.keys()) == EXPECTED_CONFIG_KEYS
    assert isinstance(equity_curve, list)


def test_walk_forward_optimize_details_structure(long_uptrend_df):
    best, equity_curve, details = walk_forward_optimize(
        long_uptrend_df,
        ticker="SYNTH",
        strategy_names=["Momentum", "Bollinger_Squeeze"],
        stop_loss_range=[0.05, 0.1],
        train_window_years=2,
        test_window_years=1,
        latency_base_delay=0.0,
        latency_jitter=0.0,
        return_details=True,
    )
    # best_config still exactly the 8-key contract.
    assert set(best.keys()) == EXPECTED_CONFIG_KEYS
    for key in (
        "total_return_pct",
        "cagr_pct",
        "profit_factor",
        "win_rate_pct",
        "total_trades",
        "avg_trade_duration_days",
        "benchmark_total_return_pct",
        "benchmark_equity_curve",
        "latency_ms",
        "dynamic_slippage_pct",
        "period_start",
        "period_end",
        "sweep",
        "top10",
    ):
        assert key in details, f"missing details key: {key}"
    # Guardrail: a selected config is profitable.
    assert details["total_return_pct"] > 0
    # Benchmark curve is length-aligned with the strategy equity curve.
    assert len(details["benchmark_equity_curve"]) == len(equity_curve)
    # Top-10 is truncated and ranked by profit factor desc then sharpe desc.
    assert len(details["top10"]) <= 10
    pfs = [(e["profit_factor"], e["sharpe"]) for e in details["top10"]]
    assert pfs == sorted(pfs, reverse=True)


def _const_return_df(per_period_log: float, n: int, start: str, base: float = 100.0):
    """Build an OHLCV frame whose Close grows so pct_change ~= per_period_log."""
    idx = pd.bdate_range(start=start, periods=n)
    close = base * (1.0 + per_period_log) ** np.arange(n)
    spread = np.maximum(np.abs(close) * 0.01, 0.1)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + spread,
            "Low": close - spread,
            "Close": close,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )


def test_walk_forward_optimize_unprofitable_never_selected():
    """A strategy with Total Return <= 0 must be flagged and never selected.

    We construct a falling series so Momentum stays flat (0% strategy return =>
    unprofitable under the guardrail of ``<= 0``). No profitable config exists,
    so best_config must be None while the sweep still records the configs.
    """
    n = 900
    close = 800.0 - np.arange(n) * 0.5
    df = _ohlcv_from_close(close)
    best, equity_curve, details = walk_forward_optimize(
        df,
        ticker="DOWN",
        strategy_names=["Momentum"],
        stop_loss_range=[0.05],
        train_window_years=2,
        test_window_years=1,
        latency_base_delay=0.0,
        latency_jitter=0.0,
        max_drawdown_limit=1.0,
        return_details=True,
    )
    assert best is None
    assert equity_curve is None
    # Every tested config was flagged unprofitable (<=0 total return).
    assert len(details["sweep"]) > 0
    assert all(e["unprofitable"] for e in details["sweep"])


def test_walk_forward_optimize_objective_selects_higher_score(monkeypatch):
    """Among profitable candidates, the higher (CAGR*PF)/(MDD+1e-5) wins.

    We stub the metric helpers so two strategies produce deterministic,
    controlled objective scores and assert the optimizer picks the larger.
    """
    import src.optimizer as opt

    # Make the loop run exactly one window with two strategies.
    df = _ohlcv_from_close(100.0 + np.arange(900) * 1.0)

    # Force a favorable regime everywhere and non-trivial signals.
    monkeypatch.setattr(
        opt, "regime_filter", lambda data: pd.Series(True, index=data.index)
    )

    def fake_apply(data, strategy):
        out = data.copy()
        out["Signal"] = 1
        return out

    monkeypatch.setattr(opt, "apply_strategy", fake_apply)

    # Both profitable, same drawdown; StratB has higher CAGR*PF => should win.
    def fake_calc(returns, risk_free_rate=0.0):
        return 1.0, 1.0, 0.1  # sharpe, sortino, mdd

    monkeypatch.setattr(opt, "calculate_metrics", fake_calc)
    monkeypatch.setattr(opt, "total_return_pct", lambda r: 10.0)  # profitable
    # StratA cagr 10, StratB cagr 30 (same PF via compute_trade_stats stub).
    cagr_by_call = {"n": 0}

    def fake_cagr(total_ret_pct, n_periods):
        cagr_by_call["n"] += 1
        return 10.0 if cagr_by_call["n"] == 1 else 30.0

    monkeypatch.setattr(opt, "cagr_pct", fake_cagr)
    monkeypatch.setattr(
        opt,
        "compute_trade_stats",
        lambda sig, rets: {
            "total_trades": 1,
            "win_rate_pct": 100.0,
            "avg_trade_duration_days": 1.0,
            "gross_profit": 1.0,
            "gross_loss": 0.0,
            "profit_factor": 2.0,
        },
    )

    best, _, details = walk_forward_optimize(
        df,
        ticker="OBJ",
        strategy_names=["StratA", "StratB"],
        stop_loss_range=[0.05],
        train_window_years=2,
        test_window_years=1,
        latency_base_delay=0.0,
        latency_jitter=0.0,
        return_details=True,
    )
    assert best is not None
    # StratB had the higher CAGR and thus higher objective.
    assert best["strategy"] == "StratB"


def test_run_walk_forward_details_opt_in(long_uptrend_df):
    from src.optimizer import run_walk_forward

    result = run_walk_forward(
        ticker="SYNTH",
        strategy_names=["Momentum", "Bollinger_Squeeze"],
        stop_loss_range=[0.05, 0.1],
        train_window_years=2,
        test_window_years=1,
        latency_base_delay=0.0,
        latency_jitter=0.0,
        data=long_uptrend_df,
        return_equity_curve=True,
        return_details=True,
    )
    assert len(result) == 3
    best, equity_curve, details = result
    assert set(best.keys()) == EXPECTED_CONFIG_KEYS
    assert "top10" in details and "sweep" in details

    # Default contract unchanged: scalar dict by default.
    best_only = run_walk_forward(
        ticker="SYNTH",
        strategy_names=["Momentum"],
        stop_loss_range=[0.05],
        train_window_years=2,
        test_window_years=1,
        latency_base_delay=0.0,
        latency_jitter=0.0,
        data=long_uptrend_df,
    )
    assert best_only is None or set(best_only.keys()) == EXPECTED_CONFIG_KEYS
