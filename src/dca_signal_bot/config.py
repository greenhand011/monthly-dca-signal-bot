from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    strategy_mode: str = "manual_total_per_asset_signal"
    base_monthly_rmb: int = 3000
    reserve_cap_multiple: float = 2.0
    core_ticker: str = "VOO"
    secondary_ticker: str | None = "VXUS"
    growth_ticker: str = "QQQM"
    core_weight_normal: float = 0.70
    secondary_weight_normal: float = 0.20
    growth_weight_normal: float = 0.10
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
    base_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def reserve_cap_rmb(self) -> int:
        return int(round(self.base_monthly_rmb * self.reserve_cap_multiple))


def _validate_strategy_mode(strategy_mode: str) -> None:
    allowed_modes = {
        "manual_total_per_asset_signal",
        "legacy_master_signal_total_amount",
    }
    if strategy_mode not in allowed_modes:
        raise ValueError(f"Unsupported strategy_mode: {strategy_mode}")


def apply_base_override(config: StrategyConfig, base_monthly_rmb: int | None) -> StrategyConfig:
    if base_monthly_rmb is None:
        return config
    overrides = config.base_overrides.get(str(base_monthly_rmb))
    if not overrides:
        return replace(config, base_monthly_rmb=base_monthly_rmb)

    secondary_override = overrides.get("secondary_ticker", config.secondary_ticker)
    if isinstance(secondary_override, dict) and not secondary_override:
        secondary_override = None
    updated = replace(
        config,
        strategy_mode=str(overrides.get("strategy_mode", config.strategy_mode)),
        base_monthly_rmb=base_monthly_rmb,
        core_ticker=str(overrides.get("core_ticker", config.core_ticker)),
        secondary_ticker=secondary_override,
        growth_ticker=str(overrides.get("growth_ticker", config.growth_ticker)),
        core_weight_normal=float(overrides.get("core_weight_normal", config.core_weight_normal)),
        secondary_weight_normal=float(overrides.get("secondary_weight_normal", config.secondary_weight_normal)),
        growth_weight_normal=float(overrides.get("growth_weight_normal", config.growth_weight_normal)),
    )
    return updated


def _validate_weights(core_weight: float, secondary_weight: float, growth_weight: float) -> None:
    total = core_weight + secondary_weight + growth_weight
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            "Normal weights must sum to 1.0; "
            f"got core={core_weight:.4f}, secondary={secondary_weight:.4f}, growth={growth_weight:.4f}"
        )


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
    base_overrides = raw.get("base_overrides", {}) or {}
    if not isinstance(base_overrides, dict):
        raise ValueError("base_overrides must be a mapping of base_monthly_rmb to override settings")
    normalized_overrides: dict[str, dict[str, Any]] = {}
    for key, value in base_overrides.items():
        normalized_key = str(key).strip().strip('"').strip("'")
        if isinstance(value, dict):
            normalized_overrides[normalized_key] = value
        else:
            raise ValueError("base_overrides values must be mappings of override settings")

    def normalize_optional_ticker(value: Any) -> str | None:
        if value in ("", None):
            return None
        if isinstance(value, dict) and not value:
            return None
        return str(value)

    config = StrategyConfig(
        strategy_name=str(raw.get("strategy_name", "monthly-dca-signal-bot")),
        strategy_mode=str(raw.get("strategy_mode", "manual_total_per_asset_signal")),
        base_monthly_rmb=int(raw.get("base_monthly_rmb", 3000)),
        reserve_cap_multiple=float(raw.get("reserve_cap_multiple", 2.0)),
        core_ticker=str(raw.get("core_ticker", "VOO")),
        secondary_ticker=normalize_optional_ticker(raw.get("secondary_ticker", "VXUS")),
        growth_ticker=str(raw.get("growth_ticker", "QQQM")),
        core_weight_normal=float(raw.get("core_weight_normal", 0.70)),
        secondary_weight_normal=float(raw.get("secondary_weight_normal", 0.20)),
        growth_weight_normal=float(raw.get("growth_weight_normal", 0.10)),
        feishu_enabled=bool(raw.get("feishu_enabled", False)),
        report_timezone=str(raw.get("report_timezone", "Asia/Shanghai")),
        execution_guidance_enabled=bool(raw.get("execution_guidance_enabled", True)),
        user_timezone=str(raw.get("user_timezone", "Asia/Tokyo")),
        preferred_order_type=str(raw.get("preferred_order_type", "LIMIT")),
        preferred_tif=str(raw.get("preferred_tif", "DAY")),
        suggest_outside_rth=bool(raw.get("suggest_outside_rth", True)),
        thresholds=merged_thresholds,
        base_overrides=normalized_overrides,
    )
    _validate_strategy_mode(config.strategy_mode)
    _validate_weights(config.core_weight_normal, config.secondary_weight_normal, config.growth_weight_normal)
    for override in base_overrides.values():
        _validate_strategy_mode(str(override.get("strategy_mode", config.strategy_mode)))
        _validate_weights(
            float(override.get("core_weight_normal", config.core_weight_normal)),
            float(override.get("secondary_weight_normal", config.secondary_weight_normal)),
            float(override.get("growth_weight_normal", config.growth_weight_normal)),
        )
    return config
