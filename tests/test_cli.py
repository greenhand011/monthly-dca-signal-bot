from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from dca_signal_bot import cli
from dca_signal_bot.data_fetcher import DATA_SOURCE, DataFetchError, MarketDataBundle, TickerHistory
from dca_signal_bot.feishu_sender import FeishuError
from dca_signal_bot.fx_converter import FxConversionSummary


def _make_history(start_price: float) -> pd.DataFrame:
    idx = pd.date_range(end="2026-03-27", periods=1100, freq="B")
    close = pd.Series([start_price + i * 0.5 for i in range(len(idx))], index=idx, dtype=float)
    return pd.DataFrame({"close": close})


def _prepare_workspace(name: str) -> Path:
    root = Path("tests") / ".tmp" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _fake_bundle() -> MarketDataBundle:
    histories = {
        "VOO": TickerHistory("VOO", _make_history(400.0), pd.Timestamp("2026-03-27").date(), 1100),
        "VXUS": TickerHistory("VXUS", _make_history(200.0), pd.Timestamp("2026-03-27").date(), 1100),
        "QQQM": TickerHistory("QQQM", _make_history(450.0), pd.Timestamp("2026-03-27").date(), 1100),
    }
    return MarketDataBundle(
        data_source=DATA_SOURCE,
        fetched_at_utc=datetime(2026, 3, 28, 3, 15, 20, tzinfo=timezone.utc),
        validation_status="PASS",
        histories=histories,
    )


def _fake_fx_summary() -> FxConversionSummary:
    return FxConversionSummary(
        source="Yahoo Finance via yfinance",
        pair_ticker="CNY=X",
        pair_description="CNY per USD",
        fetched_at_utc=datetime(2026, 3, 28, 3, 15, 20, tzinfo=timezone.utc),
        latest_market_date=pd.Timestamp("2026-03-27").date(),
        validation_status="PASS",
        rate_cny_per_usd=7.2,
        total_rmb=3000,
        core_rmb=2100,
        growth_rmb=300,
        total_usd=416.67,
        core_usd=291.67,
        growth_usd=41.67,
        extra_rmb={"VXUS": 600},
        extra_usd={"VXUS": 83.33},
        note="汇率换算完成。",
    )


def test_cli_success_path_generates_report_and_state(monkeypatch):
    sent_messages: list[str] = []

    def fake_fetch_histories(tickers, *, reference_date, fetched_at_utc):
        _ = (tickers, reference_date, fetched_at_utc)
        return _fake_bundle()

    def fake_send_feishu(webhook_url, text, timeout=10):
        _ = (webhook_url, timeout)
        sent_messages.append(text)

    monkeypatch.setattr(cli, "fetch_histories", fake_fetch_histories)
    monkeypatch.setattr(cli, "build_fx_conversion_summary", lambda **kwargs: _fake_fx_summary())
    monkeypatch.setattr("dca_signal_bot.feishu_sender.send_feishu_text", fake_send_feishu)

    workspace = _prepare_workspace("success")
    state_file = workspace / "reserve_state.json"
    reports_dir = workspace / "reports"
    code = cli._run(
        config_path="config/strategy.yaml",
        state_file=str(state_file),
        reports_dir=str(reports_dir),
        webhook_url="https://example.invalid",
        dry_run=True,
    )

    assert code == 0
    report_files = list(reports_dir.glob("*.md"))
    assert len(report_files) == 1
    content = report_files[0].read_text(encoding="utf-8")
    assert "## 信号触发详情" in content
    assert "## IBKR 执行建议" in content
    assert "## 美元估算" in content
    assert "## 历史信号回顾" in content
    assert "正式模式" in content
    assert "VOO" in content
    assert "VXUS" in content
    assert "约 USD 416.67" in content
    assert state_file.exists()
    assert sent_messages == []


def test_cli_success_path_sends_feishu_notification(monkeypatch):
    sent_messages: list[str] = []

    def fake_fetch_histories(tickers, *, reference_date, fetched_at_utc):
        _ = (tickers, reference_date, fetched_at_utc)
        return _fake_bundle()

    def fake_send_feishu(webhook_url, text, timeout=10):
        _ = (webhook_url, timeout)
        sent_messages.append(text)

    monkeypatch.setattr(cli, "fetch_histories", fake_fetch_histories)
    monkeypatch.setattr(cli, "build_fx_conversion_summary", lambda **kwargs: _fake_fx_summary())
    monkeypatch.setattr("dca_signal_bot.feishu_sender.send_feishu_text", fake_send_feishu)

    workspace = _prepare_workspace("success-send")
    state_file = workspace / "reserve_state.json"
    reports_dir = workspace / "reports"
    code = cli._run(
        config_path="config/strategy.yaml",
        state_file=str(state_file),
        reports_dir=str(reports_dir),
        webhook_url="https://example.invalid",
        dry_run=False,
    )

    assert code == 0
    assert state_file.exists()
    assert len(sent_messages) == 1
    assert "正式模式" in sent_messages[0]
    assert "VOO" in sent_messages[0]
    assert "VXUS" in sent_messages[0]
    assert "IBKR 执行建议" in sent_messages[0]
    assert "美元估算" in sent_messages[0]


def test_cli_simulation_mode_skips_state_mutation_and_labels_report(monkeypatch):
    def fake_fetch_histories(tickers, *, reference_date, fetched_at_utc):
        _ = (tickers, reference_date, fetched_at_utc)
        return _fake_bundle()

    monkeypatch.setattr(cli, "fetch_histories", fake_fetch_histories)
    monkeypatch.setattr(cli, "build_fx_conversion_summary", lambda **kwargs: _fake_fx_summary())

    workspace = _prepare_workspace("simulation")
    state_file = workspace / "reserve_state.json"
    original_state = {
        "reserve_cash_rmb": 1234,
        "last_run_at": "2026-02-01T00:00:00Z",
        "last_status": "NORMAL",
        "last_recommendation_total_rmb": 3000,
    }
    state_file.write_text(json.dumps(original_state, ensure_ascii=False, indent=2), encoding="utf-8")
    reports_dir = workspace / "reports"
    code = cli._run(
        config_path="config/strategy.yaml",
        state_file=str(state_file),
        reports_dir=str(reports_dir),
        webhook_url="https://example.invalid",
        dry_run=True,
        base_monthly_rmb=6000,
        review_months=6,
    )

    assert code == 0
    report_files = list(reports_dir.glob("*.md"))
    assert len(report_files) == 1
    content = report_files[0].read_text(encoding="utf-8")
    assert "模拟模式：基线月投金额 = 6000" in content
    assert "## IBKR 执行建议" in content
    assert "## 美元估算" in content
    assert "## 历史信号回顾（最近 6 个月）" in content
    assert "VOO" in content
    assert "VXUS" in content
    assert "QQQM" in content
    assert json.loads(state_file.read_text(encoding="utf-8")) == original_state


def test_cli_success_path_fails_when_feishu_notification_fails(monkeypatch):
    def fake_fetch_histories(tickers, *, reference_date, fetched_at_utc):
        _ = (tickers, reference_date, fetched_at_utc)
        return _fake_bundle()

    def fake_send_feishu(webhook_url, text, timeout=10):
        _ = (webhook_url, text, timeout)
        raise FeishuError("Feishu webhook HTTP error: 400 bad request")

    monkeypatch.setattr(cli, "fetch_histories", fake_fetch_histories)
    monkeypatch.setattr(cli, "build_fx_conversion_summary", lambda **kwargs: _fake_fx_summary())
    monkeypatch.setattr("dca_signal_bot.feishu_sender.send_feishu_text", fake_send_feishu)

    workspace = _prepare_workspace("success-feishu-fail")
    state_file = workspace / "reserve_state.json"
    reports_dir = workspace / "reports"
    code = cli._run(
        config_path="config/strategy.yaml",
        state_file=str(state_file),
        reports_dir=str(reports_dir),
        webhook_url="https://example.invalid",
        dry_run=False,
    )

    assert code == 4
    report_files = list(reports_dir.glob("*.md"))
    assert len(report_files) == 1
    assert state_file.exists()


def test_cli_failure_path_sends_only_failure_alert(monkeypatch):
    sent_messages: list[str] = []

    def fake_fetch_histories(*args, **kwargs):
        _ = (args, kwargs)
        raise DataFetchError("QQQM: price history is empty")

    def fake_send_feishu(webhook_url, text, timeout=10):
        _ = (webhook_url, timeout)
        sent_messages.append(text)

    monkeypatch.setattr(cli, "fetch_histories", fake_fetch_histories)
    monkeypatch.setattr("dca_signal_bot.feishu_sender.send_feishu_text", fake_send_feishu)

    workspace = _prepare_workspace("failure")
    state_file = workspace / "reserve_state.json"
    reports_dir = workspace / "reports"
    code = cli._run(
        config_path="config/strategy.yaml",
        state_file=str(state_file),
        reports_dir=str(reports_dir),
        webhook_url="https://example.invalid",
        dry_run=False,
    )

    assert code == 3
    assert not (reports_dir / "2026-03-report.md").exists()
    assert not state_file.exists()
    assert len(sent_messages) == 1
    assert "VOO + VXUS + QQQM" in sent_messages[0]
    assert "最新市场日期：N/A" in sent_messages[0]
    assert "校验状态：失败" in sent_messages[0]
