from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import requests

from dca_signal_bot.execution_guidance import ExecutionGuidance
from dca_signal_bot.feishu_sender import FeishuError, build_summary_text, maybe_send_feishu, send_feishu_text
from dca_signal_bot.fx_converter import FxConversionSummary
from dca_signal_bot.strategy_engine import AllocationBreakdown, StrategyDecision


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
        state_label="NORMAL",
        action_label="原样投",
        recommendation_total_rmb=3000,
        allocation=AllocationBreakdown(core_rmb=2550, growth_rmb=450, core_weight=0.85, growth_weight=0.15),
        reserve_delta_rmb=0,
        reserve_cash_after_rmb=0,
        reasons=["按基线配比执行。"],
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
        core_rmb=2550,
        growth_rmb=450,
        total_usd=416.67,
        core_usd=354.17,
        growth_usd=62.5,
        note="汇率换算完成。",
    )

    summary = build_summary_text(
        config=SimpleNamespace(core_ticker="VOO", growth_ticker="QQQM"),
        growth=object(),
        decision=decision,
        report_path="reports/2026-03-report.md",
        report_date="2026-03-30",
        data_source="Yahoo Finance via yfinance",
        latest_market_date_core=datetime(2026, 3, 30, tzinfo=timezone.utc).date(),
        latest_market_date_qqqm=datetime(2026, 3, 30, tzinfo=timezone.utc).date(),
        validation_status="PASS",
        run_mode_label="正式模式",
        execution_guidance=guidance,
        fx_summary=fx_summary,
    )

    assert "IBKR 执行建议：" in summary
    assert "美元估算：" in summary
    assert "总投入：3000 RMB（约 USD 416.67）" in summary
    assert "VOO：2550 RMB（约 USD 354.17）" in summary
    assert "QQQM：450 RMB（约 USD 62.50）" in summary
