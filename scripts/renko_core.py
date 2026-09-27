#!/usr/bin/env python3
"""Fixed-brick Renko event clock with ADX/DI and Bollinger stacks (offline research).

Independent Python port of the three classes shared by the two vendored MQL5
experts under ``mql5/Experts/vendor/`` (see that directory's ``PROVENANCE.md``):

* ``CRenkoBuilder``   -> :class:`RenkoBuilder`
* ``CRenkoADX``       -> :class:`RenkoADX`
* ``CRenkoBollinger`` -> :class:`RenkoBollinger`

CRITICAL causality rule
-----------------------
A Renko brick is **not knowable** until price has travelled a full brick from the
previous brick close. Every brick this module emits is stamped at the moment of
*completion*, and indicator state advances only on completed bricks — never on the
brick currently forming. This is the event-clock analogue of the pivot-confirmation
rule in ``scripts/htf_fib_core.py``: consumers must import from here rather than
re-deriving brick boundaries, because re-deriving them is how look-ahead gets back in.

Fidelity note
-------------
The vendor experts consume a live BID tick stream. Offline we have OHLC bars, so
an intrabar path has to be assumed; see :func:`bar_path`. That assumption is a
declared model, not a fact, and the screen that uses this module is required by
charter to report both conventions.

Stdlib only, deliberately: brick construction is inherently sequential, numpy buys
nothing, and the repo's declared dependency set does not carry numpy for ``uv run``.

SAFETY: offline research only. Nothing here places, sizes or simulates an order
against a live account.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import IntEnum

__all__ = [
    "BB_MODES",
    "BollingerMode",
    "Brick",
    "PATH_CONVENTIONS",
    "RenkoBollinger",
    "RenkoBuilder",
    "RenkoOverflowError",
    "RenkoADX",
    "bar_path",
    "bricks_from_bars",
    "size_in_tick_units",
]

# Mirrors ``const int MAX_BRICKS_PER_TICK=4096`` in both vendor sources. A push
# that would emit more than this fails closed: the vendor EA pauses new entries
# and keeps exits live rather than materialising a huge brick run from one gap.
MAX_BRICKS_PER_PUSH = 4096


class RenkoOverflowError(RuntimeError):
    """A single price push would emit more than :data:`MAX_BRICKS_PER_PUSH` bricks."""


@dataclass(frozen=True, slots=True)
class Brick:
    """One completed Renko brick.

    ``run`` is the count of consecutive bricks in ``direction`` including this one,
    matching ``SRenkoBrick.run``. Synthetic OHLC for indicator purposes is
    ``high = max(open, close)``, ``low = min(open, close)`` — a brick has no wick.
    """

    open: float
    close: float
    direction: int  # +1 up, -1 down
    run: int

    @property
    def high(self) -> float:
        return max(self.open, self.close)

    @property
    def low(self) -> float:
        return min(self.open, self.close)


def size_in_tick_units(brick_size: float, tick_size: float) -> int:
    """Quantize a brick size in price units to whole ticks, as ``OnInit`` does.

    The vendor rejects a brick smaller than half a tick or absurdly large, then
    rounds to at least one tick. Working in integer tick space is what keeps brick
    boundaries exact over long runs instead of accumulating float drift.
    """
    if not math.isfinite(brick_size) or brick_size <= 0.0:
        raise ValueError(f"brick_size must be finite and positive, got {brick_size!r}")
    if not math.isfinite(tick_size) or tick_size <= 0.0:
        raise ValueError(f"tick_size must be finite and positive, got {tick_size!r}")
    raw = brick_size / tick_size
    if not math.isfinite(raw) or raw < 0.5 or raw > 1e9:
        raise ValueError(f"brick size {brick_size} cannot be represented at tick {tick_size}")
    return max(1, int(round(raw)))


class RenkoBuilder:
    """Classic fixed-size Renko with the two-brick reversal rule.

    Port of ``CRenkoBuilder``. Prices are quantized to integer tick units on entry;
    all brick arithmetic is integer. The first price only anchors the series and
    emits nothing.
    """

    __slots__ = ("_anchored", "_close", "_dir", "_run", "_size", "_tick_size")

    def __init__(self, tick_size: float, size_units: int) -> None:
        if size_units < 1:
            raise ValueError(f"size_units must be >= 1, got {size_units}")
        self._tick_size = float(tick_size)
        self._size = int(size_units)
        self._close = 0
        self._dir = 0
        self._run = 0
        self._anchored = False

    @property
    def brick_size(self) -> float:
        """Effective brick size in price units after tick quantization."""
        return self._size * self._tick_size

    @property
    def direction(self) -> int:
        return self._dir

    def push_price(self, price: float) -> list[Brick]:
        """Feed one price. Returns the bricks completed by it, oldest first."""
        p = int(round(price / self._tick_size))
        if not self._anchored:
            self._close = p
            self._anchored = True
            return []

        delta = p - self._close
        size = self._size
        direction = self._dir
        count = 0
        reversal = False

        if self._dir == 0:
            if delta >= size:
                direction, count = 1, delta // size
            elif delta <= -size:
                direction, count = -1, (-delta) // size
        elif self._dir > 0:
            if delta >= size:
                count = delta // size
            elif delta <= -2 * size:
                # Two full bricks against trend are spent turning the series
                # around; only the excess prints, and the first printed brick
                # opens one brick away from the previous close.
                direction, reversal = -1, True
                count = (-delta) // size - 1
        else:
            if delta <= -size:
                count = (-delta) // size
            elif delta >= 2 * size:
                direction, reversal = 1, True
                count = delta // size - 1

        if count > MAX_BRICKS_PER_PUSH:
            raise RenkoOverflowError(
                f"{count} bricks from one push exceeds the {MAX_BRICKS_PER_PUSH} cap"
            )
        if count == 0:
            return []

        out: list[Brick] = []
        for i in range(count):
            open_units = self._close + (direction * size if (reversal and i == 0) else 0)
            self._close = open_units + direction * size
            if direction == self._dir:
                self._run += 1
            else:
                self._dir = direction
                self._run = 1
            out.append(
                Brick(
                    open=open_units * self._tick_size,
                    close=self._close * self._tick_size,
                    direction=direction,
                    run=self._run,
                )
            )
        return out


class RenkoADX:
    """Wilder ADX / +DI / -DI fed completed bricks only.

    Port of ``CRenkoADX``. Note these values are **not** comparable to ADX on a time
    chart: a brick's high-low range is constant by construction, so true range and
    the directional movements live on a different scale. The vendor's entry
    threshold of 8.5 is a brick-clock number, not a mis-typed 25.
    """

    __slots__ = (
        "_adx",
        "_dx_count",
        "_dx_sum",
        "_have_prev",
        "_minus_di",
        "_period",
        "_plus_di",
        "_prev_close",
        "_prev_high",
        "_prev_low",
        "_ready",
        "_sm_minus_dm",
        "_sm_plus_dm",
        "_sm_tr",
        "_tr_count",
    )

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError(f"period must be >= 1, got {period}")
        self._period = int(period)
        self._tr_count = 0
        self._dx_count = 0
        self._have_prev = False
        self._ready = False
        self._prev_high = 0.0
        self._prev_low = 0.0
        self._prev_close = 0.0
        self._sm_tr = 0.0
        self._sm_plus_dm = 0.0
        self._sm_minus_dm = 0.0
        self._dx_sum = 0.0
        self._adx = 0.0
        self._plus_di = 0.0
        self._minus_di = 0.0

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def adx(self) -> float:
        return self._adx

    @property
    def plus_di(self) -> float:
        return self._plus_di

    @property
    def minus_di(self) -> float:
        return self._minus_di

    def _compute_dx(self) -> float:
        if self._sm_tr <= 1.0e-12:
            self._plus_di = 0.0
            self._minus_di = 0.0
            return 0.0
        self._plus_di = 100.0 * self._sm_plus_dm / self._sm_tr
        self._minus_di = 100.0 * self._sm_minus_dm / self._sm_tr
        total = self._plus_di + self._minus_di
        if total <= 1.0e-12:
            return 0.0
        return 100.0 * abs(self._plus_di - self._minus_di) / total

    def push(self, brick: Brick) -> None:
        high, low, close = brick.high, brick.low, brick.close

        if not self._have_prev:
            self._prev_high, self._prev_low, self._prev_close = high, low, close
            self._have_prev = True
            return

        tr = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        up_move = high - self._prev_high
        down_move = self._prev_low - low
        plus_dm = up_move if (up_move > down_move and up_move > 0.0) else 0.0
        minus_dm = down_move if (down_move > up_move and down_move > 0.0) else 0.0

        self._prev_high, self._prev_low, self._prev_close = high, low, close

        period = self._period
        if self._tr_count < period:
            # Wilder warmup: plain sums until the first full period, then the
            # first DX seeds the ADX average.
            self._sm_tr += tr
            self._sm_plus_dm += plus_dm
            self._sm_minus_dm += minus_dm
            self._tr_count += 1
            if self._tr_count == period:
                dx = self._compute_dx()
                self._dx_sum = dx
                self._dx_count = 1
                if period == 1:
                    self._adx = dx
                    self._ready = True
            return

        self._sm_tr = self._sm_tr - self._sm_tr / period + tr
        self._sm_plus_dm = self._sm_plus_dm - self._sm_plus_dm / period + plus_dm
        self._sm_minus_dm = self._sm_minus_dm - self._sm_minus_dm / period + minus_dm
        dx = self._compute_dx()

        if not self._ready:
            self._dx_sum += dx
            self._dx_count += 1
            if self._dx_count >= period:
                self._adx = self._dx_sum / period
                self._ready = True
            return

        self._adx = ((period - 1) * self._adx + dx) / period

    def direction(self, adx_threshold: float, min_di_separation: float) -> int:
        """Gated direction used for **entries**: strength and separation both apply."""
        if not self._ready or self._adx < adx_threshold:
            return 0
        if abs(self._plus_di - self._minus_di) < min_di_separation:
            return 0
        if self._plus_di > self._minus_di:
            return 1
        if self._minus_di > self._plus_di:
            return -1
        return 0

    def raw_direction(self) -> int:
        """Ungated DI direction used for **exits**.

        The vendor applies the strength threshold to entries only, so a position is
        closed on a DI flip even after ADX has decayed below the entry gate. That
        asymmetry is deliberate in the source and is preserved here.
        """
        if not self._ready:
            return 0
        if self._plus_di > self._minus_di:
            return 1
        if self._minus_di > self._plus_di:
            return -1
        return 0


class BollingerMode(IntEnum):
    """Mirrors ``ENUM_GDS_BB_MODE``."""

    BREAKOUT = 0
    REENTRY = 1
    MIDLINE_CROSS = 2
    SQUEEZE_BREAKOUT = 3


BB_MODES: tuple[BollingerMode, ...] = tuple(BollingerMode)


class RenkoBollinger:
    """Bollinger bands over completed brick closes, with the four vendor rule sets.

    Port of ``CRenkoBollinger``. Two properties of the source are load-bearing and
    preserved exactly:

    * bands are evaluated **before** the new close is appended, so the brick being
      judged never contributes to the band that judges it;
    * the deviation uses the **population** standard deviation (divide by N), not
      the sample one.
    """

    __slots__ = (
        "_closes",
        "_last_mid",
        "_last_ready",
        "_period",
        "_prev_mid_side",
        "_prev_ready",
        "_prev_relation",
    )

    def __init__(self, period: int) -> None:
        if period < 2:
            raise ValueError(f"period must be >= 2, got {period}")
        self._period = int(period)
        self._closes: list[float] = []
        self._prev_ready = False
        self._prev_relation = 0
        self._prev_mid_side = 0
        self._last_ready = False
        self._last_mid = 0.0

    @property
    def ready(self) -> bool:
        return self._last_ready

    @property
    def mid(self) -> float:
        return self._last_mid

    def _append(self, close: float) -> None:
        self._closes.append(close)
        if len(self._closes) > self._period:
            del self._closes[0]

    def _bands(self, deviation: float) -> tuple[float, float, float] | None:
        if len(self._closes) < self._period:
            return None
        mid = math.fsum(self._closes) / self._period
        variance = math.fsum((c - mid) ** 2 for c in self._closes) / self._period
        sd = math.sqrt(max(0.0, variance))
        return mid, mid + deviation * sd, mid - deviation * sd

    def push(
        self,
        brick: Brick,
        mode: BollingerMode,
        deviation: float,
        brick_size: float,
        squeeze_max_width_bricks: float,
    ) -> int:
        """Advance one completed brick. Returns the raw signal (+1 / 0 / -1)."""
        bands = self._bands(deviation)
        if bands is None:
            self._append(brick.close)
            self._last_ready = False
            return 0
        mid, upper, lower = bands

        relation = 1 if brick.close > upper else (-1 if brick.close < lower else 0)
        mid_side = 1 if brick.close >= mid else -1
        width_bricks = (upper - lower) / brick_size if brick_size > 0.0 else 0.0

        signal = 0
        if mode == BollingerMode.BREAKOUT:
            if relation > 0 and brick.direction > 0:
                signal = 1
            elif relation < 0 and brick.direction < 0:
                signal = -1
        elif mode == BollingerMode.REENTRY:
            if self._prev_ready and self._prev_relation < 0 and relation >= 0 and brick.direction > 0:
                signal = 1
            elif self._prev_ready and self._prev_relation > 0 and relation <= 0 and brick.direction < 0:
                signal = -1
        elif mode == BollingerMode.MIDLINE_CROSS:
            if self._prev_ready and self._prev_mid_side < 0 and mid_side > 0 and brick.direction > 0:
                signal = 1
            elif self._prev_ready and self._prev_mid_side > 0 and mid_side < 0 and brick.direction < 0:
                signal = -1
        # nesting kept: the squeeze gate is a separate precondition in the source,
        # and flattening it hides that mode 4 is mode 1 plus a width filter
        elif mode == BollingerMode.SQUEEZE_BREAKOUT:  # noqa: SIM102
            if width_bricks <= squeeze_max_width_bricks:
                if relation > 0 and brick.direction > 0:
                    signal = 1
                elif relation < 0 and brick.direction < 0:
                    signal = -1

        self._last_ready = True
        self._last_mid = mid
        self._prev_ready = True
        self._prev_relation = relation
        self._prev_mid_side = mid_side
        self._append(brick.close)
        return signal


# --------------------------------------------------------------------------
# Bar -> intrabar path
# --------------------------------------------------------------------------

#: Intrabar traversal conventions. ``ohlc_tester_default`` matches the MT5 Strategy
#: Tester's OHLC model: a bar that closed up is assumed to have made its low first.
#: ``reversed`` is its mirror and exists purely as a falsifier — if a result depends
#: on which one we pick, the result is an artefact of an assumption we invented.
PATH_CONVENTIONS = ("ohlc_tester_default", "reversed")


def bar_path(
    open_: float,
    high: float,
    low: float,
    close: float,
    convention: str = "ohlc_tester_default",
) -> tuple[float, float, float, float]:
    """Return the assumed intrabar price path for one OHLC bar."""
    if convention not in PATH_CONVENTIONS:
        raise ValueError(f"unknown path convention {convention!r}; expected one of {PATH_CONVENTIONS}")
    bullish = close >= open_
    if convention == "reversed":
        bullish = not bullish
    return (open_, low, high, close) if bullish else (open_, high, low, close)


def bricks_from_bars(
    bars: Sequence[tuple[float, float, float, float]],
    builder: RenkoBuilder,
    convention: str = "ohlc_tester_default",
) -> Iterator[tuple[int, Brick]]:
    """Yield ``(bar_index, brick)`` for every brick completed while walking ``bars``.

    ``bar_index`` is the bar whose traversal completed the brick — the earliest bar
    at which the brick could have been acted on.
    """
    for i, (bar_open, bar_high, bar_low, bar_close) in enumerate(bars):
        for price in bar_path(bar_open, bar_high, bar_low, bar_close, convention):
            for brick in builder.push_price(price):
                yield i, brick
