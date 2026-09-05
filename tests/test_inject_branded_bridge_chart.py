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


def test_inject_alphacapital_writes_inpbroker(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "ACG Markets MT5 Terminal")
    written = inject.inject_charts("alphacapital", term_dir)
    text = _chart_text(written[0])
    assert "InpBroker=alphacapital" in text
    assert "symbol=BTCUSD" in text
    assert "InpDumpHistory=false" in text
    assert "InpSymbols=BTCUSD,BTCUSDc,BTCUSD.r,EURUSD" in text


def test_inject_alphacapital_quotes_first_omits_expert(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "ACG Markets MT5 Terminal")
    written = inject.inject_charts("alphacapital", term_dir, with_expert=False)
    text = _chart_text(written[0])
    assert "symbol=BTCUSD" in text
    assert "Mt5ArchBridge" not in text
    assert "<expert>" not in text


def test_quotes_ready_sees_history_hcc(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "ACG Markets MT5 Terminal")
    assert inject.quotes_ready(term_dir, "EURUSD") is False
    hcc = term_dir / "Bases" / "Default" / "History" / "EURUSD" / "2026.hcc"
    hcc.parent.mkdir(parents=True, exist_ok=True)
    hcc.write_bytes(b"hcc")
    assert inject.quotes_ready(term_dir, "EURUSD") is True


def test_quotes_ready_btc_counts_for_alphacapital(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "ACG Markets MT5 Terminal")
    assert inject.quotes_ready(term_dir, "EURUSD") is False
    hcc = term_dir / "Bases" / "ACGMarkets-Main" / "history" / "BTCUSD" / "2026.hcc"
    hcc.parent.mkdir(parents=True, exist_ok=True)
    hcc.write_bytes(b"hcc")
    assert inject.quotes_ready(term_dir, "BTCUSD") is True
    assert any(inject.quotes_ready(term_dir, symbol) for symbol in inject.ALPHA_QUOTE_SYMBOLS)


def test_inject_fundingpips_writes_inpbroker(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "FundingPips 2 MT5 Terminal")
    written = inject.inject_charts("fundingpips", term_dir)
    text = _chart_text(written[0])
    assert "InpBroker=fundingpips" in text
    assert "symbol=EURUSD" in text
    assert "Mt5ArchBridge" in text


def test_inject_fundingpips_quotes_first_omits_expert(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "FundingPips 2 MT5 Terminal")
    written = inject.inject_charts("fundingpips", term_dir, with_expert=False)
    text = _chart_text(written[0])
    assert "symbol=EURUSD" in text
    assert "Mt5ArchBridge" not in text
    assert "<expert>" not in text


def test_quotes_ready_btcusd_matches_pro_folder(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "ACG Markets MT5 Terminal")
    hcc = term_dir / "Bases" / "ACGMarkets-Main" / "history" / "BTCUSD.pro" / "2026.hcc"
    hcc.parent.mkdir(parents=True, exist_ok=True)
    hcc.write_bytes(b"hcc")
    assert inject.quotes_ready(term_dir, "BTCUSD") is True
    assert inject.quotes_ready(term_dir, "BTCUSD.pro") is True
    assert inject.quotes_ready(term_dir, "EURUSD") is False


def test_quotes_ready_audcad_pro_counts_for_alphacapital(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "ACG Markets MT5 Terminal")
    hcc = term_dir / "Bases" / "ACGMarkets-Main" / "history" / "AUDCAD.pro" / "2026.hcc"
    hcc.parent.mkdir(parents=True, exist_ok=True)
    hcc.write_bytes(b"hcc")
    assert inject.quotes_ready(term_dir, "AUDCAD.pro") is True
    assert inject.alpha_ready_symbol(term_dir) == "AUDCAD.pro"
    assert any(inject.quotes_ready(term_dir, symbol) for symbol in inject.ALPHA_QUOTE_SYMBOLS)


def test_inject_alphacapital_expert_uses_ready_pro_symbol(tmp_path: Path) -> None:
    term_dir = _brand_tree(tmp_path, "ACG Markets MT5 Terminal")
    hcc = term_dir / "Bases" / "ACGMarkets-Main" / "history" / "AUDCAD.pro" / "2026.hcc"
    hcc.parent.mkdir(parents=True, exist_ok=True)
    hcc.write_bytes(b"hcc")
    extra = term_dir / "MQL5" / "Profiles" / "Charts" / "Default" / "chart08.chr"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"stale")
    written = inject.inject_charts("alphacapital", term_dir, with_expert=True)
    text = _chart_text(written[0])
    assert "symbol=AUDCAD.pro" in text
    assert "Mt5ArchBridge" in text
    assert not extra.exists()


def test_prune_default_chart_siblings_is_alpha_only(tmp_path: Path) -> None:
    """WSF/FTMO/FN/FundingPips must not delete leftover Default tabs; Alpha must."""
    leftover = b"stale-tab"
    cases = (
        ("wsf", "WSFmarkets MT5 Terminal"),
        ("ftmo", "FTMO Global Markets MT5 Terminal"),
        ("fundednext", "FundedNext MT5 Terminal"),
        ("fundingpips", "FundingPips 2 MT5 Terminal"),
    )
    for broker, brand in cases:
        term_dir = _brand_tree(tmp_path / broker, brand)
        extra = term_dir / "MQL5" / "Profiles" / "Charts" / "Default" / "chart08.chr"
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_bytes(leftover)
        order = extra.parent / "order.wnd"
        order.write_bytes(b"keep-me")
        inject.inject_charts(broker, term_dir)
        assert extra.is_file() and extra.read_bytes() == leftover
        assert order.read_bytes() == b"keep-me"

    alpha = _brand_tree(tmp_path / "alphacapital", "ACG Markets MT5 Terminal")
    extra = alpha / "MQL5" / "Profiles" / "Charts" / "Default" / "chart08.chr"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(leftover)
    order = extra.parent / "order.wnd"
    order.write_bytes(b"keep-me")
    inject.inject_charts("alphacapital", alpha)
    assert not extra.exists()
    assert order.read_bytes() == b"\xff\xfe" + "chart01.chr\r\n".encode("utf-16-le")


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
