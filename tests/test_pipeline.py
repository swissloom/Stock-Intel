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
    calculate_metrics,
    dynamic_slippage,
    regime_filter,
    simulate_latency,
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
def test_walk_forward_optimize_offline_uptrend(uptrend_df):
    best = walk_forward_optimize(
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
    if best is not None:
        assert set(best.keys()) == EXPECTED_CONFIG_KEYS
        assert best["ticker"] == "SYNTH"
        assert best["strategy"] in {"Momentum", "Bollinger_Squeeze"}
        assert best["stop_loss"] in {0.05, 0.1}
        # Risk filter: drawdown constraint must hold for any returned config.
        assert best["max_drawdown"] <= 0.25


def test_walk_forward_optimize_respects_drawdown_limit(mean_reverting_df):
    best = walk_forward_optimize(
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
