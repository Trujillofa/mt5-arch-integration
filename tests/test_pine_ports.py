"""Pine v5 ports: files exist, observe-only, buffers match SignalContract.

Does not compile Pine (no TV compiler here). Checks the invariants the
ports must not drift from: version=5, indicator() not strategy(), no
OrderSend, signal-buffer comments, SCREEN_FAIL on BNS, host-only Gold/Oil
called out and not invented.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINE_DIR = ROOT / "mql5" / "pine"
README = PINE_DIR / "README.md"
CONTRACT = ROOT / "mql5" / "Include" / "SignalContract.mqh"

PORTS = {
    "HTFFIB": {
        "mq5": "ForexHtfPivotsFib.mq5",
        "pine": "ForexHtfPivotsFib.pine",
        "buffer": 8,
        "shortname": "ForexHtfPivotsFib",
    },
    "FXIT": {
        "mq5": "ForexIndicatorTemplate.mq5",
        "pine": "ForexIndicatorTemplate.pine",
        "buffer": 9,
        "shortname": "ForexIndicatorTemplate",
    },
    "UIS": {
        "mq5": "UsIndexSessionScalp.mq5",
        "pine": "UsIndexSessionScalp.pine",
        "buffer": 8,
        "shortname": "UsIndexSessionScalp",
    },
    "BTP": {
        "mq5": "BtcTrendPullback.mq5",
        "pine": "BtcTrendPullback.pine",
        "buffer": 7,
        "shortname": "BtcTrendPullback",
    },
    "BNS": {
        "mq5": "BtcNySessionScalp.mq5",
        "pine": "BtcNySessionScalp.pine",
        "buffer": 8,
        "shortname": "BtcNySessionScalp",
    },
}

DEFINE_RE = re.compile(
    r"#define\s+(UIS|BNS|HTFFIB|BTP|FXIT)_SIGNAL_BUFFER\s+(\d+)",
)
STRATEGY_RE = re.compile(
    r"\bstrategy\s*\(|\bstrategy\.(entry|order|close|exit|cancel)\b",
)
ORDER_RE = re.compile(r"\bOrderSend\s*\(")
VERSION_RE = re.compile(r"^//@version=5\s*$", re.M)
INDICATOR_RE = re.compile(r"\bindicator\s*\(")


def _strip_pine_comments(src: str) -> str:
    return "\n".join(line.split("//", 1)[0] for line in src.splitlines())


def _contract() -> dict[str, int]:
    text = CONTRACT.read_text(encoding="utf-8")
    found = {m.group(1): int(m.group(2)) for m in DEFINE_RE.finditer(text)}
    assert found == {k: v["buffer"] for k, v in PORTS.items()}, found
    return found


def test_five_pine_files_exist() -> None:
    for spec in PORTS.values():
        path = PINE_DIR / spec["pine"]
        assert path.is_file(), path
        assert (ROOT / "mql5" / "Indicators" / spec["mq5"]).is_file()


def test_pine_is_v5_indicator_not_strategy() -> None:
    for spec in PORTS.values():
        src = (PINE_DIR / spec["pine"]).read_text(encoding="utf-8")
        code = _strip_pine_comments(src)
        assert VERSION_RE.search(src), spec["pine"]
        assert INDICATOR_RE.search(src), spec["pine"]
        assert STRATEGY_RE.search(code) is None, spec["pine"]
        assert ORDER_RE.search(code) is None, spec["pine"]
        assert "observe-only" in src
        assert "promote=no" in src
        assert "Not a live signal" in src or "not a live signal" in src
        assert spec["mq5"] in src
        assert f"mql5/Indicators/{spec['mq5']}" in src


def test_pine_signal_buffers_match_signal_contract() -> None:
    frozen = _contract()
    for key, spec in PORTS.items():
        src = (PINE_DIR / spec["pine"]).read_text(encoding="utf-8")
        buf = frozen[key]
        assert spec["buffer"] == buf
        assert re.search(rf"\bbuffer\s+{buf}\b|\bsig@{buf}\b|signal buffer = {buf}", src, re.I)
        readme = README.read_text(encoding="utf-8")
        assert spec["pine"] in readme
        assert spec["mq5"] in readme
        row = next(line for line in readme.splitlines() if spec["pine"] in line)
        assert f"**{buf}**" in row, row


def test_fxit_signal_is_nine_not_eight() -> None:
    src = (PINE_DIR / "ForexIndicatorTemplate.pine").read_text(encoding="utf-8")
    assert "buffer 8" in src.lower() or "Buffer 8" in src
    assert "short arrow" in src.lower()
    assert re.search(r"sig@9|buffer 9|Signal buffer is 9", src)


def test_bns_stays_screen_fail() -> None:
    src = (PINE_DIR / "BtcNySessionScalp.pine").read_text(encoding="utf-8")
    assert "SCREEN_FAIL" in src
    assert "btc_ny_overlap_vwap_ema_flat" in src or "VWAP_EMA" in src
    assert "America/New_York" in src
    assert "[08:00, 11:30)" in src
    assert "GoldSessionScalp" not in src or "not the gold" in src.lower()


def test_us_index_keeps_dst_iana_clock() -> None:
    src = (PINE_DIR / "UsIndexSessionScalp.pine").read_text(encoding="utf-8")
    assert "America/New_York" in src
    assert "Europe/London" in src
    assert "Asia/Tokyo" in src
    assert "IndexSessionUtils" in src


def test_readme_maps_all_and_host_only_gold_oil() -> None:
    text = README.read_text(encoding="utf-8")
    for spec in PORTS.values():
        assert spec["mq5"] in text
        assert spec["pine"] in text
    assert "GoldSessionScalp.mq5" in text
    assert "OilSessionScalp.mq5" in text
    assert "not in this repo" in text.lower() or "not ported" in text.lower()
    assert "OMARCHY" in text
    assert "Merge ≠ deploy" in text or "merge ≠ deploy" in text.lower()
    # no invented gold/oil pine
    assert not (PINE_DIR / "GoldSessionScalp.pine").exists()
    assert not (PINE_DIR / "OilSessionScalp.pine").exists()


def test_no_extra_pine_overlays() -> None:
    names = {p.name for p in PINE_DIR.glob("*.pine")}
    expected = {s["pine"] for s in PORTS.values()}
    assert names == expected, names - expected


def _balance(src: str) -> None:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    in_str = False
    for ch in _strip_pine_comments(src):
        if ch == '"' and not in_str:
            in_str = True
            continue
        if ch == '"' and in_str:
            in_str = False
            continue
        if in_str:
            continue
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            assert stack and stack[-1] == pairs[ch], "unbalanced delimiters"
            stack.pop()
    assert not stack, f"unclosed {stack}"


def test_pine_delimiters_and_no_invalid_history_on_call() -> None:
    bad = re.compile(r"\w+\([^)]*\)\s*\[\s*1\s*\]")
    for spec in PORTS.values():
        src = (PINE_DIR / spec["pine"]).read_text(encoding="utf-8")
        _balance(src)
        assert bad.search(src) is None, spec["pine"]
        assert "strategy()" not in _strip_pine_comments(src)
