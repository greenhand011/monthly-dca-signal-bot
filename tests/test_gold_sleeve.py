from __future__ import annotations

from datetime import date

import pandas as pd

from dca_signal_bot.config import GoldSleeveConfig
from dca_signal_bot.gold_sleeve import GoldSleeveDecision, GoldSleeveIndicatorSnapshot, evaluate_gold_sleeve


def _gold_config(**overrides) -> GoldSleeveConfig:
    base = GoldSleeveConfig(
        enabled=True,
        ticker="GLDM",
        target_weight=0.03,
        max_weight=0.05,
        monthly_check_enabled=True,
        buy_score_threshold=3.0,
        full_rebalance_months=6,
        current_total_portfolio_value_rmb=100_000,
        current_gold_value_rmb=1_000,
        emergency_fund_ok=True,
        dxy_ticker="DXY",
        vix_ticker="^VIX",
        spy_ticker="SPY",
        real_yield_ticker="REALYIELD",
    )
    return GoldSleeveConfig(**{**base.__dict__, **overrides})


def _snapshot(
    *,
    rsi14: float = 50.0,
    sma200: float = 100.0,
    current_price: float = 100.0,
    distance_from_60d_high: float = 0.05,
    drawdown_from_120d_high: float = 0.10,
    return_20d: float = 0.02,
) -> GoldSleeveIndicatorSnapshot:
    return GoldSleeveIndicatorSnapshot(
        ticker="GLDM",
        latest_market_date=date(2026, 4, 20),
        current_price=current_price,
        sma200=sma200,
        rsi14=rsi14,
        high_60d=105.0,
        high_120d=111.0,
        distance_from_60d_high=distance_from_60d_high,
        drawdown_from_120d_high=drawdown_from_120d_high,
        return_20d=return_20d,
    )


def _history(prices: list[float], ticker: str = "TICKER") -> pd.DataFrame:
    idx = pd.date_range(end="2026-04-20", periods=len(prices), freq="B")
    return pd.DataFrame({"close": pd.Series(prices, index=idx, dtype=float)})


def _macro_lookup_factory(data: dict[str, pd.DataFrame], errors: dict[str, str] | None = None):
    errors = errors or {}

    def _lookup(ticker: str | None, *, reference_date, min_rows):  # noqa: ANN001
        _ = (reference_date, min_rows)
        if ticker is None:
            return None, None
        if ticker in errors:
            return None, errors[ticker]
        return data.get(ticker), None

    return _lookup


def test_gold_no_buy_when_current_weight_at_or_above_target(monkeypatch):
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_required_history", lambda *args, **kwargs: pd.DataFrame({"close": [1.0]}))
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._build_gold_indicator_snapshot", lambda *args, **kwargs: _snapshot())

    decision = evaluate_gold_sleeve(
        _gold_config(current_gold_value_rmb=3_500),
        reference_date=date(2026, 4, 21),
    )

    assert decision.should_buy is False
    assert decision.recommended_buy_rmb == 0
    assert "达到或超过目标配置" in decision.reason


def test_gold_no_buy_when_overheat_filter_triggers(monkeypatch):
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_required_history", lambda *args, **kwargs: pd.DataFrame({"close": [1.0]}))
    monkeypatch.setattr(
        "dca_signal_bot.gold_sleeve._build_gold_indicator_snapshot",
        lambda *args, **kwargs: _snapshot(rsi14=75.0, distance_from_60d_high=0.02, return_20d=0.10),
    )

    decision = evaluate_gold_sleeve(
        _gold_config(),
        reference_date=date(2026, 4, 21),
    )

    assert decision.should_buy is False
    assert decision.overheat_triggered is True
    assert any("RSI(14)" in reason for reason in decision.overheat_reasons)


def test_gold_buy_size_is_zero_when_score_below_threshold(monkeypatch):
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_required_history", lambda *args, **kwargs: pd.DataFrame({"close": [1.0]}))
    monkeypatch.setattr(
        "dca_signal_bot.gold_sleeve._build_gold_indicator_snapshot",
        lambda *args, **kwargs: _snapshot(rsi14=65.0, current_price=110.0, sma200=100.0, drawdown_from_120d_high=0.09),
    )
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_optional_history", _macro_lookup_factory({}, {}))

    decision = evaluate_gold_sleeve(_gold_config(), reference_date=date(2026, 4, 21))

    assert decision.total_score == 2.0
    assert decision.recommended_buy_rmb == 0


def test_gold_buy_size_is_25_percent_of_target_gap_for_score_3_or_4(monkeypatch):
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_required_history", lambda *args, **kwargs: pd.DataFrame({"close": [1.0]}))
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._build_gold_indicator_snapshot", lambda *args, **kwargs: _snapshot())
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_optional_history", _macro_lookup_factory({}, {}))

    decision = evaluate_gold_sleeve(_gold_config(), reference_date=date(2026, 4, 21))

    assert decision.total_score == 4.0
    assert decision.target_gap_value_rmb == 2_000
    assert decision.recommended_buy_rmb == 500


def test_gold_buy_size_is_50_percent_of_target_gap_for_score_5_or_6(monkeypatch):
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_required_history", lambda *args, **kwargs: pd.DataFrame({"close": [1.0]}))
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._build_gold_indicator_snapshot", lambda *args, **kwargs: _snapshot())
    macro_data = {
        "DXY": _history([100.0] * 40 + [99.0] * 21, "DXY"),
    }
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_optional_history", _macro_lookup_factory(macro_data, {}))

    decision = evaluate_gold_sleeve(_gold_config(), reference_date=date(2026, 4, 21))

    assert decision.total_score == 5.0
    assert decision.recommended_buy_rmb == 1_000


def test_gold_buy_size_is_full_target_gap_for_score_at_or_above_7(monkeypatch):
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_required_history", lambda *args, **kwargs: pd.DataFrame({"close": [1.0]}))
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._build_gold_indicator_snapshot", lambda *args, **kwargs: _snapshot())
    macro_data = {
        "DXY": _history([100.0] * 40 + [99.0] * 21, "DXY"),
        "REALYIELD": _history([2.2] * 21 + [2.0] * 21, "REALYIELD"),
        "^VIX": _history([18.0] * 60 + [22.0], "^VIX"),
        "SPY": _history([500.0] * 60 + [450.0], "SPY"),
    }
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_optional_history", _macro_lookup_factory(macro_data, {}))

    decision = evaluate_gold_sleeve(
        _gold_config(central_bank_support=0.5, gold_etf_flow_support=0.5),
        reference_date=date(2026, 4, 21),
    )

    assert decision.total_score == 7.0
    assert decision.recommended_buy_rmb == 2_000
    assert decision.projected_gold_weight_after_buy <= decision.max_gold_weight


def test_gold_buy_size_is_based_on_target_gap_not_fixed_amount(monkeypatch):
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_required_history", lambda *args, **kwargs: pd.DataFrame({"close": [1.0]}))
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._build_gold_indicator_snapshot", lambda *args, **kwargs: _snapshot())
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_optional_history", _macro_lookup_factory({}, {}))

    decision_small_gap = evaluate_gold_sleeve(
        _gold_config(current_gold_value_rmb=2_000),
        reference_date=date(2026, 4, 21),
    )
    decision_large_gap = evaluate_gold_sleeve(
        _gold_config(current_gold_value_rmb=0),
        reference_date=date(2026, 4, 21),
    )

    assert decision_small_gap.target_gap_value_rmb == 1_000
    assert decision_small_gap.recommended_buy_rmb == 250
    assert decision_large_gap.target_gap_value_rmb == 3_000
    assert decision_large_gap.recommended_buy_rmb == 750


def test_gold_optional_macro_inputs_can_be_unavailable_without_crashing(monkeypatch):
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._fetch_required_history", lambda *args, **kwargs: pd.DataFrame({"close": [1.0]}))
    monkeypatch.setattr("dca_signal_bot.gold_sleeve._build_gold_indicator_snapshot", lambda *args, **kwargs: _snapshot())
    monkeypatch.setattr(
        "dca_signal_bot.gold_sleeve._fetch_optional_history",
        _macro_lookup_factory({}, {"DXY": "DXY failed", "REALYIELD": "real yield failed", "^VIX": "vix failed", "SPY": "spy failed"}),
    )

    decision = evaluate_gold_sleeve(_gold_config(), reference_date=date(2026, 4, 21))

    assert isinstance(decision, GoldSleeveDecision)
    assert decision.validation_status == "PASS"
    assert decision.optional_data_notes
    assert decision.recommended_buy_rmb == 500
