from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import apply_base_override, load_strategy_config
from .data_fetcher import DATA_SOURCE, DataFetchError, fetch_histories
from .execution_guidance import build_execution_guidance
from .feishu_sender import FeishuError, build_failure_alert_text, build_summary_text, maybe_send_feishu
from .fx_converter import build_fx_conversion_summary
from .gold_sleeve import evaluate_gold_sleeve
from .historical_review import build_historical_signal_review
from .indicators import IndicatorComputationError, compute_ticker_indicators
from .presentation import (
    final_recommendation_label,
    mode_label,
    raw_signal_direction_label,
    raw_signal_judgment_label,
    session_label,
    state_label,
    validation_label,
    yes_no,
)
from .report_renderer import render_report, report_path_for
from .reserve_state import dump_state, load_state, utc_now_iso
from .strategy_engine import evaluate_strategy


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the monthly DCA signal bot.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Fetch data, generate the report, update state, and optionally notify Feishu.",
    )
    run_parser.add_argument("--config", default="config/strategy.yaml", help="Path to the strategy YAML file.")
    run_parser.add_argument("--state-file", default="state/reserve_state.json", help="Path to the reserve state JSON file.")
    run_parser.add_argument("--reports-dir", default="reports", help="Directory for generated reports.")
    run_parser.add_argument("--feishu-webhook-url", default=os.getenv("FEISHU_WEBHOOK_URL"), help="Feishu webhook URL.")
    run_parser.add_argument(
        "--base-monthly-rmb",
        type=int,
        default=None,
        help="Optional simulation override for the monthly base amount. When set, reserve_state.json is not updated.",
    )
    run_parser.add_argument(
        "--review-months",
        type=int,
        default=12,
        help="How many recent month-end snapshots to include in the historical signal review.",
    )
    run_parser.add_argument(
        "--current-total-portfolio-value-rmb",
        type=int,
        default=None,
        help="Current total portfolio value in RMB for gold sleeve evaluation.",
    )
    run_parser.add_argument(
        "--current-gldm-shares",
        type=float,
        default=None,
        help="Current GLDM share count for gold sleeve evaluation.",
    )
    run_parser.add_argument("--dry-run", action="store_true", help="Do not send Feishu notifications.")
    return parser


def _maybe_send_failure_alert(
    *,
    webhook_url: str | None,
    dry_run: bool,
    error: str,
    fetched_at_utc: datetime,
    core_ticker: str,
    secondary_ticker: str | None,
    growth_ticker: str,
) -> bool:
    if dry_run:
        return False
    if not webhook_url:
        raise FeishuError("FEISHU_WEBHOOK_URL 为空或未配置")

    text = build_failure_alert_text(
        error=error,
        data_source=DATA_SOURCE,
        fetched_at_utc=fetched_at_utc,
        core_ticker=core_ticker,
        secondary_ticker=secondary_ticker,
        growth_ticker=growth_ticker,
        validation_status="FAIL",
    )
    from .feishu_sender import send_feishu_text

    send_feishu_text(webhook_url, text)
    return True


def _run(
    config_path: str,
    state_file: str,
    reports_dir: str,
    webhook_url: str | None,
    dry_run: bool,
    base_monthly_rmb: int | None = None,
    review_months: int = 12,
    current_total_portfolio_value_rmb: int | None = None,
    current_gldm_shares: float | None = None,
) -> int:
    config = load_strategy_config(config_path)
    if base_monthly_rmb is not None and base_monthly_rmb <= 0:
        raise ValueError("base_monthly_rmb must be positive")
    if review_months < 1:
        raise ValueError("review_months must be at least 1")

    effective_config = apply_base_override(config, base_monthly_rmb)
    simulation_mode = base_monthly_rmb is not None and base_monthly_rmb != config.base_monthly_rmb
    run_mode_label = (
        f"模拟模式：基线月投金额 = {effective_config.base_monthly_rmb}" if simulation_mode else None
    )

    reserve_state = load_state(state_file)
    report_date = datetime.now(ZoneInfo(config.report_timezone)).date()
    fetched_at_utc = datetime.now(timezone.utc)

    try:
        tickers = [effective_config.core_ticker]
        if effective_config.secondary_ticker:
            tickers.append(effective_config.secondary_ticker)
        tickers.append(effective_config.growth_ticker)

        bundle = fetch_histories(
            tickers,
            reference_date=report_date,
            fetched_at_utc=fetched_at_utc,
        )

        core_history = bundle.histories[effective_config.core_ticker]
        growth_history = bundle.histories[effective_config.growth_ticker]
        secondary_history = (
            bundle.histories[effective_config.secondary_ticker]
            if effective_config.secondary_ticker
            else None
        )

        core_indicators = compute_ticker_indicators(core_history.history, effective_config.core_ticker)
        growth_indicators = compute_ticker_indicators(growth_history.history, effective_config.growth_ticker)
        secondary_indicators = (
            compute_ticker_indicators(secondary_history.history, effective_config.secondary_ticker)
            if secondary_history is not None and effective_config.secondary_ticker
            else None
        )

        decision = evaluate_strategy(
            config=effective_config,
            core_indicators=core_indicators,
            growth_indicators=growth_indicators,
            reserve_state=reserve_state,
            secondary_indicators=secondary_indicators,
        )

        execution_guidance = None
        if effective_config.execution_guidance_enabled:
            execution_guidance = build_execution_guidance(
                user_timezone=effective_config.user_timezone,
                preferred_order_type=effective_config.preferred_order_type,
                preferred_tif=effective_config.preferred_tif,
                suggest_outside_rth=effective_config.suggest_outside_rth,
                now_utc=fetched_at_utc,
            )

        extra_rmb: dict[str, int] = {}
        if effective_config.secondary_ticker:
            extra_rmb[effective_config.secondary_ticker] = decision.allocation.secondary_rmb
        fx_summary = build_fx_conversion_summary(
            total_rmb=decision.recommendation_total_rmb,
            core_rmb=decision.allocation.core_rmb,
            growth_rmb=decision.allocation.growth_rmb,
            reference_date=report_date,
            fetched_at_utc=fetched_at_utc,
            extra_rmb=extra_rmb,
        )

        historical_review = build_historical_signal_review(
            config=effective_config,
            core_history=core_history.history,
            secondary_history=secondary_history.history if secondary_history is not None else None,
            growth_history=growth_history.history,
            months=review_months,
        )
        gold_decision = evaluate_gold_sleeve(
            effective_config.gold_sleeve,
            reference_date=report_date,
            current_total_portfolio_value_rmb=current_total_portfolio_value_rmb,
            current_gldm_shares=current_gldm_shares,
            fx_rate_cny_per_usd=fx_summary.rate_cny_per_usd,
        )

        report_path = report_path_for(reports_dir, report_date)
        report_markdown = render_report(
            config=effective_config,
            core=core_indicators,
            secondary=secondary_indicators,
            growth=growth_indicators,
            decision=decision,
            reserve_cash_rmb=decision.reserve_cash_after_rmb,
            report_date=report_date,
            data_source=bundle.data_source,
            fetched_at_utc=bundle.fetched_at_utc,
            latest_market_date_core=core_history.latest_market_date,
            latest_market_date_secondary=secondary_history.latest_market_date if secondary_history is not None else None,
            latest_market_date_qqqm=growth_history.latest_market_date,
            validation_status=bundle.validation_status,
            run_mode_label=run_mode_label,
            historical_review=historical_review,
            execution_guidance=execution_guidance,
            fx_summary=fx_summary,
            gold_decision=gold_decision,
        )
        report_path.write_text(report_markdown, encoding="utf-8")

        if not simulation_mode:
            reserve_state.reserve_cash_rmb = decision.reserve_cash_after_rmb
            reserve_state.last_run_at = utc_now_iso()
            reserve_state.last_status = decision.state_label
            reserve_state.last_recommendation_total_rmb = decision.recommendation_total_rmb
            dump_state(reserve_state, state_file)

        summary_text = build_summary_text(
            config=effective_config,
            growth=growth_indicators,
            decision=decision,
            report_path=report_path,
            report_date=report_date.isoformat(),
            data_source=bundle.data_source,
            latest_market_date_core=core_history.latest_market_date,
            latest_market_date_secondary=secondary_history.latest_market_date if secondary_history is not None else None,
            latest_market_date_qqqm=growth_history.latest_market_date,
            validation_status=bundle.validation_status,
            run_mode_label=run_mode_label,
            execution_guidance=execution_guidance,
            fx_summary=fx_summary,
            gold_decision=gold_decision,
        )

        feishu_sent = False
        if not dry_run:
            try:
                feishu_sent = maybe_send_feishu(
                    enabled=config.feishu_enabled,
                    webhook_url=webhook_url,
                    summary_text=summary_text,
                )
            except FeishuError as exc:
                print(f"[错误] 飞书通知失败：{exc}")
                return 4

        print(f"策略：{effective_config.strategy_name}")
        print(f"运行模式：{mode_label(run_mode_label)}")
        print(f"状态：{state_label(decision.state_label)}")
        print(f"校验状态：{validation_label(bundle.validation_status)}")
        print(f"数据来源：{bundle.data_source}")
        print(f"总投入建议：{decision.recommendation_total_rmb} RMB")
        if decision.strategy_mode == "manual_total_per_asset_signal":
            print("当前总投入由手动设定，以下建议仅调整资产间分配，不改变总投入。")
            for signal in decision.asset_signals:
                base_rmb = next(
                    (
                        base
                        for ticker, base in [
                            (effective_config.core_ticker, decision.baseline_allocation.core_rmb),
                            (effective_config.secondary_ticker, decision.baseline_allocation.secondary_rmb),
                            (effective_config.growth_ticker, decision.baseline_allocation.growth_rmb),
                        ]
                        if ticker == signal.ticker
                    ),
                    0,
                )
                print(
                    f"{signal.ticker}：原始信号{raw_signal_judgment_label(signal.classification)}，"
                    f"原始建议{raw_signal_direction_label(signal.classification)}；"
                    f"归一化后{final_recommendation_label(signal.normalized_adjustment_pct, signal.delta_rmb)}，"
                    f"最终调整 {signal.normalized_adjustment_pct:+.2f}%（{signal.delta_rmb:+d} RMB），"
                    f"基线 {base_rmb} RMB，最终 {signal.final_rmb} RMB"
                )
        else:
            print(f"{effective_config.core_ticker}：{decision.allocation.core_rmb} RMB")
            if effective_config.secondary_ticker:
                print(f"{effective_config.secondary_ticker}：{decision.allocation.secondary_rmb} RMB")
            print(f"{effective_config.growth_ticker}：{decision.allocation.growth_rmb} RMB")
        print(f"储备金余额：{decision.reserve_cash_after_rmb} RMB")
        print(f"黄金保险仓：{gold_decision.action_label}")
        if gold_decision.missing_inputs:
            print(f"黄金输入状态：部分缺失（{' / '.join(gold_decision.missing_inputs)}）")
        else:
            print("黄金输入状态：完整")
        if gold_decision.current_gold_weight is not None:
            print(
                f"{gold_decision.ticker}：总资产 {gold_decision.current_total_portfolio_value_rmb} RMB / "
                f"持仓 {gold_decision.current_gldm_shares or 0:.4f} 股 / "
                f"价格 USD {gold_decision.current_gldm_price_usd:.2f} / "
                f"黄金市值 {gold_decision.current_gold_value_rmb} RMB / "
                f"当前 {gold_decision.current_gold_weight * 100:.2f}% / "
                f"目标 {gold_decision.target_gold_weight * 100:.2f}% / "
                f"上限 {gold_decision.max_gold_weight * 100:.2f}% / "
                f"建议买入 {(gold_decision.recommended_buy_rmb or 0)} RMB"
            )
        if gold_decision.remaining_gap_after_buy_rmb is not None:
            if gold_decision.projected_gold_weight_after_buy is not None:
                remaining_pct = max(
                    gold_decision.target_gold_weight * 100 - gold_decision.projected_gold_weight_after_buy * 100,
                    0,
                )
                print(f"买入后距目标仍差：{gold_decision.remaining_gap_after_buy_rmb} RMB / {remaining_pct:.2f}%")
            else:
                print(f"买入后距目标仍差：{gold_decision.remaining_gap_after_buy_rmb} RMB")
        if gold_decision.recommended_buy_shares is not None and (gold_decision.recommended_buy_rmb or 0) > 0:
            print(f"约对应 GLDM {gold_decision.recommended_buy_shares:.4f} 股")
        print(f"黄金说明：{gold_decision.reason}")
        print(f"汇率校验状态：{validation_label(fx_summary.validation_status)}")
        print(
            "IBKR 当前交易阶段："
            f"{session_label(execution_guidance.session_phase) if execution_guidance is not None else '未启用'}"
        )
        print(f"报告已写入：{report_path}")
        print(f"状态文件已写入：{state_file if not simulation_mode else '模拟模式下已跳过'}")
        print(f"飞书已发送：{yes_no(feishu_sent)}")
        return 0
    except (DataFetchError, IndicatorComputationError) as exc:
        failure_text = str(exc)
        try:
            failure_sent = _maybe_send_failure_alert(
                webhook_url=webhook_url,
                dry_run=dry_run,
                error=failure_text,
                fetched_at_utc=fetched_at_utc,
                core_ticker=effective_config.core_ticker,
                secondary_ticker=effective_config.secondary_ticker,
                growth_ticker=effective_config.growth_ticker,
            )
        except FeishuError as notify_exc:
            print(f"[错误] 失败告警发送失败：{notify_exc}")
            print(f"[错误] {failure_text}")
            return 4
        except Exception as notify_exc:
            print(f"[警告] 失败告警发送失败：{notify_exc}")
            failure_sent = False
        print(f"[错误] {failure_text}")
        print(f"失败告警已发送：{yes_no(failure_sent)}")
        return 3
    except Exception as exc:
        print(f"[错误] 未预期失败：{exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return _run(
            config_path=args.config,
            state_file=args.state_file,
            reports_dir=args.reports_dir,
            webhook_url=args.feishu_webhook_url,
            dry_run=args.dry_run,
            base_monthly_rmb=args.base_monthly_rmb,
            review_months=args.review_months,
            current_total_portfolio_value_rmb=args.current_total_portfolio_value_rmb,
            current_gldm_shares=args.current_gldm_shares,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
