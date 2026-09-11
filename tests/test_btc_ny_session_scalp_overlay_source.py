"""BtcNySessionScalp source pins: exclusive file, buffer 8, no orders."""

from __future__ import annotations

import re
from pathlib import Path

IND = Path(__file__).resolve().parents[1] / "mql5" / "Indicators" / "BtcNySessionScalp.mq5"
IDX = Path(__file__).resolve().parents[1] / "mql5" / "Indicators" / "UsIndexSessionScalp.mq5"
BTC = Path(__file__).resolve().parents[1] / "mql5" / "Indicators" / "BtcTrendPullback.mq5"
MQH = Path(__file__).resolve().parents[1] / "mql5" / "Include" / "BtcSessionUtils.mqh"
XAU_STATUS = Path(__file__).resolve().parents[1] / "results" / "xau_loop_status.md"


def _src() -> str:
    return IND.read_text(encoding="utf-8")


def test_exclusive_indicator_file_exists_and_is_not_the_index_or_htf_file():
    assert IND.is_file()
    assert IDX.is_file()
    assert BTC.is_file()
    assert IND.resolve() != IDX.resolve()
    assert IND.resolve() != BTC.resolve()
    src = _src()
    assert "UsIndexSessionScalp" not in src
    assert "ny_cash_orb" not in src
    assert "GoldSessionScalp" not in src
    assert "BtcNySessionScalp" in src
    assert "btc_ny_overlap_vwap_ema_flat" in src
    assert "observe-only" in src
    assert "Not a trading signal" in src
    assert "SCREEN_FAIL" in src


def test_signal_buffer_8_and_no_orders():
    src = _src()
    assert re.search(r"SetIndexBuffer\(8,\s*BufSignal", src)
    assert "indicator_buffers 10" in src
    assert not re.search(r"\bOrderSend\s*\(", src)
    assert MQH.is_file()
    mqh = MQH.read_text(encoding="utf-8")
    assert "BtcEtFromServer" in mqh
    assert "BTC_SERVER_MINUS_SEC" in mqh
    assert "08:00" in mqh
    assert "11:30" in mqh
    assert "09:30" not in mqh or "not cash 09:30" in mqh.lower() or "not cash 09:30" in mqh


def test_version_is_consistent():
    src = _src()
    prop = re.search(r'#property\s+version\s+"([\d.]+)"', src)
    define = re.search(r'#define\s+BNS_VERSION\s+"([\d.]+)"', src)
    assert prop is not None and define is not None
    assert prop.group(1) == define.group(1)


def test_btc_trend_pullback_untouched_buffer_7():
    src = BTC.read_text(encoding="utf-8")
    assert "SetIndexBuffer(7" in src or "buffer 7" in src.lower() or "Signal buffer 7" in src
    assert "BtcNySessionScalp" not in src


def test_xau_loop_status_not_rewritten_by_this_lane():
    text = XAU_STATUS.read_text(encoding="utf-8")
    assert "btc_ny_session_scalp" not in text.lower()
