"""ChartObjects.mqh vs the five in-scope overlays.

P2-R2: prefix-scoped upsert + one OnDeinit wipe policy (HTFFIB).
Unconditional ObjectsDeleteAll without a reason guard is forbidden.
GoldSessionScalp is excluded. Signal buffers and OrderSend stay untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ROOT / "mql5" / "Include" / "ChartObjects.mqh"
INSTALLER = ROOT / "scripts" / "18-install-forex-indicator.sh"
README = ROOT / "mql5" / "README.md"

INDICATORS = {
    "UIS": ROOT / "mql5" / "Indicators" / "UsIndexSessionScalp.mq5",
    "BNS": ROOT / "mql5" / "Indicators" / "BtcNySessionScalp.mq5",
    "HTFFIB": ROOT / "mql5" / "Indicators" / "ForexHtfPivotsFib.mq5",
    "BTP": ROOT / "mql5" / "Indicators" / "BtcTrendPullback.mq5",
    "FXIT": ROOT / "mql5" / "Indicators" / "ForexIndicatorTemplate.mq5",
}

WIPE_REASONS = ("REASON_REMOVE", "REASON_CHARTCLOSE", "REASON_RECOMPILE")
FORBIDDEN_WIPE_REASONS = ("REASON_PARAMETERS", "REASON_CHARTCHANGE")
UPSERTS = ("CoHline", "CoVline", "CoRect", "CoText", "CoTrend")
SETBUF_RE = re.compile(r"SetIndexBuffer\((\d+),\s*BufSignal\b")
CO_SHOULD_WIPE_RE = re.compile(
    r"bool\s+CoShouldWipe\s*\(\s*const\s+int\s+reason\s*\)\s*\{([^}]+)\}",
    re.S,
)
CO_WIPE_RE = re.compile(
    r"void\s+CoWipePrefix\s*\(\s*const\s+int\s+reason,\s*const\s+string\s+prefix\s*\)"
    r"\s*\{([^}]+)\}",
    re.S,
)


def _code_lines(src: str) -> list[str]:
    lines: list[str] = []
    for raw in src.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*"):
            continue
        if "//" in stripped:
            stripped = stripped[: stripped.index("//")].rstrip()
        if stripped:
            lines.append(stripped)
    return lines


def test_include_version_and_upsert_api() -> None:
    src = INCLUDE.read_text(encoding="utf-8")
    assert re.search(r'#define\s+CHART_OBJECTS_VER\s+"1\.00"', src)
    assert "GoldSessionScalp excluded" in src
    assert "GoldSessionScalp.mq5" not in src
    for name in UPSERTS:
        assert f"void {name}(" in src, f"missing upsert {name}"
    assert "void CoWipePrefix(" in src
    assert "bool CoShouldWipe(" in src
    assert "OBJPROP_RAY_RIGHT" in src
    assert not re.search(r"\bOrderSend\s*\(", src)


def test_include_wipe_policy_matches_htffib() -> None:
    src = INCLUDE.read_text(encoding="utf-8")
    match = CO_SHOULD_WIPE_RE.search(src)
    assert match, "CoShouldWipe body not found"
    body = match.group(1)
    for reason in WIPE_REASONS:
        assert reason in body, f"CoShouldWipe missing {reason}"
    for reason in FORBIDDEN_WIPE_REASONS:
        assert reason not in body, f"CoShouldWipe must never wipe on {reason}"
    wipe = CO_WIPE_RE.search(src)
    assert wipe, "CoWipePrefix body not found"
    wipe_body = wipe.group(1)
    assert "CoShouldWipe(reason)" in wipe_body
    assert "ObjectsDeleteAll(0, prefix)" in wipe_body
    assert 'Comment("")' in wipe_body.replace(" ", "")
    assert "Wine" in src or "win32u" in src


def test_five_overlays_include_chart_objects_and_call_cowipe() -> None:
    for path in INDICATORS.values():
        src = path.read_text(encoding="utf-8")
        assert "#include <ChartObjects.mqh>" in src, path.name
        assert "CoWipePrefix(reason," in src, path.name
        assert "g_pfx" in src or "g_prefix" in src, path.name
        assert not re.search(r"\bOrderSend\s*\(", src)
        assert "GoldSessionScalp.mq5" not in src


def test_unconditional_objectsdeleteall_forbidden_in_overlays() -> None:
    for path in INDICATORS.values():
        code = _code_lines(path.read_text(encoding="utf-8"))
        hits = [line for line in code if "ObjectsDeleteAll" in line]
        assert hits == [], f"{path.name} has unguarded ObjectsDeleteAll: {hits}"
        joined = "\n".join(code)
        assert "CoWipePrefix(reason," in joined
        wipe_lines = [line for line in code if "CoWipePrefix" in line]
        for line in wipe_lines:
            assert "REASON_CHARTCHANGE" not in line
            assert "REASON_PARAMETERS" not in line
            assert "ObjectsDeleteAll" not in line


def test_local_uis_drawers_replaced() -> None:
    src = INDICATORS["UIS"].read_text(encoding="utf-8")
    assert "IdxUpsertRect" not in src
    assert "IdxUpsertVline" not in src
    assert "IdxUpsertHline" not in src
    assert "IdxUpsertText" not in src
    assert "CoHline(" in src
    assert "CoVline(" in src
    assert "CoRect(" in src
    assert "CoText(" in src


def test_htffib_fxit_bns_call_into_include() -> None:
    htffib = INDICATORS["HTFFIB"].read_text(encoding="utf-8")
    assert "CoTrend(" in htffib
    assert "ObjectCreate(0, name, OBJ_TREND" not in htffib
    fxit = INDICATORS["FXIT"].read_text(encoding="utf-8")
    assert "CoTrend(" in fxit
    assert "InpLevelExtendRight" in fxit
    assert "ObjectCreate(0, name, OBJ_TREND" not in fxit
    bns = INDICATORS["BNS"].read_text(encoding="utf-8")
    assert "CoVline(" in bns
    assert "FLAT 11:30 ET" in bns
    assert "NY desk 08:00" in bns
    assert "ObjectCreate(0, name, OBJ_VLINE" not in bns


def test_signal_buffers_unchanged() -> None:
    frozen = {"UIS": "8", "BNS": "8", "HTFFIB": "8", "BTP": "7", "FXIT": "9"}
    for key, path in INDICATORS.items():
        hits = SETBUF_RE.findall(path.read_text(encoding="utf-8"))
        assert hits == [frozen[key]], f"{path.name} BufSignal drifted: {hits}"


def test_installer_and_readme_list_chart_objects() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")
    assert "mql5/Include/ChartObjects.mqh" in installer
    md = README.read_text(encoding="utf-8")
    assert "Include/ChartObjects.mqh" in md
    assert "REMOVE/CHARTCLOSE/RECOMPILE only" in md
