from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


US_EASTERN_TZ = ZoneInfo("America/New_York")
SESSION_PREMARKET_START = time(4, 0)
SESSION_REGULAR_START = time(9, 30)
SESSION_REGULAR_END = time(16, 0)
SESSION_AFTERHOURS_START = time(16, 0)
SESSION_AFTERHOURS_END = time(20, 0)


class ExecutionGuidanceError(RuntimeError):
    """Raised when execution guidance cannot be derived from the supplied settings."""


@dataclass(frozen=True)
class ExecutionGuidance:
    generated_at_utc: datetime
    user_timezone: str
    user_time: datetime
    market_time_et: datetime
    session_phase: str
    can_submit_now: bool
    can_likely_fill_now: bool
    next_regular_open: datetime
    next_extended_hours_opportunity: datetime
    preferred_order_type: str
    preferred_tif: str
    suggest_outside_rth: bool
    warnings: tuple[str, ...]
    notes: tuple[str, ...]


def _observed_date(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    first_day = date(year, month, 1)
    offset = (weekday - first_day.weekday()) % 7
    return first_day + timedelta(days=offset + 7 * (n - 1))


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=offset)


def _easter_sunday(year: int) -> date:
    # Anonymous Gregorian algorithm.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nyse_holidays_for_year(year: int) -> set[date]:
    holidays = {
        _observed_date(date(year, 1, 1)),  # New Year's Day
        _nth_weekday_of_month(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday_of_month(year, 2, 0, 3),  # Washington's Birthday / Presidents' Day
        _easter_sunday(year) - timedelta(days=2),  # Good Friday
        _last_weekday_of_month(year, 5, 0),  # Memorial Day
        _observed_date(date(year, 7, 4)),  # Independence Day
        _nth_weekday_of_month(year, 9, 0, 1),  # Labor Day
        _nth_weekday_of_month(year, 11, 3, 4),  # Thanksgiving Day
        _observed_date(date(year, 12, 25)),  # Christmas Day
    }
    if year >= 2022:
        holidays.add(_observed_date(date(year, 6, 19)))  # Juneteenth
    return holidays


def _is_nyse_holiday(day: date) -> bool:
    years = {day.year - 1, day.year, day.year + 1}
    holidays: set[date] = set()
    for year in years:
        holidays.update(_nyse_holidays_for_year(year))
    return day in holidays


def _is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and not _is_nyse_holiday(day)


def _next_trading_day_after(day: date) -> date:
    candidate = day + timedelta(days=1)
    while not _is_trading_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def _session_datetime(day: date, at: time) -> datetime:
    return datetime(day.year, day.month, day.day, at.hour, at.minute, tzinfo=US_EASTERN_TZ)


def _classify_session(now_et: datetime) -> str:
    day = now_et.date()
    current_time = now_et.timetz().replace(tzinfo=None)

    if _is_trading_day(day):
        if SESSION_PREMARKET_START <= current_time < SESSION_REGULAR_START:
            return "premarket"
        if SESSION_REGULAR_START <= current_time < SESSION_REGULAR_END:
            return "regular"
        if SESSION_AFTERHOURS_START <= current_time < SESSION_AFTERHOURS_END:
            return "afterhours"
        return "overnight"

    if current_time >= SESSION_AFTERHOURS_END:
        if _next_trading_day_after(day) == day + timedelta(days=1):
            return "overnight"

    return "closed"


def _next_regular_open(now_et: datetime) -> datetime:
    today = now_et.date()
    if _is_trading_day(today) and now_et.timetz().replace(tzinfo=None) < SESSION_REGULAR_START:
        return _session_datetime(today, SESSION_REGULAR_START)
    return _session_datetime(_next_trading_day_after(today), SESSION_REGULAR_START)


def _next_extended_hours_opportunity(now_et: datetime, session_phase: str) -> datetime:
    today = now_et.date()
    if session_phase in {"premarket", "afterhours", "overnight"}:
        return now_et

    if _is_trading_day(today) and now_et.timetz().replace(tzinfo=None) < SESSION_AFTERHOURS_START:
        return _session_datetime(today, SESSION_AFTERHOURS_START)

    next_trading = _next_trading_day_after(today)
    return _session_datetime(next_trading, SESSION_PREMARKET_START)


def build_execution_guidance(
    *,
    user_timezone: str,
    preferred_order_type: str = "LIMIT",
    preferred_tif: str = "DAY",
    suggest_outside_rth: bool = True,
    now_utc: datetime | None = None,
) -> ExecutionGuidance:
    now_utc = now_utc or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    try:
        user_tz = ZoneInfo(user_timezone)
    except ZoneInfoNotFoundError as exc:  # pragma: no cover - configuration error
        raise ExecutionGuidanceError(f"Unknown user timezone: {user_timezone}") from exc

    market_time_et = now_utc.astimezone(US_EASTERN_TZ)
    user_time = market_time_et.astimezone(user_tz)
    session_phase = _classify_session(market_time_et)
    next_regular_open = _next_regular_open(market_time_et).astimezone(user_tz)
    next_extended_hours_opportunity = _next_extended_hours_opportunity(market_time_et, session_phase).astimezone(user_tz)

    can_submit_now = session_phase != "closed"
    can_likely_fill_now = session_phase in {"premarket", "regular", "afterhours"}

    warnings = [
        "常规时段前提交市价单风险较高，不建议作为新手默认选项。",
        "当日有效（DAY）并不代表永久有效。",
        "本项目不会自动下单，也不会代替你登录 IBKR。",
    ]
    if session_phase == "overnight":
        warnings.append("夜盘可交易性受标的与会话限制影响较大，不要默认认为所有品种都支持。")
    if session_phase == "closed":
        warnings.append("当前休市，订单可能会排队等待下一次可交易时段。")
    if session_phase != "regular":
        warnings.append("是否允许常规时段外成交，请以 IBKR 设置和标的支持情况为准。")

    notes = [
        "美国东部时间（US/Eastern）是本项目的基准交易时钟，展示时会转换到你配置的用户时区。",
        f"时间戳会按 {user_tz.key if hasattr(user_tz, 'key') else user_timezone} 显示，夏令时由 zoneinfo 自动处理。",
    ]

    return ExecutionGuidance(
        generated_at_utc=now_utc,
        user_timezone=user_timezone,
        user_time=user_time,
        market_time_et=market_time_et,
        session_phase=session_phase,
        can_submit_now=can_submit_now,
        can_likely_fill_now=can_likely_fill_now,
        next_regular_open=next_regular_open,
        next_extended_hours_opportunity=next_extended_hours_opportunity,
        preferred_order_type=preferred_order_type,
        preferred_tif=preferred_tif,
        suggest_outside_rth=suggest_outside_rth,
        warnings=tuple(warnings),
        notes=tuple(notes),
    )
