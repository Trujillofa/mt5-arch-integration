"""live_trader retry safety: one intent, one fill.

Pins the duplicate-fill invariants: PLACED is not a retry state, every retry is
preceded by a book reconciliation, and one closed signal bar produces one order.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import live_trader  # noqa: E402


class FakeMT5:
    """Minimal order_send/terminal_info/positions stub."""

    TRADE_RETCODE_DONE = 10009
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    def __init__(self, retcodes: list[int], *, position_comments: tuple[str, ...] = ()):
        self._retcodes = list(retcodes)
        self._position_comments = position_comments
        self.sent: list[dict] = []

    def terminal_info(self):
        return SimpleNamespace(connected=True)

    def positions_get(self, *, symbol: str | None = None):
        return [SimpleNamespace(comment=c, symbol=symbol) for c in self._position_comments]

    def orders_get(self, *, symbol: str | None = None):
        return []

    def symbol_info_tick(self, symbol: str):
        return SimpleNamespace(ask=2400.0, bid=2399.5)

    def order_send(self, request: dict):
        self.sent.append(dict(request))
        retcode = self._retcodes.pop(0) if self._retcodes else 10009
        return SimpleNamespace(retcode=retcode, order=1, deal=1, price=request["price"], comment="")

    def last_error(self):
        return (0, "ok")


def _request(comment: str = "xau-20261105T1000-B") -> dict:
    return {
        "symbol": "XAUUSD",
        "volume": 0.1,
        "type": FakeMT5.ORDER_TYPE_BUY,
        "price": 2400.0,
        "sl": 2390.0,
        "tp": 2410.0,
        "comment": comment,
        "deviation": 30,
        "magic": 26080601,
    }


def test_placed_is_not_retried() -> None:
    """10008 PLACED means the order reached the server; resending duplicates it."""
    mt5 = FakeMT5([10008])
    result = live_trader.send_order_with_retry(mt5, _request())
    assert result.retcode == 10008
    assert len(mt5.sent) == 1


def test_timeout_retry_is_suppressed_when_intent_already_live() -> None:
    """A timeout does not prove the order failed: reconcile before resending."""
    mt5 = FakeMT5([10012], position_comments=("xau-20261105T1000-B",))
    result = live_trader.send_order_with_retry(mt5, _request())
    assert result.retcode == 10012
    assert len(mt5.sent) == 1, "blind retry after timeout would duplicate the fill"


def test_requote_retries_when_intent_not_found() -> None:
    mt5 = FakeMT5([10004, 10009])
    result = live_trader.send_order_with_retry(mt5, _request())
    assert result.retcode == 10009
    assert len(mt5.sent) == 2


def test_empty_comment_never_retries() -> None:
    """An unmatchable intent cannot be reconciled; fail closed."""
    mt5 = FakeMT5([10004, 10009])
    result = live_trader.send_order_with_retry(mt5, _request(comment=""))
    assert result.retcode == 10004
    assert len(mt5.sent) == 1


def test_signal_comment_is_unique_per_bar_and_side() -> None:
    long_a = live_trader.signal_comment(1, "20261105T1000")
    long_b = live_trader.signal_comment(1, "20261105T1100")
    short_a = live_trader.signal_comment(-1, "20261105T1000")
    assert len({long_a, long_b, short_a}) == 3
    assert long_a == "xau-20261105T1000-B"
    assert short_a == "xau-20261105T1000-S"


def test_traded_bar_state_roundtrip_is_atomic(tmp_path: Path) -> None:
    state = tmp_path / "state" / "last_signal_bar.json"
    live_trader.record_traded_bar("xau-20261105T1000-B", path=state)
    live_trader.record_traded_bar("xau-20261105T1100-S", path=state)
    bars = live_trader.load_traded_bars(state)
    assert set(bars) == {"xau-20261105T1000-B", "xau-20261105T1100-S"}
    assert not state.with_suffix(".tmp").exists(), "temp file must not survive the rename"
    assert json.loads(state.read_text(encoding="utf-8")).keys() == bars.keys()
