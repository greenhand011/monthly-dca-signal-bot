from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime

import pandas as pd

from .config import GoldSleeveConfig
from .data_fetcher import DATA_SOURCE, DataFetchError, fetch_price_history, validate_price_history
from .indicators import compute_rsi


GOLD_VALIDATION_STATUS_PASS = "PASS"
GOLD_VALIDATION_STATUS_WARN = "WARN"
GOLD_VALIDATION_STATUS_FAIL = "FAIL"


@dataclass(frozen=True)
class GoldSleeveIndicatorSnapshot:
    ticker: str
    latest_market_date: date
    current_price: float
    sma200: float
    rsi14: float
    high_60d: float
    high_120d: float
    distance_from_60d_high: float
    drawdown_from_120d_high: float
    return_20d: float


@dataclass(frozen=True)
class GoldSleeveDecision:
    enabled: bool
    ticker: str
    decision_status: str
    action_label: str
    should_buy: bool
    data_source: str
    validation_status: str
    latest_market_date: date | None
    current_gold_weight: float | None
    target_gold_weight: float
    max_gold_weight: float
    below_target: bool | None
    overheat_triggered: bool | None
    total_score: float | None
    technical_score: float | None
    macro_score: float | None
    optional_score: float | None
    target_gold_value_rmb: int | None
    target_gap_value_rmb: int | None
    recommended_buy_rmb: int | None
    projected_gold_weight_after_buy: float | None
    remaining_gap_after_buy_rmb: int | None
    reason: str
    notes: list[str]
    overheat_reasons: list[str]
    score_details: list[str]
    optional_data_notes: list[str]
    indicator_snapshot: GoldSleeveIndicatorSnapshot | None = None


def _round_rmb(value: float) -> int:
    return int(round(value))


def _safe_optional_ticker(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _fetch_required_history(
    ticker: str,
    *,
    reference_date: date,
    min_rows: int,
) -> pd.DataFrame:
    history = fetch_price_history(ticker=ticker, period="2y", interval="1d")
    validated = validate_price_history(
        history,
        ticker=ticker,
        reference_date=reference_date,
        min_rows=min_rows,
    )
    return validated.history


def _fetch_optional_history(
    ticker: str | None,
    *,
    reference_date: date,
    min_rows: int,
) -> tuple[pd.DataFrame | None, str | None]:
    ticker = _safe_optional_ticker(ticker)
    if ticker is None:
        return None, None
    try:
        history = fetch_price_history(ticker=ticker, period="2y", interval="1d")
        validated = validate_price_history(
            history,
            ticker=ticker,
            reference_date=reference_date,
            min_rows=min_rows,
        )
        return validated.history, None
    except (DataFetchError, ValueError) as exc:
        return None, f"{ticker} 不可用：{exc}"


def _close_series(history: pd.DataFrame, ticker: str, *, min_rows: int = 1) -> pd.Series:
    if "close" not in history.columns:
        raise ValueError(f"{ticker}: history must contain close column")
    close = history["close"].astype(float).dropna()
    if len(close) < min_rows:
        raise ValueError(f"{ticker}: not enough rows to compute required indicators")
    return close


def _build_gold_indicator_snapshot(ticker: str, history: pd.DataFrame) -> GoldSleeveIndicatorSnapshot:
    close = _close_series(history, ticker, min_rows=200)
    current_price = float(close.iloc[-1])
    sma200 = float(close.rolling(window=200, min_periods=200).mean().iloc[-1])
    rsi14 = float(compute_rsi(close, period=14).iloc[-1])
    high_60d = float(close.tail(60).max())
    high_120d = float(close.tail(120).max())
    return_20d = (current_price / float(close.iloc[-21])) - 1 if len(close) >= 21 else 0.0
    distance_from_60d_high = max(0.0, 1 - (current_price / high_60d)) if high_60d > 0 else 0.0
    drawdown_from_120d_high = max(0.0, 1 - (current_price / high_120d)) if high_120d > 0 else 0.0
    return GoldSleeveIndicatorSnapshot(
        ticker=ticker,
        latest_market_date=pd.to_datetime(close.index[-1]).date(),
        current_price=current_price,
        sma200=sma200,
        rsi14=rsi14,
        high_60d=high_60d,
        high_120d=high_120d,
        distance_from_60d_high=distance_from_60d_high,
        drawdown_from_120d_high=drawdown_from_120d_high,
        return_20d=return_20d,
    )


def _latest_close(history: pd.DataFrame, ticker: str) -> float:
    return float(_close_series(history, ticker, min_rows=1).iloc[-1])


def _rolling_mean(history: pd.DataFrame, ticker: str, window: int) -> float:
    close = _close_series(history, ticker, min_rows=window)
    return float(close.rolling(window=window, min_periods=window).mean().iloc[-1])


def _return_over_days(history: pd.DataFrame, ticker: str, days: int) -> float:
    close = _close_series(history, ticker, min_rows=days + 1)
    if len(close) < days + 1:
        raise ValueError(f"{ticker}: not enough rows to compute {days}d return")
    return (float(close.iloc[-1]) / float(close.iloc[-(days + 1)])) - 1


def _drawdown_from_recent_high(history: pd.DataFrame, ticker: str, days: int) -> float:
    close = _close_series(history, ticker, min_rows=days)
    recent = close.tail(days)
    high = float(recent.max())
    latest = float(recent.iloc[-1])
    return max(0.0, 1 - (latest / high)) if high > 0 else 0.0


def _buy_action_label(score: float, recommended_buy_rmb: int) -> str:
    if recommended_buy_rmb <= 0:
        return "本月不买"
    if score >= 7:
        return "可考虑补足目标仓位"
    if score >= 5:
        return "可考虑中等买入"
    return "可考虑小幅买入"


def _build_disabled_decision(config: GoldSleeveConfig, reason: str) -> GoldSleeveDecision:
    return GoldSleeveDecision(
        enabled=config.enabled,
        ticker=config.ticker,
        decision_status="DISABLED",
        action_label="未启用",
        should_buy=False,
        data_source=DATA_SOURCE,
        validation_status=GOLD_VALIDATION_STATUS_WARN,
        latest_market_date=None,
        current_gold_weight=None,
        target_gold_weight=config.target_weight,
        max_gold_weight=config.max_weight,
        below_target=None,
        overheat_triggered=None,
        total_score=None,
        technical_score=None,
        macro_score=None,
        optional_score=None,
        target_gold_value_rmb=None,
        target_gap_value_rmb=None,
        recommended_buy_rmb=None,
        projected_gold_weight_after_buy=None,
        remaining_gap_after_buy_rmb=None,
        reason=reason,
        notes=["黄金模块为保险仓择时补仓，不参与主仓月频定投。"],
        overheat_reasons=[],
        score_details=[],
        optional_data_notes=[],
    )


def _build_unavailable_decision(config: GoldSleeveConfig, reason: str) -> GoldSleeveDecision:
    return replace(
        _build_disabled_decision(config, reason),
        decision_status="UNAVAILABLE",
        action_label="本月无法评估",
        validation_status=GOLD_VALIDATION_STATUS_FAIL,
    )


def evaluate_gold_sleeve(
    config: GoldSleeveConfig,
    *,
    reference_date: date,
) -> GoldSleeveDecision:
    if not config.enabled:
        return _build_disabled_decision(config, "黄金保险仓模块未启用。")
    if not config.monthly_check_enabled:
        return _build_disabled_decision(config, "黄金保险仓本月检查已关闭。")
    if config.current_total_portfolio_value_rmb <= 0:
        return _build_unavailable_decision(config, "current_total_portfolio_value_rmb 未配置或小于等于 0，无法判断黄金目标仓位。")

    try:
        gold_history = _fetch_required_history(config.ticker, reference_date=reference_date, min_rows=240)
        gold = _build_gold_indicator_snapshot(config.ticker, gold_history)
    except (DataFetchError, ValueError) as exc:
        return _build_unavailable_decision(config, f"{config.ticker} 评估失败：{exc}")

    current_gold_weight = config.current_gold_value_rmb / config.current_total_portfolio_value_rmb
    target_gold_value = _round_rmb(config.current_total_portfolio_value_rmb * config.target_weight)
    max_gold_value = _round_rmb(config.current_total_portfolio_value_rmb * config.max_weight)
    target_gap_value = max(target_gold_value - config.current_gold_value_rmb, 0)
    max_gap_value = max(max_gold_value - config.current_gold_value_rmb, 0)
    base_notes = ["黄金模块为保险仓择时补仓，不参与主仓月频定投。"]

    if not config.emergency_fund_ok:
        return GoldSleeveDecision(
            enabled=True,
            ticker=config.ticker,
            decision_status="NO_BUY",
            action_label="本月不买",
            should_buy=False,
            data_source=DATA_SOURCE,
            validation_status=GOLD_VALIDATION_STATUS_PASS,
            latest_market_date=gold.latest_market_date,
            current_gold_weight=current_gold_weight,
            target_gold_weight=config.target_weight,
            max_gold_weight=config.max_weight,
            below_target=current_gold_weight < config.target_weight,
            overheat_triggered=False,
            total_score=0.0,
            technical_score=0.0,
            macro_score=0.0,
            optional_score=0.0,
            target_gold_value_rmb=target_gold_value,
            target_gap_value_rmb=target_gap_value,
            recommended_buy_rmb=0,
            projected_gold_weight_after_buy=current_gold_weight,
            remaining_gap_after_buy_rmb=target_gap_value,
            reason="现金安全假设未满足，本月不建议动用资金补黄金保险仓。",
            notes=base_notes,
            overheat_reasons=[],
            score_details=[],
            optional_data_notes=[],
            indicator_snapshot=gold,
        )

    if current_gold_weight >= config.target_weight or target_gap_value <= 0:
        return GoldSleeveDecision(
            enabled=True,
            ticker=config.ticker,
            decision_status="NO_BUY",
            action_label="本月不买",
            should_buy=False,
            data_source=DATA_SOURCE,
            validation_status=GOLD_VALIDATION_STATUS_PASS,
            latest_market_date=gold.latest_market_date,
            current_gold_weight=current_gold_weight,
            target_gold_weight=config.target_weight,
            max_gold_weight=config.max_weight,
            below_target=False,
            overheat_triggered=False,
            total_score=0.0,
            technical_score=0.0,
            macro_score=0.0,
            optional_score=0.0,
            target_gold_value_rmb=target_gold_value,
            target_gap_value_rmb=target_gap_value,
            recommended_buy_rmb=0,
            projected_gold_weight_after_buy=current_gold_weight,
            remaining_gap_after_buy_rmb=0,
            reason="当前黄金仓位已达到或超过目标配置，本月不需要补仓。",
            notes=base_notes,
            overheat_reasons=[],
            score_details=[],
            optional_data_notes=[],
            indicator_snapshot=gold,
        )

    if current_gold_weight >= config.max_weight:
        return GoldSleeveDecision(
            enabled=True,
            ticker=config.ticker,
            decision_status="NO_BUY",
            action_label="本月不买",
            should_buy=False,
            data_source=DATA_SOURCE,
            validation_status=GOLD_VALIDATION_STATUS_PASS,
            latest_market_date=gold.latest_market_date,
            current_gold_weight=current_gold_weight,
            target_gold_weight=config.target_weight,
            max_gold_weight=config.max_weight,
            below_target=False,
            overheat_triggered=False,
            total_score=0.0,
            technical_score=0.0,
            macro_score=0.0,
            optional_score=0.0,
            target_gold_value_rmb=target_gold_value,
            target_gap_value_rmb=target_gap_value,
            recommended_buy_rmb=0,
            projected_gold_weight_after_buy=current_gold_weight,
            remaining_gap_after_buy_rmb=target_gap_value,
            reason="当前黄金仓位已达到上限仓位，本月不建议继续买入。",
            notes=base_notes,
            overheat_reasons=[],
            score_details=[],
            optional_data_notes=[],
            indicator_snapshot=gold,
        )

    overheat_reasons: list[str] = []
    if gold.rsi14 > config.overheat_rsi_max:
        overheat_reasons.append(f"RSI(14) {gold.rsi14:.2f} 高于阈值 {config.overheat_rsi_max:.2f}")
    if gold.current_price / gold.sma200 > config.overheat_ma200_ratio_max:
        overheat_reasons.append(
            f"价格 / 200DMA = {gold.current_price / gold.sma200:.3f}，高于阈值 {config.overheat_ma200_ratio_max:.3f}"
        )
    if (
        gold.distance_from_60d_high <= config.overheat_60d_high_distance_max
        and gold.return_20d > config.overheat_20d_return_max
    ):
        overheat_reasons.append(
            f"距 60 日高点仅 {gold.distance_from_60d_high * 100:.2f}% 且 20 日涨幅 {gold.return_20d * 100:.2f}% 过快"
        )

    if overheat_reasons:
        return GoldSleeveDecision(
            enabled=True,
            ticker=config.ticker,
            decision_status="NO_BUY",
            action_label="本月不买",
            should_buy=False,
            data_source=DATA_SOURCE,
            validation_status=GOLD_VALIDATION_STATUS_PASS,
            latest_market_date=gold.latest_market_date,
            current_gold_weight=current_gold_weight,
            target_gold_weight=config.target_weight,
            max_gold_weight=config.max_weight,
            below_target=True,
            overheat_triggered=True,
            total_score=0.0,
            technical_score=0.0,
            macro_score=0.0,
            optional_score=0.0,
            target_gold_value_rmb=target_gold_value,
            target_gap_value_rmb=target_gap_value,
            recommended_buy_rmb=0,
            projected_gold_weight_after_buy=current_gold_weight,
            remaining_gap_after_buy_rmb=target_gap_value,
            reason="当前黄金仓位虽然低于目标，但已触发过热过滤，本月暂不买入。",
            notes=base_notes,
            overheat_reasons=overheat_reasons,
            score_details=[],
            optional_data_notes=[],
            indicator_snapshot=gold,
        )

    technical_score = 0.0
    macro_score = 0.0
    optional_score = 0.0
    score_details: list[str] = []
    optional_data_notes: list[str] = []

    if 0.08 <= gold.drawdown_from_120d_high <= 0.15:
        technical_score += 2.0
        score_details.append(f"技术项 +2：距 120 日高点回撤 {gold.drawdown_from_120d_high * 100:.2f}% 落在 8%-15% 区间。")
    if gold.sma200 * 0.97 <= gold.current_price <= gold.sma200 * 1.08:
        technical_score += 1.0
        score_details.append("技术项 +1：价格位于 200 日均线附近。")
    if 40 <= gold.rsi14 <= 60:
        technical_score += 1.0
        score_details.append(f"技术项 +1：RSI(14) = {gold.rsi14:.2f} 落在 40-60 区间。")

    dxy_history, dxy_error = _fetch_optional_history(config.dxy_ticker, reference_date=reference_date, min_rows=60)
    if dxy_history is not None and config.dxy_ticker:
        dxy_latest = _latest_close(dxy_history, config.dxy_ticker)
        dxy_50d = _rolling_mean(dxy_history, config.dxy_ticker, 50)
        dxy_return_20d = _return_over_days(dxy_history, config.dxy_ticker, 20)
        if dxy_latest < dxy_50d or dxy_return_20d < 0:
            macro_score += 1.0
            score_details.append(
                f"宏观项 +1：DXY 偏弱（最新 {dxy_latest:.2f} / 50 日均线 {dxy_50d:.2f} / 20 日收益 {dxy_return_20d * 100:.2f}%）。"
            )
    elif dxy_error:
        optional_data_notes.append(f"DXY 未纳入：{dxy_error}")

    real_yield_history, real_yield_error = _fetch_optional_history(
        config.real_yield_ticker,
        reference_date=reference_date,
        min_rows=30,
    )
    if real_yield_history is not None and config.real_yield_ticker:
        real_yield_close = _close_series(real_yield_history, config.real_yield_ticker)
        if float(real_yield_close.iloc[-1]) < float(real_yield_close.iloc[-21]):
            macro_score += 1.0
            score_details.append(
                f"宏观项 +1：{config.real_yield_ticker} 近 20 日趋势向下。"
            )
    elif real_yield_error:
        optional_data_notes.append(f"10Y 实际利率代理未纳入：{real_yield_error}")
    else:
        optional_data_notes.append("10Y 实际利率代理本月未配置，未纳入评分。")

    vix_history, vix_error = _fetch_optional_history(config.vix_ticker, reference_date=reference_date, min_rows=30)
    spy_history, spy_error = _fetch_optional_history(config.spy_ticker, reference_date=reference_date, min_rows=80)
    risk_off_triggered = False
    risk_off_parts: list[str] = []
    if vix_history is not None and config.vix_ticker:
        vix_latest = _latest_close(vix_history, config.vix_ticker)
        if vix_latest > 20:
            risk_off_triggered = True
            risk_off_parts.append(f"{config.vix_ticker} = {vix_latest:.2f} > 20")
    elif vix_error:
        optional_data_notes.append(f"VIX 未纳入：{vix_error}")
    if spy_history is not None and config.spy_ticker:
        spy_drawdown_60d = _drawdown_from_recent_high(spy_history, config.spy_ticker, 60)
        if spy_drawdown_60d > 0.08:
            risk_off_triggered = True
            risk_off_parts.append(f"{config.spy_ticker} 距 60 日高点回撤 {spy_drawdown_60d * 100:.2f}%")
    elif spy_error:
        optional_data_notes.append(f"SPY 风险偏好代理未纳入：{spy_error}")
    if risk_off_triggered:
        macro_score += 1.0
        score_details.append(f"宏观项 +1：风险偏好转弱（{'；'.join(risk_off_parts)}）。")

    if config.central_bank_support is not None:
        optional_score += float(config.central_bank_support)
        score_details.append(f"慢变量 +{float(config.central_bank_support):.1f}：央行支持项已纳入。")
    else:
        optional_data_notes.append("央行支持慢变量本月未提供，未纳入评分。")
    if config.gold_etf_flow_support is not None:
        optional_score += float(config.gold_etf_flow_support)
        score_details.append(f"慢变量 +{float(config.gold_etf_flow_support):.1f}：黄金 ETF 资金流支持已纳入。")
    else:
        optional_data_notes.append("黄金 ETF 资金流慢变量本月未提供，未纳入评分。")

    total_score = technical_score + macro_score + optional_score
    if total_score < config.buy_score_threshold:
        recommended_buy_rmb = 0
        reason = f"综合评分 {total_score:.1f} 低于买入阈值 {config.buy_score_threshold:.1f}，本月先不买。"
    elif total_score < 5:
        recommended_buy_rmb = _round_rmb(target_gap_value * 0.25)
        reason = f"综合评分 {total_score:.1f}，达到轻仓补位区间，可考虑买入目标缺口的 25%。"
    elif total_score < 7:
        recommended_buy_rmb = _round_rmb(target_gap_value * 0.50)
        reason = f"综合评分 {total_score:.1f}，达到中等补位区间，可考虑买入目标缺口的 50%。"
    else:
        recommended_buy_rmb = target_gap_value
        reason = f"综合评分 {total_score:.1f}，条件较完整，可考虑一次补足当前目标缺口。"

    recommended_buy_rmb = min(recommended_buy_rmb, max_gap_value)
    remaining_gap = max(target_gap_value - recommended_buy_rmb, 0)
    projected_gold_weight_after_buy = (
        (config.current_gold_value_rmb + recommended_buy_rmb) / config.current_total_portfolio_value_rmb
    )

    return GoldSleeveDecision(
        enabled=True,
        ticker=config.ticker,
        decision_status="BUY" if recommended_buy_rmb > 0 else "NO_BUY",
        action_label=_buy_action_label(total_score, recommended_buy_rmb),
        should_buy=recommended_buy_rmb > 0,
        data_source=DATA_SOURCE,
        validation_status=GOLD_VALIDATION_STATUS_PASS,
        latest_market_date=gold.latest_market_date,
        current_gold_weight=current_gold_weight,
        target_gold_weight=config.target_weight,
        max_gold_weight=config.max_weight,
        below_target=True,
        overheat_triggered=False,
        total_score=total_score,
        technical_score=technical_score,
        macro_score=macro_score,
        optional_score=optional_score,
        target_gold_value_rmb=target_gold_value,
        target_gap_value_rmb=target_gap_value,
        recommended_buy_rmb=recommended_buy_rmb,
        projected_gold_weight_after_buy=projected_gold_weight_after_buy,
        remaining_gap_after_buy_rmb=remaining_gap,
        reason=reason,
        notes=base_notes,
        overheat_reasons=[],
        score_details=score_details,
        optional_data_notes=optional_data_notes,
        indicator_snapshot=gold,
    )
