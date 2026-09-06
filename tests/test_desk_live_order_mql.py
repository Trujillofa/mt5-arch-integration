"""Keep the two Seven Desk one-shot history helpers in lockstep."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WSF = ROOT / "apps" / "seven-desk" / "mql5" / "WsfDeskLiveOrder.mq5"
DESK = ROOT / "apps" / "seven-desk" / "mql5" / "DeskLiveOrder.mq5"


def _fill_fn(source: str) -> str:
    start = source.index("void FillDealsFromHistory")
    end = source.index("bool SendDeal", start)
    return source[start:end]


def test_fill_deals_from_history_is_shared() -> None:
    assert _fill_fn(WSF.read_text(encoding="utf-8")) == _fill_fn(
        DESK.read_text(encoding="utf-8")
    )
    text = _fill_fn(WSF.read_text(encoding="utf-8"))
    assert "HistorySelectByPosition" in text
    assert "DEAL_ENTRY_OUT_BY" in text
    assert "need_close" in text


def test_desk_live_order_creates_dir_and_falls_back_to_file_common() -> None:
    text = DESK.read_text(encoding="utf-8")
    assert "FolderCreate(\"mt5_arch\")" in text
    assert "FILE_COMMON" in text
    assert "SymbolIsSynchronized" in text
    assert "ACCOUNT_MARGIN_MODE_RETAIL_NETTING" in text
    assert "BTCUSD" in text
    assert "SymbolAllowed" in text
    assert "WaitConnected(20000)" in text
    assert "WaitSymbolReady(symbol, 20000)" in text
    assert "AlreadyClaimed" in text
    assert "REQUEST_TTL_SEC" in text
    assert (
        "return (g_expect_login > 0 && AccountInfoInteger(ACCOUNT_LOGIN) == g_expect_login)"
        not in text
    )
