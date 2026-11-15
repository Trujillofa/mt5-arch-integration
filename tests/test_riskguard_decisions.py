"""Off-terminal pins for the RiskGuard decisions.

Step 2 rules, driven through ``scripts/riskguard_decisions.py``:

* sub-step overage closes the position
* stop distance is points times the symbol point
* a failed history read is not a day profit figure
* overnight floating P/L stays out of today
* unlocked pendings keep only the oldest slots under the position cap
* a zero quote is not a usable price

This does not compile, attach, or send an order.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import riskguard_decisions as rg  # noqa: E402

BUY = rg.DEAL_TYPE_BUY
SELL = rg.DEAL_TYPE_SELL
BALANCE = rg.DEAL_TYPE_BALANCE
DAY = 1_000_000_000


def _between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


def test_normalize_volume_floors_and_rejects_below_min() -> None:
    assert rg.normalize_volume(0.019, 0.01, 0.01) == 0.01
    assert rg.normalize_volume(0.03, 0.01, 0.01) == 0.03
    assert rg.normalize_volume(0.009, 0.01, 0.01) == 0.0
    assert rg.normalize_volume(0.005, 0.01, 0.01) == 0.0
    assert rg.normalize_volume(0.05, 0.01, 0.10) == 0.0
    assert rg.normalize_volume(0.015, 0.01, 0.01) == 0.01
    assert rg.normalize_volume(0.025, 0.0, 0.01) is None


def test_volume_decision_closes_a_sub_step_overage() -> None:
    assert rg.volume_decision(0.05, 0.02, 0.01, 0.01) == (rg.VolumeAction.PARTIAL, 0.03)
    assert rg.volume_decision(0.035, 0.02, 0.01, 0.01) == (rg.VolumeAction.PARTIAL, 0.01)
    assert rg.volume_decision(0.025, 0.02, 0.01, 0.01) == (rg.VolumeAction.CLOSE, 0.0)
    assert rg.volume_decision(0.02000002, 0.02, 0.01, 0.01) == (rg.VolumeAction.CLOSE, 0.0)
    assert rg.volume_decision(0.02, 0.02, 0.01, 0.01) == (rg.VolumeAction.OK, 0.0)
    assert rg.volume_decision(0.05, 0.02, 0.0, 0.01) == (rg.VolumeAction.SKIP, 0.0)


def test_required_stop_uses_points() -> None:
    assert rg.required_stop(True, 2650.37, 1000, 0.01, 2) == 2640.37
    assert rg.required_stop(False, 2650.37, 1000, 0.01, 2) == 2660.37
    assert rg.required_stop(True, 1.08500, 1000, 0.00001, 5) == 1.07500
    assert rg.required_stop(True, 60000.00, 1000, 0.01, 2) == 59990.0
    assert rg.required_stop(True, 2650.37, 1000, 0.0, 2) is None


def test_stop_needs_fix_half_point_band() -> None:
    buy = 2640.37
    sell = 2660.37
    point = 0.01
    assert rg.stop_needs_fix(True, 0.0, buy, point) is True
    assert rg.stop_needs_fix(True, 2640.36, buy, point) is True
    assert rg.stop_needs_fix(True, 2640.37, buy, point) is False
    assert rg.stop_needs_fix(True, 2645.00, buy, point) is False
    assert rg.stop_needs_fix(True, 2660.00, buy, point) is False
    assert rg.stop_needs_fix(False, 0.0, sell, point) is True
    assert rg.stop_needs_fix(False, 2660.38, sell, point) is True
    assert rg.stop_needs_fix(False, 2660.37, sell, point) is False
    assert rg.stop_needs_fix(False, 2655.00, sell, point) is False
    assert rg.stop_needs_fix(False, 2640.00, sell, point) is False


def test_zero_quote_is_not_usable() -> None:
    assert rg.quote_usable(True, 0.0, 2650.0, 0.01) is False
    assert rg.quote_usable(False, 2650.0, 0.0, 0.01) is False
    assert rg.quote_usable(True, 2640.50, 2640.65, 0.0) is False
    assert rg.quote_usable(True, 2640.50, 2640.65, 0.01) is True
    assert rg.quote_usable(False, 2660.10, 2660.30, 0.01) is True


def test_already_through_matches_evaluated_doubles() -> None:
    buy = 2640.37
    sell = 2660.37
    gap = 0.20
    assert rg.stop_already_through(True, buy, 2652.10, 2652.25, gap) is False
    assert rg.stop_already_through(True, buy, 2640.50, 2640.65, gap) is True
    assert rg.stop_already_through(True, buy, 2640.57, 2640.70, gap) is False
    assert rg.stop_already_through(False, sell, 2654.80, 2655.00, gap) is False
    assert rg.stop_already_through(False, sell, 2660.10, 2660.30, gap) is True
    assert rg.stop_already_through(False, sell, 2660.00, 2660.17, gap) is True
    assert rg.stop_already_through(True, buy, buy, 0.0, 0.0) is True
    assert rg.stop_already_through(False, sell, 0.0, sell, 0.0) is True


def test_newest_ticket_breaks_time_ties_toward_the_higher_index() -> None:
    rows = [(101, 1000), (102, 3000), (103, 3000), (104, 2000)]
    assert rg.newest_ticket(rows) == 103
    assert rg.newest_ticket([]) == 0
    assert rg.newest_ticket([(0, 9_999_999), (101, 1000)]) == 101


def test_lock_until_takes_the_later_deadline() -> None:
    midnight = 1_000_000_000
    ten = midnight + 10 * 3600
    eighteen_thirty = midnight + 18 * 3600 + 30 * 60
    noon = midnight + 12 * 3600
    assert rg.lock_until(midnight, ten, 12) == midnight + 86400
    assert rg.lock_until(midnight, eighteen_thirty, 12) == eighteen_thirty + 12 * 3600
    assert noon + 12 * 3600 == midnight + 86400
    assert rg.lock_until(midnight, noon, 12) == midnight + 86400


def test_daily_pl_skips_overnight_floating_and_balance_deals() -> None:
    deals = (
        (BUY, 0.0, 0.0, -0.06),
        (SELL, -12.50, -0.40, -0.06),
        (BALANCE, 100.0, 0.0, 0.0),
    )
    positions = (
        (-15.00, -0.20, DAY - 1),
        (3.00, 0.0, DAY + 60),
    )
    assert rg.daily_pl(deals, positions, history_ok=True, day_start=DAY) == pytest.approx(-10.02)
    opened_at_midnight = ((-15.00, -0.20, DAY),)
    assert rg.daily_pl((), opened_at_midnight, history_ok=True, day_start=DAY) == pytest.approx(
        -15.20
    )


def test_failed_history_is_not_a_day_figure() -> None:
    hidden = ((SELL, -30.00, -1.00, -0.10),)
    hidden_pos = ((-9.00, -0.50, DAY + 60),)
    assert rg.daily_pl(hidden, hidden_pos, history_ok=True, day_start=DAY) == pytest.approx(-40.60)
    assert rg.daily_pl(hidden, hidden_pos, history_ok=False, day_start=DAY) is None

    false_trip = ((SELL, 20.30, 0.0, -0.30),)
    false_pos = ((-50.00, 0.0, DAY + 60),)
    assert rg.daily_pl(false_trip, false_pos, history_ok=True, day_start=DAY) == pytest.approx(
        -30.00
    )
    assert rg.daily_pl(false_trip, false_pos, history_ok=False, day_start=DAY) is None
    overnight = ((-55.0, -1.0, DAY - 10),)
    assert rg.daily_pl((), overnight, history_ok=True, day_start=DAY) == pytest.approx(0.0)


def test_unlocked_pendings_keep_the_oldest_free_slots() -> None:
    pendings = (
        (11, 0.01, 100),
        (12, 0.03, 50),
        (13, 0.02, 200),
        (14, 0.02, 100),
        (0, 1.00, 1),
    )
    assert rg.pendings_to_delete(1, 2, 0.02, pendings) == [12, 13, 14]
    assert rg.pendings_to_delete(2, 2, 0.02, pendings) == [11, 12, 13, 14]
    assert rg.pendings_to_delete(0, 2, 0.02, pendings) == [12, 13]


def test_expert_wires_the_decisions_without_sending_from_the_handler() -> None:
    expert = (_ROOT / "mql5" / "Experts" / "RiskGuard.mq5").read_text(encoding="utf-8")
    header = (_ROOT / "mql5" / "Include" / "RiskGuardDecisions.mqh").read_text(encoding="utf-8")
    assert "#include <RiskGuardDecisions.mqh>" in expert
    for call in (
        "DecideVolume(",
        "RequiredStop(",
        "StopNeedsFix(",
        "StopAlreadyThrough(",
        "QuoteUsable(",
        "ConsiderPosition(",
        "LockDeadline(",
        "DealContribution(",
        "FloatingPL(",
        "PositionCountsToday(",
        "MarkPendingsToDelete(",
        "SymbolSelect(sym, true)",
        "TryClose(",
        "TryClosePartial(",
        "TryModify(",
        "TryDelete(",
    ):
        assert call in expert
    assert "InpMaxSLPoints" in expert
    assert "InpMaxSLDistance" not in expert
    assert "step = 0.01" not in header
    assert "step = 0.01" not in expert
    assert "MathFloor(volume / step + 1e-9) * step" in header
    assert "volume > maxLots + 1e-8" in header
    assert "distancePoints * point" in header
    assert "isBuy ? openPrice - distance : openPrice + distance" in header
    assert "required >= bid - minGap" in header
    assert "required <= ask + minGap" in header
    assert "timeMsc > newestTime" in header
    assert "nextDay > minEnd" in header
    assert "dayStart + 86400" in header
    assert "openTime >= dayStart" in header
    assert "older >= slots" in header
    assert "DEAL_TYPE_BUY" in header and "DEAL_TYPE_SELL" in header
    assert "OrderSend" not in header
    assert "CTrade" not in header
    assert "SymbolInfoDouble" not in header

    handler = _between(expert, "void OnTradeTransaction", "void OnTimer")
    assert "Enforce()" not in handler
    assert "g_tradeArrived = true" in handler
    timer = _between(expert, "void OnTimer", "void Enforce")
    assert "Enforce()" in timer
    assert "RG_ATTEMPTS" in expert

    per_position = _between(expert, "void EnforcePerPosition", "void EnsureStop")
    assert "stop is checked on the next pass" not in per_position
    assert per_position.index("PrepareSymbol(") < per_position.index("SymbolInfoDouble(")
    assert per_position.index("DecideVolume(") < per_position.index("EnsureStop(")

    ensure = _between(expert, "void EnsureStop", "void EnforceMaxPositions")
    assert ensure.index("PrepareSymbol(") < ensure.index("SymbolInfoDouble(")
    assert ensure.index("QuoteUsable(") < ensure.index("StopAlreadyThrough(")

    daily = _between(expert, "bool DailyPL", "datetime DayStart")
    assert daily.index("return false") < daily.index("PositionCountsToday(")
