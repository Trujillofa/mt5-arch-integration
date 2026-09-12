"""SignalContract.mqh vs SetIndexBuffer vs README.

The FXIT-table-8 class: README listed ForexIndicatorTemplate signal as 8
while SetIndexBuffer(9, BufSignal) was the live index. This file greps the
#defines, the five in-scope overlay SetIndexBuffer(SIGNAL) lines, the logger
comments, and the README buffer tables so that mismatch cannot recur.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "mql5" / "Include" / "SignalContract.mqh"
LOGGER = ROOT / "mql5" / "Experts" / "ForexSignalLogger.mq5"
README = ROOT / "mql5" / "README.md"
INSTALLER = ROOT / "scripts" / "18-install-forex-indicator.sh"

FROZEN = {
    "UIS": 8,
    "BNS": 8,
    "HTFFIB": 8,
    "BTP": 7,
    "FXIT": 9,
}

INDICATORS = {
    "UIS": ROOT / "mql5" / "Indicators" / "UsIndexSessionScalp.mq5",
    "BNS": ROOT / "mql5" / "Indicators" / "BtcNySessionScalp.mq5",
    "HTFFIB": ROOT / "mql5" / "Indicators" / "ForexHtfPivotsFib.mq5",
    "BTP": ROOT / "mql5" / "Indicators" / "BtcTrendPullback.mq5",
    "FXIT": ROOT / "mql5" / "Indicators" / "ForexIndicatorTemplate.mq5",
}

README_HEADINGS = {
    "UIS": "### UsIndexSessionScalp buffers",
    "BNS": "### BtcNySessionScalp buffers",
    "HTFFIB": "### ForexHtfPivotsFib buffers",
    "BTP": "### BtcTrendPullback buffers",
    "FXIT": "### ForexIndicatorTemplate buffers",
}

DEFINE_RE = re.compile(
    r"#define\s+(UIS|BNS|HTFFIB|BTP|FXIT)_SIGNAL_BUFFER\s+(\d+)",
)
SETBUF_RE = re.compile(r"SetIndexBuffer\((\d+),\s*BufSignal\b")
SIGNAL_ROW_RE = re.compile(
    r"\|\s*\*{0,2}(\d+)\*{0,2}\s*\|\s*\*{0,2}([^*|\n]+)",
)


def _defines() -> dict[str, int]:
    text = CONTRACT.read_text(encoding="utf-8")
    found = {m.group(1): int(m.group(2)) for m in DEFINE_RE.finditer(text)}
    assert found == FROZEN, f"SignalContract defines drifted: {found}"
    return found


def _setindex_signal(src: str) -> list[str]:
    hits: list[str] = []
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        hits.extend(SETBUF_RE.findall(line))
    return hits


def _section(md: str, heading: str) -> str:
    start = md.find(heading)
    assert start >= 0, f"missing README heading {heading!r}"
    rest = md[start + len(heading) :]
    nxt = rest.find("\n### ")
    return rest if nxt < 0 else rest[:nxt]


def _signal_index_in_section(section: str) -> int:
    for match in SIGNAL_ROW_RE.finditer(section):
        content = match.group(2).strip().lower()
        if content.startswith("signal"):
            return int(match.group(1))
    raise AssertionError(f"no Signal row in section:\n{section}")


def test_contract_defines_match_setindexbuffer_signal() -> None:
    defines = _defines()
    for key, path in INDICATORS.items():
        src = path.read_text(encoding="utf-8")
        hits = _setindex_signal(src)
        assert hits == [str(defines[key])], (
            f"{path.name}: SetIndexBuffer(*, BufSignal)={hits} "
            f"vs {key}_SIGNAL_BUFFER={defines[key]}"
        )
        assert "#include <SignalContract.mqh>" in src
        assert f"{key}_SIGNAL_BUFFER" in src
        assert not re.search(r"\bOrderSend\s*\(", src)


def test_fxit_is_nine_not_eight() -> None:
    defines = _defines()
    assert defines["FXIT"] == 9
    fxit = INDICATORS["FXIT"].read_text(encoding="utf-8")
    assert "SetIndexBuffer(9, BufSignal" in fxit
    assert "SetIndexBuffer(8, BufSignal" not in fxit
    assert "SetIndexBuffer(8, BufShort" in fxit


def test_readme_buffer_tables_match_contract() -> None:
    defines = _defines()
    md = README.read_text(encoding="utf-8")
    assert "Include/SignalContract.mqh" in md
    assert "Template = 8" not in md
    assert "**Template = 9**" in md
    for key, heading in README_HEADINGS.items():
        section = _section(md, heading)
        assert _signal_index_in_section(section) == defines[key], heading
        assert f"{key}_SIGNAL_BUFFER" in section
    fxit = _section(md, README_HEADINGS["FXIT"])
    assert _signal_index_in_section(fxit) == 9
    assert re.search(r"not(?: the signal| 8)|never 8", fxit, re.I)
    assert "| **8** | **Signal" not in fxit
    assert "signal=8" in fxit and "do not write signal=8" in fxit.lower()


def test_logger_table_derives_from_contract() -> None:
    defines = _defines()
    src = LOGGER.read_text(encoding="utf-8")
    assert "#include <SignalContract.mqh>" in src
    assert "InpSignalBuffer    = 8" in src
    assert "SignalContractTable()" in src
    assert "SignalContractBufferFor(" in src
    assert not re.search(r"\bOrderSend\s*\(", src)
    for key, idx in defines.items():
        assert re.search(rf"{key}\s*=\s*{idx}", src), f"logger missing {key}={idx}"
    assert re.search(r"FXIT\s*=\s*9", src)
    assert not re.search(r"FXIT\s*=\s*8", src)
    assert "Template=8" not in src


def test_installer_copies_signal_contract() -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    assert "mql5/Include/SignalContract.mqh" in text
    contract = CONTRACT.read_text(encoding="utf-8")
    assert "GoldSessionScalp excluded" in contract
    assert "GoldSessionScalp.mq5" not in contract
