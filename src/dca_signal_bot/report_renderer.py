from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from .config import StrategyConfig
from .execution_guidance import ExecutionGuidance
from .fx_converter import FxConversionSummary, convert_rmb_to_usd, format_rmb_usd_estimate
from .gold_sleeve import GoldSleeveDecision
from .historical_review import HistoricalSignalReview
from .indicators import TickerIndicators
from .presentation import (
    decision_path_label,
    final_recommendation_label,
    mode_label,
    order_type_label,
    outside_rth_label,
    raw_signal_direction_label,
    raw_signal_judgment_label,
    rule_label,
    session_label,
    state_label,
    tif_label,
    validation_label,
    yes_no,
)
from .strategy_engine import AssetSignalEvaluation, RuleEvaluation, StrategyDecision


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_local_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M %Z")


def _format_delta_rmb(value: int) -> str:
    return f"{value:+d} RMB"


def _format_delta_usd(value: int, fx_summary: FxConversionSummary | None) -> str:
    if fx_summary is None or fx_summary.rate_cny_per_usd is None:
        return "美元估算不可用"
    usd = convert_rmb_to_usd(abs(value), fx_summary.rate_cny_per_usd)
    sign = "+" if value >= 0 else "-"
    return f"{sign}USD {usd:.2f}"


def _format_gold_usd_amount(amount_rmb: int | None, fx_summary: FxConversionSummary | None) -> str:
    if amount_rmb is None:
        return "美元估算不可用"
    if fx_summary is None or fx_summary.rate_cny_per_usd is None:
        return "美元估算不可用"
    return f"约 USD {convert_rmb_to_usd(amount_rmb, fx_summary.rate_cny_per_usd):.2f}"


def _format_shares(value: float | None, *, precision: int = 4) -> str:
    if value is None:
        return "不可用"
    text = f"{value:.{precision}f}"
    return text.rstrip("0").rstrip(".")


def _format_gold_market_value(gold_decision: GoldSleeveDecision) -> str:
    if gold_decision.current_gold_value_rmb is not None:
        if gold_decision.current_gold_value_usd is not None:
            return f"{gold_decision.current_gold_value_rmb} RMB（约 USD {gold_decision.current_gold_value_usd:.2f}）"
        return f"{gold_decision.current_gold_value_rmb} RMB"
    if gold_decision.current_gold_value_usd is not None:
        return f"约 USD {gold_decision.current_gold_value_usd:.2f}（RMB 不可用）"
    return "不可用"


def _base_amount_for_signal(config: StrategyConfig, decision: StrategyDecision, signal: AssetSignalEvaluation) -> int:
    if signal.ticker == config.core_ticker:
        return decision.baseline_allocation.core_rmb
    if signal.ticker == config.secondary_ticker:
        return decision.baseline_allocation.secondary_rmb
    return decision.baseline_allocation.growth_rmb


def _indicator_for_signal(
    *,
    config: StrategyConfig,
    core: TickerIndicators,
    secondary: TickerIndicators | None,
    growth: TickerIndicators,
    ticker: str,
) -> TickerIndicators:
    if ticker == config.core_ticker:
        return core
    if ticker == config.secondary_ticker and secondary is not None:
        return secondary
    return growth


def _format_asset_signal_conditions(signal: AssetSignalEvaluation) -> str:
    return "<br>".join(
        f"{condition.label}：{yes_no(condition.passed)}（{condition.observed}，阈值 {condition.threshold}）"
        for condition in signal.conditions
    )


def _format_signal_basis(indicators: TickerIndicators) -> str:
    return (
        f"52 周回撤 {indicators.drawdown_52w * 100:.2f}% / "
        f"相对 200DMA {indicators.deviation_from_sma200 * 100:.2f}% / "
        f"RSI(14) {indicators.rsi14:.2f}"
    )


def _render_final_adjustment_text(signal: AssetSignalEvaluation) -> str:
    if signal.delta_rmb == 0:
        return "原始信号存在偏热或偏弱信息，但在三资产零和归一化后，本月相对调整为 0，维持基线。"
    return (
        f"零和归一化后形成{final_recommendation_label(signal.normalized_adjustment_pct, signal.delta_rmb)}，"
        f"本月建议调整 {signal.normalized_adjustment_pct:+.2f}%（{signal.delta_rmb:+d} RMB）。"
    )


def _render_legacy_condition_lines(rule: RuleEvaluation) -> str:
    return "<br>".join(
        f"{condition.label}：{yes_no(condition.passed)}（{condition.observed}，阈值 {condition.threshold}）"
        for condition in rule.conditions
    )


def _render_historical_review_table(
    review: HistoricalSignalReview,
    *,
    config: StrategyConfig,
    strategy_mode: str,
) -> str:
    if not review.rows:
        return "_暂无可显示的历史回顾记录。_\n"

    if strategy_mode == "manual_total_per_asset_signal":
        lines = [
            f"| 月份 | 状态 | 基线金额 | 建议总投入 | {config.core_ticker} | {config.secondary_ticker} | {config.growth_ticker} | 触发摘要 | 原因 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
        for row in review.rows:
            lines.append(
                "| "
                f"{row.month} | {state_label(row.status)} | {row.base_monthly_rmb} | {row.suggested_total_rmb} | "
                f"{row.core_rmb} | {row.secondary_rmb} | {row.qqqm_rmb} | {decision_path_label(row.key_trigger_summary)} | "
                f"{row.short_reason} |"
            )
        return "\n".join(lines) + "\n"

    if config.secondary_ticker:
        lines = [
            f"| 月份 | 状态 | 基线金额 | 建议总投入 | {config.core_ticker} | {config.secondary_ticker} | {config.growth_ticker} | 储备金变动 | 储备金余额 | 触发项 | 原因 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    else:
        lines = [
            f"| 月份 | 状态 | 基线金额 | 建议总投入 | {config.core_ticker} | {config.growth_ticker} | 储备金变动 | 储备金余额 | 触发项 | 原因 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    for row in review.rows:
        if config.secondary_ticker:
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


def _render_gold_sleeve_section(
    gold_decision: GoldSleeveDecision,
    *,
    fx_summary: FxConversionSummary | None,
) -> str:
    lines = [
        "## 黄金保险仓判定",
        "",
        f"- 标的：`{gold_decision.ticker}`",
        f"- 数据来源：{gold_decision.data_source}",
        f"- 校验状态：{validation_label(gold_decision.validation_status)}",
    ]
    if gold_decision.latest_market_date is not None:
        lines.append(f"- 最新市场日期：{gold_decision.latest_market_date.isoformat()}")

    if gold_decision.missing_inputs:
        lines.append(f"- 输入状态：部分缺失（{' / '.join(gold_decision.missing_inputs)}）")
    else:
        lines.append("- 输入状态：完整")

    lines.extend(
        [
            f"- 当前总资产：`{gold_decision.current_total_portfolio_value_rmb} RMB`"
            if gold_decision.current_total_portfolio_value_rmb is not None
            else "- 当前总资产：不可用",
            f"- 当前 GLDM 持仓：`{_format_shares(gold_decision.current_gldm_shares)}` 股"
            if gold_decision.current_gldm_shares is not None
            else "- 当前 GLDM 持仓：不可用",
            f"- 当前 GLDM 价格：`USD {gold_decision.current_gldm_price_usd:.2f}`"
            if gold_decision.current_gldm_price_usd is not None
            else "- 当前 GLDM 价格：不可用",
            f"- 当前黄金市值：`{_format_gold_market_value(gold_decision)}`",
            f"- 当前黄金仓位：`{gold_decision.current_gold_weight * 100:.2f}%`"
            if gold_decision.current_gold_weight is not None
            else "- 当前黄金仓位：不可用",
            f"- 目标黄金仓位：`{gold_decision.target_gold_weight * 100:.2f}%`",
            f"- 黄金上限仓位：`{gold_decision.max_gold_weight * 100:.2f}%`",
            f"- 当前是否低于目标：`{yes_no(bool(gold_decision.below_target))}`"
            if gold_decision.below_target is not None
            else "- 当前是否低于目标：不可用",
            f"- 是否触发过热过滤：`{yes_no(gold_decision.overheat_triggered)}`"
            if gold_decision.overheat_triggered is not None
            else "- 是否触发过热过滤：不可用",
            f"- 综合评分：`{gold_decision.total_score:.1f}`" if gold_decision.total_score is not None else "- 综合评分：不可用",
        ]
    )
    if gold_decision.total_score is not None:
        lines.append(
            f"- 技术分：`{gold_decision.technical_score:.1f}` / 宏观分：`{gold_decision.macro_score:.1f}` / 慢变量分：`{gold_decision.optional_score:.1f}`"
        )

    buy_rmb = gold_decision.recommended_buy_rmb or 0
    lines.extend(
        [
            f"- 建议：`{gold_decision.action_label}`",
            f"- 建议买入金额：`{buy_rmb} RMB（{_format_gold_usd_amount(gold_decision.recommended_buy_rmb, fx_summary)}）`",
        ]
    )
    if gold_decision.recommended_buy_shares is not None and gold_decision.recommended_buy_rmb and gold_decision.recommended_buy_rmb > 0:
        lines.append(f"- 约对应 GLDM `{_format_shares(gold_decision.recommended_buy_shares)}` 股")
    if gold_decision.projected_gold_weight_after_buy is not None:
        lines.append(f"- 建议买入后黄金仓位：`{gold_decision.projected_gold_weight_after_buy * 100:.2f}%`")
    if gold_decision.remaining_gap_after_buy_rmb is not None:
        if gold_decision.projected_gold_weight_after_buy is not None:
            lines.append(
                f"- 买入后距目标仍差：`{gold_decision.remaining_gap_after_buy_rmb} RMB / "
                f"{max(gold_decision.target_gold_weight * 100 - gold_decision.projected_gold_weight_after_buy * 100, 0):.2f}%`"
            )
        else:
            lines.append(f"- 买入后距目标仍差：`{gold_decision.remaining_gap_after_buy_rmb} RMB`")
    lines.extend(
        [
            f"- 说明：{gold_decision.reason}",
            "- 黄金模块为保险仓择时补仓，不参与主仓月频定投。",
        ]
    )
    if gold_decision.overheat_reasons:
        lines.append("")
        lines.append("### 过热过滤说明")
        lines.append("")
        lines.extend(f"- {reason}" for reason in gold_decision.overheat_reasons)
    if gold_decision.score_details:
        lines.append("")
        lines.append("### 评分细项")
        lines.append("")
        lines.extend(f"- {detail}" for detail in gold_decision.score_details)
    if gold_decision.optional_data_notes:
        lines.append("")
        lines.append("### 可选因子说明")
        lines.append("")
        lines.extend(f"- {note}" for note in gold_decision.optional_data_notes)
    return "\n".join(lines) + "\n"


def _render_fx_section(
    fx_summary: FxConversionSummary,
    *,
    config: StrategyConfig,
    decision: StrategyDecision,
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

    lines.append(f"- 使用汇率：`1 USD = {fx_summary.rate_cny_per_usd:.4f} CNY`")
    lines.append(f"- 总投入：`{format_rmb_usd_estimate(decision.recommendation_total_rmb, fx_summary.total_usd)}`")

    if decision.strategy_mode == "manual_total_per_asset_signal":
        for signal in decision.asset_signals:
            base_rmb = _base_amount_for_signal(config, decision, signal)
            base_usd = convert_rmb_to_usd(base_rmb, fx_summary.rate_cny_per_usd)
            final_usd = convert_rmb_to_usd(signal.final_rmb, fx_summary.rate_cny_per_usd)
            delta_usd = _format_delta_usd(signal.delta_rmb, fx_summary)
            lines.extend(
                [
                    f"- {signal.ticker} 基线：`{base_rmb} RMB（约 USD {base_usd:.2f}）`",
                    f"- {signal.ticker} 调整：`{signal.normalized_adjustment_pct:+.2f}% / {_format_delta_rmb(signal.delta_rmb)} / {delta_usd}`",
                    f"- {signal.ticker} 最终建议：`{signal.final_rmb} RMB（约 USD {final_usd:.2f}）`",
                ]
            )
    else:
        lines.extend(
            [
                f"- {config.core_ticker}：`{format_rmb_usd_estimate(decision.allocation.core_rmb, fx_summary.core_usd)}`",
                f"- {config.secondary_ticker}：`{format_rmb_usd_estimate(decision.allocation.secondary_rmb, fx_summary.extra_usd.get(config.secondary_ticker))}`"
                if config.secondary_ticker
                else "",
                f"- {config.growth_ticker}：`{format_rmb_usd_estimate(decision.allocation.growth_rmb, fx_summary.growth_usd)}`",
            ]
        )
    return "\n".join(line for line in lines if line) + "\n"


def _render_asset_snapshot(
    config: StrategyConfig,
    core: TickerIndicators,
    secondary: TickerIndicators | None,
    growth: TickerIndicators,
) -> str:
    rows = [
        "| 标的 | 当前价格 | 52 周高点 | 回撤 | 200 日均线 | 200 日均线偏离 | RSI(14) | 3 年分位 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {config.core_ticker} | {core.current_price:.2f} | {core.high_52w:.2f} | {core.drawdown_52w * 100:.2f}% | {core.sma200:.2f} | {core.deviation_from_sma200 * 100:.2f}% | {core.rsi14:.2f} | {core.price_percentile_3y:.2f}% |",
    ]
    if secondary is not None and config.secondary_ticker:
        rows.append(
            f"| {config.secondary_ticker} | {secondary.current_price:.2f} | {secondary.high_52w:.2f} | "
            f"{secondary.drawdown_52w * 100:.2f}% | {secondary.sma200:.2f} | "
            f"{secondary.deviation_from_sma200 * 100:.2f}% | {secondary.rsi14:.2f} | {secondary.price_percentile_3y:.2f}% |"
        )
    rows.append(
        f"| {config.growth_ticker} | {growth.current_price:.2f} | {growth.high_52w:.2f} | "
        f"{growth.drawdown_52w * 100:.2f}% | {growth.sma200:.2f} | "
        f"{growth.deviation_from_sma200 * 100:.2f}% | {growth.rsi14:.2f} | {growth.price_percentile_3y:.2f}% |"
    )
    return "\n".join(rows)


def _render_manual_raw_signal_section(
    *,
    config: StrategyConfig,
    core: TickerIndicators,
    secondary: TickerIndicators | None,
    growth: TickerIndicators,
    decision: StrategyDecision,
) -> str:
    lines = [
        "## 资产原始信号",
        "",
        "- 当前总投入由手动设定。",
        "- 这里展示的是各资产独立计算后的原始信号，尚未进行零和归一化。",
        "",
        "| 资产 | 基线权重 | 基线金额 | 原始信号判断 | 原始信号依据 | 原始建议方向 |",
        "| --- | ---: | ---: | --- | --- | --- |",
    ]
    for signal in decision.asset_signals:
        base_rmb = _base_amount_for_signal(config, decision, signal)
        indicators = _indicator_for_signal(
            config=config,
            core=core,
            secondary=secondary,
            growth=growth,
            ticker=signal.ticker,
        )
        lines.append(
            f"| {signal.ticker} | {(base_rmb / decision.recommendation_total_rmb) * 100:.2f}% | "
            f"{base_rmb} | {raw_signal_judgment_label(signal.classification)} | "
            f"{_format_signal_basis(indicators)} | {raw_signal_direction_label(signal.classification)} |"
        )
    return "\n".join(lines) + "\n"


def _render_manual_final_section(
    *,
    config: StrategyConfig,
    decision: StrategyDecision,
    fx_summary: FxConversionSummary | None,
) -> str:
    lines = [
        "## 归一化后最终建议",
        "",
        "- 以下建议才是本月可执行的相对增减配结果，总投入保持不变。",
        "",
        "| 资产 | 基线金额 | 归一化后建议 | 最终调整百分比 | 调整金额（RMB） | 调整金额（USD） | 最终建议金额 | 最终说明 |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for signal in decision.asset_signals:
        base_rmb = _base_amount_for_signal(config, decision, signal)
        usd_delta = _format_delta_usd(signal.delta_rmb, fx_summary)
        lines.append(
            f"| {signal.ticker} | {base_rmb} | {final_recommendation_label(signal.normalized_adjustment_pct, signal.delta_rmb)} | "
            f"{signal.normalized_adjustment_pct:+.2f}% | {signal.delta_rmb:+d} | {usd_delta} | {signal.final_rmb} | "
            f"{_render_final_adjustment_text(signal)} |"
        )
    return "\n".join(lines) + "\n"


def _render_manual_condition_details(decision: StrategyDecision) -> str:
    lines = [
        "## 条件检查详情",
        "",
        "| 资产 | 原始信号判断 | 条件检查 | 原始信号说明 |",
        "| --- | --- | --- | --- |",
    ]
    for signal in decision.asset_signals:
        lines.append(
            f"| {signal.ticker} | {raw_signal_judgment_label(signal.classification)} | "
            f"{_format_asset_signal_conditions(signal)} | {signal.summary} |"
        )
    return "\n".join(lines) + "\n"


def _render_legacy_signal_details(decision: StrategyDecision) -> str:
    trigger_rows = "\n".join(
        f"| {rule_label(rule.rule_name)} | {yes_no(rule.triggered)} | {_render_legacy_condition_lines(rule)} | {rule.summary} |"
        for rule in decision.rule_evaluations
    )
    return (
        "## 信号触发详情\n\n"
        "### 规则评估\n\n"
        "| 规则 | 是否触发 | 条件检查 | 说明 |\n"
        "| --- | --- | --- | --- |\n"
        f"{trigger_rows}\n\n"
        "### 决策路径\n\n"
        f"- 触发规则：`{decision.triggered_rule}`\n"
        f"- 决策路径：`{decision_path_label(decision.decision_path)}`\n"
        f"- 已触发规则：`{', '.join(rule_label(rule.rule_name) for rule in decision.rule_evaluations if rule.triggered) or '无'}`\n"
        f"- 未触发规则：`{', '.join(rule_label(rule.rule_name) for rule in decision.rule_evaluations if not rule.triggered) or '无'}`\n"
    )


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
    gold_decision: GoldSleeveDecision | None = None,
) -> str:
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

    execution_section = _render_execution_guidance(execution_guidance).rstrip() if execution_guidance is not None else ""
    fx_section = _render_fx_section(fx_summary, config=config, decision=decision).rstrip() if fx_summary is not None else ""
    gold_section = _render_gold_sleeve_section(gold_decision, fx_summary=fx_summary).rstrip() if gold_decision is not None else ""
    historical_section = ""
    if historical_review is not None:
        historical_section = (
            f"## 历史信号回顾（最近 {historical_review.months} 个月）\n\n"
            f"> {historical_review.note}\n\n"
            f"{_render_historical_review_table(historical_review, config=config, strategy_mode=decision.strategy_mode)}"
        ).rstrip()

    market_section = (
        "## 市场数据\n\n"
        f"{_render_asset_snapshot(config, core, secondary, growth)}\n\n"
        f"- 当前储备金余额：`{reserve_cash_rmb} RMB`\n"
        f"- 储备金变动：`{decision.reserve_delta_rmb:+d} RMB`\n"
    )

    if decision.strategy_mode == "manual_total_per_asset_signal":
        raw_signal_section = _render_manual_raw_signal_section(
            config=config,
            core=core,
            secondary=secondary,
            growth=growth,
            decision=decision,
        ).rstrip()
        recommendation_section = _render_manual_final_section(
            config=config,
            decision=decision,
            fx_summary=fx_summary,
        ).rstrip()
        trigger_section = _render_manual_condition_details(decision).rstrip()
    else:
        recommendation_section = (
            "## 本月建议\n\n"
            f"- 本月建议总投入金额：`{decision.recommendation_total_rmb} RMB`\n"
            f"- {config.core_ticker} 建议投入金额：`{decision.allocation.core_rmb} RMB`\n"
            + (f"- {config.secondary_ticker} 建议投入金额：`{decision.allocation.secondary_rmb} RMB`\n" if config.secondary_ticker else "")
            + f"- {config.growth_ticker} 建议投入金额：`{decision.allocation.growth_rmb} RMB`\n"
            f"- 本月建议动作：`{decision.action_label}`\n"
            f"- 储备金复用触发：`{decision.reserve_delta_rmb:+d} RMB`\n"
        ).rstrip()
        trigger_section = _render_legacy_signal_details(decision).rstrip()

    risk_lines = [
        "### 风险提示",
        "",
        "- 本报告仅提供规则化辅助决策，不构成投资建议。",
        "- 本项目不会自动交易，资产级高配/低配建议仅用于手动执行参考。",
        "- 历史指标不能保证未来收益，ETF 价格、汇率与数据源都可能波动或修正。",
    ]
    if run_mode_label:
        risk_lines.append("- 模拟模式默认不会修改正式储备金状态。")
    risk_lines.extend(
        [
            "",
            "### 原因说明",
            "",
            *[f"- {reason}" for reason in decision.reasons],
            "",
            "### 下次查看建议",
            "",
            "建议在下一个月首个交易日或下一次月度运行时再次查看；如需手动调整总投入，可直接在 workflow_dispatch 或 CLI 中覆盖月投金额。",
        ]
    )

    body = [
        f"# {config.strategy_name} 月度定投报告",
        "",
        f"**日期**：{report_date.isoformat()}  ",
        f"**运行模式**：`{mode_label(run_mode_label)}`  ",
        f"**当前状态**：`{state_label(decision.state_label)}` (`{decision.state_label}`)  ",
        f"**策略模式**：`{decision.strategy_mode}`",
        "",
        *data_lines,
    ]
    if execution_section:
        body.extend([execution_section, ""])
    if fx_section:
        body.extend([fx_section, ""])
    if gold_section:
        body.extend([gold_section, ""])
    body.extend(
        [
            market_section.rstrip(),
            "",
            raw_signal_section if decision.strategy_mode == "manual_total_per_asset_signal" else "",
            "" if decision.strategy_mode == "manual_total_per_asset_signal" else "",
            recommendation_section,
            "",
            trigger_section,
            "",
            *risk_lines,
            "",
        ]
    )
    if historical_section:
        body.extend([historical_section, ""])
    return "\n".join(body).strip() + "\n"


def report_path_for(report_dir: str | Path, report_date: date) -> Path:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / f"{report_date:%Y-%m}-report.md"
