"""Read-only OnTradeTransaction journal: load + verify identifiers.

Platform layer only. Does not import research harnesses. Does not place orders.
A live OnTradeTransaction attach is not claimed here.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

JOURNAL_SCHEMA = "mt5-trade-journal/v1"
KNOWN_BROKERS = frozenset({"vantage", "fpmarkets", "exness", "wsf"})
_SECRET_KEY_RE = re.compile(r"pass(word|wd)|secret|token|api[_-]?key", re.I)

# ENUM_TRADE_TRANSACTION_TYPE (MQL5)
TRANS_TYPES = {
    0: "TRADE_TRANSACTION_ORDER_ADD",
    1: "TRADE_TRANSACTION_ORDER_UPDATE",
    2: "TRADE_TRANSACTION_ORDER_DELETE",
    3: "TRADE_TRANSACTION_DEAL_ADD",
    4: "TRADE_TRANSACTION_DEAL_UPDATE",
    5: "TRADE_TRANSACTION_DEAL_DELETE",
    6: "TRADE_TRANSACTION_HISTORY_ADD",
    7: "TRADE_TRANSACTION_HISTORY_UPDATE",
    8: "TRADE_TRANSACTION_HISTORY_DELETE",
    9: "TRADE_TRANSACTION_POSITION",
    10: "TRADE_TRANSACTION_REQUEST",
}
DEAL_ADD = 3
DEAL_DELETE = 5


class TradeJournalError(Exception):
    """Invalid or inconsistent trade-transaction journal."""


def _raise(errors: list[str]) -> None:
    preview = "\n  ".join(errors[:20])
    extra = f" (+{len(errors) - 20} more)" if len(errors) > 20 else ""
    raise TradeJournalError(f"{len(errors)} trade-journal error(s):\n  {preview}{extra}")


def _walk_secrets(obj: Any, trail: str, errors: list[str]) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            loc = f"{trail}.{key}" if trail else str(key)
            if _SECRET_KEY_RE.search(str(key)):
                errors.append(f"secret key {loc} is forbidden")
            _walk_secrets(val, loc, errors)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            _walk_secrets(val, f"{trail}[{i}]", errors)


def _as_id(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_login(value: Any) -> int:
    return _as_id(value)


def _journal_dir(path: Path) -> Path:
    loc = Path(path)
    if loc.is_file():
        return loc.parent
    return loc


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_events_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise TradeJournalError(f"{path.name}:{line_no} is not a JSON object")
        events.append(row)
    return events


def _load_events_csv(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            events.append(dict(row))
    return events


def _find_snapshot(journal_dir: Path, name: str) -> Path | None:
    here = journal_dir / name
    if here.is_file():
        return here
    parent = journal_dir.parent / name
    if parent.is_file():
        return parent
    return None


def _position_tickets(snapshot: Any) -> set[int]:
    rows: list[Any]
    if isinstance(snapshot, dict):
        raw = snapshot.get("positions", snapshot.get("open", []))
        rows = raw if isinstance(raw, list) else []
    elif isinstance(snapshot, list):
        rows = snapshot
    else:
        rows = []
    tickets: set[int] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticket = _as_id(row.get("ticket", row.get("position", row.get("id"))))
        if ticket:
            tickets.add(ticket)
    return tickets


def load_journal(path: Path) -> dict[str, Any]:
    """Load manifest + events + optional bridge snapshots."""
    loc = _journal_dir(path)
    manifest_path = loc / "manifest.json"
    if not manifest_path.is_file():
        raise TradeJournalError(f"missing manifest.json in {loc}")
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise TradeJournalError("manifest must be a JSON object")

    jsonl = loc / "events.jsonl"
    csv_path = loc / "events.csv"
    if jsonl.is_file():
        events = _load_events_jsonl(jsonl)
    elif csv_path.is_file():
        events = _load_events_csv(csv_path)
    else:
        raise TradeJournalError(f"missing events.jsonl or events.csv in {loc}")

    account = None
    account_path = _find_snapshot(loc, "account.json")
    if account_path is not None:
        account = _read_json(account_path)
        if not isinstance(account, dict):
            raise TradeJournalError("account.json must be a JSON object")

    positions = None
    positions_path = _find_snapshot(loc, "positions.json")
    if positions_path is not None:
        positions = _read_json(positions_path)

    return {
        "dir": loc,
        "manifest": manifest,
        "events": events,
        "account": account,
        "positions": positions,
    }


def verify_journal(path: Path) -> dict[str, Any]:
    """Validate identifier journal. Fail-closed on missing/duplicate/unexpected deals."""
    loaded = load_journal(path)
    manifest = loaded["manifest"]
    events: list[dict[str, Any]] = loaded["events"]
    errors: list[str] = []

    if manifest.get("schema") != JOURNAL_SCHEMA:
        raise TradeJournalError(
            f"unsupported journal schema {manifest.get('schema')!r} (need {JOURNAL_SCHEMA})"
        )
    source = str(manifest.get("source") or "")
    if source not in {"synthetic", "mql5_export"}:
        errors.append(f"source {source!r} must be synthetic or mql5_export")

    _walk_secrets(manifest, "manifest", errors)
    _walk_secrets(events, "events", errors)
    if loaded["account"] is not None:
        _walk_secrets(loaded["account"], "account", errors)
    if loaded["positions"] is not None:
        _walk_secrets(loaded["positions"], "positions", errors)

    account = manifest.get("account") if isinstance(manifest.get("account"), dict) else {}
    login = _as_login(account.get("login"))
    if loaded["account"] is not None:
        snap_login = _as_login(loaded["account"].get("login"))
        if snap_login and login and snap_login != login:
            errors.append(f"account snapshot login {snap_login} != manifest login {login}")
        if login == 0:
            login = snap_login
    if login == 0:
        errors.append("Login=0 (account not specified)")

    broker = str(manifest.get("broker") or "").strip().lower()
    if not broker:
        errors.append("empty broker")
    elif broker not in KNOWN_BROKERS:
        errors.append(f"unknown broker {broker!r}")

    snapshot_tickets = (
        _position_tickets(loaded["positions"]) if loaded["positions"] is not None else None
    )
    seen_deals: set[int] = set()
    n_deals = 0
    deal_positions: set[int] = set()

    for i, ev in enumerate(events):
        loc = f"events[{i}]"
        trans_type = _as_id(ev.get("trans_type"))
        deal_id = _as_id(ev.get("deal"))
        position = _as_id(ev.get("position"))
        if trans_type not in TRANS_TYPES:
            errors.append(f"{loc}: unexpected trans_type {trans_type}")
            continue
        if trans_type == DEAL_ADD:
            n_deals += 1
            if deal_id == 0:
                errors.append(f"{loc}: DEAL_ADD missing deal id")
            elif deal_id in seen_deals:
                errors.append(f"duplicate deal id {deal_id}")
            else:
                seen_deals.add(deal_id)
            if position == 0:
                errors.append(f"missing position after deal {deal_id or '?'}")
            else:
                deal_positions.add(position)
                if snapshot_tickets is not None and position not in snapshot_tickets:
                    errors.append(
                        f"missing position after deal {deal_id}: position {position} not in snapshot"
                    )
        elif trans_type == DEAL_DELETE:
            if deal_id == 0 or deal_id not in seen_deals:
                errors.append(
                    f"unexpected state transition: DEAL_DELETE {deal_id or '?'} without DEAL_ADD"
                )

    if errors:
        _raise(errors)

    return {
        "ok": True,
        "schema": JOURNAL_SCHEMA,
        "source": source,
        "broker": broker,
        "login": login,
        "n_events": len(events),
        "n_deals": n_deals,
        "n_positions": len(deal_positions),
        "correlated": snapshot_tickets is not None,
    }
