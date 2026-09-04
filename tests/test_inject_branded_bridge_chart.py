"""Offline tests for branded Mt5ArchBridge chart inject (no Wine)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inject_branded_bridge_chart.py"
SPEC = importlib.util.spec_from_file_location("inject_branded_bridge_chart", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
inject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inject)


def _brand_tree(tmp_path: Path, name: str, *, with_ex5: bool = True) -> Path:
    term_dir = tmp_path / "Program Files" / name
    if with_ex5:
        ex5 = term_dir / "MQL5" / "Experts" / "Mt5ArchBridge.ex5"
        ex5.parent.mkdir(parents=True, exist_ok=True)
        ex5.write_bytes(b"ex5")
    return term_dir


def _chart_text(path: Path) -> str:
    raw = path.read_bytes()
    assert raw[:2] == b"\xff\xfe"
    return raw[2:].decode("utf-16-le")


def test_inject_ftmo_writes_inpbroker_on_both_default_charts(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "FTMO Global Markets MT5 Terminal")
    written = inject.inject_charts("ftmo", term_dir)
    assert len(written) == 2
    for path in written:
        text = _chart_text(path)
        assert "InpBroker=ftmo" in text
        assert "symbol=EURUSD" in text
        assert "Mt5ArchBridge" in text


def test_inject_wsf_uses_eurusdc(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "WSFmarkets MT5 Terminal")
    written = inject.inject_charts("wsf", term_dir)
    text = _chart_text(written[0])
    assert "InpBroker=wsf" in text
    assert "symbol=EURUSDc" in text


def test_refuse_generic_metatrader_tree(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "MetaTrader 5")
    with pytest.raises(inject.InjectError, match="generic"):
        inject.inject_charts("ftmo", term_dir)


def test_refuse_vantage_and_wrong_brand_name(tmp_path: Path) -> None:
    with pytest.raises(inject.InjectError, match="refusing broker"):
        inject.brand_dir_name("vantage")
    term_dir = _brand_tree(tmp_path, "Vantage International MT5")
    with pytest.raises(inject.InjectError, match="must be"):
        inject.inject_charts("ftmo", term_dir)


def test_missing_ex5_fails_closed(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "FundedNext MT5 Terminal", with_ex5=False)
    with pytest.raises(inject.InjectError, match="Mt5ArchBridge.ex5 missing"):
        inject.inject_charts("fundednext", term_dir)


def test_heartbeat_freshness(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "FundedNext MT5 Terminal")
    assert inject.heartbeat_age_seconds(term_dir) is None
    assert inject.heartbeat_is_fresh(term_dir) is False
    hb = inject.heartbeat_path(term_dir)
    hb.parent.mkdir(parents=True, exist_ok=True)
    hb.write_text("1 version=1.24\n", encoding="utf-8")
    assert inject.heartbeat_is_fresh(term_dir, max_age=60) is True
