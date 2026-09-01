"""UsIndexSessionScalp source pins: Asia/London H/L are observe-only."""

from __future__ import annotations

import re
from pathlib import Path

IND = Path(__file__).resolve().parents[1] / "mql5" / "Indicators" / "UsIndexSessionScalp.mq5"


def _src() -> str:
    return IND.read_text(encoding="utf-8")


def test_asia_london_hl_labels_and_defaults() -> None:
    src = _src()
    assert re.search(r"InpShowAsiaLevels\s*=\s*true", src)
    assert re.search(r"InpShowLondonLevels\s*=\s*true", src)
    assert re.search(r"InpShowTokyo\s*=\s*false", src), "Tokyo vlines stay off"
    assert '"ASIA HIGH"' in src
    assert '"ASIA LOW"' in src
    assert '"LONDON HIGH"' in src
    assert '"LONDON LOW"' in src


def test_signal_buffer_8_unchanged_and_no_orders() -> None:
    src = _src()
    assert "SetIndexBuffer(8, BufSignal" in src
    assert re.search(r"SetIndexBuffer\(8,\s*BufSignal", src)
    assert not re.search(r"\bOrderSend\s*\(", src)
    assert "indicator_buffers 10" in src


def test_overlay_version_is_consistent() -> None:
    src = _src()
    prop = re.search(r'#property\s+version\s+"([\d.]+)"', src)
    define = re.search(r'#define\s+UIS_VERSION\s+"([\d.]+)"', src)
    assert prop is not None
    assert define is not None
    assert prop.group(1) == define.group(1) == "1.41"
    assert "v1.40" not in src
    assert "UIS_VERSION" in src
    assert not re.search(r'UsIndexSessionScalp v1\.\d+', src)
