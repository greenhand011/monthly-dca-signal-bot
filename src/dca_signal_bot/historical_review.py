from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .config import StrategyConfig
from .indicators import compute_ticker_indicators
from .reserve_state import ReserveState
from .strategy_engine import evaluate_strategy


@dataclass(frozen=True)
class HistoricalSignalReviewRow:
    month: str
    status: str
    base_monthly_rmb: int
    suggested_total_rmb: int
    spym_rmb: int
    qqqm_rmb: int
    reserve_cash_delta_rmb: int
    reserve_cash_balance_rmb: int
    key_trigger_summary: str
    short_reason: str
    latest_market_date: date


@dataclass(frozen=True)
class HistoricalSignalReview:
    months: int
    note: str
    rows: list[HistoricalSignalReviewRow]


def _monthly_cutoff_dates(history: pd.DataFrame, months: int) -> list[pd.Timestamp]:
    if history.empty:
        return []

    normalized = pd.to_datetime(history.index).sort_values()
    month_periods = normalized.to_period("M")
    cutoffs: list[pd.Timestamp] = []
    for period in month_periods.unique():
        period_rows = normalized[month_periods == period]
        if len(period_rows) > 0:
            cutoffs.append(pd.Timestamp(period_rows[-1]))
    return cutoffs[-months:]


def build_historical_signal_review(
    *,
    config: StrategyConfig,
    core_history: pd.DataFrame,
    growth_history: pd.DataFrame,
    months: int = 12,
) -> HistoricalSignalReview:
    months = max(1, int(months))
    cutoff_dates = _monthly_cutoff_dates(growth_history, months)
    rows: list[HistoricalSignalReviewRow] = []
    simulated_state = ReserveState(reserve_cash_rmb=0)

    for cutoff in cutoff_dates:
        core_slice = core_history.loc[:cutoff]
        growth_slice = growth_history.loc[:cutoff]
        if core_slice.empty or growth_slice.empty:
            continue

        core_indicators = compute_ticker_indicators(core_slice, config.core_ticker)
        growth_indicators = compute_ticker_indicators(growth_slice, config.growth_ticker)
        decision = evaluate_strategy(
            config=config,
            core_indicators=core_indicators,
            growth_indicators=growth_indicators,
            reserve_state=simulated_state,
        )
        simulated_state = ReserveState(reserve_cash_rmb=decision.reserve_cash_after_rmb)

        rows.append(
            HistoricalSignalReviewRow(
                month=f"{cutoff:%Y-%m}",
                status=decision.state_label,
                base_monthly_rmb=config.base_monthly_rmb,
                suggested_total_rmb=decision.recommendation_total_rmb,
                spym_rmb=decision.allocation.core_rmb,
                qqqm_rmb=decision.allocation.growth_rmb,
                reserve_cash_delta_rmb=decision.reserve_delta_rmb,
                reserve_cash_balance_rmb=decision.reserve_cash_after_rmb,
                key_trigger_summary=decision.triggered_rule,
                short_reason=decision.reasons[-1],
                latest_market_date=pd.to_datetime(cutoff).date(),
            )
        )

    note = (
        f"Signal-only historical review for the most recent {len(rows)} month-end snapshots; "
        "reserve balance is hypothetically reconstructed from the review window start at 0 RMB."
    )
    return HistoricalSignalReview(months=len(rows), note=note, rows=rows)
