from __future__ import annotations

from datetime import datetime, timezone

from dca_signal_bot.execution_guidance import build_execution_guidance


def test_execution_guidance_detects_regular_session():
    guidance = build_execution_guidance(
        user_timezone="Asia/Tokyo",
        now_utc=datetime(2026, 3, 30, 14, 0, tzinfo=timezone.utc),
    )

    assert guidance.session_phase == "regular"
    assert guidance.can_submit_now is True
    assert guidance.can_likely_fill_now is True
    assert guidance.next_regular_open.strftime("%Y-%m-%d %H:%M %Z") == "2026-03-31 22:30 JST"
    assert guidance.next_extended_hours_opportunity.strftime("%Y-%m-%d %H:%M %Z") == "2026-03-31 05:00 JST"


def test_execution_guidance_detects_premarket_session():
    guidance = build_execution_guidance(
        user_timezone="Asia/Tokyo",
        now_utc=datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc),
    )

    assert guidance.session_phase == "premarket"
    assert guidance.can_submit_now is True
    assert guidance.can_likely_fill_now is True


def test_execution_guidance_detects_afterhours_session():
    guidance = build_execution_guidance(
        user_timezone="Asia/Tokyo",
        now_utc=datetime(2026, 3, 30, 21, 0, tzinfo=timezone.utc),
    )

    assert guidance.session_phase == "afterhours"
    assert guidance.can_submit_now is True
    assert guidance.can_likely_fill_now is True
    assert guidance.next_extended_hours_opportunity.strftime("%Y-%m-%d %H:%M %Z") == "2026-03-31 06:00 JST"


def test_execution_guidance_detects_overnight_session():
    guidance = build_execution_guidance(
        user_timezone="Asia/Tokyo",
        now_utc=datetime(2026, 3, 31, 1, 0, tzinfo=timezone.utc),
    )

    assert guidance.session_phase == "overnight"
    assert guidance.can_submit_now is True
    assert guidance.can_likely_fill_now is False


def test_execution_guidance_detects_weekend_and_holiday_closed_sessions():
    weekend_guidance = build_execution_guidance(
        user_timezone="Asia/Tokyo",
        now_utc=datetime(2026, 3, 28, 16, 0, tzinfo=timezone.utc),
    )
    holiday_guidance = build_execution_guidance(
        user_timezone="Asia/Tokyo",
        now_utc=datetime(2026, 7, 3, 15, 0, tzinfo=timezone.utc),
    )

    assert weekend_guidance.session_phase == "closed"
    assert weekend_guidance.can_submit_now is False
    assert weekend_guidance.can_likely_fill_now is False
    assert holiday_guidance.session_phase == "closed"
    assert holiday_guidance.can_submit_now is False
    assert holiday_guidance.can_likely_fill_now is False


def test_execution_guidance_handles_dst_shift_for_display_timezone():
    before_dst = build_execution_guidance(
        user_timezone="Asia/Tokyo",
        now_utc=datetime(2026, 3, 6, 14, 0, tzinfo=timezone.utc),
    )
    after_dst = build_execution_guidance(
        user_timezone="Asia/Tokyo",
        now_utc=datetime(2026, 3, 9, 13, 0, tzinfo=timezone.utc),
    )

    assert before_dst.next_regular_open.strftime("%H:%M %Z") == "23:30 JST"
    assert after_dst.next_regular_open.strftime("%H:%M %Z") == "22:30 JST"
