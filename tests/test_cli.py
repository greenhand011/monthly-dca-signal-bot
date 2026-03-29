from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from dca_signal_bot import cli
from dca_signal_bot.data_fetcher import DATA_SOURCE, DataFetchError, MarketDataBundle, TickerHistory
from dca_signal_bot.feishu_sender import FeishuError


def _make_history(start_price: float) -> pd.DataFrame:
    idx = pd.date_range(end="2026-03-27", periods=800, freq="B")
    close = pd.Series([start_price + i * 0.5 for i in range(800)], index=idx, dtype=float)
    return pd.DataFrame({"close": close})


def _prepare_workspace(name: str) -> Path:
    root = Path("tests") / ".tmp" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_cli_success_path_generates_report_and_state(monkeypatch):
    sent_messages: list[str] = []

    def fake_fetch_histories(tickers, *, reference_date, fetched_at_utc):
        _ = (reference_date, fetched_at_utc)
        histories = {
            "SPYM": TickerHistory("SPYM", _make_history(400.0), pd.Timestamp("2026-03-27").date(), 800),
            "QQQM": TickerHistory("QQQM", _make_history(450.0), pd.Timestamp("2026-03-27").date(), 800),
        }
        return MarketDataBundle(
            data_source=DATA_SOURCE,
            fetched_at_utc=datetime(2026, 3, 28, 3, 15, 20, tzinfo=timezone.utc),
            validation_status="PASS",
            histories=histories,
        )

    def fake_send_feishu(webhook_url, text, timeout=10):
        _ = (webhook_url, timeout)
        sent_messages.append(text)

    monkeypatch.setattr(cli, "fetch_histories", fake_fetch_histories)
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
    report_file = reports_dir / "2026-03-report.md"
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "Data source: Yahoo Finance via yfinance" in content
    assert "Validation status: PASS" in content
    assert state_file.exists()
    assert sent_messages == []


def test_cli_success_path_sends_feishu_notification(monkeypatch):
    sent_messages: list[str] = []

    def fake_fetch_histories(tickers, *, reference_date, fetched_at_utc):
        _ = (reference_date, fetched_at_utc)
        histories = {
            "SPYM": TickerHistory("SPYM", _make_history(400.0), pd.Timestamp("2026-03-27").date(), 800),
            "QQQM": TickerHistory("QQQM", _make_history(450.0), pd.Timestamp("2026-03-27").date(), 800),
        }
        return MarketDataBundle(
            data_source=DATA_SOURCE,
            fetched_at_utc=datetime(2026, 3, 28, 3, 15, 20, tzinfo=timezone.utc),
            validation_status="PASS",
            histories=histories,
        )

    def fake_send_feishu(webhook_url, text, timeout=10):
        _ = (webhook_url, timeout)
        sent_messages.append(text)

    monkeypatch.setattr(cli, "fetch_histories", fake_fetch_histories)
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
    assert "储备金变动" in sent_messages[0]
    assert "报告：" in sent_messages[0]


def test_cli_success_path_fails_when_feishu_notification_fails(monkeypatch):
    def fake_fetch_histories(tickers, *, reference_date, fetched_at_utc):
        _ = (reference_date, fetched_at_utc)
        histories = {
            "SPYM": TickerHistory("SPYM", _make_history(400.0), pd.Timestamp("2026-03-27").date(), 800),
            "QQQM": TickerHistory("QQQM", _make_history(450.0), pd.Timestamp("2026-03-27").date(), 800),
        }
        return MarketDataBundle(
            data_source=DATA_SOURCE,
            fetched_at_utc=datetime(2026, 3, 28, 3, 15, 20, tzinfo=timezone.utc),
            validation_status="PASS",
            histories=histories,
        )

    def fake_send_feishu(webhook_url, text, timeout=10):
        _ = (webhook_url, text, timeout)
        raise FeishuError("Feishu webhook HTTP error: 400 bad request")

    monkeypatch.setattr(cli, "fetch_histories", fake_fetch_histories)
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
    assert (reports_dir / "2026-03-report.md").exists()
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
    assert "数据校验失败" in sent_messages[0]
    assert "最新市场日期：N/A" in sent_messages[0]
    assert "校验状态：FAIL" in sent_messages[0]
