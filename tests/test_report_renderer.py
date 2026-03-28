from __future__ import annotations

import pandas as pd

from dca_signal_bot.config import load_strategy_config
from dca_signal_bot.indicators import TickerIndicators
from dca_signal_bot.report_renderer import render_report
from dca_signal_bot.strategy_engine import AllocationBreakdown, StrategyDecision


def _indicator(ticker: str, price: float) -> TickerIndicators:
    return TickerIndicators(
        ticker=ticker,
        latest_date=pd.Timestamp("2026-03-27"),
        current_price=price,
        high_52w=price * 1.1,
        drawdown_52w=0.05,
        sma200=price * 0.95,
        deviation_from_sma200=0.0526316,
        sma20=price * 0.98,
        deviation_from_sma20=0.020408,
        rsi14=55.0,
        price_percentile_3y=60.0,
    )


def test_render_report_contains_required_sections():
    config = load_strategy_config("config/strategy.yaml")
    core = _indicator("SPYM", 500.0)
    growth = _indicator("QQQM", 450.0)
    decision = StrategyDecision(
        state_label="NORMAL",
        action_label="\u539f\u6837\u6295",
        recommendation_total_rmb=3000,
        allocation=AllocationBreakdown(core_rmb=2550, growth_rmb=450, core_weight=0.85, growth_weight=0.15),
        reserve_delta_rmb=0,
        reserve_cash_after_rmb=0,
        reasons=["\u672a\u540c\u65f6\u6ee1\u8db3\u66f4\u5f3a\u7684\u70ed\u5ea6\u6216\u56de\u64a4\u6761\u4ef6\uff0c\u6309\u57fa\u7ebf\u914d\u6bd4\u6267\u884c\u3002"],
        triggered_rule="NORMAL",
    )

    markdown = render_report(
        config=config,
        core=core,
        growth=growth,
        decision=decision,
        reserve_cash_rmb=0,
        report_date=pd.Timestamp("2026-03-28").date(),
        data_source="Yahoo Finance via yfinance",
        fetched_at_utc=pd.Timestamp("2026-03-28T03:15:20Z").to_pydatetime(),
        latest_market_date_spym=pd.Timestamp("2026-03-27").date(),
        latest_market_date_qqqm=pd.Timestamp("2026-03-27").date(),
        validation_status="PASS",
    )

    assert "Data source: Yahoo Finance via yfinance" in markdown
    assert "Data fetched at (UTC): 2026-03-28T03:15:20Z" in markdown
    assert "Latest market date for SPYM: 2026-03-27" in markdown
    assert "Latest market date for QQQM: 2026-03-27" in markdown
    assert "Validation status: PASS" in markdown
    assert "\u5f53\u524d\u5e02\u573a\u72b6\u6001" in markdown
    assert "\u672c\u6708\u5efa\u8bae\u603b\u6295\u5165\u91d1\u989d" in markdown
