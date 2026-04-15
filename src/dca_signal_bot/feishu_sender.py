from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .config import StrategyConfig
from .execution_guidance import ExecutionGuidance
from .fx_converter import FxConversionSummary, convert_rmb_to_usd, format_rmb_usd_estimate
from .indicators import TickerIndicators
from .presentation import (
    asset_signal_label,
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


def _format_local_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M %Z")


def _base_amount_for_signal(config: StrategyConfig, decision: StrategyDecision, ticker: str) -> int:
    if ticker == config.core_ticker:
        return decision.baseline_allocation.core_rmb
    if ticker == config.secondary_ticker:
        return decision.baseline_allocation.secondary_rmb
    return decision.baseline_allocation.growth_rmb


def _format_delta_usd(value: int, fx_summary: FxConversionSummary | None) -> str:
    if fx_summary is None or fx_summary.rate_cny_per_usd is None:
        return "USD 不可用"
    usd = convert_rmb_to_usd(abs(value), fx_summary.rate_cny_per_usd)
    sign = "+" if value >= 0 else "-"
    return f"{sign}USD {usd:.2f}"


def build_summary_text(
    *,
    config: StrategyConfig,
    growth: TickerIndicators,
    decision: StrategyDecision,
    report_path: str | Path,
    report_date: str,
    data_source: str,
    latest_market_date_core: date,
    latest_market_date_secondary: date | None = None,
    latest_market_date_qqqm: date,
    validation_status: str,
    run_mode_label: str | None = None,
    execution_guidance: ExecutionGuidance | None = None,
    fx_summary: FxConversionSummary | None = None,
) -> str:
    _ = growth
    lines = [
        f"日期：{report_date}",
        f"运行模式：{mode_label(run_mode_label)}",
        f"状态：{state_label(decision.state_label)}",
        f"总投入：{decision.recommendation_total_rmb} RMB",
    ]

    if decision.strategy_mode == "manual_total_per_asset_signal":
        lines.extend(
            [
                "当前总投入由手动设定，以下建议仅调整资产间分配，不改变本月总投入。",
                f"基线分配：{config.core_ticker} {decision.baseline_allocation.core_rmb} / "
                f"{config.secondary_ticker} {decision.baseline_allocation.secondary_rmb} / "
                f"{config.growth_ticker} {decision.baseline_allocation.growth_rmb} RMB",
            ]
        )
        for signal in decision.asset_signals:
            base_rmb = _base_amount_for_signal(config, decision, signal.ticker)
            lines.append(
                f"{signal.ticker}：{asset_signal_label(signal.classification)}，"
                f"基线 {base_rmb} RMB，调整 {signal.normalized_adjustment_pct:+.2f}% "
                f"({signal.delta_rmb:+d} RMB / {_format_delta_usd(signal.delta_rmb, fx_summary)})，"
                f"最终 {signal.final_rmb} RMB"
            )
    else:
        lines.extend(
            [
                f"{config.core_ticker}：{decision.allocation.core_rmb} RMB",
                f"{config.secondary_ticker}：{decision.allocation.secondary_rmb} RMB" if config.secondary_ticker else "",
                f"{config.growth_ticker}：{decision.allocation.growth_rmb} RMB",
                f"储备金变动：{decision.reserve_delta_rmb:+d} RMB",
                f"储备金余额：{decision.reserve_cash_after_rmb} RMB",
            ]
        )

    lines.extend(["", f"数据源：{data_source}"])

    latest_parts = [f"{config.core_ticker} {latest_market_date_core.isoformat()}"]
    if config.secondary_ticker and latest_market_date_secondary is not None:
        latest_parts.append(f"{config.secondary_ticker} {latest_market_date_secondary.isoformat()}")
    latest_parts.append(f"{config.growth_ticker} {latest_market_date_qqqm.isoformat()}")
    lines.extend(
        [
            f"最新市场日期：{' / '.join(latest_parts)}",
            f"校验状态：{validation_label(validation_status)}",
            "",
            f"原因：{decision.reasons[-1]}",
            f"报告：{report_path}",
        ]
    )

    if execution_guidance is not None:
        lines.extend(
            [
                "",
                "IBKR 执行建议：",
                f"- 当前交易阶段：{session_label(execution_guidance.session_phase)}",
                f"- 现在可提交：{yes_no(execution_guidance.can_submit_now)}",
                f"- 现在大概率可成交：{yes_no(execution_guidance.can_likely_fill_now)}",
                f"- 下一次常规开盘（{execution_guidance.user_timezone}）：{_format_local_dt(execution_guidance.next_regular_open)}",
                f"- 下一次盘前/盘后可交易时段（{execution_guidance.user_timezone}）：{_format_local_dt(execution_guidance.next_extended_hours_opportunity)}",
                f"- 建议下单设置：{order_type_label(execution_guidance.preferred_order_type)} / "
                f"{tif_label(execution_guidance.preferred_tif)} / "
                f"{outside_rth_label(execution_guidance.suggest_outside_rth)}",
            ]
        )

    if fx_summary is not None:
        lines.extend(
            [
                "",
                "美元估算：",
                f"- 总投入：{format_rmb_usd_estimate(decision.recommendation_total_rmb, fx_summary.total_usd)}",
            ]
        )
        if decision.strategy_mode == "manual_total_per_asset_signal":
            for signal in decision.asset_signals:
                base_rmb = _base_amount_for_signal(config, decision, signal.ticker)
                if fx_summary.rate_cny_per_usd is None:
                    lines.append(f"- {signal.ticker}：基线 {base_rmb} RMB，调整 {_format_delta_usd(signal.delta_rmb, fx_summary)}，最终 USD 不可用")
                else:
                    base_usd = convert_rmb_to_usd(base_rmb, fx_summary.rate_cny_per_usd)
                    final_usd = convert_rmb_to_usd(signal.final_rmb, fx_summary.rate_cny_per_usd)
                    lines.append(
                        f"- {signal.ticker}：基线约 USD {base_usd:.2f} / 调整 {_format_delta_usd(signal.delta_rmb, fx_summary)} / 最终约 USD {final_usd:.2f}"
                    )
        else:
            lines.extend(
                [
                    f"- {config.core_ticker}：{format_rmb_usd_estimate(decision.allocation.core_rmb, fx_summary.core_usd)}",
                    f"- {config.secondary_ticker}：{format_rmb_usd_estimate(decision.allocation.secondary_rmb, fx_summary.extra_usd.get(config.secondary_ticker))}"
                    if config.secondary_ticker
                    else "",
                    f"- {config.growth_ticker}：{format_rmb_usd_estimate(decision.allocation.growth_rmb, fx_summary.growth_usd)}",
                ]
            )
        lines.extend(
            [
                f"- 汇率来源：{fx_summary.source}",
                f"- 汇率校验状态：{validation_label(fx_summary.validation_status)}",
            ]
        )
        if fx_summary.rate_cny_per_usd is not None:
            lines.append(f"- 使用汇率：1 USD = {fx_summary.rate_cny_per_usd:.4f} CNY")
        else:
            lines.append("- 美元估算不可用（汇率数据问题）")

    return "\n".join(line for line in lines if line != "")


def build_failure_alert_text(
    *,
    error: str,
    data_source: str,
    fetched_at_utc: datetime,
    core_ticker: str = "VOO",
    secondary_ticker: str | None = "VXUS",
    growth_ticker: str = "QQQM",
    validation_status: str = "FAIL",
) -> str:
    ticker_parts = [core_ticker]
    if secondary_ticker:
        ticker_parts.append(secondary_ticker)
    ticker_parts.append(growth_ticker)
    return "\n".join(
        [
            "数据校验失败，未生成可信报告。",
            f"时间：{_utc_iso(fetched_at_utc)}",
            f"标的组合：{' + '.join(ticker_parts)}",
            f"数据源：{data_source}",
            "最新市场日期：N/A",
            f"校验状态：{validation_label(validation_status)}",
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


def send_feishu_text(webhook_url: str, text: str, timeout: int = 10, retries: int = 2) -> None:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise FeishuError("requests is required to send Feishu notifications") from exc

    webhook_url = webhook_url.strip() if webhook_url else ""
    if not webhook_url:
        raise FeishuError("FEISHU_WEBHOOK_URL 为空或未配置")

    outgoing_text = _apply_keyword_prefix(text)
    _log("飞书 Webhook 已配置：是")
    _log("飞书发送器已调用：是")
    _log(f"飞书关键字已配置：{yes_no(outgoing_text != text)}")

    retries = max(1, retries)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                webhook_url,
                json={"msg_type": "text", "content": {"text": outgoing_text}},
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
            _warn(f"飞书 Webhook 在第 {attempt}/{retries} 次返回 HTTP {response.status_code}，正在重试")
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
