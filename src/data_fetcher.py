"""Market data download & validation.

Wraps :func:`yfinance.download` with:

* exponential-backoff retries on HTTP 429 / rate-limit errors (per the project
  data standard), and
* a pure :func:`normalize_ohlcv` function that flattens a MultiIndex column
  frame, enforces a ``DatetimeIndex`` and validates the required OHLCV columns.

Keeping normalization/validation in :func:`normalize_ohlcv` (which accepts an
in-memory DataFrame) means the parsing logic can be unit-tested fully offline,
while :func:`fetch_market_data` handles the networked download + retry loop.
"""

from __future__ import annotations

import time

import pandas as pd

try:  # yfinance is required for live fetches but not for offline tests.
    import yfinance as yf
except Exception:  # pragma: no cover - import guard for offline environments
    yf = None

REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")

# Backoff defaults for rate-limit handling.
DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_BACKOFF = 1.0  # seconds; doubled on each retry (capped).
DEFAULT_MAX_BACKOFF = 30.0  # seconds; ceiling for the exponential backoff.

# Default liquid benchmark universe scanned by the multi-ticker pipeline.
DEFAULT_UNIVERSE = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "SPY")


class DataFetchError(RuntimeError):
    """Raised when market data cannot be fetched or fails validation."""


def _is_rate_limit_error(exc: Exception) -> bool:
    """Heuristically detect HTTP 429 / rate-limit style errors."""
    text = str(exc).lower()
    markers = ("429", "too many requests", "rate limit", "rate-limit", "ratelimited")
    if any(marker in text for marker in markers):
        return True
    # yfinance >= 0.2 raises a dedicated exception type for rate limiting.
    if yf is not None:
        rl_exc = getattr(getattr(yf, "exceptions", None), "YFRateLimitError", None)
        if rl_exc is not None and isinstance(exc, rl_exc):
            return True
    return type(exc).__name__ in {"YFRateLimitError"}


def normalize_ohlcv(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Flatten, index and validate a raw yfinance OHLCV frame.

    Parameters
    ----------
    data:
        Raw frame as returned by :func:`yfinance.download`. May carry a
        ``(field, ticker)`` MultiIndex column structure.
    ticker:
        Symbol used to select the correct slice from a MultiIndex frame.

    Returns
    -------
    pandas.DataFrame
        Single-level OHLCV frame with a ``DatetimeIndex``.

    Raises
    ------
    DataFetchError
        If the frame is empty, missing required columns, or otherwise invalid.
    """
    if data is None or len(data) == 0:
        raise DataFetchError(f"No market data returned for ticker '{ticker}'.")

    df = data.copy()

    # Flatten the MultiIndex (field, ticker) column structure if present.
    if isinstance(df.columns, pd.MultiIndex):
        if ticker in df.columns.get_level_values(-1):
            df = df.xs(ticker, axis=1, level=1)
        else:
            # Collapse to the first level so single-ticker frames still work.
            df.columns = df.columns.get_level_values(0)

    # Ensure a DatetimeIndex so downstream rolling/windowing behaves correctly.
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise DataFetchError(
            f"Market data for '{ticker}' is missing required columns: {missing}. "
            f"Got columns: {list(df.columns)}"
        )

    if df["Close"].dropna().empty:
        raise DataFetchError(
            f"Market data for '{ticker}' contains no usable Close prices."
        )

    return df


def fetch_market_data(
    ticker: str,
    start: str = "2020-01-01",
    end: str = "2026-01-01",
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_backoff: float = DEFAULT_BASE_BACKOFF,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
    downloader=None,
) -> pd.DataFrame:
    """Download and validate OHLCV data for ``ticker`` with 429 backoff.

    On HTTP 429 / rate-limit errors the call is retried with exponential
    backoff (``base_backoff * 2**attempt`` capped at ``max_backoff``), up to
    ``max_retries`` attempts. Any other exception is re-raised immediately as a
    :class:`DataFetchError`.

    Parameters
    ----------
    downloader:
        Optional callable with the same signature as ``yf.download`` used for
        dependency injection in tests. Defaults to :func:`yfinance.download`.
    """
    if downloader is None:
        if yf is None:
            raise DataFetchError(
                "yfinance is not available; cannot fetch live market data."
            )
        downloader = yf.download

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            raw = downloader(ticker, start=start, end=end)
            return normalize_ohlcv(raw, ticker)
        except DataFetchError:
            # Validation failures are deterministic; do not retry.
            raise
        except Exception as exc:  # noqa: BLE001 - we classify below
            last_exc = exc
            if _is_rate_limit_error(exc) and attempt < max_retries - 1:
                backoff = min(base_backoff * (2 ** attempt), max_backoff)
                print(
                    f"[!] Rate limited while fetching '{ticker}' "
                    f"(attempt {attempt + 1}/{max_retries}). "
                    f"Backing off {backoff:.1f}s..."
                )
                time.sleep(backoff)
                continue
            break

    raise DataFetchError(
        f"Failed to fetch market data for '{ticker}' after {max_retries} "
        f"attempt(s): {last_exc}"
    ) from last_exc


def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Clean a single normalized OHLCV frame for backtesting.

    * Sorts by the DatetimeIndex (ascending).
    * Drops exact-duplicate index rows (keeps the last).
    * Forward-then-back fills interior gaps in the OHLC price columns, then
      drops any rows that still carry a NaN ``Close`` (leading gaps with no
      prior value to carry forward).
    * Fills missing ``Volume`` with ``0.0``.

    The function is pure (no network) so it is unit-testable offline.
    """
    out = df.copy()
    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]

    price_cols = [c for c in ("Open", "High", "Low", "Close") if c in out.columns]
    if price_cols:
        out[price_cols] = out[price_cols].ffill().bfill()
    if "Volume" in out.columns:
        out["Volume"] = out["Volume"].fillna(0.0)

    out = out.dropna(subset=["Close"])
    return out


def align_universe(frames: dict) -> dict:
    """Align a mapping of ``{ticker: OHLCV DataFrame}`` onto a shared calendar.

    All frames are reindexed onto the **intersection** of their DatetimeIndexes
    (the set of dates for which every ticker has data), so cross-sectional and
    comparative logic operates on genuinely contemporaneous bars. Each reindexed
    frame is then cleaned via :func:`clean_ohlcv`.

    Parameters
    ----------
    frames:
        Mapping of ticker symbol -> cleaned/normalized OHLCV DataFrame. Empty
        or ``None`` frames are ignored.

    Returns
    -------
    dict
        ``{ticker: aligned DataFrame}`` restricted to the shared date index.
        Returns an empty dict when there is no common date range.
    """
    usable = {
        t: f for t, f in frames.items()
        if f is not None and len(f) > 0 and isinstance(f.index, pd.DatetimeIndex)
    }
    if not usable:
        return {}

    common_index = None
    for frame in usable.values():
        idx = frame.index
        common_index = idx if common_index is None else common_index.intersection(idx)

    if common_index is None or len(common_index) == 0:
        return {}

    common_index = common_index.sort_values()
    aligned = {}
    for ticker, frame in usable.items():
        aligned[ticker] = clean_ohlcv(frame.reindex(common_index))
    return aligned


def fetch_universe(
    tickers=DEFAULT_UNIVERSE,
    start: str = "2020-01-01",
    end: str = "2026-01-01",
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_backoff: float = DEFAULT_BASE_BACKOFF,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
    downloader=None,
    align: bool = True,
) -> dict:
    """Download, validate and (optionally) align a basket of tickers.

    Each ticker is fetched through :func:`fetch_market_data`, so the per-ticker
    HTTP 429 exponential-backoff retry logic (the project data standard) is
    reused unchanged. A single ticker that fails all retries is skipped with a
    warning rather than aborting the whole universe download, so one bad symbol
    never sinks the run.

    Parameters
    ----------
    tickers:
        Iterable of ticker symbols. Defaults to :data:`DEFAULT_UNIVERSE`.
    align:
        When ``True`` (default) the surviving frames are reindexed onto their
        shared trading calendar via :func:`align_universe` so every ticker is
        aligned bar-for-bar.

    Returns
    -------
    dict
        ``{ticker: OHLCV DataFrame}`` for every ticker that downloaded and
        validated successfully.

    Raises
    ------
    DataFetchError
        Only when **no** ticker in the basket could be fetched at all.
    """
    frames: dict = {}
    errors: dict = {}
    for ticker in tickers:
        try:
            frames[ticker] = fetch_market_data(
                ticker,
                start=start,
                end=end,
                max_retries=max_retries,
                base_backoff=base_backoff,
                max_backoff=max_backoff,
                downloader=downloader,
            )
        except DataFetchError as exc:
            errors[ticker] = str(exc)
            print(f"[!] Skipping '{ticker}': {exc}")

    if not frames:
        raise DataFetchError(
            f"Failed to fetch any ticker in the universe {list(tickers)}. "
            f"Errors: {errors}"
        )

    if align:
        frames = align_universe(frames)
        if not frames:
            raise DataFetchError(
                "No overlapping trading dates across the fetched universe; "
                "cannot align the basket onto a shared calendar."
            )

    return frames
