from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd


FX_SOURCE = "Yahoo Finance via yfinance"
FX_PAIR_TICKER = "CNY=X"
FX_PAIR_DESCRIPTION = "CNY per USD"
FX_MAX_DATA_AGE_DAYS = 10


class FxConversionError(RuntimeError):
    """Raised when FX data cannot be fetched or validated."""


@dataclass(frozen=True)
class FxRateSnapshot:
    source: str
    pair_ticker: str
    pair_description: str
    fetched_at_utc: datetime
    latest_market_date: date
    rate_cny_per_usd: float


@dataclass(frozen=True)
class FxConversionSummary:
    source: str
    pair_ticker: str
    pair_description: str
    fetched_at_utc: datetime
    latest_market_date: date | None
    validation_status: str
    rate_cny_per_usd: float | None
    total_rmb: int
    core_rmb: int
    growth_rmb: int
    total_usd: float | None
    core_usd: float | None
    growth_usd: float | None
    note: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _configure_yfinance_cache() -> None:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise FxConversionError("yfinance is required to fetch FX data") from exc

    cache_dir = Path.cwd() / ".yfinance-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(yf, "set_cache_location"):
        yf.set_cache_location(str(cache_dir))
    elif hasattr(yf, "set_tz_cache_location"):
        yf.set_tz_cache_location(str(cache_dir))


def _normalize_history_dataframe(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if not isinstance(data, pd.DataFrame):
        raise FxConversionError(f"{ticker}: yfinance returned a non-DataFrame history object")
    if data.empty:
        raise FxConversionError(f"{ticker}: FX history is empty")

    data = data.copy()
    if "Close" not in data.columns:
        if "Adj Close" in data.columns:
            data["Close"] = data["Adj Close"]
        else:
            raise FxConversionError(f"{ticker}: history does not contain a Close or Adj Close column")

    history = data[["Close"]].rename(columns={"Close": "close"})
    history.index = pd.to_datetime(history.index, utc=False)
    history = history.sort_index()
    if history["close"].isna().all():
        raise FxConversionError(f"{ticker}: close series contains only NaN values")
    history = history.dropna(how="all")
    if history.empty:
        raise FxConversionError(f"{ticker}: normalized FX history is empty")
    return history


def _fetch_fx_history(ticker: str = FX_PAIR_TICKER, period: str = "1mo", interval: str = "1d") -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise FxConversionError("yfinance is required to fetch FX data") from exc

    _configure_yfinance_cache()
    try:
        data = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True, actions=False)
    except Exception as exc:  # pragma: no cover - network/provider failures
        raise FxConversionError(f"{ticker}: failed to fetch FX data from Yahoo Finance: {exc}") from exc
    return _normalize_history_dataframe(data, ticker)


def fetch_fx_rate(
    *,
    reference_date: date,
    fetched_at_utc: datetime | None = None,
    ticker: str = FX_PAIR_TICKER,
) -> FxRateSnapshot:
    fetched_at_utc = fetched_at_utc or _utc_now()
    if fetched_at_utc.tzinfo is None:
        fetched_at_utc = fetched_at_utc.replace(tzinfo=timezone.utc)

    history = _fetch_fx_history(ticker=ticker)
    if "close" not in history.columns:
        if "Close" in history.columns:
            history = history.rename(columns={"Close": "close"})
        elif "Adj Close" in history.columns:
            history = history.rename(columns={"Adj Close": "close"})
        else:
            raise FxConversionError(f"{ticker}: FX history is missing a close column")
    row_count = len(history)
    if row_count < 1:
        raise FxConversionError(f"{ticker}: FX history does not contain usable rows")

    latest_market_date = pd.to_datetime(history.index[-1]).date()
    age_days = (reference_date - latest_market_date).days
    if age_days < 0:
        raise FxConversionError(
            f"{ticker}: latest FX market date {latest_market_date.isoformat()} is in the future relative to {reference_date.isoformat()}"
        )
    if age_days > FX_MAX_DATA_AGE_DAYS:
        raise FxConversionError(
            f"{ticker}: latest FX market date {latest_market_date.isoformat()} is too old for reference date {reference_date.isoformat()} (age {age_days} days)"
        )

    rate = float(history["close"].iloc[-1])
    if rate <= 1 or rate > 20:
        raise FxConversionError(
            f"{ticker}: unexpected FX rate direction or value ({rate:.6f}); expected CNY per USD"
        )

    return FxRateSnapshot(
        source=FX_SOURCE,
        pair_ticker=ticker,
        pair_description=FX_PAIR_DESCRIPTION,
        fetched_at_utc=fetched_at_utc,
        latest_market_date=latest_market_date,
        rate_cny_per_usd=rate,
    )


def convert_rmb_to_usd(amount_rmb: int, rate_cny_per_usd: float) -> float:
    return round(float(amount_rmb) / float(rate_cny_per_usd), 2)


def build_fx_conversion_summary(
    *,
    total_rmb: int,
    core_rmb: int,
    growth_rmb: int,
    reference_date: date,
    fetched_at_utc: datetime | None = None,
    ticker: str = FX_PAIR_TICKER,
) -> FxConversionSummary:
    fetched_at_utc = fetched_at_utc or _utc_now()
    try:
        snapshot = fetch_fx_rate(reference_date=reference_date, fetched_at_utc=fetched_at_utc, ticker=ticker)
    except FxConversionError as exc:
        return FxConversionSummary(
            source=FX_SOURCE,
            pair_ticker=ticker,
            pair_description=FX_PAIR_DESCRIPTION,
            fetched_at_utc=fetched_at_utc,
            latest_market_date=None,
            validation_status="FAIL",
            rate_cny_per_usd=None,
            total_rmb=total_rmb,
            core_rmb=core_rmb,
            growth_rmb=growth_rmb,
            total_usd=None,
            core_usd=None,
            growth_usd=None,
            note=f"由于汇率抓取或校验失败，美元估算不可用：{exc}",
        )

    total_usd = convert_rmb_to_usd(total_rmb, snapshot.rate_cny_per_usd)
    core_usd = convert_rmb_to_usd(core_rmb, snapshot.rate_cny_per_usd)
    growth_usd = convert_rmb_to_usd(growth_rmb, snapshot.rate_cny_per_usd)
    return FxConversionSummary(
        source=snapshot.source,
        pair_ticker=snapshot.pair_ticker,
        pair_description=snapshot.pair_description,
        fetched_at_utc=snapshot.fetched_at_utc,
        latest_market_date=snapshot.latest_market_date,
        validation_status="PASS",
        rate_cny_per_usd=snapshot.rate_cny_per_usd,
        total_rmb=total_rmb,
        core_rmb=core_rmb,
        growth_rmb=growth_rmb,
        total_usd=total_usd,
        core_usd=core_usd,
        growth_usd=growth_usd,
        note="汇率换算完成。",
    )


def format_rmb_usd_estimate(rmb_amount: int, usd_amount: float | None) -> str:
    if usd_amount is None:
        return f"{rmb_amount} RMB（美元估算不可用）"
    return f"{rmb_amount} RMB（约 USD {usd_amount:.2f}）"
