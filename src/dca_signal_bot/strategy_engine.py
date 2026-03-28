from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import StrategyConfig
from .indicators import TickerIndicators
from .reserve_state import ReserveState


ACTION_NORMAL = "\u539f\u6837\u6295"
ACTION_REDUCE = "\u51cf\u5c11\u6295\u5165"
ACTION_INCREASE = "\u589e\u52a0\u6295\u5165"


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


def _rule_matches_extreme_heat(ind: TickerIndicators, thresholds: dict[str, Any]) -> bool:
    return (
        ind.drawdown_52w <= float(thresholds["drawdown_max"])
        and ind.current_price > ind.sma200 * float(thresholds["above_sma200_multiplier"])
        and ind.rsi14 >= float(thresholds["rsi_min"])
    )


def _rule_matches_heat(ind: TickerIndicators, thresholds: dict[str, Any]) -> bool:
    return (
        ind.drawdown_52w <= float(thresholds["drawdown_max"])
        and ind.current_price > ind.sma200 * float(thresholds["above_sma200_multiplier"])
        and ind.rsi14 >= float(thresholds["rsi_min"])
    )


def _rule_matches_pullback(ind: TickerIndicators, thresholds: dict[str, Any]) -> bool:
    return ind.drawdown_52w >= float(thresholds["drawdown_min"]) and ind.current_price < ind.sma200


def _rule_matches_deep_pullback(ind: TickerIndicators, thresholds: dict[str, Any]) -> bool:
    return ind.drawdown_52w >= float(thresholds["drawdown_min"]) and ind.rsi14 < float(thresholds["rsi_max"])


def _rule_matches_capitulation_recovery(ind: TickerIndicators, thresholds: dict[str, Any]) -> bool:
    return (
        ind.drawdown_52w >= float(thresholds["drawdown_min"])
        and ind.current_price > ind.sma20
        and ind.rsi14 > float(thresholds["rsi_min"])
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

    state_label = "NORMAL"
    action_label = ACTION_NORMAL
    recommendation_total = base
    allocation = _allocations(base, config.core_weight_normal, config.growth_weight_normal)
    reserve_delta = 0
    triggered_rule = "NORMAL"

    if _rule_matches_extreme_heat(growth_indicators, growth_thresholds["extreme_heat"]):
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

    elif _rule_matches_heat(growth_indicators, growth_thresholds["heat"]):
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

    elif _rule_matches_capitulation_recovery(growth_indicators, growth_thresholds["capitulation_recovery"]):
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

    elif _rule_matches_deep_pullback(growth_indicators, growth_thresholds["deep_pullback"]):
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

    elif _rule_matches_pullback(growth_indicators, growth_thresholds["pullback"]):
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
    )
