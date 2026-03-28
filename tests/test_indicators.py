from __future__ import annotations

import pandas as pd
import pytest

from dca_signal_bot.data_fetcher import DataFetchError, MarketDataValidationError, validate_price_history
from dca_signal_bot.indicators import compute_rsi, compute_ticker_indicators


def test_compute_rsi_returns_series_with_expected_length():
    close = pd.Series(range(1, 31), dtype=float)
    rsi = compute_rsi(close, period=14)
    assert len(rsi) == len(close)
    assert rsi.iloc[-1] == 100.0


def test_compute_ticker_indicators_requires_sufficient_history():
    idx = pd.date_range("2022-01-03", periods=800, freq="B")
    close = pd.Series(range(100, 900), index=idx, dtype=float)
    history = pd.DataFrame({"close": close})

    indicators = compute_ticker_indicators(history, "QQQM")

    assert indicators.ticker == "QQQM"
    assert indicators.current_price == float(close.iloc[-1])
    assert indicators.high_52w == float(close.tail(252).max())
    assert indicators.drawdown_52w == 0.0
    assert indicators.price_percentile_3y == 100.0


def test_compute_ticker_indicators_raises_on_short_history():
    idx = pd.date_range("2025-01-01", periods=700, freq="B")
    close = pd.Series(range(100, 800), index=idx, dtype=float)
    history = pd.DataFrame({"close": close})

    with pytest.raises(ValueError, match="Not enough data to compute indicators"):
        compute_ticker_indicators(history, "QQQM")


def test_validate_price_history_raises_on_empty_history():
    with pytest.raises(DataFetchError, match="price history is empty"):
        validate_price_history(pd.DataFrame(), ticker="QQQM", reference_date=pd.Timestamp("2026-03-28").date())


def test_validate_price_history_raises_on_missing_close_column():
    idx = pd.date_range("2026-03-01", periods=5, freq="B")
    history = pd.DataFrame({"open": [1, 2, 3, 4, 5]}, index=idx)
    with pytest.raises(DataFetchError, match="does not contain a Close or Adj Close column"):
        validate_price_history(history, ticker="QQQM", reference_date=pd.Timestamp("2026-03-28").date())


def test_validate_price_history_raises_on_missing_ticker():
    history = pd.DataFrame({"close": [1.0, 2.0, 3.0]}, index=pd.date_range("2026-01-01", periods=3, freq="B"))
    with pytest.raises(DataFetchError, match="Ticker symbol is missing or invalid"):
        validate_price_history(history, ticker="", reference_date=pd.Timestamp("2026-03-28").date())


def test_validate_price_history_raises_on_all_nan_close_series():
    idx = pd.date_range("2026-03-01", periods=5, freq="B")
    history = pd.DataFrame({"Close": [float("nan")] * 5}, index=idx)
    with pytest.raises(DataFetchError, match="contains only NaN values"):
        validate_price_history(history, ticker="QQQM", reference_date=pd.Timestamp("2026-03-28").date())


def test_validate_price_history_raises_on_stale_data():
    idx = pd.date_range(end="2026-03-01", periods=800, freq="B")
    history = pd.DataFrame({"Close": range(800)}, index=idx)
    with pytest.raises(MarketDataValidationError, match="too old"):
        validate_price_history(history, ticker="QQQM", reference_date=pd.Timestamp("2026-03-28").date())
