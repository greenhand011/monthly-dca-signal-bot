from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from .config import StrategyConfig
from .indicators import TickerIndicators
from .strategy_engine import StrategyDecision


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def render_report(
    *,
    config: StrategyConfig,
    core: TickerIndicators,
    growth: TickerIndicators,
    decision: StrategyDecision,
    reserve_cash_rmb: int,
    report_date: date,
    data_source: str,
    fetched_at_utc: datetime,
    latest_market_date_spym: date,
    latest_market_date_qqqm: date,
    validation_status: str,
) -> str:
    reasons = "\n".join(f"- {reason}" for reason in decision.reasons)
    return (
        f"# {config.strategy_name} \u6708\u5ea6\u5b9a\u6295\u62a5\u544a\n\n"
        f"**\u65e5\u671f**\uff1a{report_date.isoformat()}  \n"
        f"**\u5f53\u524d\u5e02\u573a\u72b6\u6001**\uff1a`{decision.state_label}`\n\n"
        "## \u6570\u636e\u4fe1\u606f\n\n"
        f"- Data source: {data_source}\n"
        f"- Data fetched at (UTC): {_utc_iso(fetched_at_utc)}\n"
        f"- Latest market date for {config.core_ticker}: {latest_market_date_spym.isoformat()}\n"
        f"- Latest market date for {config.growth_ticker}: {latest_market_date_qqqm.isoformat()}\n"
        f"- Validation status: {validation_status}\n\n"
        "## \u5e02\u573a\u6570\u636e\n\n"
        f"- {config.core_ticker} \u5f53\u524d\u4ef7\u683c\uff1a`{core.current_price:.2f}`\n"
        f"- {config.growth_ticker} \u5f53\u524d\u4ef7\u683c\uff1a`{growth.current_price:.2f}`\n"
        f"- {config.growth_ticker} 52 \u5468\u9ad8\u70b9\u56de\u64a4\uff1a`{growth.drawdown_52w * 100:.2f}%`\n"
        f"- {config.growth_ticker} \u76f8\u5bf9 200 \u65e5\u5747\u7ebf\u504f\u79bb\uff1a`{growth.deviation_from_sma200 * 100:.2f}%`\n"
        f"- {config.growth_ticker} RSI(14)\uff1a`{growth.rsi14:.2f}`\n"
        f"- {config.core_ticker} 3 \u5e74\u4ef7\u683c\u5206\u4f4d\uff1a`{core.price_percentile_3y:.2f}%`\n"
        f"- {config.growth_ticker} 3 \u5e74\u4ef7\u683c\u5206\u4f4d\uff1a`{growth.price_percentile_3y:.2f}%`\n"
        f"- \u5f53\u524d\u50a8\u5907\u91d1\u4f59\u989d\uff1a`{reserve_cash_rmb} RMB`\n\n"
        "## \u672c\u6708\u5efa\u8bae\n\n"
        f"- \u672c\u6708\u5efa\u8bae\u603b\u6295\u5165\u91d1\u989d\uff1a`{decision.recommendation_total_rmb} RMB`\n"
        f"- {config.core_ticker} \u5efa\u8bae\u6295\u5165\u91d1\u989d\uff1a`{decision.allocation.core_rmb} RMB`\n"
        f"- {config.growth_ticker} \u5efa\u8bae\u6295\u5165\u91d1\u989d\uff1a`{decision.allocation.growth_rmb} RMB`\n"
        f"- \u672c\u6708\u5efa\u8bae\u52a8\u4f5c\uff1a`{decision.action_label}`\n\n"
        "### \u539f\u56e0\u8bf4\u660e\n\n"
        f"{reasons}\n\n"
        "### \u98ce\u9669\u63d0\u793a\n\n"
        "- \u672c\u62a5\u544a\u4ec5\u63d0\u4f9b\u89c4\u5219\u5316\u8f85\u52a9\u51b3\u7b56\uff0c\u4e0d\u6784\u6210\u6295\u8d44\u5efa\u8bae\u3002\n"
        "- \u5386\u53f2\u6307\u6807\u4e0d\u80fd\u4fdd\u8bc1\u672a\u6765\u6536\u76ca\uff0cETF \u4ef7\u683c\u3001\u6c47\u7387\u4e0e\u6570\u636e\u6e90\u90fd\u53ef\u80fd\u6ce2\u52a8\u6216\u4fee\u6b63\u3002\n"
        "- \u50a8\u5907\u91d1\u673a\u5236\u53ef\u4ee5\u5e73\u6ed1\u8282\u594f\uff0c\u4f46\u4e0d\u4f1a\u6d88\u9664\u5e02\u573a\u98ce\u9669\u3002\n\n"
        "### \u4e0b\u6b21\u67e5\u770b\u5efa\u8bae\n\n"
        "\u5efa\u8bae\u5728\u4e0b\u4e2a\u6708\u9996\u4e2a\u4ea4\u6613\u65e5\u6216\u4e0b\u4e00\u6b21\u6708\u5ea6\u8fd0\u884c\u65f6\u518d\u6b21\u67e5\u770b\uff1b\u5982\u679c QQQM \u7684\u4ef7\u683c\u7ed3\u6784\u53d1\u751f\u660e\u663e\u53d8\u5316\uff0c\u4e5f\u53ef\u4ee5\u63d0\u524d\u590d\u6838\u3002\n"
    )


def report_path_for(report_dir: str | Path, report_date: date) -> Path:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / f"{report_date:%Y-%m}-report.md"
