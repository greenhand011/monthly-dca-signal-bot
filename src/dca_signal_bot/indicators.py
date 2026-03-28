from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data_fetcher import MIN_HISTORY_ROWS


@dataclass(frozen=True)
class TickerIndicators:
    ticker: str
    latest_date: pd.Timestamp
    current_price: float
    high_52w: float
    drawdown_52w: float
    sma200: float
    deviation_from_sma200: float
    sma20: float
    deviation_from_sma20: float
    rsi14: float
    price_percentile_3y: float


class IndicatorComputationError(ValueError):
    """Raised when indicator calculation cannot proceed with the provided history."""


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    flat_mask = (avg_gain == 0) & (avg_loss == 0)
    rising_mask = (avg_gain > 0) & (avg_loss == 0)
    falling_mask = (avg_gain == 0) & (avg_loss > 0)
    rsi = rsi.where(~flat_mask, 50.0)
    rsi = rsi.where(~rising_mask, 100.0)
    rsi = rsi.where(~falling_mask, 0.0)
    rsi = rsi.fillna(50.0)
    return rsi


def _percentile_of_last_value(values: pd.Series) -> float:
    if values.empty:
        return float("nan")
    latest = float(values.iloc[-1])
    rank = float((values <= latest).sum()) / float(len(values))
    return round(rank * 100, 2)


def compute_ticker_indicators(history: pd.DataFrame, ticker: str) -> TickerIndicators:
    if "close" not in history.columns:
        raise IndicatorComputationError("history must contain a close column")

    close = history["close"].astype(float).dropna()
    if len(close) < MIN_HISTORY_ROWS:
        raise IndicatorComputationError(
            f"Not enough data to compute indicators for {ticker}: "
            f"need at least {MIN_HISTORY_ROWS} rows, got {len(close)}"
        )

    latest_date = pd.to_datetime(close.index[-1])
    current_price = float(close.iloc[-1])

    trailing_52w = close.tail(252)
    if len(trailing_52w) < 252:
        raise IndicatorComputationError(f"Not enough data to compute 52-week drawdown for {ticker}")
    high_52w = float(trailing_52w.max())
    drawdown_52w = max(0.0, 1 - (current_price / high_52w)) if high_52w > 0 else float("nan")

    sma200 = float(close.rolling(window=200, min_periods=200).mean().iloc[-1])
    sma20 = float(close.rolling(window=20, min_periods=20).mean().iloc[-1])

    deviation_from_sma200 = (current_price / sma200) - 1 if sma200 else float("nan")
    deviation_from_sma20 = (current_price / sma20) - 1 if sma20 else float("nan")
    rsi14 = float(compute_rsi(close, period=14).iloc[-1])

    trailing_3y = close.tail(756)
    if len(trailing_3y) < MIN_HISTORY_ROWS:
        raise IndicatorComputationError(f"Not enough data to compute 3-year price percentile for {ticker}")
    price_percentile_3y = _percentile_of_last_value(trailing_3y)

    return TickerIndicators(
        ticker=ticker,
        latest_date=latest_date,
        current_price=current_price,
        high_52w=high_52w,
        drawdown_52w=drawdown_52w,
        sma200=sma200,
        deviation_from_sma200=deviation_from_sma200,
        sma20=sma20,
        deviation_from_sma20=deviation_from_sma20,
        rsi14=rsi14,
        price_percentile_3y=price_percentile_3y,
    )
