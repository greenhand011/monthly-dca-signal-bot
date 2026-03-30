from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import StrategyConfig
from .indicators import TickerIndicators
from .reserve_state import ReserveState
from .presentation import condition_label, rule_summary


ACTION_NORMAL = "\u539f\u6837\u6295"
ACTION_REDUCE = "\u51cf\u5c11\u6295\u5165"
ACTION_INCREASE = "\u589e\u52a0\u6295\u5165"


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
    growth_rmb: int
    core_weight: float
    growth_weight: float


@dataclass(frozen=True)
class StrategyDecision:
    state_label: str
    action_label: str
    recommendation_total_rmb: int
    allocation: AllocationBreakdown
    reserve_delta_rmb: int
    reserve_cash_after_rmb: int
    reasons: list[str] = field(default_factory=list)
    triggered_rule: str = "NORMAL"
    decision_path: str = "NORMAL"
    rule_evaluations: list[RuleEvaluation] = field(default_factory=list)


def _as_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _round_rmb(value: float) -> int:
    return int(round(value))


def _allocations(total_rmb: int, core_weight: float, growth_weight: float) -> AllocationBreakdown:
    core_rmb = _round_rmb(total_rmb * core_weight)
    growth_rmb = max(0, total_rmb - core_rmb)
    return AllocationBreakdown(
        core_rmb=core_rmb,
        growth_rmb=growth_rmb,
        core_weight=core_weight,
        growth_weight=growth_weight,
    )


def _condition_check(label: str, observed: str, threshold: str, passed: bool) -> ConditionCheck:
    return ConditionCheck(label=label, observed=observed, threshold=threshold, passed=passed)


def _rule_evaluation(rule_name: str, conditions: list[ConditionCheck], summary: str) -> RuleEvaluation:
    return RuleEvaluation(rule_name=rule_name, triggered=all(condition.passed for condition in conditions), conditions=conditions, summary=summary)


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


def evaluate_strategy(
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
        f"{config.growth_ticker} \u5f53\u524d\u4ef7 {growth_indicators.current_price:.2f}",
        f"52 \u5468\u56de\u64a4 {_as_percent(growth_indicators.drawdown_52w)}",
        f"200 \u65e5\u504f\u79bb {_as_percent(growth_indicators.deviation_from_sma200)}",
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

    state_label = "NORMAL"
    action_label = ACTION_NORMAL
    recommendation_total = base
    allocation = _allocations(base, config.core_weight_normal, config.growth_weight_normal)
    reserve_delta = 0
    triggered_rule = "NORMAL"

    if rule_evaluations[0].triggered:
        state_label = "EXTREME_HEAT"
        action_label = ACTION_REDUCE
        recommendation_total = _round_rmb(base * float(growth_thresholds["extreme_heat"]["total_multiplier"]))
        allocation = _allocations(
            recommendation_total,
            float(growth_thresholds["extreme_heat"]["core_weight"]),
            float(growth_thresholds["extreme_heat"]["growth_weight"]),
        )
        reserve_delta = min(base - recommendation_total, reserve_space)
        triggered_rule = "EXTREME_HEAT"
        reasons.append(
            "\u540c\u65f6\u6ee1\u8db3\u6781\u70ed\u6761\u4ef6\uff1a\u63a5\u8fd1 52 \u5468\u9ad8\u70b9\uff0c\u663e\u8457\u9ad8\u4e8e 200 \u65e5\u5747\u7ebf\u4e14 RSI \u504f\u9ad8\u3002"
        )
    elif rule_evaluations[1].triggered:
        state_label = "HEAT"
        action_label = ACTION_REDUCE
        recommendation_total = _round_rmb(base * float(growth_thresholds["heat"]["total_multiplier"]))
        allocation = _allocations(
            recommendation_total,
            float(growth_thresholds["heat"]["core_weight"]),
            float(growth_thresholds["heat"]["growth_weight"]),
        )
        reserve_delta = min(base - recommendation_total, reserve_space)
        triggered_rule = "HEAT"
        reasons.append(
            "\u540c\u65f6\u6ee1\u8db3\u8fc7\u70ed\u6761\u4ef6\uff1a\u63a5\u8fd1 52 \u5468\u9ad8\u70b9\uff0c\u7ad9\u4e0a 200 \u65e5\u5747\u7ebf\u4e14 RSI \u504f\u9ad8\u3002"
        )
    elif rule_evaluations[2].triggered:
        state_label = "CAPITULATION_RECOVERY"
        extra = min(
            _round_rmb(base * float(growth_thresholds["capitulation_recovery"]["reserve_multiplier"])),
            reserve_before,
        )
        recommendation_total = base + extra
        allocation = _allocations(
            recommendation_total,
            float(growth_thresholds["capitulation_recovery"]["core_weight"]),
            float(growth_thresholds["capitulation_recovery"]["growth_weight"]),
        )
        reserve_delta = -extra
        action_label = ACTION_INCREASE if extra > 0 else ACTION_NORMAL
        triggered_rule = "CAPITULATION_RECOVERY"
        reasons.append(
            "\u6ee1\u8db3\u6781\u7aef\u56de\u64a4\u540e\u521d\u6b65\u6b62\u8dcc\uff1a\u6df1\u5ea6\u56de\u64a4\u3001\u91cd\u65b0\u7ad9\u4e0a 20 \u65e5\u5747\u7ebf\u4e14 RSI \u56de\u5347\u3002"
        )
    elif rule_evaluations[3].triggered:
        state_label = "DEEP_PULLBACK"
        extra = min(
            _round_rmb(base * float(growth_thresholds["deep_pullback"]["reserve_multiplier"])),
            reserve_before,
        )
        recommendation_total = base + extra
        allocation = _allocations(
            recommendation_total,
            float(growth_thresholds["deep_pullback"]["core_weight"]),
            float(growth_thresholds["deep_pullback"]["growth_weight"]),
        )
        reserve_delta = -extra
        action_label = ACTION_INCREASE if extra > 0 else ACTION_NORMAL
        triggered_rule = "DEEP_PULLBACK"
        reasons.append(
            "\u6ee1\u8db3\u6df1\u5ea6\u56de\u64a4\u6761\u4ef6\uff1a\u4ece 52 \u5468\u9ad8\u70b9\u663e\u8457\u56de\u64a4\u4e14 RSI \u504f\u5f31\u3002"
        )
    elif rule_evaluations[4].triggered:
        state_label = "PULLBACK"
        extra = min(
            _round_rmb(base * float(growth_thresholds["pullback"]["reserve_multiplier"])),
            reserve_before,
        )
        recommendation_total = base + extra
        allocation = _allocations(
            recommendation_total,
            float(growth_thresholds["pullback"]["core_weight"]),
            float(growth_thresholds["pullback"]["growth_weight"]),
        )
        reserve_delta = -extra
        action_label = ACTION_INCREASE if extra > 0 else ACTION_NORMAL
        triggered_rule = "PULLBACK"
        reasons.append(
            "\u6ee1\u8db3\u56de\u64a4\u6761\u4ef6\uff1aQQQM \u8dcc\u7834 200 \u65e5\u5747\u7ebf\u4e14\u4ece 52 \u5468\u9ad8\u70b9\u6709\u660e\u663e\u56de\u64a4\u3002"
        )
    else:
        reasons.append(
            "\u672a\u540c\u65f6\u6ee1\u8db3\u66f4\u5f3a\u7684\u70ed\u5ea6\u6216\u56de\u64a4\u6761\u4ef6\uff0c\u6309\u57fa\u7ebf\u914d\u6bd4\u6267\u884c\u3002"
        )

    reserve_after = max(0, reserve_before + reserve_delta)

    return StrategyDecision(
        state_label=state_label,
        action_label=action_label,
        recommendation_total_rmb=recommendation_total,
        allocation=allocation,
        reserve_delta_rmb=reserve_delta,
        reserve_cash_after_rmb=reserve_after,
        reasons=reasons,
        triggered_rule=triggered_rule,
        decision_path=f"{decision_path} => {triggered_rule}",
        rule_evaluations=rule_evaluations,
    )
