"""OilSessionScalp source pins: exclusive file, buffer 8, no orders."""

from __future__ import annotations

import re
from pathlib import Path

IND = Path(__file__).resolve().parents[1] / "mql5" / "Indicators" / "OilSessionScalp.mq5"
IDX = Path(__file__).resolve().parents[1] / "mql5" / "Indicators" / "UsIndexSessionScalp.mq5"
BTC = Path(__file__).resolve().parents[1] / "mql5" / "Indicators" / "BtcTrendPullback.mq5"
MQH = Path(__file__).resolve().parents[1] / "mql5" / "Include" / "OilSessionUtils.mqh"
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
    assert "OilSessionScalp" in src
    assert "oil_london_orb_vwap_ema_flat" in src
    assert "observe-only" in src
    assert "SCREEN_FAIL" in src
    assert "Not a trading signal" in src


def test_signal_buffer_8_and_no_orders():
    src = _src()
    assert re.search(r"SetIndexBuffer\(8,\s*BufSignal", src)
    assert "indicator_buffers 10" in src
    assert not re.search(r"\bOrderSend\s*\(", src)
    assert MQH.is_file()
    mqh = MQH.read_text(encoding="utf-8")
    assert "OilEtFromServer" in mqh
    assert "OIL_SERVER_MINUS_SEC" in mqh
    assert "11:30" in mqh or "OIL_NY_END_MIN" in mqh
    assert "OIL_NY_END_MIN" in mqh
    assert "10:25" in mqh


def test_version_is_consistent():
    src = _src()
    prop = re.search(r'#property\s+version\s+"([\d.]+)"', src)
    define = re.search(r'#define\s+OSS_VERSION\s+"([\d.]+)"', src)
    assert prop is not None and define is not None
    assert prop.group(1) == define.group(1)


def test_xau_loop_status_not_rewritten_by_this_lane():
    text = XAU_STATUS.read_text(encoding="utf-8")
    assert "oil_session_scalp" not in text.lower()
    assert "XTIUSD" not in text
