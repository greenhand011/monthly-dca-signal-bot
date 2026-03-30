from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from dca_signal_bot import fx_converter
from dca_signal_bot.fx_converter import FxConversionError, build_fx_conversion_summary, convert_rmb_to_usd


def _fx_history(rate: float) -> pd.DataFrame:
    idx = pd.date_range(end="2026-03-30", periods=8, freq="B")
    close = pd.Series([rate] * len(idx), index=idx, dtype=float)
    return pd.DataFrame({"Close": close})


def test_fx_conversion_math_is_correct_for_cny_per_usd(monkeypatch):
    monkeypatch.setattr(fx_converter, "_fetch_fx_history", lambda *args, **kwargs: _fx_history(7.2))

    summary = build_fx_conversion_summary(
        total_rmb=3000,
        core_rmb=2550,
        growth_rmb=450,
        reference_date=pd.Timestamp("2026-03-30").date(),
        fetched_at_utc=datetime(2026, 3, 30, 6, 55, 40, tzinfo=timezone.utc),
    )

    assert summary.validation_status == "PASS"
    assert summary.rate_cny_per_usd == 7.2
    assert summary.total_usd == 416.67
    assert summary.core_usd == 354.17
    assert summary.growth_usd == 62.5
    assert convert_rmb_to_usd(720, 7.2) == 100.0


def test_fx_failure_does_not_fabricate_usd_values(monkeypatch):
    def fake_history(*args, **kwargs):
        raise FxConversionError("CNY=X: failed to fetch FX data from Yahoo Finance")

    monkeypatch.setattr(fx_converter, "_fetch_fx_history", fake_history)

    summary = build_fx_conversion_summary(
        total_rmb=3000,
        core_rmb=2550,
        growth_rmb=450,
        reference_date=pd.Timestamp("2026-03-30").date(),
        fetched_at_utc=datetime(2026, 3, 30, 6, 55, 40, tzinfo=timezone.utc),
    )

    assert summary.validation_status == "FAIL"
    assert summary.rate_cny_per_usd is None
    assert summary.total_usd is None
    assert summary.core_usd is None
    assert summary.growth_usd is None
    assert "USD estimate unavailable" in summary.note
