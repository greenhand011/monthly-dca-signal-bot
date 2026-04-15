from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from dca_signal_bot.config import load_strategy_config
from dca_signal_bot.execution_guidance import ExecutionGuidance
from dca_signal_bot.fx_converter import FxConversionSummary
from dca_signal_bot.historical_review import HistoricalSignalReview, HistoricalSignalReviewRow
from dca_signal_bot.indicators import TickerIndicators
from dca_signal_bot.report_renderer import render_report
from dca_signal_bot.reserve_state import ReserveState
from dca_signal_bot.strategy_engine import evaluate_strategy


def _indicator(
    ticker: str,
    *,
    price: float,
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
        latest_date=pd.Timestamp("2026-03-27"),
        current_price=price,
        high_52w=high_52w,
        drawdown_52w=drawdown_52w,
        sma200=sma200,
        deviation_from_sma200=deviation_from_sma200,
        sma20=sma20,
        deviation_from_sma20=deviation_from_sma20,
        rsi14=rsi14,
        price_percentile_3y=price_percentile_3y,
    )


def test_render_report_contains_trigger_details_historical_review_and_simulation_label():
    config = load_strategy_config("config/strategy.yaml")
    core = _indicator(
        "VOO",
        price=500.0,
        high_52w=520.0,
        drawdown_52w=0.04,
        sma200=480.0,
        deviation_from_sma200=0.0416667,
        sma20=495.0,
        deviation_from_sma20=0.010101,
        rsi14=55.0,
        price_percentile_3y=60.0,
    )
    secondary = _indicator(
        "VXUS",
        price=62.0,
        high_52w=65.0,
        drawdown_52w=0.0462,
        sma200=60.0,
        deviation_from_sma200=0.0333,
        sma20=61.0,
        deviation_from_sma20=0.0164,
        rsi14=52.0,
        price_percentile_3y=58.0,
    )
    growth = _indicator(
        "QQQM",
        price=108.0,
        high_52w=109.0,
        drawdown_52w=0.0092,
        sma200=95.0,
        deviation_from_sma200=0.1368,
        sma20=100.0,
        deviation_from_sma20=0.08,
        rsi14=68.0,
        price_percentile_3y=95.0,
    )
    decision = evaluate_strategy(
        config,
        core,
        growth,
        ReserveState(reserve_cash_rmb=200),
        secondary_indicators=secondary,
    )
    review = HistoricalSignalReview(
        months=1,
        note="仅用于信号观察的历史回顾，最近 1 个按月收盘快照。",
        rows=[
            HistoricalSignalReviewRow(
                month="2026-03",
                status="TACTICAL_REBALANCE",
                base_monthly_rmb=3000,
                suggested_total_rmb=3000,
                core_rmb=2160,
                secondary_rmb=660,
                qqqm_rmb=180,
                reserve_cash_delta_rmb=0,
                reserve_cash_balance_rmb=0,
                key_trigger_summary="VOO:OVERWEIGHT | VXUS:OVERWEIGHT | QQQM:STRONG_UNDERWEIGHT",
                short_reason="当前总投入由手动设定，以下加减仓建议仅用于调整资产间分配，不改变本月总投入。",
                latest_market_date=pd.Timestamp("2026-03-27").date(),
            )
        ],
    )
    guidance = ExecutionGuidance(
        generated_at_utc=datetime(2026, 3, 28, 3, 15, 20, tzinfo=timezone.utc),
        user_timezone="Asia/Tokyo",
        user_time=datetime(2026, 3, 28, 12, 15, tzinfo=ZoneInfo("Asia/Tokyo")),
        market_time_et=datetime(2026, 3, 27, 23, 15, tzinfo=ZoneInfo("America/New_York")),
        session_phase="overnight",
        can_submit_now=True,
        can_likely_fill_now=False,
        next_regular_open=datetime(2026, 3, 28, 22, 30, tzinfo=ZoneInfo("Asia/Tokyo")),
        next_extended_hours_opportunity=datetime(2026, 3, 28, 22, 30, tzinfo=ZoneInfo("Asia/Tokyo")),
        preferred_order_type="LIMIT",
        preferred_tif="DAY",
        suggest_outside_rth=True,
        warnings=("常规时段前提交市价单风险较高，不建议作为新手默认选项。",),
        notes=("美国东部时间（US/Eastern）是本项目的基准交易时钟，展示时会转换到你配置的用户时区。",),
    )
    fx_summary = FxConversionSummary(
        source="Yahoo Finance via yfinance",
        pair_ticker="CNY=X",
        pair_description="CNY per USD",
        fetched_at_utc=datetime(2026, 3, 28, 3, 15, 20, tzinfo=timezone.utc),
        latest_market_date=pd.Timestamp("2026-03-27").date(),
        validation_status="PASS",
        rate_cny_per_usd=7.2,
        total_rmb=decision.recommendation_total_rmb,
        core_rmb=decision.allocation.core_rmb,
        growth_rmb=decision.allocation.growth_rmb,
        total_usd=round(decision.recommendation_total_rmb / 7.2, 2),
        core_usd=round(decision.allocation.core_rmb / 7.2, 2),
        growth_usd=round(decision.allocation.growth_rmb / 7.2, 2),
        extra_rmb={"VXUS": decision.allocation.secondary_rmb},
        extra_usd={"VXUS": round(decision.allocation.secondary_rmb / 7.2, 2)},
        note="汇率换算完成。",
    )

    markdown = render_report(
        config=config,
        core=core,
        secondary=secondary,
        growth=growth,
        decision=decision,
        reserve_cash_rmb=200,
        report_date=pd.Timestamp("2026-03-28").date(),
        data_source="Yahoo Finance via yfinance",
        fetched_at_utc=pd.Timestamp("2026-03-28T03:15:20Z").to_pydatetime(),
        latest_market_date_core=pd.Timestamp("2026-03-27").date(),
        latest_market_date_secondary=pd.Timestamp("2026-03-27").date(),
        latest_market_date_qqqm=pd.Timestamp("2026-03-27").date(),
        validation_status="PASS",
        run_mode_label="模拟模式：基线月投金额 = 6000",
        historical_review=review,
        execution_guidance=guidance,
        fx_summary=fx_summary,
    )

    assert "模拟模式：基线月投金额 = 6000" in markdown
    assert "## 信号触发详情" in markdown
    assert "## IBKR 执行建议" in markdown
    assert "## 美元估算" in markdown
    assert "## 单资产战术建议" in markdown
    assert "适度高配" in markdown
    assert "明显低配" in markdown
    assert "是" in markdown
    assert "否" in markdown
    assert "final_decision_path" not in markdown
    assert "## 历史信号回顾（最近 1 个月）" in markdown
    assert "仅用于信号观察的历史回顾" in markdown
    assert "2026-03" in markdown
    assert "RMB 变化" in markdown
    assert "USD 变化" in markdown
    assert "VOO" in markdown
    assert "VXUS" in markdown
    assert f"{decision.recommendation_total_rmb} RMB（约 USD {fx_summary.total_usd:.2f}）" in markdown
