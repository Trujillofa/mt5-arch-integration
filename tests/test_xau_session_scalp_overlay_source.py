"""GoldSessionScalp source pins: exclusive file, buffer 8, no orders."""

from __future__ import annotations

import re
from pathlib import Path

IND = Path(__file__).resolve().parents[1] / "mql5" / "Indicators" / "GoldSessionScalp.mq5"
IDX = Path(__file__).resolve().parents[1] / "mql5" / "Indicators" / "UsIndexSessionScalp.mq5"
MQH = Path(__file__).resolve().parents[1] / "mql5" / "Include" / "GoldSessionUtils.mqh"


def _src() -> str:
    return IND.read_text(encoding="utf-8")


def test_exclusive_indicator_file_exists_and_is_not_the_index_file():
    assert IND.is_file()
    assert IDX.is_file()
    assert IND.resolve() != IDX.resolve()
    gold = _src()
    assert "UsIndexSessionScalp" not in gold
    assert "ny_cash_orb" not in gold
    assert "GoldSessionScalp" in gold
    assert "xau_london_defined_r_be_flat_v1" in gold
    assert "InpTpR" in gold
    assert "observe-only" in gold
    assert "Not a trading signal" in gold


def test_signal_buffer_8_and_no_orders():
    src = _src()
    assert re.search(r"SetIndexBuffer\(8,\s*BufSignal", src)
    assert "indicator_buffers 10" in src
    assert not re.search(r"\bOrderSend\s*\(", src)
    assert MQH.is_file()
    mqh = MQH.read_text(encoding="utf-8")
    assert "GldIsNyMetals" in mqh
    assert "GldInHm(et.hour, et.min, 8, 0, 17, 0)" in mqh
    assert "GldInHm(et.hour, et.min, 9, 30, 16, 0)" not in mqh


def test_version_is_consistent():
    src = _src()
    prop = re.search(r'#property\s+version\s+"([\d.]+)"', src)
    define = re.search(r'#define\s+GSS_VERSION\s+"([\d.]+)"', src)
    assert prop is not None and define is not None
    assert prop.group(1) == define.group(1)


def test_indicator_is_closed_observe_only():
    src = _src()
    assert "CLOSED" in src
    assert "observe-only" in src
    assert "Not a trading signal" in src
    assert "xau_london_defined_r_be_flat_v1" in src
