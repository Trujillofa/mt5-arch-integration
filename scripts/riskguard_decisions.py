#!/usr/bin/env python3
"""Pure RiskGuard decisions. Twin of ``mql5/Include/RiskGuardDecisions.mqh``.

No function here opens, closes, or modifies an order. Stdlib only, so
``uv run pytest`` can pin the rules without a terminal.

``required_stop`` uses Python ``round`` as the stand-in for MQL
``NormalizeDouble`` on prices that are already on the digit grid. Halfway
prices are not part of the pinned oracle.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Sequence

# MQL5 ENUM_DEAL_TYPE values used by the daily sum.
DEAL_TYPE_BUY = 0
DEAL_TYPE_SELL = 1
DEAL_TYPE_BALANCE = 2

DealRow = tuple[int, float, float, float]
# profit, swap, open time in seconds
PositionRow = tuple[float, float, int]
# ticket, volume, setup time in milliseconds
PendingRow = tuple[int, float, int]


class VolumeAction(enum.Enum):
    """What to do with one position's volume. ``lots`` is set only for ``PARTIAL``."""

    OK = "ok"
    PARTIAL = "partial"
    CLOSE = "close"
    SKIP = "skip"


def normalize_volume(volume: float, step: float, volume_min: float) -> float | None:
    """Floor ``volume`` to ``step``. Return 0 when the result is below ``volume_min``.

    A non-positive step is missing symbol info. Return None instead of inventing 0.01.
    """
    if step <= 0.0:
        return None
    floored = math.floor(volume / step + 1e-9) * step
    if floored < volume_min - 1e-9:
        return 0.0
    digits = int(max(0.0, math.ceil(-math.log10(step))))
    return round(floored, digits)


def volume_decision(
    volume: float,
    max_lots: float,
    step: float,
    volume_min: float,
) -> tuple[VolumeAction, float]:
    """Partial-close lots, or close the position when the excess is below one step.

    ``SKIP`` means the volume step is unusable. ``OK`` means the position is inside
    the cap. A sub-step overage (0.025 against a 0.02 cap with a 0.01 step) is
    ``CLOSE``: the cap cannot be reached by a legal partial close.
    """
    if step <= 0.0:
        return (VolumeAction.SKIP, 0.0)
    if not volume > max_lots + 1e-8:
        return (VolumeAction.OK, 0.0)
    excess = normalize_volume(volume - max_lots, step, volume_min)
    if excess is None:
        return (VolumeAction.SKIP, 0.0)
    if excess > 0.0:
        return (VolumeAction.PARTIAL, excess)
    return (VolumeAction.CLOSE, 0.0)


def required_stop(
    is_buy: bool,
    open_price: float,
    distance_points: int,
    point: float,
    digits: int,
) -> float | None:
    """Buy stop is ``open - points * point``. Sell stop is ``open + points * point``.

    None when ``point`` is not a real price increment. The distance is in points
    so one input scales with the symbol instead of a single price-unit gap.
    """
    if point <= 0.0 or distance_points < 0:
        return None
    distance = distance_points * point
    raw = open_price - distance if is_buy else open_price + distance
    return round(raw, digits)


def stop_needs_fix(is_buy: bool, current_sl: float, required: float, point: float) -> bool:
    """True when the stop is missing or wider than ``required`` by more than half a point."""
    if current_sl == 0.0:
        return True
    if is_buy:
        return current_sl < required - point / 2
    return current_sl > required + point / 2


def quote_usable(is_buy: bool, bid: float, ask: float, point: float) -> bool:
    """False when a zero quote or a zero point would be treated as a real price."""
    if point <= 0.0:
        return False
    if is_buy:
        return bid > 0.0
    return ask > 0.0


def stop_already_through(
    is_buy: bool,
    required: float,
    bid: float,
    ask: float,
    min_gap: float,
) -> bool:
    """True when the required stop is already through the market plus the stops level.

    Buy compares ``required >= bid - min_gap``. Sell compares ``required <= ask + min_gap``.
    Call this only after ``quote_usable`` is true.
    """
    if is_buy:
        return required >= bid - min_gap
    return required <= ask + min_gap


def newest_ticket(rows: Sequence[tuple[int, int]]) -> int:
    """Ticket with the greatest ``time_msc``.

    ``rows`` are ``(ticket, time_msc)`` in position-index order, low index first.
    The scan walks from the high index down and replaces only on a strict ``>``,
    so a time tie keeps the higher index. Ticket 0 is skipped. No row yields 0.
    """
    newest = 0
    newest_time = 0
    for ticket, time_msc in reversed(tuple(rows)):
        if ticket == 0:
            continue
        if time_msc > newest_time:
            newest = ticket
            newest_time = time_msc
    return newest


def lock_until(day_start: int, now: int, lock_min_hours: int) -> int:
    """Later of the next server midnight and ``now + lock_min_hours``.

    Both inputs are seconds. A tie stores ``now + lock_min_hours``, which is
    the same instant as ``day_start + 86400``.
    """
    next_day = day_start + 86400
    min_end = now + lock_min_hours * 3600
    if next_day > min_end:
        return next_day
    return min_end


def deal_contribution(deal_type: int, profit: float, swap: float, commission: float) -> float:
    """Profit + swap + commission for a buy or sell deal. Every other deal type adds 0."""
    if deal_type != DEAL_TYPE_BUY and deal_type != DEAL_TYPE_SELL:
        return 0.0
    return profit + swap + commission


def position_counts_today(open_time: int, day_start: int) -> bool:
    """An overnight position does not contribute its lifetime floating P/L to today."""
    return open_time >= day_start


def daily_pl(
    deals: Sequence[DealRow],
    positions: Sequence[PositionRow],
    *,
    history_ok: bool,
    day_start: int,
) -> float | None:
    """Today's buy/sell deal P/L plus floating P/L of positions opened today.

    None when history could not be read. That is not a day of zero realized P/L,
    and the lock must not use it. Positions opened before ``day_start`` are
    omitted; their result enters on the day the closing deal is in history.
    This is not equity minus a stored day-start balance.
    """
    if not history_ok:
        return None
    total = 0.0
    for deal_type, profit, swap, commission in deals:
        total += deal_contribution(deal_type, profit, swap, commission)
    for profit, swap, open_time in positions:
        if position_counts_today(open_time, day_start):
            total += profit + swap
    return total


def pendings_to_delete(
    positions: int,
    max_positions: int,
    max_lots: float,
    pendings: Sequence[PendingRow],
) -> list[int]:
    """Unlocked pending tickets to delete.

    An oversized pending always goes. Of the rest, keep the oldest up to
    ``max(0, max_positions - positions)`` slots. Oldest is the smaller setup
    time. A time tie keeps the lower index. Ticket 0 is ignored.

    The locked path does not use this. A lock deletes every pending, because
    the guard flattens after the fact and does not block new orders.
    """
    slots = max(0, max_positions - positions)
    drop: list[int] = []
    for index, (ticket, volume, time_msc) in enumerate(pendings):
        if ticket == 0:
            continue
        if volume > max_lots + 1e-8:
            drop.append(ticket)
            continue
        older = 0
        for other, (other_ticket, other_volume, other_time) in enumerate(pendings):
            if other == index or other_ticket == 0:
                continue
            if other_volume > max_lots + 1e-8:
                continue
            if other_time < time_msc or (other_time == time_msc and other < index):
                older += 1
        if older >= slots:
            drop.append(ticket)
    return drop
