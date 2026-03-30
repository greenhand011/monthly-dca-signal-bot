from __future__ import annotations

STATE_LABELS = {
    "NORMAL": "正常执行",
    "HEAT": "过热",
    "EXTREME_HEAT": "极热",
    "PULLBACK": "回撤加投",
    "DEEP_PULLBACK": "深度回撤",
    "CAPITULATION_RECOVERY": "止跌回升",
}

VALIDATION_LABELS = {
    "PASS": "通过",
    "WARN": "警告",
    "FAIL": "失败",
}

SESSION_LABELS = {
    "closed": "休市/关闭",
    "premarket": "盘前",
    "regular": "常规时段",
    "afterhours": "盘后",
    "overnight": "夜盘",
}

YES_NO_LABELS = {
    True: "是",
    False: "否",
}

MODE_LABELS = {
    "production": "正式模式",
    "simulation": "模拟模式",
}

ORDER_TYPE_LABELS = {
    "LIMIT": "限价单",
    "MARKET": "市价单",
}

TIF_LABELS = {
    "DAY": "当日有效",
    "GTC": "长期有效",
}

RULE_LABELS = {
    "EXTREME_HEAT": "极热",
    "HEAT": "过热",
    "CAPITULATION_RECOVERY": "极端回撤后止跌",
    "DEEP_PULLBACK": "深度回撤",
    "PULLBACK": "回撤",
    "NORMAL": "正常执行",
}

CONDITION_LABELS = {
    "Drawdown from 52-week high": "距 52 周高点回撤",
    "Price vs SMA200": "价格 vs 200 日均线",
    "Price vs SMA20": "价格 vs 20 日均线",
    "RSI(14)": "RSI(14)",
}

RULE_SUMMARY_LABELS = {
    "QQQM is near its 52-week high, materially above SMA200, and RSI is hot.": "QQQM 接近 52 周高点，显著高于 200 日均线，且 RSI 偏热。",
    "QQQM is close to its 52-week high, above SMA200, and RSI is elevated.": "QQQM 接近 52 周高点，位于 200 日均线上方，且 RSI 偏高。",
    "QQQM is in a deep drawdown but has started to stabilize above SMA20 with RSI recovering.": "QQQM 处于深度回撤中，但已重新站上 20 日均线且 RSI 开始修复。",
    "QQQM is deeply below its 52-week high and RSI is weak.": "QQQM 距 52 周高点回撤较深，且 RSI 偏弱。",
    "QQQM is meaningfully below its 52-week high and under SMA200.": "QQQM 已明显跌破 52 周高点，且位于 200 日均线下方。",
}

RUN_MODE_LABELS = {
    "Production Mode": "正式模式",
}


def yes_no(value: bool) -> str:
    return YES_NO_LABELS[bool(value)]


def state_label(label: str) -> str:
    return STATE_LABELS.get(label, label)


def validation_label(label: str) -> str:
    return VALIDATION_LABELS.get(label, label)


def session_label(label: str) -> str:
    return SESSION_LABELS.get(label, label)


def mode_label(label: str | None) -> str:
    if not label:
        return MODE_LABELS["production"]
    if label.startswith("Simulation Mode"):
        return label.replace("Simulation Mode", "模拟模式")
    return RUN_MODE_LABELS.get(label, label)


def order_type_label(label: str) -> str:
    return ORDER_TYPE_LABELS.get(label, label)


def tif_label(label: str) -> str:
    return TIF_LABELS.get(label, label)


def outside_rth_label(value: bool) -> str:
    return f"允许常规时段外成交：{yes_no(value)}"


def rule_label(label: str) -> str:
    return RULE_LABELS.get(label, label)


def condition_label(label: str) -> str:
    return CONDITION_LABELS.get(label, label)


def rule_summary(label: str) -> str:
    return RULE_SUMMARY_LABELS.get(label, label)


def decision_path_label(text: str) -> str:
    replacements = [
        ("EXTREME_HEAT", "极热"),
        ("HEAT", "过热"),
        ("CAPITULATION_RECOVERY", "止跌回升"),
        ("DEEP_PULLBACK", "深度回撤"),
        ("PULLBACK", "回撤"),
        ("NORMAL", "正常执行"),
        ("YES", "是"),
        ("NO", "否"),
    ]
    result = text
    for source, target in replacements:
        result = result.replace(source, target)
    return result
