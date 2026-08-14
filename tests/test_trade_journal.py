"""Offline OnTradeTransaction journal: identifiers, no live attach, no orders."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from mt5_arch.trade_journal import TradeJournalError, verify_journal

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "mql5" / "Experts" / "TradeTransactionJournal.mq5"
MODULE = ROOT / "src" / "mt5_arch" / "trade_journal.py"
VERIFY = ROOT / "scripts" / "verify_trade_journal.py"
INSTALLER = ROOT / "scripts" / "18-install-forex-indicator.sh"
OFFLINE = ROOT / "tests" / "fixtures" / "trade_journal" / "offline_ok"

_HANDLER_FORBIDDEN = (
    "OrderSend",
    "OrderSendAsync",
    "CTrade",
    "FileOpen",
    "FileWrite",
    "FileWriteString",
    "WebRequest",
    "Socket",
    "HistorySelect",
    "HistoryDealGet",
    "PositionsTotal",
    "OrdersTotal",
    "SymbolSelect",
    "for(",
    "while(",
    "Sleep(",
)


def _handler_body(text: str) -> str:
    start = text.index("void OnTradeTransaction")
    end = text.find("//+------------------------------------------------------------------+", start + 10)
    return text[start:end] if end > 0 else text[start:]


def _clone(tmp_path: Path) -> Path:
    dest = tmp_path / "journal"
    shutil.copytree(OFFLINE, dest)
    return dest


def test_offline_synthetic_fixture():
    report = verify_journal(OFFLINE)
    assert report["ok"] is True
    assert report["source"] == "synthetic"
    assert report["broker"] == "vantage"
    assert report["login"] == 84000001
    assert report["n_deals"] == 1
    assert report["n_positions"] == 1
    assert report["correlated"] is True


def test_platform_layer_does_not_import_research():
    imports = [
        line
        for line in MODULE.read_text(encoding="utf-8").splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    joined = "\n".join(imports)
    assert "xau_" not in joined
    assert "backtest" not in joined
    assert "htf_fib" not in joined
    assert "OrderSend" not in MODULE.read_text(encoding="utf-8")
    assert "order_send" not in MODULE.read_text(encoding="utf-8")


def test_ea_is_read_only_and_handler_is_small():
    text = EA.read_text(encoding="utf-8")
    assert "OrderSend(" not in text
    assert "OrderSendAsync(" not in text
    assert "CTrade" not in text
    assert "#include <Trade/Trade.mqh>" not in text
    assert "WebRequest" not in text
    assert "InpBroker" in text
    assert "FxSymbolRegistry" in text
    assert "FxRegistryLookup" in text
    assert "mt5_arch\\journal" in text or "mt5_arch/journal" in text
    handler = _handler_body(text)
    for needle in _HANDLER_FORBIDDEN:
        assert needle not in handler, f"{needle} must not appear in OnTradeTransaction"
    body_lines = [
        line
        for line in handler.splitlines()
        if line.strip() and not line.strip().startswith("//")
    ]
    assert len(body_lines) <= 30


def test_installer_copies_journal_ea():
    text = INSTALLER.read_text(encoding="utf-8")
    assert "TradeTransactionJournal.mq5" in text
    assert "OrderSend" not in text


def test_duplicate_deal_id_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    events = dest.joinpath("events.jsonl").read_text(encoding="utf-8")
    deal_line = [ln for ln in events.splitlines() if '"trans_type":3' in ln][0]
    dest.joinpath("events.jsonl").write_text(events + deal_line + "\n", encoding="utf-8")
    with pytest.raises(TradeJournalError, match="duplicate deal id"):
        verify_journal(dest)


def test_missing_position_after_deal_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    rows = []
    for line in dest.joinpath("events.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("trans_type") == 3:
            row["position"] = 0
        rows.append(json.dumps(row, separators=(",", ":")))
    dest.joinpath("events.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(TradeJournalError, match="missing position after deal"):
        verify_journal(dest)


def test_missing_position_in_snapshot_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    dest.joinpath("positions.json").write_text(
        json.dumps({"positions": []}), encoding="utf-8"
    )
    with pytest.raises(TradeJournalError, match="missing position after deal"):
        verify_journal(dest)


def test_secret_key_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    raw = json.loads(dest.joinpath("manifest.json").read_text(encoding="utf-8"))
    raw["account"]["password"] = "nope"
    dest.joinpath("manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(TradeJournalError, match="secret key"):
        verify_journal(dest)


def test_committed_fixture_has_no_secrets():
    for path in OFFLINE.iterdir():
        text = path.read_text(encoding="utf-8").lower()
        assert "password" not in text
        assert "mt5_password" not in text
        assert "api_key" not in text


def test_unexpected_deal_delete_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    extra = {
        "seq": 99,
        "time": "2026.08.14 12:00:02",
        "trans_type": 5,
        "request_id": 1,
        "order": 0,
        "deal": 9999,
        "position": 0,
        "position_by": 0,
        "symbol": "XAUUSD",
        "order_type": 0,
        "deal_type": 0,
        "order_state": 0,
    }
    with dest.joinpath("events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(extra, separators=(",", ":")) + "\n")
    with pytest.raises(TradeJournalError, match="unexpected state transition"):
        verify_journal(dest)


def test_empty_broker_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    raw = json.loads(dest.joinpath("manifest.json").read_text(encoding="utf-8"))
    raw["broker"] = ""
    dest.joinpath("manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(TradeJournalError, match="empty broker"):
        verify_journal(dest)


def test_login_zero_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    raw = json.loads(dest.joinpath("manifest.json").read_text(encoding="utf-8"))
    raw["account"]["login"] = 0
    dest.joinpath("manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    dest.joinpath("account.json").write_text(
        json.dumps({"login": 0, "server": "Synthetic-Demo"}), encoding="utf-8"
    )
    with pytest.raises(TradeJournalError, match="Login=0"):
        verify_journal(dest)


def test_tests_and_verifier_never_place_orders():
    for path in (MODULE, VERIFY):
        text = path.read_text(encoding="utf-8")
        assert "OrderSend" not in text
        assert "order_send" not in text
    assert "OrderSend(" not in EA.read_text(encoding="utf-8")


def test_verify_cli_default_fixture():
    proc = subprocess.run(
        ["python3", str(VERIFY)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "PASSED" in proc.stdout
