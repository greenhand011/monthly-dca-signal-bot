from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .config import StrategyConfig
from .indicators import TickerIndicators
from .strategy_engine import StrategyDecision


class FeishuError(RuntimeError):
    """Raised when the Feishu webhook returns an error."""


@dataclass(frozen=True)
class FeishuPayload:
    text: str


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_summary_text(
    *,
    config: StrategyConfig,
    growth: TickerIndicators,
    decision: StrategyDecision,
    report_path: str | Path,
    report_date: str,
    data_source: str,
    latest_market_date_spym: date,
    latest_market_date_qqqm: date,
    validation_status: str,
) -> str:
    _ = growth
    return "\n".join(
        [
            f"\u65e5\u671f\uff1a{report_date}",
            f"\u72b6\u6001\uff1a{decision.state_label}",
            f"\u603b\u6295\u5165\uff1a{decision.recommendation_total_rmb} RMB",
            f"{config.core_ticker}\uff1a{decision.allocation.core_rmb} RMB",
            f"{config.growth_ticker}\uff1a{decision.allocation.growth_rmb} RMB",
            f"\u50a8\u5907\u91d1\u4f59\u989d\uff1a{decision.reserve_cash_after_rmb} RMB",
            f"\u6570\u636e\u6e90\uff1a{data_source}",
            f"\u6700\u65b0\u5e02\u573a\u65e5\u671f\uff1a{config.core_ticker} {latest_market_date_spym.isoformat()} / {config.growth_ticker} {latest_market_date_qqqm.isoformat()}",
            f"\u6821\u9a8c\u72b6\u6001\uff1a{validation_status}",
            f"\u539f\u56e0\uff1a{decision.reasons[-1]}",
            f"\u62a5\u544a\uff1a{report_path}",
        ]
    )


def build_failure_alert_text(
    *,
    error: str,
    data_source: str,
    fetched_at_utc: datetime,
    validation_status: str = "FAIL",
) -> str:
    return "\n".join(
        [
            "\u6570\u636e\u6821\u9a8c\u5931\u8d25\uff0c\u672a\u751f\u6210\u53ef\u4fe1\u62a5\u544a\u3002",
            f"\u65f6\u95f4\uff1a{_utc_iso(fetched_at_utc)}",
            f"\u6570\u636e\u6e90\uff1a{data_source}",
            "\u6700\u65b0\u5e02\u573a\u65e5\u671f\uff1aN/A",
            f"\u6821\u9a8c\u72b6\u6001\uff1a{validation_status}",
            f"\u9519\u8bef\uff1a{error}",
        ]
    )


def send_feishu_text(webhook_url: str, text: str, timeout: int = 10) -> None:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise FeishuError("requests is required to send Feishu notifications") from exc

    response = requests.post(
        webhook_url,
        json={
            "msg_type": "text",
            "content": {
                "text": text,
            },
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise FeishuError(f"Feishu webhook HTTP error: {response.status_code} {response.text}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise FeishuError("Feishu webhook did not return JSON") from exc

    if payload.get("code", 0) != 0:
        raise FeishuError(f"Feishu webhook returned error payload: {payload}")


def maybe_send_feishu(
    *,
    enabled: bool,
    webhook_url: str | None,
    summary_text: str,
) -> bool:
    if not enabled or not webhook_url:
        return False
    send_feishu_text(webhook_url, summary_text)
    return True
