"""BtcTrendPullback overlay isolation — this lane validates the existing indicator."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IND = ROOT / "mql5" / "Indicators" / "BtcTrendPullback.mq5"
LOCK = ROOT / "results" / "btc_trend_pullback_lock.json"


def test_indicator_exists_buffer_7_no_ordersend():
    src = IND.read_text()
    assert "SetIndexBuffer(7, BufSignal" in src or "SetIndexBuffer(7," in src
    assert "OrderSend(" not in src
    assert "iCustom" not in src  # this file IS the indicator
    assert "PERIOD_H4" in src
    assert "InpEmaFast" in src and "InpEmaSlow" in src


def test_lock_does_not_claim_a_new_overlay():
    text = LOCK.read_text()
    assert "buffer 7" in text
    assert "untouched" in text
    assert "BtcNySessionScalp" not in text
