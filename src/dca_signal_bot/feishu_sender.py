from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .config import StrategyConfig
from .execution_guidance import ExecutionGuidance
from .fx_converter import FxConversionSummary, format_rmb_usd_estimate
from .indicators import TickerIndicators
from .presentation import mode_label, order_type_label, outside_rth_label, session_label, state_label, tif_label, validation_label, yes_no
from .strategy_engine import StrategyDecision


class FeishuError(RuntimeError):
    """Raised when the Feishu webhook returns an error."""


@dataclass(frozen=True)
class FeishuPayload:
    text: str


def _log(message: str) -> None:
    print(f"[信息] {message}")


def _warn(message: str) -> None:
    print(f"[警告] {message}")


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
    execution_guidance: ExecutionGuidance | None = None,
    fx_summary: FxConversionSummary | None = None,
) -> str:
    _ = growth
    mode_line = mode_label(run_mode_label)
    lines = [
        f"\u65e5\u671f\uff1a{report_date}",
        f"\u8fd0\u884c\u6a21\u5f0f\uff1a{mode_line}",
        f"\u72b6\u6001\uff1a{state_label(decision.state_label)} (`{decision.state_label}`)",
        f"\u603b\u6295\u5165\uff1a{decision.recommendation_total_rmb} RMB",
        f"{config.core_ticker}\uff1a{decision.allocation.core_rmb} RMB",
        f"{config.growth_ticker}\uff1a{decision.allocation.growth_rmb} RMB",
        f"\u50a8\u5907\u91d1\u53d8\u52a8\uff1a{decision.reserve_delta_rmb:+d} RMB",
        f"\u50a8\u5907\u91d1\u4f59\u989d\uff1a{decision.reserve_cash_after_rmb} RMB",
        f"\u6570\u636e\u6e90\uff1a{data_source}",
        f"\u6700\u65b0\u5e02\u573a\u65e5\u671f\uff1a{config.core_ticker} {latest_market_date_core.isoformat()} / {config.growth_ticker} {latest_market_date_qqqm.isoformat()}",
        f"\u6821\u9a8c\u72b6\u6001\uff1a{validation_label(validation_status)} (`{validation_status}`)",
        f"\u539f\u56e0\uff1a{decision.reasons[-1]}",
        f"\u62a5\u544a\uff1a{report_path}",
    ]

    if execution_guidance is not None:
        lines.extend(
            [
                "IBKR 执行建议：",
                f"- 当前交易阶段：{session_label(execution_guidance.session_phase)}",
                f"- 现在可提交：{yes_no(execution_guidance.can_submit_now)}",
                f"- 现在大概率可成交：{yes_no(execution_guidance.can_likely_fill_now)}",
                f"- 下一次常规开盘（{execution_guidance.user_timezone}）：{_format_local_dt(execution_guidance.next_regular_open)}",
                f"- 下一次盘前/盘后可交易时段（{execution_guidance.user_timezone}）：{_format_local_dt(execution_guidance.next_extended_hours_opportunity)}",
                f"- 建议下单设置：{order_type_label(execution_guidance.preferred_order_type)} / {tif_label(execution_guidance.preferred_tif)} / {outside_rth_label(execution_guidance.suggest_outside_rth)}",
            ]
        )

    if fx_summary is not None:
        lines.extend(
            [
                "美元估算：",
                f"- 总投入：{format_rmb_usd_estimate(fx_summary.total_rmb, fx_summary.total_usd)}",
                f"- {config.core_ticker}：{format_rmb_usd_estimate(fx_summary.core_rmb, fx_summary.core_usd)}",
                f"- {config.growth_ticker}：{format_rmb_usd_estimate(fx_summary.growth_rmb, fx_summary.growth_usd)}",
                f"- 汇率来源：{fx_summary.source}",
                f"- 汇率校验状态：{validation_label(fx_summary.validation_status)}",
            ]
        )
        if fx_summary.rate_cny_per_usd is not None:
            lines.append(f"- 使用汇率：{fx_summary.rate_cny_per_usd:.4f} CNY per USD")
        else:
            lines.append("- 美元估算不可用（汇率数据问题）")

    return "\n".join(lines)


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
            f"\u6821\u9a8c\u72b6\u6001\uff1a{validation_label(validation_status)} (`{validation_status}`)",
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


def _format_local_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M %Z")


def send_feishu_text(webhook_url: str, text: str, timeout: int = 10, retries: int = 2) -> None:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise FeishuError("requests is required to send Feishu notifications") from exc

    webhook_url = webhook_url.strip() if webhook_url else ""
    if not webhook_url:
        raise FeishuError("FEISHU_WEBHOOK_URL is missing or blank")

    outgoing_text = _apply_keyword_prefix(text)
    _log("飞书 Webhook 已配置：是")
    _log("飞书发送器已调用：是")
    _log(f"飞书关键字已配置：{yes_no(outgoing_text != text)}")

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
            _warn(f"飞书请求第 {attempt}/{retries} 次失败：{exc}")
            if attempt >= retries:
                raise FeishuError("飞书 Webhook 请求失败") from exc
            continue

        _log(f"飞书 HTTP 状态：{response.status_code}")

        if response.status_code >= 500 and attempt < retries:
            _warn(
                f"飞书 Webhook 在第 {attempt}/{retries} 次返回 HTTP {response.status_code}，正在重试"
            )
            continue

        if response.status_code >= 400:
            raise FeishuError(
                f"飞书 Webhook HTTP 错误：{response.status_code}；响应体={_truncate(response.text)}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuError(f"飞书 Webhook 未返回 JSON；响应体={_truncate(response.text)}") from exc

        if not isinstance(payload, dict):
            raise FeishuError(f"飞书 Webhook 返回了非对象 JSON：{payload!r}")

        if payload.get("code", 0) != 0:
            raise FeishuError(
                "飞书 Webhook 返回业务错误："
                f"code={payload.get('code')}，msg={payload.get('msg')}，响应体={_truncate(response.text)}"
            )

        return

    if last_error is not None:
        raise FeishuError("飞书 Webhook 请求失败") from last_error


def maybe_send_feishu(
    *,
    enabled: bool,
    webhook_url: str | None,
    summary_text: str,
) -> bool:
    configured = bool(webhook_url and webhook_url.strip())
    _log(f"飞书 Webhook 已配置：{yes_no(configured)}")
    _log(f"飞书发送器已调用：{yes_no(enabled and configured)}")
    if not enabled:
        return False
    if not configured:
        raise FeishuError("FEISHU_WEBHOOK_URL 为空或未配置")
    send_feishu_text(webhook_url, summary_text)
    return True
