from __future__ import annotations

import os
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


def _log(message: str) -> None:
    print(f"[info] {message}")


def _warn(message: str) -> None:
    print(f"[warn] {message}")


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
    latest_market_date_core: date,
    latest_market_date_qqqm: date,
    validation_status: str,
    run_mode_label: str | None = None,
) -> str:
    _ = growth
    mode_line = run_mode_label or "Production Mode"
    return "\n".join(
        [
            f"\u65e5\u671f\uff1a{report_date}",
            f"\u8fd0\u884c\u6a21\u5f0f\uff1a{mode_line}",
            f"\u72b6\u6001\uff1a{decision.state_label}",
            f"\u603b\u6295\u5165\uff1a{decision.recommendation_total_rmb} RMB",
            f"{config.core_ticker}\uff1a{decision.allocation.core_rmb} RMB",
            f"{config.growth_ticker}\uff1a{decision.allocation.growth_rmb} RMB",
            f"\u50a8\u5907\u91d1\u53d8\u52a8\uff1a{decision.reserve_delta_rmb:+d} RMB",
            f"\u50a8\u5907\u91d1\u4f59\u989d\uff1a{decision.reserve_cash_after_rmb} RMB",
            f"\u6570\u636e\u6e90\uff1a{data_source}",
            f"\u6700\u65b0\u5e02\u573a\u65e5\u671f\uff1a{config.core_ticker} {latest_market_date_core.isoformat()} / {config.growth_ticker} {latest_market_date_qqqm.isoformat()}",
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
    core_ticker: str = "VOO",
    growth_ticker: str = "QQQM",
    validation_status: str = "FAIL",
) -> str:
    return "\n".join(
        [
            "\u6570\u636e\u6821\u9a8c\u5931\u8d25\uff0c\u672a\u751f\u6210\u53ef\u4fe1\u62a5\u544a\u3002",
            f"\u65f6\u95f4\uff1a{_utc_iso(fetched_at_utc)}",
            f"\u6807\u7684\u7ec4\u5408\uff1a{core_ticker} + {growth_ticker}",
            f"\u6570\u636e\u6e90\uff1a{data_source}",
            "\u6700\u65b0\u5e02\u573a\u65e5\u671f\uff1aN/A",
            f"\u6821\u9a8c\u72b6\u6001\uff1a{validation_status}",
            f"\u9519\u8bef\uff1a{error}",
        ]
    )


def _apply_keyword_prefix(text: str) -> str:
    keyword = os.getenv("FEISHU_KEYWORD", "").strip()
    if not keyword:
        return text
    return f"{keyword}\n{text}"


def _truncate(text: str, limit: int = 400) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3] + "..."


def send_feishu_text(webhook_url: str, text: str, timeout: int = 10, retries: int = 2) -> None:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise FeishuError("requests is required to send Feishu notifications") from exc

    webhook_url = webhook_url.strip() if webhook_url else ""
    if not webhook_url:
        raise FeishuError("FEISHU_WEBHOOK_URL is missing or blank")

    outgoing_text = _apply_keyword_prefix(text)
    _log("Feishu webhook configured: true")
    _log("Feishu sender called: true")
    _log(f"Feishu keyword configured: {'true' if outgoing_text != text else 'false'}")

    if retries < 1:
        retries = 1

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                webhook_url,
                json={
                    "msg_type": "text",
                    "content": {
                        "text": outgoing_text,
                    },
                },
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = exc
            _warn(f"Feishu request attempt {attempt}/{retries} failed: {exc}")
            if attempt >= retries:
                raise FeishuError("Feishu webhook request failed") from exc
            continue

        _log(f"Feishu HTTP status: {response.status_code}")

        if response.status_code >= 500 and attempt < retries:
            _warn(
                f"Feishu webhook returned HTTP {response.status_code} on attempt {attempt}/{retries}; retrying"
            )
            continue

        if response.status_code >= 400:
            raise FeishuError(
                f"Feishu webhook HTTP error: {response.status_code}; body={_truncate(response.text)}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuError(f"Feishu webhook did not return JSON; body={_truncate(response.text)}") from exc

        if not isinstance(payload, dict):
            raise FeishuError(f"Feishu webhook returned a non-object JSON payload: {payload!r}")

        if payload.get("code", 0) != 0:
            raise FeishuError(
                "Feishu webhook returned error payload: "
                f"code={payload.get('code')}, msg={payload.get('msg')}, body={_truncate(response.text)}"
            )

        return

    if last_error is not None:
        raise FeishuError("Feishu webhook request failed") from last_error


def maybe_send_feishu(
    *,
    enabled: bool,
    webhook_url: str | None,
    summary_text: str,
) -> bool:
    configured = bool(webhook_url and webhook_url.strip())
    _log(f"Feishu webhook configured: {'true' if configured else 'false'}")
    _log(f"Feishu sender called: {'true' if enabled and configured else 'false'}")
    if not enabled:
        return False
    if not configured:
        raise FeishuError("FEISHU_WEBHOOK_URL is missing or blank")
    send_feishu_text(webhook_url, summary_text)
    return True
