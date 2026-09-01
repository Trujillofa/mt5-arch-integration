"""The EA must not misreport its own version.

A deployed build that claims the wrong version is how a stale EA hides: the
live FP Markets terminal served the deal dump while printing "v1.23", and the
Vantage terminal printed "v1.23" while running a build that had no deal dump at
all. Both were only caught by hand-grepping the deployed source. These tests
keep the three places the version appears from drifting apart again.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

EA = Path(__file__).resolve().parents[1] / "mql5" / "Mt5ArchBridge.mq5"


@pytest.fixture(scope="module")
def source() -> str:
    return EA.read_text(encoding="utf-8")


def test_property_version_matches_bridge_version_define(source: str) -> None:
    prop = re.search(r'#property\s+version\s+"([\d.]+)"', source)
    define = re.search(r'#define\s+BRIDGE_VERSION\s+"([\d.]+)"', source)
    assert prop is not None, "no #property version"
    assert define is not None, "no BRIDGE_VERSION define"
    assert prop.group(1) == define.group(1), (
        "#property version and BRIDGE_VERSION disagree — the EA would misreport "
        "its version in the Journal and the heartbeat"
    )


def test_oninit_print_uses_the_define_not_a_literal(source: str) -> None:
    """A literal here is exactly the drift that shipped v1.23 twice."""
    assert 'WRITER v" + BRIDGE_VERSION' in source
    assert not re.search(r'WRITER v\d+\.\d+', source), "hardcoded version in OnInit print"


def test_heartbeat_writes_the_version_field(source: str) -> None:
    assert '" version=" + BRIDGE_VERSION' in source


def test_min_deal_dump_version_is_not_ahead_of_the_ea(source: str) -> None:
    """Python must not demand a version the shipped EA cannot report."""
    from mt5_arch.file_bridge import MIN_DEAL_DUMP_VERSION

    define = re.search(r'#define\s+BRIDGE_VERSION\s+"([\d.]+)"', source)
    assert define is not None
    ea_version = tuple(int(p) for p in define.group(1).split("."))
    assert ea_version >= MIN_DEAL_DUMP_VERSION
