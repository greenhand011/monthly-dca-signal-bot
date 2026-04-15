from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from .config import StrategyConfig
from .execution_guidance import ExecutionGuidance
from .fx_converter import FxConversionSummary, format_rmb_usd_estimate
from .historical_review import HistoricalSignalReview
from .indicators import TickerIndicators
from .presentation import (
    condition_label,
    decision_path_label,
    mode_label,
    order_type_label,
    outside_rth_label,
    rule_label,
    session_label,
    state_label,
    tif_label,
    validation_label,
    yes_no,
)
from .strategy_engine import RuleEvaluation, StrategyDecision


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_local_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M %Z")


def _render_condition_lines(rule: RuleEvaluation) -> str:
    return "<br>".join(
        f"{condition_label(condition.label)}：{yes_no(condition.passed)}"
        f"（{condition.observed}，阈值 {condition.threshold}）"
        for condition in rule.conditions
    )


def _render_historical_review_table(
    review: HistoricalSignalReview,
    *,
    core_label: str,
    growth_label: str,
    secondary_label: str | None,
) -> str:
    if not review.rows:
        return "_暂无可显示的历史回顾记录。_\n"

    if secondary_label:
        lines = [
            f"| 月份 | 状态 | 基线金额 | 建议总投入 | {core_label} | {secondary_label} | {growth_label} | 储备金变动 | 储备金余额 | 触发项 | 原因 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    else:
        lines = [
            f"| 月份 | 状态 | 基线金额 | 建议总投入 | {core_label} | {growth_label} | 储备金变动 | 储备金余额 | 触发项 | 原因 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]

    for row in review.rows:
        if secondary_label:
            lines.append(
                "| "
                f"{row.month} | {state_label(row.status)} | {row.base_monthly_rmb} | {row.suggested_total_rmb} | "
                f"{row.core_rmb} | {row.secondary_rmb} | {row.qqqm_rmb} | {row.reserve_cash_delta_rmb:+d} | "
                f"{row.reserve_cash_balance_rmb} | {rule_label(row.key_trigger_summary)} | {row.short_reason} |"
            )
        else:
            lines.append(
                "| "
                f"{row.month} | {state_label(row.status)} | {row.base_monthly_rmb} | {row.suggested_total_rmb} | "
                f"{row.core_rmb} | {row.qqqm_rmb} | {row.reserve_cash_delta_rmb:+d} | {row.reserve_cash_balance_rmb} | "
                f"{rule_label(row.key_trigger_summary)} | {row.short_reason} |"
            )
    return "\n".join(lines) + "\n"


def _render_execution_guidance(guidance: ExecutionGuidance) -> str:
    warnings = "\n".join(f"- {warning}" for warning in guidance.warnings)
    notes = "\n".join(f"- {note}" for note in guidance.notes)
    return (
        "## IBKR 执行建议\n\n"
        f"- 当前交易阶段（US/Eastern）：`{session_label(guidance.session_phase)}`\n"
        f"- 现在可提交：`{yes_no(guidance.can_submit_now)}`\n"
        f"- 现在大概率可成交：`{yes_no(guidance.can_likely_fill_now)}`\n"
        f"- 下一次常规开盘（{guidance.user_timezone}）：`{_format_local_dt(guidance.next_regular_open)}`\n"
        f"- 下一次盘前/盘后可交易时段（{guidance.user_timezone}）：`{_format_local_dt(guidance.next_extended_hours_opportunity)}`\n"
        f"- 建议下单设置：`{order_type_label(guidance.preferred_order_type)}` / "
        f"`{tif_label(guidance.preferred_tif)}` / "
        f"`{outside_rth_label(guidance.suggest_outside_rth)}`\n\n"
        "### 风险与说明\n\n"
        f"{warnings}\n"
        f"{notes}\n"
    )


def _render_fx_section(
    fx_summary: FxConversionSummary,
    *,
    core_label: str,
    growth_label: str,
) -> str:
    lines = [
        "## 美元估算",
        "",
        f"- 汇率来源：{fx_summary.source}",
        f"- 汇率标的：`{fx_summary.pair_ticker}`（{fx_summary.pair_description}）",
        f"- 汇率抓取时间（UTC）：{_utc_iso(fx_summary.fetched_at_utc)}",
        f"- 汇率校验状态：{validation_label(fx_summary.validation_status)} (`{fx_summary.validation_status}`)",
    ]

    if fx_summary.rate_cny_per_usd is None:
        lines.append("- 美元估算不可用（汇率抓取或校验失败）。")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            f"- 使用汇率：`1 USD = {fx_summary.rate_cny_per_usd:.4f} CNY`",
            f"- 总投入：`{format_rmb_usd_estimate(fx_summary.total_rmb, fx_summary.total_usd)}`",
            f"- {core_label}：`{format_rmb_usd_estimate(fx_summary.core_rmb, fx_summary.core_usd)}`",
        ]
    )
    for ticker, amount in fx_summary.extra_rmb.items():
        lines.append(f"- {ticker}：`{format_rmb_usd_estimate(amount, fx_summary.extra_usd.get(ticker))}`")
    lines.append(f"- {growth_label}：`{format_rmb_usd_estimate(fx_summary.growth_rmb, fx_summary.growth_usd)}`")
    return "\n".join(lines) + "\n"


def render_report(
    *,
    config: StrategyConfig,
    core: TickerIndicators,
    secondary: TickerIndicators | None,
    growth: TickerIndicators,
    decision: StrategyDecision,
    reserve_cash_rmb: int,
    report_date: date,
    data_source: str,
    fetched_at_utc: datetime,
    latest_market_date_core: date,
    latest_market_date_secondary: date | None = None,
    latest_market_date_qqqm: date,
    validation_status: str,
    run_mode_label: str | None = None,
    historical_review: HistoricalSignalReview | None = None,
    execution_guidance: ExecutionGuidance | None = None,
    fx_summary: FxConversionSummary | None = None,
) -> str:
    reasons = "\n".join(f"- {reason}" for reason in decision.reasons)
    run_mode_line = f"`{mode_label(run_mode_label)}`"
    status_line = f"`{state_label(decision.state_label)}` (`{decision.state_label}`)"
    trigger_rows = "\n".join(
        f"| {rule_label(rule.rule_name)} | {yes_no(rule.triggered)} | {_render_condition_lines(rule)} | {rule.summary} |"
        for rule in decision.rule_evaluations
    )
    trigger_table = (
        "| 规则 | 是否触发 | 条件检查 | 说明 |\n"
        "| --- | --- | --- | --- |\n"
        f"{trigger_rows}\n"
    )

    data_lines = [
        "## 数据信息",
        "",
        f"- 数据来源：{data_source}",
        f"- 数据抓取时间（UTC）：{_utc_iso(fetched_at_utc)}",
        f"- {config.core_ticker} 最新市场日期：{latest_market_date_core.isoformat()}",
    ]
    if config.secondary_ticker and latest_market_date_secondary is not None:
        data_lines.append(f"- {config.secondary_ticker} 最新市场日期：{latest_market_date_secondary.isoformat()}")
    data_lines.extend(
        [
            f"- {config.growth_ticker} 最新市场日期：{latest_market_date_qqqm.isoformat()}",
            f"- 校验状态：{validation_label(validation_status)} (`{validation_status}`)",
            "",
        ]
    )

    execution_section = ""
    if execution_guidance is not None:
        execution_section = _render_execution_guidance(execution_guidance) + "\n"

    fx_section = ""
    if fx_summary is not None:
        fx_section = _render_fx_section(
            fx_summary,
            core_label=config.core_ticker,
            growth_label=config.growth_ticker,
        ) + "\n"

    market_lines = [
        "## 市场数据",
        "",
        f"- {config.core_ticker} 当前价格：`{core.current_price:.2f}`",
    ]
    if secondary is not None and config.secondary_ticker:
        market_lines.append(f"- {config.secondary_ticker} 当前价格：`{secondary.current_price:.2f}`")
    market_lines.extend(
        [
            f"- {config.growth_ticker} 当前价格：`{growth.current_price:.2f}`",
            f"- {config.growth_ticker} 52 周高点：`{growth.high_52w:.2f}`",
            f"- {config.growth_ticker} 距 52 周高点回撤：`{growth.drawdown_52w * 100:.2f}%`",
            f"- {config.growth_ticker} 相对 200 日均线偏离：`{growth.deviation_from_sma200 * 100:.2f}%`",
            f"- {config.growth_ticker} 200 日均线：`{growth.sma200:.2f}`",
            f"- {config.growth_ticker} RSI(14)：`{growth.rsi14:.2f}`",
            f"- {config.core_ticker} 3 年价格分位：`{core.price_percentile_3y:.2f}%`",
        ]
    )
    if secondary is not None and config.secondary_ticker:
        market_lines.append(f"- {config.secondary_ticker} 3 年价格分位：`{secondary.price_percentile_3y:.2f}%`")
    market_lines.extend(
        [
            f"- {config.growth_ticker} 3 年价格分位：`{growth.price_percentile_3y:.2f}%`",
            f"- 当前储备金余额：`{reserve_cash_rmb} RMB`",
            f"- 储备金变动：`{decision.reserve_delta_rmb:+d} RMB`",
            "",
        ]
    )

    snapshot_rows = [
        "| 标的 | 当前价格 | 52 周高点 | 回撤 | 200 日均线 | 200 日均线偏离 | RSI(14) | 3 年分位 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {config.core_ticker} | {core.current_price:.2f} | {core.high_52w:.2f} | {core.drawdown_52w * 100:.2f}% | {core.sma200:.2f} | {core.deviation_from_sma200 * 100:.2f}% | {core.rsi14:.2f} | {core.price_percentile_3y:.2f}% |",
    ]
    if secondary is not None and config.secondary_ticker:
        snapshot_rows.append(
            f"| {config.secondary_ticker} | {secondary.current_price:.2f} | {secondary.high_52w:.2f} | "
            f"{secondary.drawdown_52w * 100:.2f}% | {secondary.sma200:.2f} | "
            f"{secondary.deviation_from_sma200 * 100:.2f}% | {secondary.rsi14:.2f} | {secondary.price_percentile_3y:.2f}% |"
        )
    snapshot_rows.append(
        f"| {config.growth_ticker} | {growth.current_price:.2f} | {growth.high_52w:.2f} | "
        f"{growth.drawdown_52w * 100:.2f}% | {growth.sma200:.2f} | "
        f"{growth.deviation_from_sma200 * 100:.2f}% | {growth.rsi14:.2f} | {growth.price_percentile_3y:.2f}% |"
    )

    recommendation_lines = [
        "## 本月建议",
        "",
        f"- 本月建议总投入金额：`{decision.recommendation_total_rmb} RMB`",
        f"- {config.core_ticker} 建议投入金额：`{decision.allocation.core_rmb} RMB`",
    ]
    if config.secondary_ticker:
        recommendation_lines.append(f"- {config.secondary_ticker} 建议投入金额：`{decision.allocation.secondary_rmb} RMB`")
    recommendation_lines.extend(
        [
            f"- {config.growth_ticker} 建议投入金额：`{decision.allocation.growth_rmb} RMB`",
            f"- 本月建议动作：`{decision.action_label}`",
            f"- 储备金复用触发：`{decision.reserve_delta_rmb:+d} RMB`",
            "",
            "### 原因说明",
            "",
            reasons,
            "",
        ]
    )

    historical_section = ""
    if historical_review is not None:
        historical_section = (
            f"## 历史信号回顾（最近 {historical_review.months} 个月）\n\n"
            f"> {historical_review.note}\n\n"
            f"{_render_historical_review_table(historical_review, core_label=config.core_ticker, growth_label=config.growth_ticker, secondary_label=config.secondary_ticker)}\n"
        )

    risk_lines = [
        "### 风险提示",
        "",
        "- 本报告仅提供规则化辅助决策，不构成投资建议。",
        "- 历史指标不能保证未来收益，ETF 价格、汇率与数据源都可能波动或修正。",
        "- 储备金机制可以平滑节奏，但不会消除市场风险。",
    ]
    if run_mode_label:
        risk_lines.append("- 模拟模式默认不会修改正式储备金状态。")
    risk_lines.extend(
        [
            "",
            "### 下次查看建议",
            "",
            "建议在下一个月首个交易日或下一次月度运行时再次查看；如果市场结构发生明显变化，也可以提前复核。",
        ]
    )

    return "\n".join(
        [
            f"# {config.strategy_name} 月度定投报告",
            "",
            f"**日期**：{report_date.isoformat()}  ",
            f"**运行模式**：{run_mode_line}  ",
            f"**当前市场状态**：{status_line}",
            "",
            *data_lines,
            execution_section.rstrip(),
            fx_section.rstrip(),
            *market_lines,
            "## 信号触发详情",
            "",
            "### 当前资产快照",
            "",
            *snapshot_rows,
            "",
            "### 规则评估",
            "",
            trigger_table.rstrip(),
            "",
            "### 决策路径",
            "",
            f"- 触发规则：`{decision.triggered_rule}`",
            f"- 决策路径：`{decision_path_label(decision.decision_path)}`",
            f"- 已触发规则：`{', '.join(rule_label(rule.rule_name) for rule in decision.rule_evaluations if rule.triggered) or '无'}`",
            f"- 未触发规则：`{', '.join(rule_label(rule.rule_name) for rule in decision.rule_evaluations if not rule.triggered) or '无'}`",
            "",
            *recommendation_lines,
            *risk_lines,
            "",
            historical_section.rstrip(),
        ]
    ).strip() + "\n"


def report_path_for(report_dir: str | Path, report_date: date) -> Path:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / f"{report_date:%Y-%m}-report.md"
