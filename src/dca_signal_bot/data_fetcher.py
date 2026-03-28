from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


DATA_SOURCE = "Yahoo Finance via yfinance"
MIN_HISTORY_ROWS = 756
MAX_DATA_AGE_DAYS = 10


class DataFetchError(RuntimeError):
    """Raised when market data cannot be fetched or normalized."""


class MarketDataValidationError(DataFetchError):
    """Raised when fetched market data fails integrity checks."""


@dataclass(frozen=True)
class TickerHistory:
    ticker: str
    history: pd.DataFrame
    latest_market_date: date
    row_count: int


@dataclass(frozen=True)
class MarketDataBundle:
    data_source: str
    fetched_at_utc: datetime
    validation_status: str
    histories: dict[str, TickerHistory]

    def latest_market_date_for(self, ticker: str) -> date:
        return self.histories[ticker].latest_market_date


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _configure_yfinance_cache() -> None:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise DataFetchError("yfinance is required to fetch price history") from exc

    cache_dir = Path.cwd() / ".yfinance-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(yf, "set_cache_location"):
        yf.set_cache_location(str(cache_dir))
    elif hasattr(yf, "set_tz_cache_location"):
        yf.set_tz_cache_location(str(cache_dir))


def _ensure_ticker_symbol(ticker: str) -> str:
    if not isinstance(ticker, str) or not ticker.strip():
        raise DataFetchError("Ticker symbol is missing or invalid")
    return ticker.strip().upper()


def _normalize_history_dataframe(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if not isinstance(data, pd.DataFrame):
        raise DataFetchError(f"{ticker}: yfinance returned a non-DataFrame history object")

    if data.empty:
        raise DataFetchError(f"{ticker}: price history is empty")

    data = data.copy()
    if "Close" not in data.columns:
        if "Adj Close" in data.columns:
            data["Close"] = data["Adj Close"]
        else:
            raise DataFetchError(f"{ticker}: history does not contain a Close or Adj Close column")

    history = data[["Close"]].rename(columns={"Close": "close"})
    history.index = pd.to_datetime(history.index, utc=False)
    history = history.sort_index()
    if "close" not in history.columns:
        raise DataFetchError(f"{ticker}: normalized history is missing a close column")
    if history["close"].isna().all():
        raise DataFetchError(f"{ticker}: close series contains only NaN values")
    history = history.dropna(how="all")
    if history.empty:
        raise DataFetchError(f"{ticker}: normalized history is empty")

    return history


def fetch_price_history(ticker: str, period: str = "4y", interval: str = "1d") -> pd.DataFrame:
    ticker = _ensure_ticker_symbol(ticker)

    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise DataFetchError("yfinance is required to fetch price history") from exc

    _configure_yfinance_cache()
    try:
        data = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True, actions=False)
    except Exception as exc:  # pragma: no cover - network/provider failures
        raise DataFetchError(f"{ticker}: failed to fetch price history from Yahoo Finance: {exc}") from exc
    return _normalize_history_dataframe(data, ticker)


def validate_price_history(
    history: pd.DataFrame,
    *,
    ticker: str,
    reference_date: date,
    min_rows: int = MIN_HISTORY_ROWS,
    max_age_days: int = MAX_DATA_AGE_DAYS,
) -> TickerHistory:
    ticker = _ensure_ticker_symbol(ticker)
    normalized = _normalize_history_dataframe(history, ticker)

    row_count = int(len(normalized))
    if row_count < min_rows:
        raise MarketDataValidationError(
            f"{ticker}: history length {row_count} is below required minimum {min_rows}"
        )

    latest_market_date = pd.to_datetime(normalized.index[-1]).date()
    age_days = (reference_date - latest_market_date).days
    if age_days < 0:
        raise MarketDataValidationError(
            f"{ticker}: latest market date {latest_market_date.isoformat()} is in the future relative to {reference_date.isoformat()}"
        )
    if age_days > max_age_days:
        raise MarketDataValidationError(
            f"{ticker}: latest market date {latest_market_date.isoformat()} is too old for reference date {reference_date.isoformat()} (age {age_days} days)"
        )

    return TickerHistory(
        ticker=ticker,
        history=normalized,
        latest_market_date=latest_market_date,
        row_count=row_count,
    )


def fetch_histories(
    tickers: list[str],
    *,
    reference_date: date,
    fetched_at_utc: datetime | None = None,
    min_rows: int = MIN_HISTORY_ROWS,
    max_age_days: int = MAX_DATA_AGE_DAYS,
) -> MarketDataBundle:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise DataFetchError("yfinance is required to fetch price history") from exc

    fetched_at_utc = fetched_at_utc or _utc_now()
    _configure_yfinance_cache()
    histories: dict[str, TickerHistory] = {}

    for raw_ticker in tickers:
        ticker = _ensure_ticker_symbol(raw_ticker)
        try:
            data = yf.Ticker(ticker).history(period="4y", interval="1d", auto_adjust=True, actions=False)
        except Exception as exc:  # pragma: no cover - network/provider failures
            raise DataFetchError(f"{ticker}: failed to fetch price history from Yahoo Finance: {exc}") from exc
        validated = validate_price_history(
            data,
            ticker=ticker,
            reference_date=reference_date,
            min_rows=min_rows,
            max_age_days=max_age_days,
        )
        histories[ticker] = validated

    return MarketDataBundle(
        data_source=DATA_SOURCE,
        fetched_at_utc=fetched_at_utc,
        validation_status="PASS",
        histories=histories,
    )
