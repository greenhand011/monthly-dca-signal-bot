from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency guard
    yaml = None


DEFAULT_THRESHOLDS: dict[str, dict[str, Any]] = {
    "extreme_heat": {
        "drawdown_max": 0.02,
        "above_sma200_multiplier": 1.15,
        "rsi_min": 70,
        "total_multiplier": 2 / 3,
        "core_weight": 0.90,
        "growth_weight": 0.10,
    },
    "heat": {
        "drawdown_max": 0.05,
        "above_sma200_multiplier": 1.08,
        "rsi_min": 65,
        "total_multiplier": 5 / 6,
        "core_weight": 0.88,
        "growth_weight": 0.12,
    },
    "pullback": {
        "drawdown_min": 0.15,
        "below_sma200": True,
        "reserve_multiplier": 1 / 6,
        "core_weight": 0.75,
        "growth_weight": 0.25,
    },
    "deep_pullback": {
        "drawdown_min": 0.25,
        "rsi_max": 35,
        "reserve_multiplier": 1 / 3,
        "core_weight": 0.70,
        "growth_weight": 0.30,
    },
    "capitulation_recovery": {
        "drawdown_min": 0.35,
        "above_sma20": True,
        "rsi_min": 40,
        "reserve_multiplier": 0.5,
        "core_weight": 0.65,
        "growth_weight": 0.35,
    },
}


@dataclass(frozen=True)
class StrategyConfig:
    strategy_name: str = "monthly-dca-signal-bot"
    base_monthly_rmb: int = 3000
    reserve_cap_multiple: float = 2.0
    core_ticker: str = "VOO"
    growth_ticker: str = "QQQM"
    core_weight_normal: float = 0.85
    growth_weight_normal: float = 0.15
    feishu_enabled: bool = False
    report_timezone: str = "Asia/Shanghai"
    execution_guidance_enabled: bool = True
    user_timezone: str = "Asia/Tokyo"
    preferred_order_type: str = "LIMIT"
    preferred_tif: str = "DAY"
    suggest_outside_rth: bool = True
    thresholds: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {name: dict(values) for name, values in DEFAULT_THRESHOLDS.items()}
    )

    @property
    def reserve_cap_rmb(self) -> int:
        return int(round(self.base_monthly_rmb * self.reserve_cap_multiple))


def _deep_merge(default: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(default)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Strategy config not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        text = handle.read()

    if yaml is not None:
        data = yaml.safe_load(text) or {}
    else:
        data = _load_simple_yaml(text)

    if not isinstance(data, dict):
        raise ValueError(f"Strategy config must be a YAML mapping: {path}")
    return data


def _load_simple_yaml(text: str) -> dict[str, Any]:
    def parse_scalar(raw: str) -> Any:
        value = raw.strip()
        if not value:
            return ""
        lowered = value.lower()
        if lowered in {"true", "yes"}:
            return True
        if lowered in {"false", "no"}:
            return False
        if lowered in {"null", "none", "~"}:
            return None
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            return value[1:-1]
        try:
            if any(ch in value for ch in (".", "e", "E")):
                return float(value)
            return int(value)
        except ValueError:
            return value

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            raise ValueError(f"Unsupported YAML line: {raw_line!r}")

        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if value == "":
            nested: dict[str, Any] = {}
            parent[key] = nested
            stack.append((indent, nested))
        else:
            parent[key] = parse_scalar(value)

    return root


def load_strategy_config(path: str | Path) -> StrategyConfig:
    path = Path(path)
    raw = load_yaml_file(path)
    merged_thresholds = _deep_merge(DEFAULT_THRESHOLDS, raw.get("thresholds", {}) or {})

    return StrategyConfig(
        strategy_name=str(raw.get("strategy_name", "monthly-dca-signal-bot")),
        base_monthly_rmb=int(raw.get("base_monthly_rmb", 3000)),
        reserve_cap_multiple=float(raw.get("reserve_cap_multiple", 2.0)),
        core_ticker=str(raw.get("core_ticker", "VOO")),
        growth_ticker=str(raw.get("growth_ticker", "QQQM")),
        core_weight_normal=float(raw.get("core_weight_normal", 0.85)),
        growth_weight_normal=float(raw.get("growth_weight_normal", 0.15)),
        feishu_enabled=bool(raw.get("feishu_enabled", False)),
        report_timezone=str(raw.get("report_timezone", "Asia/Shanghai")),
        execution_guidance_enabled=bool(raw.get("execution_guidance_enabled", True)),
        user_timezone=str(raw.get("user_timezone", "Asia/Tokyo")),
        preferred_order_type=str(raw.get("preferred_order_type", "LIMIT")),
        preferred_tif=str(raw.get("preferred_tif", "DAY")),
        suggest_outside_rth=bool(raw.get("suggest_outside_rth", True)),
        thresholds=merged_thresholds,
    )
