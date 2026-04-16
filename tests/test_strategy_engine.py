from __future__ import annotations

from dataclasses import replace

import pandas as pd

from dca_signal_bot.config import apply_base_override, load_strategy_config
from dca_signal_bot.indicators import TickerIndicators
from dca_signal_bot.reserve_state import ReserveState
from dca_signal_bot.strategy_engine import evaluate_strategy


def _indicator(
    ticker: str,
    *,
    current_price: float,
    high_52w: float,
    drawdown_52w: float,
    sma200: float,
    deviation_from_sma200: float,
    sma20: float,
    deviation_from_sma20: float,
    rsi14: float,
    price_percentile_3y: float,
) -> TickerIndicators:
    return TickerIndicators(
        ticker=ticker,
        latest_date=pd.Timestamp("2026-03-28"),
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


def _voo_indicator() -> TickerIndicators:
    return _indicator(
        "VOO",
        current_price=500.0,
        high_52w=620.0,
        drawdown_52w=0.1935,
        sma200=530.0,
        deviation_from_sma200=-0.0566,
        sma20=505.0,
        deviation_from_sma20=-0.0099,
        rsi14=42.0,
        price_percentile_3y=35.0,
    )


def _vxus_indicator() -> TickerIndicators:
    return _indicator(
        "VXUS",
        current_price=60.0,
        high_52w=65.5,
        drawdown_52w=0.0840,
        sma200=59.5,
        deviation_from_sma200=0.0084,
        sma20=60.2,
        deviation_from_sma20=-0.0033,
        rsi14=51.0,
        price_percentile_3y=55.0,
    )


def _qqqm_indicator() -> TickerIndicators:
    return _indicator(
        "QQQM",
        current_price=210.0,
        high_52w=214.0,
        drawdown_52w=0.0187,
        sma200=198.0,
        deviation_from_sma200=0.0606,
        sma20=208.0,
        deviation_from_sma20=0.0096,
        rsi14=74.0,
        price_percentile_3y=92.0,
    )


def _strong_heat_indicator(ticker: str) -> TickerIndicators:
    return _indicator(
        ticker,
        current_price=210.0,
        high_52w=214.0,
        drawdown_52w=0.0187,
        sma200=198.0,
        deviation_from_sma200=0.0606,
        sma20=208.0,
        deviation_from_sma20=0.0096,
        rsi14=74.0,
        price_percentile_3y=92.0,
    )


def test_manual_total_mode_evaluates_assets_independently_and_keeps_total_fixed():
    config = load_strategy_config("config/strategy.yaml")

    result = evaluate_strategy(
        config,
        _voo_indicator(),
        _qqqm_indicator(),
        ReserveState(reserve_cash_rmb=500),
        secondary_indicators=_vxus_indicator(),
    )

    assert result.strategy_mode == "manual_total_per_asset_signal"
    assert result.total_is_fixed is True
    assert result.recommendation_total_rmb == 3000
    assert result.allocation.core_rmb + result.allocation.secondary_rmb + result.allocation.growth_rmb == 3000
    assert result.reserve_delta_rmb == 0
    assert result.reserve_cash_after_rmb == 500
    assert len(result.asset_signals) == 3


def test_manual_total_mode_produces_per_asset_independent_classifications():
    config = load_strategy_config("config/strategy.yaml")

    result = evaluate_strategy(
        config,
        _voo_indicator(),
        _qqqm_indicator(),
        ReserveState(reserve_cash_rmb=0),
        secondary_indicators=_vxus_indicator(),
    )
    signals = {signal.ticker: signal for signal in result.asset_signals}

    assert signals["VOO"].classification == "OVERWEIGHT"
    assert signals["VXUS"].classification == "NEUTRAL"
    assert signals["QQQM"].classification == "STRONG_UNDERWEIGHT"


def test_manual_total_mode_adjustments_sum_to_zero_after_normalization():
    config = load_strategy_config("config/strategy.yaml")

    result = evaluate_strategy(
        config,
        _voo_indicator(),
        _qqqm_indicator(),
        ReserveState(reserve_cash_rmb=0),
        secondary_indicators=_vxus_indicator(),
    )

    assert sum(signal.delta_rmb for signal in result.asset_signals) == 0
    assert round(sum(signal.normalized_adjustment_pct for signal in result.asset_signals), 6) == 0.0


def test_manual_total_mode_uses_same_ratio_for_6000_override_before_tactical_adjustment():
    config = load_strategy_config("config/strategy.yaml")
    override = apply_base_override(config, 6000)

    result = evaluate_strategy(
        override,
        _voo_indicator(),
        _qqqm_indicator(),
        ReserveState(reserve_cash_rmb=0),
        secondary_indicators=_vxus_indicator(),
    )

    assert result.recommendation_total_rmb == 6000
    assert result.baseline_allocation.core_rmb == 4200
    assert result.baseline_allocation.secondary_rmb == 1200
    assert result.baseline_allocation.growth_rmb == 600
    assert result.allocation.core_rmb + result.allocation.secondary_rmb + result.allocation.growth_rmb == 6000


def test_manual_total_mode_reasons_distinguish_raw_signal_from_final_zero_adjustment():
    config = load_strategy_config("config/strategy.yaml")

    result = evaluate_strategy(
        config,
        _strong_heat_indicator("VOO"),
        _strong_heat_indicator("QQQM"),
        ReserveState(reserve_cash_rmb=0),
        secondary_indicators=_strong_heat_indicator("VXUS"),
    )

    assert all(signal.delta_rmb == 0 for signal in result.asset_signals)
    assert "原始信号显示偏热或偏弱" in result.reasons[2]
    assert any("原始信号明显偏热" in reason for reason in result.reasons[3:])
    assert any("最终调整为 0，维持基线" in reason for reason in result.reasons[3:])


def test_legacy_mode_still_exists_for_rollback_safety():
    config = replace(load_strategy_config("config/strategy.yaml"), strategy_mode="legacy_master_signal_total_amount")
    growth = _indicator(
        "QQQM",
        current_price=108.0,
        high_52w=109.0,
        drawdown_52w=0.0092,
        sma200=95.0,
        deviation_from_sma200=0.1368,
        sma20=100.0,
        deviation_from_sma20=0.08,
        rsi14=68.0,
        price_percentile_3y=95.0,
    )

    result = evaluate_strategy(
        config,
        _voo_indicator(),
        growth,
        ReserveState(reserve_cash_rmb=200),
        secondary_indicators=_vxus_indicator(),
    )

    assert result.strategy_mode == "legacy_master_signal_total_amount"
    assert result.total_is_fixed is False
    assert result.state_label == "HEAT"
    assert result.recommendation_total_rmb == 2500
