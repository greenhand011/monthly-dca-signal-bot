from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .config import StrategyConfig
from .execution_guidance import ExecutionGuidance
from .fx_converter import FxConversionSummary, format_rmb_usd_estimate
from .indicators import TickerIndicators
from .presentation import (
    mode_label,
    order_type_label,
    outside_rth_label,
    session_label,
    state_label,
    tif_label,
    validation_label,
    yes_no,
)
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
        f"日期：{report_date}",
        f"运行模式：{mode_line}",
        f"状态：{state_label(decision.state_label)} (`{decision.state_label}`)",
        f"总投入：{decision.recommendation_total_rmb} RMB",
        f"{config.core_ticker}：{decision.allocation.core_rmb} RMB",
    ]
    if config.secondary_ticker:
        lines.append(f"{config.secondary_ticker}：{decision.allocation.secondary_rmb} RMB")
    lines.extend(
        [
            f"{config.growth_ticker}：{decision.allocation.growth_rmb} RMB",
            f"储备金变动：{decision.reserve_delta_rmb:+d} RMB",
            f"储备金余额：{decision.reserve_cash_after_rmb} RMB",
            f"数据源：{data_source}",
            f"最新市场日期：{config.core_ticker} {latest_market_date_core.isoformat()} / {config.growth_ticker} {latest_market_date_qqqm.isoformat()}",
            f"校验状态：{validation_label(validation_status)} (`{validation_status}`)",
            f"原因：{decision.reasons[-1]}",
            f"报告：{report_path}",
        ]
    )

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
            ]
        )
        if fx_summary.extra_rmb:
            lines.extend(
                [
                    f"- {ticker}：{format_rmb_usd_estimate(amount, fx_summary.extra_usd.get(ticker))}"
                    for ticker, amount in fx_summary.extra_rmb.items()
                ]
            )
        lines.extend(
            [
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
            "数据校验失败，未生成可信报告。",
            f"时间：{_utc_iso(fetched_at_utc)}",
            f"标的组合：{core_ticker} + {growth_ticker}",
            f"数据源：{data_source}",
            "最新市场日期：N/A",
            f"校验状态：{validation_label(validation_status)} (`{validation_status}`)",
            f"错误：{error}",
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
