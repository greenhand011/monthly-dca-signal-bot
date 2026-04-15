from __future__ import annotations

from dataclasses import replace

import pandas as pd

from dca_signal_bot.config import apply_base_override, load_strategy_config
from dca_signal_bot.indicators import TickerIndicators
from dca_signal_bot.reserve_state import ReserveState
from dca_signal_bot.strategy_engine import ACTION_INCREASE, ACTION_NORMAL, ACTION_REDUCE, evaluate_strategy


def _indicator(
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
        ticker="QQQM",
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


def _core_indicator() -> TickerIndicators:
    return TickerIndicators(
        ticker="VOO",
        latest_date=pd.Timestamp("2026-03-28"),
        current_price=500.0,
        high_52w=550.0,
        drawdown_52w=0.05,
        sma200=480.0,
        deviation_from_sma200=0.0416667,
        sma20=495.0,
        deviation_from_sma20=0.010101,
        rsi14=55.0,
        price_percentile_3y=65.0,
    )


def test_normal_rule_applies_when_no_other_rule_matches():
    config = load_strategy_config("config/strategy.yaml")
    growth = _indicator(
        current_price=100.0,
        high_52w=105.0,
        drawdown_52w=0.0476,
        sma200=110.0,
        deviation_from_sma200=-0.0909,
        sma20=102.0,
        deviation_from_sma20=-0.0196,
        rsi14=50.0,
        price_percentile_3y=40.0,
    )
    result = evaluate_strategy(config, _core_indicator(), growth, ReserveState(reserve_cash_rmb=0))

    assert result.state_label == "NORMAL"
    assert result.action_label == ACTION_NORMAL
    assert result.recommendation_total_rmb == 3000
    assert result.allocation.core_rmb == 2100
    assert result.allocation.secondary_rmb == 600
    assert result.allocation.growth_rmb == 300


def test_heat_rule_reduces_monthly_amount_and_adds_reserve():
    config = load_strategy_config("config/strategy.yaml")
    growth = _indicator(
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
    result = evaluate_strategy(config, _core_indicator(), growth, ReserveState(reserve_cash_rmb=200))

    assert result.state_label == "HEAT"
    assert result.action_label == ACTION_REDUCE
    assert result.recommendation_total_rmb == 2500
    assert result.reserve_delta_rmb == 500
    assert result.reserve_cash_after_rmb == 700


def test_heat_rule_respects_reserve_cap():
    config = load_strategy_config("config/strategy.yaml")
    growth = _indicator(
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
    result = evaluate_strategy(config, _core_indicator(), growth, ReserveState(reserve_cash_rmb=5900))

    assert result.state_label == "HEAT"
    assert result.reserve_delta_rmb == 100
    assert result.reserve_cash_after_rmb == 6000


def test_deep_pullback_uses_reserve_when_available():
    config = load_strategy_config("config/strategy.yaml")
    growth = _indicator(
        current_price=90.0,
        high_52w=120.0,
        drawdown_52w=0.25,
        sma200=100.0,
        deviation_from_sma200=-0.10,
        sma20=95.0,
        deviation_from_sma20=-0.0526,
        rsi14=32.0,
        price_percentile_3y=15.0,
    )
    result = evaluate_strategy(config, _core_indicator(), growth, ReserveState(reserve_cash_rmb=600))

    assert result.state_label == "DEEP_PULLBACK"
    assert result.action_label == ACTION_INCREASE
    assert result.recommendation_total_rmb == 3600
    assert result.reserve_delta_rmb == -600
    assert result.reserve_cash_after_rmb == 0


def test_execution_guidance_settings_do_not_change_strategy_outputs():
    config = load_strategy_config("config/strategy.yaml")
    growth = _indicator(
        current_price=104.0,
        high_52w=110.0,
        drawdown_52w=0.0545,
        sma200=108.0,
        deviation_from_sma200=-0.0370,
        sma20=105.0,
        deviation_from_sma20=-0.0095,
        rsi14=51.0,
        price_percentile_3y=42.0,
    )

    baseline = evaluate_strategy(config, _core_indicator(), growth, ReserveState(reserve_cash_rmb=100))
    guidance_enabled = evaluate_strategy(
        replace(
            config,
            execution_guidance_enabled=True,
            user_timezone="Asia/Tokyo",
            preferred_order_type="LIMIT",
            preferred_tif="DAY",
            suggest_outside_rth=True,
        ),
        _core_indicator(),
        growth,
        ReserveState(reserve_cash_rmb=100),
    )

    assert guidance_enabled == baseline


def test_base_override_6000_keeps_voo_vxus_qqqm_allocation():
    config = load_strategy_config("config/strategy.yaml")
    override = apply_base_override(config, 6000)
    growth = _indicator(
        current_price=100.0,
        high_52w=105.0,
        drawdown_52w=0.0476,
        sma200=110.0,
        deviation_from_sma200=-0.0909,
        sma20=102.0,
        deviation_from_sma20=-0.0196,
        rsi14=50.0,
        price_percentile_3y=40.0,
    )

    result = evaluate_strategy(override, _core_indicator(), growth, ReserveState(reserve_cash_rmb=0))

    assert override.core_ticker == "VOO"
    assert override.secondary_ticker == "VXUS"
    assert override.growth_ticker == "QQQM"
    assert result.recommendation_total_rmb == 6000
    assert result.allocation.core_rmb == 4200
    assert result.allocation.secondary_rmb == 1200
    assert result.allocation.growth_rmb == 600
