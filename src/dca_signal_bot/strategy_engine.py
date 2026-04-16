from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import StrategyConfig
from .indicators import TickerIndicators
from .reserve_state import ReserveState
from .presentation import (
    condition_label,
    final_recommendation_label,
    raw_signal_direction_label,
    raw_signal_judgment_label,
    rule_summary,
)


ACTION_NORMAL = "原样投"
ACTION_REDUCE = "减少投入"
ACTION_INCREASE = "增加投入"
ACTION_REBALANCE = "固定总额，调整分配"
ACTION_BASELINE = "固定总额，维持基线"

CLASSIFICATION_TO_SCORE = {
    "STRONG_OVERWEIGHT": 2,
    "OVERWEIGHT": 1,
    "NEUTRAL": 0,
    "UNDERWEIGHT": -1,
    "STRONG_UNDERWEIGHT": -2,
}

SCORE_TO_RAW_ADJUSTMENT_PCT = {
    2: 4.0,
    1: 2.0,
    0: 0.0,
    -1: -2.0,
    -2: -4.0,
}


@dataclass(frozen=True)
class ConditionCheck:
    label: str
    observed: str
    threshold: str
    passed: bool


@dataclass(frozen=True)
class RuleEvaluation:
    rule_name: str
    triggered: bool
    conditions: list[ConditionCheck]
    summary: str


@dataclass(frozen=True)
class AllocationBreakdown:
    core_rmb: int
    secondary_rmb: int
    growth_rmb: int
    core_weight: float
    secondary_weight: float
    growth_weight: float


@dataclass(frozen=True)
class AssetSignalEvaluation:
    ticker: str
    score: int
    classification: str
    raw_adjustment_pct: float
    normalized_adjustment_pct: float
    delta_rmb: int
    final_rmb: int
    summary: str
    conditions: list[ConditionCheck] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyDecision:
    state_label: str
    action_label: str
    recommendation_total_rmb: int
    allocation: AllocationBreakdown
    baseline_allocation: AllocationBreakdown
    reserve_delta_rmb: int
    reserve_cash_after_rmb: int
    strategy_mode: str
    reasons: list[str] = field(default_factory=list)
    triggered_rule: str = "NORMAL"
    decision_path: str = "NORMAL"
    rule_evaluations: list[RuleEvaluation] = field(default_factory=list)
    asset_signals: list[AssetSignalEvaluation] = field(default_factory=list)
    total_is_fixed: bool = False


def _as_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _round_rmb(value: float) -> int:
    return int(round(value))


def _allocation_from_weights(
    total_rmb: int,
    core_weight: float,
    secondary_weight: float,
    growth_weight: float,
) -> AllocationBreakdown:
    core_rmb = _round_rmb(total_rmb * core_weight)
    secondary_rmb = _round_rmb(total_rmb * secondary_weight)
    growth_rmb = max(0, total_rmb - core_rmb - secondary_rmb)
    return AllocationBreakdown(
        core_rmb=core_rmb,
        secondary_rmb=secondary_rmb,
        growth_rmb=growth_rmb,
        core_weight=core_weight,
        secondary_weight=secondary_weight,
        growth_weight=growth_weight,
    )


def _legacy_allocation(
    total_rmb: int,
    core_weight: float,
    growth_weight: float,
    core_weight_normal: float,
    secondary_weight_normal: float,
) -> AllocationBreakdown:
    core_total_rmb = _round_rmb(total_rmb * core_weight)
    growth_rmb = max(0, total_rmb - core_total_rmb)
    if secondary_weight_normal > 0:
        ratio = secondary_weight_normal / max(1e-9, core_weight_normal + secondary_weight_normal)
        secondary_rmb = _round_rmb(core_total_rmb * ratio)
        core_rmb = max(0, core_total_rmb - secondary_rmb)
    else:
        secondary_rmb = 0
        core_rmb = core_total_rmb
    secondary_weight = core_weight * (
        secondary_weight_normal / max(1e-9, core_weight_normal + secondary_weight_normal)
    )
    return AllocationBreakdown(
        core_rmb=core_rmb,
        secondary_rmb=secondary_rmb,
        growth_rmb=growth_rmb,
        core_weight=core_weight,
        secondary_weight=secondary_weight,
        growth_weight=growth_weight,
    )


def _condition_check(label: str, observed: str, threshold: str, passed: bool) -> ConditionCheck:
    return ConditionCheck(label=label, observed=observed, threshold=threshold, passed=passed)


def _rule_evaluation(rule_name: str, conditions: list[ConditionCheck], summary: str) -> RuleEvaluation:
    return RuleEvaluation(
        rule_name=rule_name,
        triggered=all(condition.passed for condition in conditions),
        conditions=conditions,
        summary=summary,
    )


def _evaluate_extreme_heat(ind: TickerIndicators, thresholds: dict[str, Any]) -> RuleEvaluation:
    drawdown_threshold = float(thresholds["drawdown_max"])
    sma_multiplier = float(thresholds["above_sma200_multiplier"])
    rsi_threshold = float(thresholds["rsi_min"])
    conditions = [
        _condition_check(
            label=condition_label("Drawdown from 52-week high"),
            observed=f"{ind.drawdown_52w * 100:.2f}%",
            threshold=f"<= {drawdown_threshold * 100:.2f}%",
            passed=ind.drawdown_52w <= drawdown_threshold,
        ),
        _condition_check(
            label=condition_label("Price vs SMA200"),
            observed=f"{ind.current_price:.2f} vs {ind.sma200 * sma_multiplier:.2f}",
            threshold=f"> SMA200 * {sma_multiplier:.2f}",
            passed=ind.current_price > ind.sma200 * sma_multiplier,
        ),
        _condition_check(
            label=condition_label("RSI(14)"),
            observed=f"{ind.rsi14:.2f}",
            threshold=f">= {rsi_threshold:.2f}",
            passed=ind.rsi14 >= rsi_threshold,
        ),
    ]
    return _rule_evaluation(
        "EXTREME_HEAT",
        conditions,
        rule_summary("QQQM is near its 52-week high, materially above SMA200, and RSI is hot."),
    )


def _evaluate_heat(ind: TickerIndicators, thresholds: dict[str, Any]) -> RuleEvaluation:
    drawdown_threshold = float(thresholds["drawdown_max"])
    sma_multiplier = float(thresholds["above_sma200_multiplier"])
    rsi_threshold = float(thresholds["rsi_min"])
    conditions = [
        _condition_check(
            label=condition_label("Drawdown from 52-week high"),
            observed=f"{ind.drawdown_52w * 100:.2f}%",
            threshold=f"<= {drawdown_threshold * 100:.2f}%",
            passed=ind.drawdown_52w <= drawdown_threshold,
        ),
        _condition_check(
            label=condition_label("Price vs SMA200"),
            observed=f"{ind.current_price:.2f} vs {ind.sma200 * sma_multiplier:.2f}",
            threshold=f"> SMA200 * {sma_multiplier:.2f}",
            passed=ind.current_price > ind.sma200 * sma_multiplier,
        ),
        _condition_check(
            label=condition_label("RSI(14)"),
            observed=f"{ind.rsi14:.2f}",
            threshold=f">= {rsi_threshold:.2f}",
            passed=ind.rsi14 >= rsi_threshold,
        ),
    ]
    return _rule_evaluation(
        "HEAT",
        conditions,
        rule_summary("QQQM is close to its 52-week high, above SMA200, and RSI is elevated."),
    )


def _evaluate_capitulation_recovery(ind: TickerIndicators, thresholds: dict[str, Any]) -> RuleEvaluation:
    drawdown_threshold = float(thresholds["drawdown_min"])
    rsi_threshold = float(thresholds["rsi_min"])
    conditions = [
        _condition_check(
            label=condition_label("Drawdown from 52-week high"),
            observed=f"{ind.drawdown_52w * 100:.2f}%",
            threshold=f">= {drawdown_threshold * 100:.2f}%",
            passed=ind.drawdown_52w >= drawdown_threshold,
        ),
        _condition_check(
            label=condition_label("Price vs SMA20"),
            observed=f"{ind.current_price:.2f} vs {ind.sma20:.2f}",
            threshold="> SMA20",
            passed=ind.current_price > ind.sma20,
        ),
        _condition_check(
            label=condition_label("RSI(14)"),
            observed=f"{ind.rsi14:.2f}",
            threshold=f"> {rsi_threshold:.2f}",
            passed=ind.rsi14 > rsi_threshold,
        ),
    ]
    return _rule_evaluation(
        "CAPITULATION_RECOVERY",
        conditions,
        rule_summary("QQQM is in a deep drawdown but has started to stabilize above SMA20 with RSI recovering."),
    )


def _evaluate_deep_pullback(ind: TickerIndicators, thresholds: dict[str, Any]) -> RuleEvaluation:
    drawdown_threshold = float(thresholds["drawdown_min"])
    rsi_threshold = float(thresholds["rsi_max"])
    conditions = [
        _condition_check(
            label=condition_label("Drawdown from 52-week high"),
            observed=f"{ind.drawdown_52w * 100:.2f}%",
            threshold=f">= {drawdown_threshold * 100:.2f}%",
            passed=ind.drawdown_52w >= drawdown_threshold,
        ),
        _condition_check(
            label=condition_label("RSI(14)"),
            observed=f"{ind.rsi14:.2f}",
            threshold=f"< {rsi_threshold:.2f}",
            passed=ind.rsi14 < rsi_threshold,
        ),
    ]
    return _rule_evaluation(
        "DEEP_PULLBACK",
        conditions,
        rule_summary("QQQM is deeply below its 52-week high and RSI is weak."),
    )


def _evaluate_pullback(ind: TickerIndicators, thresholds: dict[str, Any]) -> RuleEvaluation:
    drawdown_threshold = float(thresholds["drawdown_min"])
    conditions = [
        _condition_check(
            label=condition_label("Drawdown from 52-week high"),
            observed=f"{ind.drawdown_52w * 100:.2f}%",
            threshold=f">= {drawdown_threshold * 100:.2f}%",
            passed=ind.drawdown_52w >= drawdown_threshold,
        ),
        _condition_check(
            label=condition_label("Price vs SMA200"),
            observed=f"{ind.current_price:.2f} vs {ind.sma200:.2f}",
            threshold="< SMA200",
            passed=ind.current_price < ind.sma200,
        ),
    ]
    return _rule_evaluation(
        "PULLBACK",
        conditions,
        rule_summary("QQQM is meaningfully below its 52-week high and under SMA200."),
    )


def _build_asset_signal(ticker: str, indicators: TickerIndicators) -> tuple[int, str, list[ConditionCheck], str]:
    strong_over_checks = [
        _condition_check("强加仓：回撤 >= 20%", f"{indicators.drawdown_52w * 100:.2f}%", ">= 20.00%", indicators.drawdown_52w >= 0.20),
        _condition_check(
            "强加仓：低于 200 日均线 >= 5%",
            f"{indicators.deviation_from_sma200 * 100:.2f}%",
            "<= -5.00%",
            indicators.deviation_from_sma200 <= -0.05,
        ),
        _condition_check("强加仓：RSI <= 35", f"{indicators.rsi14:.2f}", "<= 35.00", indicators.rsi14 <= 35),
    ]
    overweight_checks = [
        _condition_check("加仓：回撤 >= 10%", f"{indicators.drawdown_52w * 100:.2f}%", ">= 10.00%", indicators.drawdown_52w >= 0.10),
        _condition_check(
            "加仓：低于 200 日均线",
            f"{indicators.deviation_from_sma200 * 100:.2f}%",
            "< 0.00%",
            indicators.deviation_from_sma200 < 0,
        ),
        _condition_check("加仓：RSI <= 45", f"{indicators.rsi14:.2f}", "<= 45.00", indicators.rsi14 <= 45),
    ]
    underweight_checks = [
        _condition_check("减仓：距 52 周高点 <= 5%", f"{indicators.drawdown_52w * 100:.2f}%", "<= 5.00%", indicators.drawdown_52w <= 0.05),
        _condition_check(
            "减仓：高于 200 日均线",
            f"{indicators.deviation_from_sma200 * 100:.2f}%",
            "> 0.00%",
            indicators.deviation_from_sma200 > 0,
        ),
        _condition_check("减仓：RSI >= 65", f"{indicators.rsi14:.2f}", ">= 65.00", indicators.rsi14 >= 65),
    ]
    strong_under_checks = [
        _condition_check("强减仓：距 52 周高点 <= 2%", f"{indicators.drawdown_52w * 100:.2f}%", "<= 2.00%", indicators.drawdown_52w <= 0.02),
        _condition_check(
            "强减仓：高于 200 日均线 >= 5%",
            f"{indicators.deviation_from_sma200 * 100:.2f}%",
            ">= 5.00%",
            indicators.deviation_from_sma200 >= 0.05,
        ),
        _condition_check("强减仓：RSI >= 72", f"{indicators.rsi14:.2f}", ">= 72.00", indicators.rsi14 >= 72),
    ]

    strong_over_count = sum(check.passed for check in strong_over_checks)
    overweight_count = sum(check.passed for check in overweight_checks)
    underweight_count = sum(check.passed for check in underweight_checks)
    strong_under_count = sum(check.passed for check in strong_under_checks)

    if strong_over_count >= 2:
        score = 2
        classification = "STRONG_OVERWEIGHT"
        summary = f"{ticker} 至少满足 2 项强加仓条件，可考虑明显高配。"
    elif strong_under_count >= 2:
        score = -2
        classification = "STRONG_UNDERWEIGHT"
        summary = f"{ticker} 至少满足 2 项强减仓条件，可考虑明显低配。"
    elif overweight_count >= 2:
        score = 1
        classification = "OVERWEIGHT"
        summary = f"{ticker} 至少满足 2 项加仓条件，可考虑适当高配。"
    elif underweight_count >= 2:
        score = -1
        classification = "UNDERWEIGHT"
        summary = f"{ticker} 至少满足 2 项减仓条件，可考虑轻微低配。"
    else:
        score = 0
        classification = "NEUTRAL"
        summary = f"{ticker} 当前信号中性，维持基线。"

    return score, classification, strong_over_checks + overweight_checks + underweight_checks + strong_under_checks, summary


def _normalize_deltas_to_zero_sum(
    tickers: list[str],
    total_rmb: int,
    raw_pct_map: dict[str, float],
) -> tuple[dict[str, float], dict[str, int]]:
    mean_raw = sum(raw_pct_map.values()) / len(raw_pct_map)
    centered_pct = {ticker: raw_pct_map[ticker] - mean_raw for ticker in tickers}
    float_deltas = {ticker: total_rmb * centered_pct[ticker] / 100.0 for ticker in tickers}
    rounded = {ticker: int(round(delta)) for ticker, delta in float_deltas.items()}
    correction = -sum(rounded.values())

    if correction != 0:
        remainders = {ticker: float_deltas[ticker] - rounded[ticker] for ticker in tickers}
        ordered = sorted(
            tickers,
            key=lambda ticker: remainders[ticker],
            reverse=correction > 0,
        )
        step = 1 if correction > 0 else -1
        for index in range(abs(correction)):
            rounded[ordered[index % len(ordered)]] += step

    normalized_pct = {
        ticker: (rounded[ticker] / total_rmb * 100.0) if total_rmb else 0.0
        for ticker in tickers
    }
    return normalized_pct, rounded


def _evaluate_manual_total_per_asset_signal(
    config: StrategyConfig,
    core_indicators: TickerIndicators,
    secondary_indicators: TickerIndicators | None,
    growth_indicators: TickerIndicators,
    reserve_state: ReserveState,
) -> StrategyDecision:
    if config.secondary_ticker and secondary_indicators is None:
        raise ValueError(f"{config.secondary_ticker}: secondary_indicators is required in manual_total_per_asset_signal mode")
    total_rmb = config.base_monthly_rmb
    baseline = _allocation_from_weights(
        total_rmb,
        config.core_weight_normal,
        config.secondary_weight_normal,
        config.growth_weight_normal,
    )

    assets: list[tuple[str, TickerIndicators, int, float]] = [
        (config.core_ticker, core_indicators, baseline.core_rmb, config.core_weight_normal),
    ]
    if config.secondary_ticker and secondary_indicators is not None:
        assets.append((config.secondary_ticker, secondary_indicators, baseline.secondary_rmb, config.secondary_weight_normal))
    assets.append((config.growth_ticker, growth_indicators, baseline.growth_rmb, config.growth_weight_normal))

    raw_pct_map: dict[str, float] = {}
    signal_meta: dict[str, tuple[int, str, list[ConditionCheck], str]] = {}
    for ticker, indicators, _, _ in assets:
        score, classification, checks, summary = _build_asset_signal(ticker, indicators)
        raw_pct_map[ticker] = SCORE_TO_RAW_ADJUSTMENT_PCT[score]
        signal_meta[ticker] = (score, classification, checks, summary)

    normalized_pct, delta_rmb = _normalize_deltas_to_zero_sum(
        [ticker for ticker, _, _, _ in assets],
        total_rmb,
        raw_pct_map,
    )

    final_amounts: dict[str, int] = {}
    asset_signals: list[AssetSignalEvaluation] = []
    for ticker, _, base_rmb, _ in assets:
        score, classification, checks, summary = signal_meta[ticker]
        final_rmb = base_rmb + delta_rmb[ticker]
        if final_rmb < 0:
            raise ValueError(f"{ticker}: tactical final amount became negative after adjustment")
        final_amounts[ticker] = final_rmb
        asset_signals.append(
            AssetSignalEvaluation(
                ticker=ticker,
                score=score,
                classification=classification,
                raw_adjustment_pct=raw_pct_map[ticker],
                normalized_adjustment_pct=normalized_pct[ticker],
                delta_rmb=delta_rmb[ticker],
                final_rmb=final_rmb,
                summary=summary,
                conditions=checks,
            )
        )

    allocation = AllocationBreakdown(
        core_rmb=final_amounts[config.core_ticker],
        secondary_rmb=final_amounts.get(config.secondary_ticker or "", 0),
        growth_rmb=final_amounts[config.growth_ticker],
        core_weight=final_amounts[config.core_ticker] / total_rmb,
        secondary_weight=(final_amounts.get(config.secondary_ticker or "", 0) / total_rmb) if config.secondary_ticker else 0.0,
        growth_weight=final_amounts[config.growth_ticker] / total_rmb,
    )

    total_abs_delta = sum(abs(signal.delta_rmb) for signal in asset_signals)
    state_label = "TACTICAL_REBALANCE" if total_abs_delta > 0 else "BASELINE_ONLY"
    action_label = ACTION_REBALANCE if total_abs_delta > 0 else ACTION_BASELINE
    decision_path = " | ".join(f"{signal.ticker}:{signal.classification}" for signal in asset_signals)
    asset_names = "、".join(signal.ticker for signal in asset_signals)
    reasons = [
        f"本月总投入由手动设定为 {total_rmb} RMB，不参与自动增减仓。",
        f"系统分别评估了 {asset_names} 的原始资产信号。",
    ]
    if total_abs_delta == 0:
        reasons.append(
            "尽管部分资产原始信号显示偏热或偏弱，但在三资产零和归一化后，本月未形成明确的相对增减配结果，因此最终维持基线分配。"
        )
    else:
        reasons.append("系统已将原始建议归一化为零和分配调整，因此最终只改变资产间配比，不改变本月总投入。")

    reasons.extend(
        (
            f"{signal.ticker}：原始信号{raw_signal_judgment_label(signal.classification)}，"
            f"原始建议{raw_signal_direction_label(signal.classification)}；"
            + (
                "但在三资产零和归一化后，本月最终调整为 0，维持基线。"
                if signal.delta_rmb == 0
                else f"归一化后最终建议为{final_recommendation_label(signal.normalized_adjustment_pct, signal.delta_rmb)}，"
                f"调整 {signal.normalized_adjustment_pct:+.2f}%（{signal.delta_rmb:+d} RMB）。"
            )
        )
        for signal in asset_signals
    )

    return StrategyDecision(
        state_label=state_label,
        action_label=action_label,
        recommendation_total_rmb=total_rmb,
        allocation=allocation,
        baseline_allocation=baseline,
        reserve_delta_rmb=0,
        reserve_cash_after_rmb=reserve_state.reserve_cash_rmb,
        strategy_mode=config.strategy_mode,
        reasons=reasons,
        triggered_rule="PER_ASSET_TACTICAL",
        decision_path=decision_path,
        rule_evaluations=[],
        asset_signals=asset_signals,
        total_is_fixed=True,
    )


def _evaluate_legacy_master_signal(
    config: StrategyConfig,
    core_indicators: TickerIndicators,
    growth_indicators: TickerIndicators,
    reserve_state: ReserveState,
) -> StrategyDecision:
    _ = core_indicators
    growth_thresholds = config.thresholds
    base = config.base_monthly_rmb
    reserve_before = max(0, min(int(reserve_state.reserve_cash_rmb), config.reserve_cap_rmb))
    reserve_space = max(0, config.reserve_cap_rmb - reserve_before)
    reasons = [
        f"{config.growth_ticker} 当前价 {growth_indicators.current_price:.2f}",
        f"52 周回撤 {_as_percent(growth_indicators.drawdown_52w)}",
        f"200 日偏离 {_as_percent(growth_indicators.deviation_from_sma200)}",
        f"RSI(14) {growth_indicators.rsi14:.2f}",
    ]

    rule_evaluations = [
        _evaluate_extreme_heat(growth_indicators, growth_thresholds["extreme_heat"]),
        _evaluate_heat(growth_indicators, growth_thresholds["heat"]),
        _evaluate_capitulation_recovery(growth_indicators, growth_thresholds["capitulation_recovery"]),
        _evaluate_deep_pullback(growth_indicators, growth_thresholds["deep_pullback"]),
        _evaluate_pullback(growth_indicators, growth_thresholds["pullback"]),
    ]
    decision_path = " -> ".join(
        f"{evaluation.rule_name}:{'YES' if evaluation.triggered else 'NO'}" for evaluation in rule_evaluations
    )

    baseline = _allocation_from_weights(
        base,
        config.core_weight_normal,
        config.secondary_weight_normal,
        config.growth_weight_normal,
    )
    state_label = "NORMAL"
    action_label = ACTION_NORMAL
    recommendation_total = base
    core_total_weight = config.core_weight_normal + config.secondary_weight_normal
    allocation = _legacy_allocation(
        base,
        core_total_weight,
        config.growth_weight_normal,
        config.core_weight_normal,
        config.secondary_weight_normal,
    )
    reserve_delta = 0
    triggered_rule = "NORMAL"

    if rule_evaluations[0].triggered:
        state_label = "EXTREME_HEAT"
        action_label = ACTION_REDUCE
        recommendation_total = _round_rmb(base * float(growth_thresholds["extreme_heat"]["total_multiplier"]))
        allocation = _legacy_allocation(
            recommendation_total,
            float(growth_thresholds["extreme_heat"]["core_weight"]),
            float(growth_thresholds["extreme_heat"]["growth_weight"]),
            config.core_weight_normal,
            config.secondary_weight_normal,
        )
        reserve_delta = min(base - recommendation_total, reserve_space)
        triggered_rule = "EXTREME_HEAT"
        reasons.append("同时满足极热条件：接近 52 周高点，显著高于 200 日均线且 RSI 偏高。")
    elif rule_evaluations[1].triggered:
        state_label = "HEAT"
        action_label = ACTION_REDUCE
        recommendation_total = _round_rmb(base * float(growth_thresholds["heat"]["total_multiplier"]))
        allocation = _legacy_allocation(
            recommendation_total,
            float(growth_thresholds["heat"]["core_weight"]),
            float(growth_thresholds["heat"]["growth_weight"]),
            config.core_weight_normal,
            config.secondary_weight_normal,
        )
        reserve_delta = min(base - recommendation_total, reserve_space)
        triggered_rule = "HEAT"
        reasons.append("同时满足过热条件：接近 52 周高点，站上 200 日均线且 RSI 偏高。")
    elif rule_evaluations[2].triggered:
        state_label = "CAPITULATION_RECOVERY"
        extra = min(
            _round_rmb(base * float(growth_thresholds["capitulation_recovery"]["reserve_multiplier"])),
            reserve_before,
        )
        recommendation_total = base + extra
        allocation = _legacy_allocation(
            recommendation_total,
            float(growth_thresholds["capitulation_recovery"]["core_weight"]),
            float(growth_thresholds["capitulation_recovery"]["growth_weight"]),
            config.core_weight_normal,
            config.secondary_weight_normal,
        )
        reserve_delta = -extra
        action_label = ACTION_INCREASE if extra > 0 else ACTION_NORMAL
        triggered_rule = "CAPITULATION_RECOVERY"
        reasons.append("满足极端回撤后初步止跌：深度回撤、重新站上 20 日均线且 RSI 回升。")
    elif rule_evaluations[3].triggered:
        state_label = "DEEP_PULLBACK"
        extra = min(
            _round_rmb(base * float(growth_thresholds["deep_pullback"]["reserve_multiplier"])),
            reserve_before,
        )
        recommendation_total = base + extra
        allocation = _legacy_allocation(
            recommendation_total,
            float(growth_thresholds["deep_pullback"]["core_weight"]),
            float(growth_thresholds["deep_pullback"]["growth_weight"]),
            config.core_weight_normal,
            config.secondary_weight_normal,
        )
        reserve_delta = -extra
        action_label = ACTION_INCREASE if extra > 0 else ACTION_NORMAL
        triggered_rule = "DEEP_PULLBACK"
        reasons.append("满足深度回撤条件：从 52 周高点显著回撤且 RSI 偏弱。")
    elif rule_evaluations[4].triggered:
        state_label = "PULLBACK"
        extra = min(
            _round_rmb(base * float(growth_thresholds["pullback"]["reserve_multiplier"])),
            reserve_before,
        )
        recommendation_total = base + extra
        allocation = _legacy_allocation(
            recommendation_total,
            float(growth_thresholds["pullback"]["core_weight"]),
            float(growth_thresholds["pullback"]["growth_weight"]),
            config.core_weight_normal,
            config.secondary_weight_normal,
        )
        reserve_delta = -extra
        action_label = ACTION_INCREASE if extra > 0 else ACTION_NORMAL
        triggered_rule = "PULLBACK"
        reasons.append("满足回撤条件：QQQM 跌破 200 日均线且从 52 周高点有明显回撤。")
    else:
        reasons.append("未同时满足更强的热度或回撤条件，按基线配比执行。")

    reserve_after = max(0, reserve_before + reserve_delta)

    return StrategyDecision(
        state_label=state_label,
        action_label=action_label,
        recommendation_total_rmb=recommendation_total,
        allocation=allocation,
        baseline_allocation=baseline,
        reserve_delta_rmb=reserve_delta,
        reserve_cash_after_rmb=reserve_after,
        strategy_mode=config.strategy_mode,
        reasons=reasons,
        triggered_rule=triggered_rule,
        decision_path=f"{decision_path} => {triggered_rule}",
        rule_evaluations=rule_evaluations,
        asset_signals=[],
        total_is_fixed=False,
    )


def evaluate_strategy(
    config: StrategyConfig,
    core_indicators: TickerIndicators,
    growth_indicators: TickerIndicators,
    reserve_state: ReserveState,
    secondary_indicators: TickerIndicators | None = None,
) -> StrategyDecision:
    if config.strategy_mode == "manual_total_per_asset_signal":
        return _evaluate_manual_total_per_asset_signal(
            config,
            core_indicators,
            secondary_indicators,
            growth_indicators,
            reserve_state,
        )
    if config.strategy_mode == "legacy_master_signal_total_amount":
        return _evaluate_legacy_master_signal(
            config,
            core_indicators,
            growth_indicators,
            reserve_state,
        )
    raise ValueError(f"Unsupported strategy_mode: {config.strategy_mode}")
