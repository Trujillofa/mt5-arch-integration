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

from mt5_arch.symbol_registry import SymbolRegistryError, load_registry, resolve

JOURNAL_SCHEMA = "mt5-trade-journal/v1"
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
OVERFLOW_TRANS = -1


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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


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


def _load_overflow(journal_dir: Path) -> dict[str, Any]:
    path = journal_dir / "overflow.json"
    if not path.is_file():
        raise TradeJournalError(f"missing overflow.json in {journal_dir}")
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise TradeJournalError("overflow.json must be a JSON object")
    seqs_raw = raw.get("seqs", [])
    if not isinstance(seqs_raw, list):
        raise TradeJournalError("overflow.seqs must be an array")
    seqs = [_as_id(s) for s in seqs_raw]
    dropped = _as_id(raw.get("dropped"))
    return {
        "dropped": dropped,
        "seqs": seqs,
        "truncated": bool(raw.get("truncated")),
        "raw": raw,
    }


def load_journal(path: Path) -> dict[str, Any]:
    """Load manifest + events + overflow + optional bridge snapshots."""
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

    overflow = _load_overflow(loc)

    return {
        "dir": loc,
        "manifest": manifest,
        "events": events,
        "account": account,
        "positions": positions,
        "overflow": overflow,
    }


def _validate_session_and_sequences(
    manifest: dict[str, Any],
    events: list[dict[str, Any]],
    overflow: dict[str, Any],
    errors: list[str],
) -> str:
    session_id = str(manifest.get("session_id") or "").strip()
    if not session_id:
        errors.append("missing session_id (fresh run directory required)")

    seen_seq: set[int] = set()
    overflow_event_seqs: list[int] = []
    for i, ev in enumerate(events):
        loc = f"events[{i}]"
        ev_session = str(ev.get("session_id") or "").strip()
        if session_id and ev_session != session_id:
            errors.append(
                f"{loc}: session_id {ev_session!r} != manifest {session_id!r} "
                "(appended/restarted history refused)"
            )
        seq = _as_id(ev.get("seq"))
        if seq <= 0:
            errors.append(f"{loc}: seq must be a positive integer")
            continue
        if seq in seen_seq:
            errors.append(f"duplicate seq {seq} (restart/appended history refused)")
            continue
        seen_seq.add(seq)
        if _as_bool(ev.get("overflow")) or _as_id(ev.get("trans_type")) == OVERFLOW_TRANS:
            overflow_event_seqs.append(seq)

    overflow_seqs = [s for s in overflow["seqs"] if s > 0]
    if overflow["dropped"] < 0:
        errors.append("overflow.dropped must be >= 0")
    if overflow["dropped"] != len(overflow_seqs) and not overflow["truncated"]:
        errors.append(
            f"overflow.dropped {overflow['dropped']} != persisted seqs "
            f"{len(overflow_seqs)}"
        )
    if set(overflow_event_seqs) != set(overflow_seqs):
        errors.append(
            "overflow terminals in events must match overflow.json seqs "
            f"(events={sorted(overflow_event_seqs)} file={sorted(overflow_seqs)})"
        )
    if overflow["dropped"] > 0 and not overflow_seqs and not overflow["truncated"]:
        errors.append("overflow.dropped > 0 but no persisted overflow terminals")

    union = set(seen_seq) | set(overflow_seqs)
    if union:
        expect = set(range(1, max(union) + 1))
        missing = sorted(expect - union)
        extra_gap = sorted(s for s in seen_seq if s > 0)
        if missing:
            errors.append(
                f"sequence gap(s) {missing} (contiguous 1..{max(union)} required)"
            )
        jumped = extra_gap != list(range(min(extra_gap), max(extra_gap) + 1))
        if extra_gap and jumped and 999 in extra_gap and 2 not in extra_gap:
            errors.append("sequence gap: seq 2 replaced / jumped to 999")
    return session_id


def _validate_symbol(manifest: dict[str, Any], broker: str, errors: list[str]) -> None:
    symbol = manifest.get("symbol") if isinstance(manifest.get("symbol"), dict) else {}
    requested = str(symbol.get("requested") or "").strip()
    canonical = str(symbol.get("canonical") or "").strip()
    broker_symbol = str(symbol.get("broker_symbol") or "").strip()
    if not requested:
        errors.append("symbol.requested is required")
        return
    if not broker:
        return
    try:
        mapping = resolve(load_registry(), broker, requested)
    except SymbolRegistryError as exc:
        errors.append(f"unresolved symbol: {exc}")
        return
    if canonical and canonical != mapping.canonical:
        errors.append(
            f"symbol.canonical {canonical!r} != registry {mapping.canonical!r}"
        )
    if broker_symbol and broker_symbol != mapping.broker_symbol:
        errors.append(
            f"symbol.broker_symbol {broker_symbol!r} != registry {mapping.broker_symbol!r}"
        )


def verify_journal(path: Path) -> dict[str, Any]:
    """Validate identifier journal. Fail-closed on missing/duplicate/unexpected deals."""
    loaded = load_journal(path)
    manifest = loaded["manifest"]
    events: list[dict[str, Any]] = loaded["events"]
    overflow = loaded["overflow"]
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
    _walk_secrets(overflow["raw"], "overflow", errors)
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

    _validate_symbol(manifest, broker, errors)
    session_id = _validate_session_and_sequences(manifest, events, overflow, errors)

    snapshot_tickets = (
        _position_tickets(loaded["positions"]) if loaded["positions"] is not None else None
    )
    seen_deals: set[int] = set()
    n_deals = 0
    deal_positions: set[int] = set()

    for i, ev in enumerate(events):
        loc = f"events[{i}]"
        if _as_bool(ev.get("overflow")) or _as_id(ev.get("trans_type")) == OVERFLOW_TRANS:
            continue
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
        "session_id": session_id,
        "n_events": len(events),
        "n_deals": n_deals,
        "n_positions": len(deal_positions),
        "n_dropped": overflow["dropped"],
        "correlated": snapshot_tickets is not None,
    }
