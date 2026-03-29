from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import load_strategy_config
from .data_fetcher import DATA_SOURCE, DataFetchError, fetch_histories
from .feishu_sender import FeishuError, build_failure_alert_text, build_summary_text, maybe_send_feishu
from .indicators import IndicatorComputationError, compute_ticker_indicators
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
    run_parser.add_argument("--dry-run", action="store_true", help="Do not send Feishu notifications.")

    return parser


def _maybe_send_failure_alert(
    *,
    webhook_url: str | None,
    dry_run: bool,
    error: str,
    fetched_at_utc: datetime,
) -> bool:
    if dry_run:
        return False
    if not webhook_url:
        raise FeishuError("FEISHU_WEBHOOK_URL is missing or blank")

    text = build_failure_alert_text(
        error=error,
        data_source=DATA_SOURCE,
        fetched_at_utc=fetched_at_utc,
        validation_status="FAIL",
    )
    from .feishu_sender import send_feishu_text

    send_feishu_text(webhook_url, text)
    return True


def _run(config_path: str, state_file: str, reports_dir: str, webhook_url: str | None, dry_run: bool) -> int:
    config = load_strategy_config(config_path)
    reserve_state = load_state(state_file)
    report_date = datetime.now(ZoneInfo(config.report_timezone)).date()
    fetched_at_utc = datetime.now(timezone.utc)

    try:
        bundle = fetch_histories(
            [config.core_ticker, config.growth_ticker],
            reference_date=report_date,
            fetched_at_utc=fetched_at_utc,
        )

        core_history = bundle.histories[config.core_ticker]
        growth_history = bundle.histories[config.growth_ticker]

        core_indicators = compute_ticker_indicators(core_history.history, config.core_ticker)
        growth_indicators = compute_ticker_indicators(growth_history.history, config.growth_ticker)

        decision = evaluate_strategy(
            config=config,
            core_indicators=core_indicators,
            growth_indicators=growth_indicators,
            reserve_state=reserve_state,
        )

        reserve_state.reserve_cash_rmb = decision.reserve_cash_after_rmb
        reserve_state.last_run_at = utc_now_iso()
        reserve_state.last_status = decision.state_label
        reserve_state.last_recommendation_total_rmb = decision.recommendation_total_rmb

        report_path = report_path_for(reports_dir, report_date)
        report_markdown = render_report(
            config=config,
            core=core_indicators,
            growth=growth_indicators,
            decision=decision,
            reserve_cash_rmb=reserve_state.reserve_cash_rmb,
            report_date=report_date,
            data_source=bundle.data_source,
            fetched_at_utc=bundle.fetched_at_utc,
            latest_market_date_spym=core_history.latest_market_date,
            latest_market_date_qqqm=growth_history.latest_market_date,
            validation_status=bundle.validation_status,
        )
        report_path.write_text(report_markdown, encoding="utf-8")
        dump_state(reserve_state, state_file)

        summary_text = build_summary_text(
            config=config,
            growth=growth_indicators,
            decision=decision,
            report_path=report_path,
            report_date=report_date.isoformat(),
            data_source=bundle.data_source,
            latest_market_date_spym=core_history.latest_market_date,
            latest_market_date_qqqm=growth_history.latest_market_date,
            validation_status=bundle.validation_status,
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
                print(f"[error] Feishu notification failed: {exc}")
                return 4

        print(f"Strategy: {config.strategy_name}")
        print(f"Status: {decision.state_label}")
        print(f"Validation status: {bundle.validation_status}")
        print(f"Data source: {bundle.data_source}")
        print(f"Total recommendation: {decision.recommendation_total_rmb} RMB")
        print(f"{config.core_ticker}: {decision.allocation.core_rmb} RMB")
        print(f"{config.growth_ticker}: {decision.allocation.growth_rmb} RMB")
        print(f"Reserve after run: {reserve_state.reserve_cash_rmb} RMB")
        print(f"Report written to: {report_path}")
        print(f"State written to: {state_file}")
        print(f"Feishu sent: {'yes' if feishu_sent else 'no'}")
        return 0
    except (DataFetchError, IndicatorComputationError) as exc:
        failure_text = str(exc)
        try:
            failure_sent = _maybe_send_failure_alert(
                webhook_url=webhook_url,
                dry_run=dry_run,
                error=failure_text,
                fetched_at_utc=fetched_at_utc,
            )
        except FeishuError as notify_exc:
            print(f"[error] Failure alert could not be sent: {notify_exc}")
            print(f"[error] {failure_text}")
            return 4
        except Exception as notify_exc:
            print(f"[warn] Failure alert could not be sent: {notify_exc}")
            failure_sent = False
        print(f"[error] {failure_text}")
        print(f"Failure alert sent: {'yes' if failure_sent else 'no'}")
        return 3
    except Exception as exc:
        print(f"[error] Unexpected failure: {exc}")
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
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
