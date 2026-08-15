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
    assert report["n_dropped"] == 0
    assert report["session_id"] == "run-1755129600-84000001-1"
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
    assert "HistoryDealGetInteger" in text
    assert "DEAL_ENTRY" in text
    handler = _handler_body(text)
    assert "HistoryDealGetInteger" not in handler
    assert "HistorySelect" not in handler
    assert "DEAL_ENTRY" not in handler
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


def test_open_close_round_trip_empty_snapshot_ok(tmp_path: Path):
    """Close (DEAL_ENTRY_OUT) must not require the position in the snapshot."""
    dest = _clone(tmp_path)
    rows = []
    for line in dest.joinpath("events.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("trans_type") == 3 and row.get("deal") == 2001:
            row["deal_entry"] = 0  # DEAL_ENTRY_IN
        rows.append(row)
    rows.append(
        {
            "seq": 6,
            "session_id": "run-1755129600-84000001-1",
            "time": "2026.08.14 12:00:02",
            "trans_type": 3,
            "request_id": 1,
            "order": 1002,
            "deal": 2002,
            "position": 3001,
            "position_by": 0,
            "symbol": "XAUUSD",
            "order_type": 1,
            "deal_type": 1,
            "deal_entry": 1,  # DEAL_ENTRY_OUT
            "order_state": 0,
            "overflow": False,
        }
    )
    dest.joinpath("events.jsonl").write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n",
        encoding="utf-8",
    )
    dest.joinpath("positions.json").write_text(
        json.dumps({"positions": []}), encoding="utf-8"
    )
    report = verify_journal(dest)
    assert report["ok"] is True
    assert report["n_deals"] == 2
    assert report["n_positions"] == 1


def test_unparseable_trans_type_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    rows = []
    for line in dest.joinpath("events.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("trans_type") == 3:
            row["trans_type"] = "ORDER_ADD"
        rows.append(json.dumps(row, separators=(",", ":")))
    dest.joinpath("events.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(TradeJournalError, match="unparseable trans_type"):
        verify_journal(dest)


def test_absent_trans_type_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    rows = []
    for line in dest.joinpath("events.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("trans_type") == 3:
            del row["trans_type"]
        rows.append(json.dumps(row, separators=(",", ":")))
    dest.joinpath("events.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(TradeJournalError, match="missing trans_type"):
        verify_journal(dest)


def test_secret_key_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    raw = json.loads(dest.joinpath("manifest.json").read_text(encoding="utf-8"))
    raw["account"]["password"] = "nope"
    dest.joinpath("manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(TradeJournalError, match="secret key"):
        verify_journal(dest)


def test_secret_value_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    raw = json.loads(dest.joinpath("manifest.json").read_text(encoding="utf-8"))
    raw["note"] = "password=nope"
    dest.joinpath("manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(TradeJournalError, match="secret value"):
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
        "seq": 6,
        "session_id": "run-1755129600-84000001-1",
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
        "overflow": False,
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


def test_sequence_gap_999_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    rows = []
    for line in dest.joinpath("events.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("seq") == 2:
            row["seq"] = 999
        rows.append(json.dumps(row, separators=(",", ":")))
    dest.joinpath("events.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(TradeJournalError, match="sequence gap"):
        verify_journal(dest)


def test_restart_appended_history_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    restart = {
        "seq": 1,
        "session_id": "run-1755129999-84000001-2",
        "time": "2026.08.14 13:00:00",
        "trans_type": 10,
        "request_id": 2,
        "order": 0,
        "deal": 0,
        "position": 0,
        "position_by": 0,
        "symbol": "XAUUSD",
        "order_type": 0,
        "deal_type": 0,
        "order_state": 0,
        "overflow": False,
    }
    with dest.joinpath("events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(restart, separators=(",", ":")) + "\n")
    with pytest.raises(TradeJournalError, match="session_id|duplicate seq|appended"):
        verify_journal(dest)


def test_sequence_reset_same_session_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    reset = {
        "seq": 1,
        "session_id": "run-1755129600-84000001-1",
        "time": "2026.08.14 13:00:00",
        "trans_type": 10,
        "request_id": 2,
        "order": 0,
        "deal": 0,
        "position": 0,
        "position_by": 0,
        "symbol": "XAUUSD",
        "order_type": 0,
        "deal_type": 0,
        "order_state": 0,
        "overflow": False,
    }
    with dest.joinpath("events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(reset, separators=(",", ":")) + "\n")
    with pytest.raises(TradeJournalError, match="duplicate seq"):
        verify_journal(dest)


def test_overflow_without_persisted_terminals_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    dest.joinpath("overflow.json").write_text(
        json.dumps({"dropped": 3, "seqs": [], "truncated": False}),
        encoding="utf-8",
    )
    with pytest.raises(TradeJournalError, match="overflow"):
        verify_journal(dest)


def test_overflow_terminals_contiguous_ok(tmp_path: Path):
    dest = _clone(tmp_path)
    terminal = {
        "seq": 6,
        "session_id": "run-1755129600-84000001-1",
        "time": "2026.08.14 12:00:02",
        "trans_type": -1,
        "request_id": 0,
        "order": 0,
        "deal": 0,
        "position": 0,
        "position_by": 0,
        "symbol": "",
        "order_type": 0,
        "deal_type": 0,
        "order_state": 0,
        "overflow": True,
    }
    with dest.joinpath("events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(terminal, separators=(",", ":")) + "\n")
    dest.joinpath("overflow.json").write_text(
        json.dumps({"dropped": 1, "seqs": [6], "truncated": False}),
        encoding="utf-8",
    )
    report = verify_journal(dest)
    assert report["ok"] is True
    assert report["n_dropped"] == 1
    assert report["session_id"] == "run-1755129600-84000001-1"


def test_missing_overflow_file_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    dest.joinpath("overflow.json").unlink()
    with pytest.raises(TradeJournalError, match="overflow.json"):
        verify_journal(dest)


def test_missing_session_id_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    raw = json.loads(dest.joinpath("manifest.json").read_text(encoding="utf-8"))
    del raw["session_id"]
    dest.joinpath("manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(TradeJournalError, match="session_id"):
        verify_journal(dest)


def test_exness_eurusd_manifest_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    raw = json.loads(dest.joinpath("manifest.json").read_text(encoding="utf-8"))
    raw["broker"] = "exness"
    raw["symbol"] = {
        "requested": "EURUSD",
        "canonical": "EURUSD",
        "broker_symbol": "EURUSD",
    }
    dest.joinpath("manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(TradeJournalError, match="unresolved symbol"):
        verify_journal(dest)


def test_canonical_mismatch_refuses(tmp_path: Path):
    dest = _clone(tmp_path)
    raw = json.loads(dest.joinpath("manifest.json").read_text(encoding="utf-8"))
    raw["symbol"]["canonical"] = "EURUSD"
    dest.joinpath("manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(TradeJournalError, match="canonical"):
        verify_journal(dest)


def test_ea_refuses_any_broker_fallback_and_overwrites():
    text = EA.read_text(encoding="utf-8")
    assert "FxCanonicalFromBrokerSymbolAny" not in text
    assert "FxRegistryLookup" in text
    assert "INIT_PARAMETERS_INCORRECT" in text
    assert "INIT_FAILED" in text
    assert "refuse overwrite" in text
    assert "session_id" in text
    assert "overflow.json" in text
    assert "RecordOverflow" in text
    assert "g_session" in text
    assert "MakeSessionId" in text


def test_python_uses_registry_resolve():
    text = MODULE.read_text(encoding="utf-8")
    assert "from mt5_arch.symbol_registry import" in text
    assert "resolve(" in text
    assert "KNOWN_BROKERS" not in text
