from __future__ import annotations

import argparse
import os
from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import apply_base_override, load_strategy_config
from .data_fetcher import DATA_SOURCE, DataFetchError, fetch_histories
from .feishu_sender import FeishuError, build_failure_alert_text, build_summary_text, maybe_send_feishu
from .execution_guidance import build_execution_guidance
from .fx_converter import build_fx_conversion_summary
from .historical_review import build_historical_signal_review
from .indicators import IndicatorComputationError, compute_ticker_indicators
from .presentation import mode_label, session_label, state_label, validation_label, yes_no
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
    run_parser.add_argument("--dry-run", action="store_true", help="Do not send Feishu notifications.")

    return parser


def _maybe_send_failure_alert(
    *,
    webhook_url: str | None,
    dry_run: bool,
    error: str,
    fetched_at_utc: datetime,
    core_ticker: str,
    growth_ticker: str,
) -> bool:
    if dry_run:
        return False
    if not webhook_url:
        raise FeishuError("FEISHU_WEBHOOK_URL is missing or blank")

    text = build_failure_alert_text(
        error=error,
        data_source=DATA_SOURCE,
        fetched_at_utc=fetched_at_utc,
        core_ticker=core_ticker,
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
) -> int:
    config = load_strategy_config(config_path)
    if base_monthly_rmb is not None and base_monthly_rmb <= 0:
        raise ValueError("base_monthly_rmb must be positive")
    effective_config = apply_base_override(config, base_monthly_rmb)
    if review_months < 1:
        raise ValueError("review_months must be at least 1")
    simulation_mode = base_monthly_rmb is not None and base_monthly_rmb != config.base_monthly_rmb
    run_mode_label = (
        f"模拟模式：基线月投金额 = {effective_config.base_monthly_rmb}"
        if simulation_mode
        else None
    )
    reserve_state = load_state(state_file)
    report_date = datetime.now(ZoneInfo(config.report_timezone)).date()
    fetched_at_utc = datetime.now(timezone.utc)

    try:
        tickers = [effective_config.core_ticker, effective_config.growth_ticker]
        if effective_config.secondary_ticker:
            tickers.insert(1, effective_config.secondary_ticker)
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
        )
        reserve_after_rmb = decision.reserve_cash_after_rmb
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

        report_path = report_path_for(reports_dir, report_date)
        historical_review = build_historical_signal_review(
            config=effective_config,
            core_history=core_history.history,
            growth_history=growth_history.history,
            months=review_months,
        )
        report_markdown = render_report(
            config=effective_config,
            core=core_indicators,
            secondary=secondary_indicators,
            growth=growth_indicators,
            decision=decision,
            reserve_cash_rmb=reserve_after_rmb,
            report_date=report_date,
            data_source=bundle.data_source,
            fetched_at_utc=bundle.fetched_at_utc,
            latest_market_date_core=core_history.latest_market_date,
            latest_market_date_qqqm=growth_history.latest_market_date,
            validation_status=bundle.validation_status,
            run_mode_label=run_mode_label,
            historical_review=historical_review,
            execution_guidance=execution_guidance,
            fx_summary=fx_summary,
        )
        report_path.write_text(report_markdown, encoding="utf-8")

        if not simulation_mode:
            reserve_state.reserve_cash_rmb = reserve_after_rmb
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
            latest_market_date_qqqm=growth_history.latest_market_date,
            validation_status=bundle.validation_status,
            run_mode_label=run_mode_label,
            execution_guidance=execution_guidance,
            fx_summary=fx_summary,
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
        print(f"{effective_config.core_ticker}：{decision.allocation.core_rmb} RMB")
        if effective_config.secondary_ticker:
            print(f"{effective_config.secondary_ticker}：{decision.allocation.secondary_rmb} RMB")
        print(f"{effective_config.growth_ticker}：{decision.allocation.growth_rmb} RMB")
        print(f"储备金余额：{reserve_after_rmb} RMB")
        print(f"汇率校验状态：{validation_label(fx_summary.validation_status)}")
        print(
            "IBKR 当前交易阶段："
            f"{session_label(execution_guidance.session_phase) if execution_guidance is not None else '已关闭'}"
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
                core_ticker=config.core_ticker,
                growth_ticker=config.growth_ticker,
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
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
