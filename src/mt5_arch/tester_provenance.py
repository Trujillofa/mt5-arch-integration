"""Strategy Tester reproducibility / provenance records.

Platform layer only: schema load + verify + hash helpers.
Does not import research harnesses. Does not place orders.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mt5_arch.symbol_registry import SymbolRegistry, SymbolRegistryError, load_registry, resolve

PROVENANCE_SCHEMA = "mt5-tester-provenance/v1"
HISTORY_NOTE = (
    "Multi-currency Strategy Tester results depend on available synchronized "
    "foreign-symbol history; this record is identity, not a quality score."
)

REQUIRED_HASH_KEYS = ("ini", "set", "mql5_expert", "mql5_include", "ex5")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SECRET_KEY_RE = re.compile(r"pass(word|wd)|secret|token|api[_-]?key", re.I)

_MODEL_NAMES = {
    0: "every tick",
    1: "1-minute OHLC",
    2: "open prices only",
    3: "every tick based on real ticks",
    4: "math calculations",
}


class ProvenanceError(Exception):
    """Invalid or incomplete tester provenance record."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value.strip().lower()))


def read_text_auto(path: Path) -> str:
    """Decode UTF-16LE (BOM or even-odd nulls) or UTF-8, as MT5 ini/set files use."""
    raw = path.read_bytes()
    if len(raw) >= 2 and (raw[:2] == b"\xff\xfe" or raw[1] == 0):
        return raw.decode("utf-16-le", "replace")
    return raw.decode("utf-8", "replace")


def parse_ini_map(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in read_text_auto(path).replace("\r", "").split("\n"):
        if "=" not in line or line.lstrip().startswith(";") or line.lstrip().startswith("["):
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip()
    return out


def login_from_common_ini(path: Path, env_login: str = "") -> tuple[int, str]:
    """Return (login, server) from env overlay + common.ini. Login 0 is not resolved."""
    login_s = (env_login or os.environ.get("MT5_LOGIN") or "").strip()
    server = (os.environ.get("MT5_SERVER") or "").strip()
    fields = parse_ini_map(path)
    if (not login_s or login_s == "0") and fields.get("Login") and fields["Login"] != "0":
        login_s = fields["Login"]
    if not server and fields.get("Server"):
        server = fields["Server"]
    try:
        login = int(login_s)
    except (TypeError, ValueError):
        login = 0
    return login, server


def infer_account_type(server: str, explicit: str = "") -> str:
    if explicit:
        return explicit.strip().lower()
    low = (server or "").lower()
    if "demo" in low:
        return "demo"
    if "live" in low or "real" in low:
        return "real"
    if "contest" in low:
        return "contest"
    return "unknown"


def model_name(model: int | str) -> str:
    try:
        return _MODEL_NAMES[int(model)]
    except (TypeError, ValueError, KeyError):
        return "unknown"


def pe_file_version(path: Path) -> str:
    """Best-effort ProductVersion / FileVersion from a PE resource. Empty if unavailable."""
    if not path.is_file():
        return ""
    data = path.read_bytes()
    for label in ("ProductVersion", "FileVersion"):
        needle = (label + "\x00").encode("utf-16-le")
        idx = data.find(needle)
        if idx < 0:
            continue
        rest = data[idx + len(needle) :]
        while rest.startswith(b"\x00\x00"):
            rest = rest[2:]
        chars: list[str] = []
        for off in range(0, min(len(rest), 80), 2):
            pair = rest[off : off + 2]
            if pair == b"\x00\x00":
                break
            chars.append(pair.decode("utf-16-le", "replace"))
        ver = "".join(chars).strip("\x00").strip()
        if ver:
            return ver
    return ""


def parse_mt5_build(version: str) -> int | str:
    parts = re.findall(r"\d+", version or "")
    if parts:
        return int(parts[-1])
    return version or ""


def history_listing_identity(history_dir: Path) -> dict[str, Any]:
    """Identity of a history tree: listing hash, not bar contents."""
    note = HISTORY_NOTE
    if not history_dir.is_dir():
        return {
            "found": False,
            "path": str(history_dir),
            "n_files": 0,
            "listing_sha256": "",
            "note": note,
        }
    rows: list[str] = []
    newest = 0
    for item in sorted(history_dir.rglob("*")):
        if not item.is_file():
            continue
        st = item.stat()
        rel = item.relative_to(history_dir).as_posix()
        rows.append(f"{rel}\t{st.st_size}\t{int(st.st_mtime)}")
        newest = max(newest, int(st.st_mtime))
    listing = "\n".join(rows) + ("\n" if rows else "")
    return {
        "found": True,
        "path": str(history_dir),
        "n_files": len(rows),
        "listing_sha256": sha256_bytes(listing.encode("utf-8")),
        "newest_mtime": newest,
        "note": note,
    }


def find_symbol_history_dir(mt5_dir: Path, server: str, broker_symbol: str) -> Path:
    """Prefer Tester agent bases, then terminal bases. Path may not exist."""
    server_name = (server or "").strip() or "_"
    symbol = (broker_symbol or "").strip() or "_"
    tester = mt5_dir / "Tester" / "bases" / server_name / "history" / symbol
    if tester.is_dir():
        return tester
    terminal = mt5_dir / "bases" / server_name / "history" / symbol
    if terminal.is_dir():
        return terminal
    return tester


def find_latest_report(reports_dir: Path, symbol: str, period: str) -> Path | None:
    if not reports_dir.is_dir():
        return None
    prefix = f"htf_fib_{symbol}_{period}_"
    cands: list[Path] = []
    for path in reports_dir.iterdir():
        name = path.name
        if name.endswith(".provenance.json"):
            continue
        if name.startswith(prefix) or name.startswith(f"{prefix.rstrip('_')}"):
            cands.append(path)
    if not cands:
        cands = [
            p
            for p in reports_dir.glob("htf_fib_*")
            if not p.name.endswith(".provenance.json")
        ]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def provenance_path_for_report(report_path: Path) -> Path:
    if report_path.suffix.lower() in {".htm", ".html", ".xml", ".md"}:
        return report_path.with_name(report_path.stem + ".provenance.json")
    return report_path.with_name(report_path.name + ".provenance.json")


def _raise(errors: list[str]) -> None:
    preview = "\n  ".join(errors[:20])
    extra = f" (+{len(errors) - 20} more)" if len(errors) > 20 else ""
    raise ProvenanceError(f"{len(errors)} provenance error(s):\n  {preview}{extra}")


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


def _as_login(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _resolve_report_path(raw: str, provenance_file: Path) -> Path:
    loc = Path(raw)
    if loc.is_absolute():
        return loc
    return (provenance_file.parent / loc).resolve()


def load_provenance(path: Path) -> dict[str, Any]:
    loc = path / "provenance.json" if path.is_dir() else path
    raw = json.loads(loc.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProvenanceError("provenance must be a JSON object")
    return raw


def verify_provenance(
    path: Path,
    registry: SymbolRegistry | None = None,
) -> dict[str, Any]:
    """Validate a tester provenance record. Fail-closed on missing identity."""
    loc = path / "provenance.json" if path.is_dir() else path
    raw = load_provenance(loc)
    errors: list[str] = []
    if raw.get("schema") != PROVENANCE_SCHEMA:
        raise ProvenanceError(
            f"unsupported provenance schema {raw.get('schema')!r} (need {PROVENANCE_SCHEMA})"
        )
    source = str(raw.get("source") or "")
    if source not in {"synthetic", "mql5_export"}:
        errors.append(f"source {source!r} must be synthetic or mql5_export")

    _walk_secrets(raw, "", errors)

    login = _as_login((raw.get("account") or {}).get("login") if isinstance(raw.get("account"), dict) else 0)
    if login == 0:
        errors.append("Login=0 (account not specified)")

    broker = str(raw.get("broker") or "").strip().lower()
    if not broker:
        errors.append("empty broker")

    symbol = raw.get("symbol") if isinstance(raw.get("symbol"), dict) else {}
    requested = str(symbol.get("requested") or symbol.get("canonical") or "").strip()
    broker_symbol = str(symbol.get("broker_symbol") or "").strip()
    if not requested:
        errors.append("unresolved symbol (requested is empty)")

    if broker and requested:
        try:
            mapping = resolve(registry or load_registry(), broker, requested)
            if broker_symbol and broker_symbol != mapping.broker_symbol:
                errors.append(
                    f"broker_symbol {broker_symbol!r} != registry {mapping.broker_symbol!r}"
                )
        except SymbolRegistryError as exc:
            errors.append(f"unresolved symbol: {exc}")

    hashes = raw.get("hashes") if isinstance(raw.get("hashes"), dict) else {}
    if not hashes:
        errors.append("missing hashes")
    else:
        for key in REQUIRED_HASH_KEYS:
            digest = hashes.get(key)
            if digest is None or digest == "":
                errors.append(f"missing hash {key}")
            elif not is_sha256_hex(digest):
                errors.append(f"hash {key} is not a 64-char sha256 hex")

    tester = raw.get("tester") if isinstance(raw.get("tester"), dict) else {}
    if tester.get("model") in (None, ""):
        errors.append("tester.model is required")
    if not tester.get("from_date") or not tester.get("to_date"):
        errors.append("tester date window is required")

    history = raw.get("history")
    if not isinstance(history, dict) or not history:
        errors.append("history identity is required")
    elif history.get("found") is True and not is_sha256_hex(history.get("listing_sha256")):
        errors.append("history.listing_sha256 missing or invalid while found=true")

    report_raw = str(raw.get("report_path") or "").strip()
    if source == "mql5_export":
        if not report_raw:
            errors.append("report_path is required when source=mql5_export")
        else:
            report = _resolve_report_path(report_raw, loc)
            if not report.exists():
                errors.append(f"report path does not exist: {report}")
        for key in ("parity_trace_path", "sync_audit_path"):
            extra = raw.get(key)
            if extra:
                extra_path = _resolve_report_path(str(extra), loc)
                if not extra_path.exists():
                    errors.append(f"{key} does not exist: {extra_path}")

    if errors:
        _raise(errors)
    return {
        "ok": True,
        "schema": PROVENANCE_SCHEMA,
        "source": source,
        "broker": broker,
        "login": login,
        "path": str(loc),
    }


def build_provenance(
    *,
    source: str,
    broker: str,
    requested: str,
    login: int | str,
    server: str,
    period: str,
    model: int | str,
    from_date: str,
    to_date: str,
    report_path: str | Path,
    hashes: dict[str, str] | None = None,
    ini_path: Path | None = None,
    set_path: Path | None = None,
    mql5_expert_path: Path | None = None,
    mql5_include_path: Path | None = None,
    ex5_path: Path | None = None,
    account_type: str = "",
    terminal_name: str = "",
    terminal_path: str = "",
    terminal_build: int | str = "",
    terminal_company: str = "",
    wine_version: str = "",
    deposit: int | str = 10000,
    leverage: str = "1:100",
    currency: str = "USD",
    expert: str = "ForexHtfFibTester",
    max_spread_pips: float | str = 0,
    slippage_points: int | str = 50,
    spread_mode: str = "tester_current",
    history: dict[str, Any] | None = None,
    parity_trace_path: str | None = None,
    sync_audit_path: str | None = None,
    registry: SymbolRegistry | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Assemble a provenance document. Does not write secrets."""
    reg = registry or load_registry()
    mapping = resolve(reg, broker, requested)
    digest = dict(hashes or {})
    path_for = {
        "ini": ini_path,
        "set": set_path,
        "mql5_expert": mql5_expert_path,
        "mql5_include": mql5_include_path,
        "ex5": ex5_path,
    }
    for key, file_path in path_for.items():
        if key in digest:
            continue
        if file_path is None or not Path(file_path).is_file():
            raise ProvenanceError(f"cannot hash {key}: file missing ({file_path})")
        digest[key] = sha256_file(Path(file_path))

    login_i = _as_login(login)
    try:
        model_i: int | str = int(model)
    except (TypeError, ValueError):
        model_i = model
    hist = dict(history) if history else {"found": False, "path": "", "n_files": 0, "listing_sha256": "", "note": HISTORY_NOTE}
    if "note" not in hist:
        hist["note"] = HISTORY_NOTE

    return {
        "schema": PROVENANCE_SCHEMA,
        "source": source,
        "recorded_at": recorded_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "terminal": {
            "name": terminal_name,
            "path": terminal_path,
            "build": terminal_build,
            "company": terminal_company,
            "wine_version": wine_version,
        },
        "account": {
            "login": login_i,
            "server": server,
            "type": infer_account_type(server, account_type),
        },
        "broker": mapping.broker,
        "symbol": {
            "requested": requested,
            "canonical": mapping.canonical,
            "broker_symbol": mapping.broker_symbol,
        },
        "tester": {
            "expert": expert,
            "period": period,
            "model": model_i,
            "model_name": model_name(model_i),
            "from_date": from_date,
            "to_date": to_date,
            "deposit": int(deposit) if str(deposit).isdigit() else deposit,
            "leverage": leverage,
            "currency": currency,
        },
        "hashes": {key: digest[key] for key in REQUIRED_HASH_KEYS},
        "history": hist,
        "costs": {
            "spread_mode": spread_mode,
            "max_spread_pips": float(max_spread_pips),
            "slippage_points": int(slippage_points),
            "commission": None,
        },
        "report_path": str(report_path),
        "parity_trace_path": parity_trace_path or None,
        "sync_audit_path": sync_audit_path or None,
    }


def write_provenance(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def record_tester_run(
    out_path: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build, write, and verify a provenance file."""
    doc = build_provenance(**kwargs)
    write_provenance(out_path, doc)
    return verify_provenance(out_path)
