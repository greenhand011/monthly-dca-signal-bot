from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import requests

from dca_signal_bot.execution_guidance import ExecutionGuidance
from dca_signal_bot.feishu_sender import FeishuError, build_summary_text, maybe_send_feishu, send_feishu_text
from dca_signal_bot.fx_converter import FxConversionSummary
from dca_signal_bot.gold_sleeve import GoldSleeveDecision
from dca_signal_bot.strategy_engine import AllocationBreakdown, AssetSignalEvaluation, StrategyDecision


class _DummyResponse:
    def __init__(self, *, status_code: int, text: str, payload: object | None = None, json_error: Exception | None = None):
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def test_sender_raises_when_webhook_missing():
    with pytest.raises(FeishuError, match="为空或未配置"):
        maybe_send_feishu(enabled=True, webhook_url="   ", summary_text="hello")


def test_sender_raises_on_non_200_response(monkeypatch):
    def fake_post(*args, **kwargs):
        _ = (args, kwargs)
        return _DummyResponse(status_code=500, text="server exploded", payload={"code": 0})

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(FeishuError, match="HTTP 错误：500"):
        send_feishu_text("https://example.invalid", "hello")


def test_sender_raises_on_business_error_response(monkeypatch):
    def fake_post(*args, **kwargs):
        _ = (args, kwargs)
        return _DummyResponse(status_code=200, text='{"code":19000,"msg":"bad"}', payload={"code": 19000, "msg": "bad"})

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(FeishuError, match="返回业务错误"):
        send_feishu_text("https://example.invalid", "hello")


def test_sender_succeeds_on_valid_success_response(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _DummyResponse(status_code=200, text='{"code":0,"msg":"success"}', payload={"code": 0, "msg": "success"})

    monkeypatch.setenv("FEISHU_KEYWORD", "")
    monkeypatch.setattr(requests, "post", fake_post)

    send_feishu_text("https://example.invalid", "hello world", timeout=7)

    assert captured["url"] == "https://example.invalid"
    assert captured["timeout"] == 7
    assert captured["json"]["msg_type"] == "text"
    assert captured["json"]["content"]["text"] == "hello world"


def test_sender_prefixes_keyword_when_configured(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _DummyResponse(status_code=200, text='{"code":0,"msg":"success"}', payload={"code": 0, "msg": "success"})

    monkeypatch.setenv("FEISHU_KEYWORD", "DCA-BOT")
    monkeypatch.setattr(requests, "post", fake_post)

    send_feishu_text("https://example.invalid", "monthly summary")

    assert captured["json"]["content"]["text"].startswith("DCA-BOT\n")


def test_summary_text_includes_execution_guidance_and_usd_estimates():
    decision = StrategyDecision(
        state_label="TACTICAL_REBALANCE",
        action_label="固定总额，调整分配",
        recommendation_total_rmb=3000,
        allocation=AllocationBreakdown(
            core_rmb=2160,
            secondary_rmb=660,
            growth_rmb=180,
            core_weight=0.72,
            secondary_weight=0.22,
            growth_weight=0.06,
        ),
        baseline_allocation=AllocationBreakdown(
            core_rmb=2100,
            secondary_rmb=600,
            growth_rmb=300,
            core_weight=0.70,
            secondary_weight=0.20,
            growth_weight=0.10,
        ),
        reserve_delta_rmb=0,
        reserve_cash_after_rmb=0,
        strategy_mode="manual_total_per_asset_signal",
        reasons=["按基线配比执行。"],
        asset_signals=[
            AssetSignalEvaluation(
                ticker="VOO",
                score=1,
                classification="OVERWEIGHT",
                raw_adjustment_pct=2.0,
                normalized_adjustment_pct=2.0,
                delta_rmb=60,
                final_rmb=2160,
                summary="VOO 至少满足 2 项加仓条件，可考虑适当高配。",
            ),
            AssetSignalEvaluation(
                ticker="VXUS",
                score=1,
                classification="OVERWEIGHT",
                raw_adjustment_pct=2.0,
                normalized_adjustment_pct=2.0,
                delta_rmb=60,
                final_rmb=660,
                summary="VXUS 至少满足 2 项加仓条件，可考虑适当高配。",
            ),
            AssetSignalEvaluation(
                ticker="QQQM",
                score=-2,
                classification="STRONG_UNDERWEIGHT",
                raw_adjustment_pct=-4.0,
                normalized_adjustment_pct=-4.0,
                delta_rmb=-120,
                final_rmb=180,
                summary="QQQM 至少满足 2 项强减仓条件，可考虑明显低配。",
            ),
        ],
        total_is_fixed=True,
    )
    guidance = ExecutionGuidance(
        generated_at_utc=datetime(2026, 3, 30, 6, 55, 40, tzinfo=timezone.utc),
        user_timezone="Asia/Tokyo",
        user_time=datetime(2026, 3, 30, 15, 55, tzinfo=timezone.utc),
        market_time_et=datetime(2026, 3, 30, 2, 55, tzinfo=timezone.utc),
        session_phase="regular",
        can_submit_now=True,
        can_likely_fill_now=True,
        next_regular_open=datetime(2026, 3, 31, 9, 30, tzinfo=timezone.utc),
        next_extended_hours_opportunity=datetime(2026, 3, 30, 16, 0, tzinfo=timezone.utc),
        preferred_order_type="LIMIT",
        preferred_tif="DAY",
        suggest_outside_rth=True,
        warnings=("常规时段前提交市价单风险较高，不建议作为新手默认选项。",),
        notes=("本项目不会自动下单，也不会代替你登录 IBKR。",),
    )
    fx_summary = FxConversionSummary(
        source="Yahoo Finance via yfinance",
        pair_ticker="CNY=X",
        pair_description="CNY per USD",
        fetched_at_utc=datetime(2026, 3, 30, 6, 55, 40, tzinfo=timezone.utc),
        latest_market_date=datetime(2026, 3, 30, tzinfo=timezone.utc).date(),
        validation_status="PASS",
        rate_cny_per_usd=7.2,
        total_rmb=3000,
        core_rmb=2160,
        growth_rmb=180,
        total_usd=416.67,
        core_usd=300.00,
        growth_usd=25.00,
        extra_rmb={"VXUS": 660},
        extra_usd={"VXUS": 91.67},
        note="汇率换算完成。",
    )
    gold_decision = GoldSleeveDecision(
        enabled=True,
        ticker="GLDM",
        decision_status="BUY",
        action_label="可考虑小幅买入",
        should_buy=True,
        data_source="Yahoo Finance via yfinance",
        validation_status="PASS",
        latest_market_date=datetime(2026, 3, 30, tzinfo=timezone.utc).date(),
        current_gold_weight=0.01,
        target_gold_weight=0.03,
        max_gold_weight=0.05,
        below_target=True,
        overheat_triggered=False,
        total_score=4.0,
        technical_score=4.0,
        macro_score=0.0,
        optional_score=0.0,
        target_gold_value_rmb=3000,
        target_gap_value_rmb=2000,
        recommended_buy_rmb=500,
        projected_gold_weight_after_buy=0.015,
        remaining_gap_after_buy_rmb=1500,
        reason="综合评分 4.0，达到轻仓补位区间，可考虑买入目标缺口的 25%。",
        notes=[],
        overheat_reasons=[],
        score_details=[],
        optional_data_notes=[],
        indicator_snapshot=None,
    )

    summary = build_summary_text(
        config=SimpleNamespace(core_ticker="VOO", secondary_ticker="VXUS", growth_ticker="QQQM"),
        growth=object(),
        decision=decision,
        report_path="reports/2026-03-report.md",
        report_date="2026-03-30",
        data_source="Yahoo Finance via yfinance",
        latest_market_date_core=datetime(2026, 3, 30, tzinfo=timezone.utc).date(),
        latest_market_date_secondary=datetime(2026, 3, 30, tzinfo=timezone.utc).date(),
        latest_market_date_qqqm=datetime(2026, 3, 30, tzinfo=timezone.utc).date(),
        validation_status="PASS",
        run_mode_label="正式模式",
        execution_guidance=guidance,
        fx_summary=fx_summary,
        gold_decision=gold_decision,
    )

    assert "IBKR 执行建议：" in summary
    assert "美元估算：" in summary
    assert "当前总投入由手动设定" in summary
    assert "VOO：原始信号偏弱；最终适度高配" in summary
    assert "VXUS：原始信号偏弱；最终适度高配" in summary
    assert "QQQM：原始信号明显偏热；最终适度低配" in summary
    assert "VOO：基线约 USD" in summary
    assert "原因：按基线配比执行。" in summary
    assert "黄金保险仓判定：" in summary
    assert "GLDM" in summary
    assert "可考虑小幅买入" in summary


def test_summary_text_zero_final_delta_is_not_described_as_direct_underweight():
    decision = StrategyDecision(
        state_label="BASELINE_ONLY",
        action_label="固定总额，维持基线",
        recommendation_total_rmb=3000,
        allocation=AllocationBreakdown(
            core_rmb=2100,
            secondary_rmb=600,
            growth_rmb=300,
            core_weight=0.70,
            secondary_weight=0.20,
            growth_weight=0.10,
        ),
        baseline_allocation=AllocationBreakdown(
            core_rmb=2100,
            secondary_rmb=600,
            growth_rmb=300,
            core_weight=0.70,
            secondary_weight=0.20,
            growth_weight=0.10,
        ),
        reserve_delta_rmb=0,
        reserve_cash_after_rmb=0,
        strategy_mode="manual_total_per_asset_signal",
        reasons=[
            "本月总投入由手动设定为 3000 RMB，不参与自动增减仓。",
            "系统分别评估了 VOO、VXUS、QQQM 的原始资产信号。",
            "尽管部分资产原始信号显示偏热或偏弱，但在三资产零和归一化后，本月未形成明确的相对增减配结果，因此最终维持基线分配。",
        ],
        asset_signals=[
            AssetSignalEvaluation(
                ticker="VOO",
                score=-2,
                classification="STRONG_UNDERWEIGHT",
                raw_adjustment_pct=-4.0,
                normalized_adjustment_pct=0.0,
                delta_rmb=0,
                final_rmb=2100,
                summary="VOO 至少满足 2 项强减仓条件，可考虑明显低配。",
            ),
            AssetSignalEvaluation(
                ticker="VXUS",
                score=-1,
                classification="UNDERWEIGHT",
                raw_adjustment_pct=-2.0,
                normalized_adjustment_pct=0.0,
                delta_rmb=0,
                final_rmb=600,
                summary="VXUS 至少满足 2 项减仓条件，可考虑轻微低配。",
            ),
            AssetSignalEvaluation(
                ticker="QQQM",
                score=0,
                classification="NEUTRAL",
                raw_adjustment_pct=0.0,
                normalized_adjustment_pct=0.0,
                delta_rmb=0,
                final_rmb=300,
                summary="QQQM 当前信号中性，维持基线。",
            ),
        ],
        total_is_fixed=True,
    )

    summary = build_summary_text(
        config=SimpleNamespace(core_ticker="VOO", secondary_ticker="VXUS", growth_ticker="QQQM"),
        growth=object(),
        decision=decision,
        report_path="reports/2026-03-report.md",
        report_date="2026-03-30",
        data_source="Yahoo Finance via yfinance",
        latest_market_date_core=datetime(2026, 3, 30, tzinfo=timezone.utc).date(),
        latest_market_date_secondary=datetime(2026, 3, 30, tzinfo=timezone.utc).date(),
        latest_market_date_qqqm=datetime(2026, 3, 30, tzinfo=timezone.utc).date(),
        validation_status="PASS",
        run_mode_label="正式模式",
        execution_guidance=None,
        fx_summary=None,
    )

    assert "VOO：原始信号明显偏热；最终维持基线（+0 RMB" in summary
    assert "VXUS：原始信号偏热；最终维持基线（+0 RMB" in summary
    assert "明显低配（+0 RMB" not in summary
