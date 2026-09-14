"""SessionVwapOr.mqh vs UIS/BNS inline copies.

P2-R3: ET-day VWAP (vnum/vden) + opening-range hi/lo accumulator.
BtcTrendPullback RollingVwap is lookback, not ET-day — must stay separate.
GoldSessionScalp is excluded. Signal buffers and OrderSend stay untouched.
Clocks stay in the callers (IdxEtOfBar / BtcEtFromServer).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ROOT / "mql5" / "Include" / "SessionVwapOr.mqh"
INSTALLER = ROOT / "scripts" / "18-install-forex-indicator.sh"
README = ROOT / "mql5" / "README.md"

UIS = ROOT / "mql5" / "Indicators" / "UsIndexSessionScalp.mq5"
BNS = ROOT / "mql5" / "Indicators" / "BtcNySessionScalp.mq5"
BTP = ROOT / "mql5" / "Indicators" / "BtcTrendPullback.mq5"

SETBUF_RE = re.compile(r"SetIndexBuffer\((\d+),\s*BufSignal\b")
ROLLING_VWAP_RE = re.compile(
    r"double\s+RollingVwap\s*\(\s*const\s+int\s+i\s*,",
)


def _code(src: str) -> str:
    lines: list[str] = []
    for raw in src.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*"):
            continue
        if "//" in stripped:
            stripped = stripped[: stripped.index("//")].rstrip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def test_include_struct_and_api() -> None:
    src = INCLUDE.read_text(encoding="utf-8")
    code = _code(src)
    assert re.search(r'#define\s+SESSION_VWAP_OR_VER\s+"1\.00"', src)
    assert "struct SessionVwapOr" in src
    for field in ("vnum", "vden", "or_hi", "or_lo", "day_key", "or_set"):
        assert re.search(rf"\b{field}\b", src), field
    assert "void SvoInit(" in src
    assert "void SvoReset(" in src
    assert "bool SvoOnDayChange(" in src
    assert "void SvoAccumulate(" in src
    assert "double SvoVwap(" in src
    assert "void SvoOrBar(" in src
    assert "(high + low + close) / 3.0" in src
    assert "s.vnum / s.vden" in src
    assert "s.vden > 0.0" in src
    assert "GoldSessionScalp excluded" in src
    assert "lookback, not ET-day" in src
    assert "IdxEtOfBar" not in code
    assert "BtcEtFromServer" not in code
    assert "double RollingVwap" not in code
    assert not re.search(r"\bOrderSend\s*\(", src)
    assert "BufVwap" not in code
    assert "BufOrHigh" not in code
    assert "BufOrLow" not in code


def test_uis_and_bns_include_session_vwap_or() -> None:
    for path in (UIS, BNS):
        src = path.read_text(encoding="utf-8")
        assert "#include <SessionVwapOr.mqh>" in src, path.name
        assert "SvoOnDayChange(" in src, path.name
        assert "SvoAccumulate(" in src, path.name
        assert "SvoOrBar(" in src, path.name
        assert "SvoVwap(" in src, path.name
        assert "BufVwap[" in src, path.name
        assert "BufOrHigh[" in src, path.name
        assert "BufOrLow[" in src, path.name
        assert not re.search(r"\bOrderSend\s*\(", src)
        assert "double vnum" not in src
        assert "double vden" not in src
        assert "vnum +=" not in src
        assert "vden +=" not in src


def test_callers_keep_their_clocks() -> None:
    uis = UIS.read_text(encoding="utf-8")
    assert "IdxEtOfBar(" in uis
    assert "IdxEtDateKey(" in uis
    assert "IdxIsNyCash(" in uis
    assert "IdxInOrWindow(" in uis
    assert "BtcEtFromServer" not in uis
    bns = BNS.read_text(encoding="utf-8")
    assert "BtcEtFromServer(" in bns
    assert "BtcEtKey(" in bns
    assert "BtcInOverlap(" in bns
    assert "BTC_SESSION_START_MIN" in bns
    assert "IdxEtOfBar" not in bns


def test_btp_keeps_rolling_vwap_and_does_not_include_session_vwap_or() -> None:
    src = BTP.read_text(encoding="utf-8")
    assert "#include <SessionVwapOr.mqh>" not in src
    assert ROLLING_VWAP_RE.search(src)
    assert "InpVwapLookback" in src
    assert "SvoAccumulate" not in src
    assert "SvoOnDayChange" not in src
    assert "SessionVwapOr" not in src
    hits = SETBUF_RE.findall(src)
    assert hits == ["7"], f"BTP BufSignal drifted: {hits}"


def test_signal_buffers_unchanged() -> None:
    frozen = {UIS: "8", BNS: "8", BTP: "7"}
    for path, idx in frozen.items():
        hits = SETBUF_RE.findall(path.read_text(encoding="utf-8"))
        assert hits == [idx], f"{path.name} BufSignal drifted: {hits}"


def test_installer_and_readme_list_session_vwap_or() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")
    assert "mql5/Include/SessionVwapOr.mqh" in installer
    md = README.read_text(encoding="utf-8")
    assert "Include/SessionVwapOr.mqh" in md
    assert "RollingVwap stays lookback" in md
