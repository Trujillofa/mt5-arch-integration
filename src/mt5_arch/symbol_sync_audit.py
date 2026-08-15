"""Verify a read-only multi-symbol H1 sync audit against the registry.

Does not import research scripts. Does not place orders. Does not invent
an averaged synthetic symbol — each canonical stays its own series.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from mt5_arch.symbol_registry import (
    SymbolRegistry,
    SymbolRegistryError,
    load_registry,
    mappings_for_broker,
    missing_mapped_canonicals,
    resolve,
)

SYNC_AUDIT_SCHEMA = "mt5-symbol-sync-audit/v1"
_TIME_RE = re.compile(
    r"^(\d{4})[.\-](\d{2})[.\-](\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?"
)


def _norm_broker(name: str) -> str:
    return str(name or "").strip().lower()


def _norm_time(value: Any) -> str:
    """Normalize a server-clock stamp to ``YYYY-MM-DD HH:MM:SS`` (no UTC claim)."""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        dt = datetime(1970, 1, 1) + timedelta(seconds=int(value))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    raw = str(value).strip()
    m = _TIME_RE.match(raw)
    if not m:
        return raw
    sec = m.group(6) or "00"
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{sec}"


def _parse_times(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values:
        stamp = _norm_time(item)
        if stamp:
            out.append(stamp)
    return out


def _timestamp_series_errors(canon: str, stamps: list[str], bars: int) -> list[str]:
    """Every mapped row needs a complete, unique, strictly ordered series."""
    errors: list[str] = []
    if not stamps:
        errors.append(f"{canon} missing timestamps")
        return errors
    if len(stamps) != bars:
        errors.append(f"{canon} len(timestamps) {len(stamps)} != bars_h1 {bars}")
    if len(stamps) != len(set(stamps)):
        errors.append(f"{canon} timestamps are not unique")
    for prev, cur in zip(stamps, stamps[1:], strict=False):
        if cur <= prev:
            errors.append(f"{canon} timestamps not strictly ordered ({prev} -> {cur})")
            break
    return errors


def _hour_of(stamp: str) -> str:
    return stamp[:13] if len(stamp) >= 13 else stamp


def _hourly_slots(first: str, last: str) -> list[str]:
    a = datetime.strptime(first, "%Y-%m-%d %H:%M:%S")
    b = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
    if b < a:
        return []
    out: list[str] = []
    t = a
    while t <= b:
        out.append(t.strftime("%Y-%m-%d %H:%M:%S"))
        t += timedelta(hours=1)
    return out


def _raise(errors: list[str]) -> None:
    preview = "\n  ".join(errors[:20])
    extra = f" (+{len(errors) - 20} more)" if len(errors) > 20 else ""
    raise SymbolRegistryError(f"{len(errors)} sync-audit error(s):\n  {preview}{extra}")


def load_package_snapshot(path: Path) -> dict[str, Any]:
    """Normalize a readiness/package compare JSON (not a live MT5 dump)."""
    loc = path / "package_compare.json" if path.is_dir() else path
    raw = json.loads(loc.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SymbolRegistryError("package snapshot must be a JSON object")
    symbols: dict[str, dict[str, Any]] = {}
    raw_syms = raw.get("symbols")
    if isinstance(raw_syms, dict):
        for name, spec in raw_syms.items():
            if not isinstance(spec, dict):
                raise SymbolRegistryError(f"package symbols.{name} must be an object")
            symbols[str(name).strip().upper()] = spec
    elif isinstance(raw_syms, list):
        raise SymbolRegistryError(
            "package snapshot symbols must be a map, not a dump list"
        )
    counts = raw.get("n_bars_per_symbol")
    if isinstance(counts, dict):
        for name, n in counts.items():
            key = str(name).strip().upper()
            symbols.setdefault(key, {})
            symbols[key]["n_rows_h1"] = n
    starts = raw.get("per_symbol_develop_start_server") or raw.get("per_symbol_start")
    ends = raw.get("per_symbol_develop_end_server") or raw.get("per_symbol_end")
    if isinstance(starts, dict):
        for name, stamp in starts.items():
            key = str(name).strip().upper()
            symbols.setdefault(key, {})
            symbols[key].setdefault("time_min_server", stamp)
    if isinstance(ends, dict):
        for name, stamp in ends.items():
            key = str(name).strip().upper()
            symbols.setdefault(key, {})
            symbols[key].setdefault("time_max_server", stamp)
    return {
        "symbols": symbols,
        "n_intersection_timestamps": raw.get("n_intersection_timestamps"),
        "common_start_server": raw.get("common_start_server"),
        "common_end_server": raw.get("common_end_server"),
        "path": str(loc),
    }


def _compare_package(
    *,
    by_canon: dict[str, dict[str, Any]],
    inter: set[str],
    package: dict[str, Any],
    errors: list[str],
) -> None:
    for canon, spec in package.get("symbols", {}).items():
        row = by_canon.get(canon)
        if row is None:
            errors.append(f"package symbol {canon} missing from audit dump")
            continue
        if "n_rows_h1" in spec and int(row.get("bars_h1", -1) or -1) != int(
            spec["n_rows_h1"]
        ):
            errors.append(
                f"{canon} bars_h1 {row.get('bars_h1')} != package {spec['n_rows_h1']}"
            )
        want_first = _norm_time(spec.get("time_min_server"))
        want_last = _norm_time(spec.get("time_max_server"))
        got_first = _norm_time(row.get("first_time"))
        got_last = _norm_time(row.get("last_time"))
        if want_first and got_first != want_first:
            errors.append(f"{canon} first_time {got_first} != package {want_first}")
        if want_last and got_last != want_last:
            errors.append(f"{canon} last_time {got_last} != package {want_last}")
    claimed = package.get("n_intersection_timestamps")
    if claimed is not None and int(claimed) != len(inter):
        errors.append(
            f"intersection count {len(inter)} != package {claimed}"
        )
    pkg_start = _norm_time(package.get("common_start_server"))
    pkg_end = _norm_time(package.get("common_end_server"))
    if inter and pkg_start and min(inter) != pkg_start:
        errors.append(f"intersection first {min(inter)} != package {pkg_start}")
    if inter and pkg_end and max(inter) != pkg_end:
        errors.append(f"intersection last {max(inter)} != package {pkg_end}")


def verify_sync_audit_dump(
    path: Path,
    registry: SymbolRegistry | None = None,
    package: dict[str, Any] | Path | None = None,
) -> dict[str, Any]:
    """Validate an ExportSymbolSyncAudit dump (or a synthetic fixture)."""
    reg = registry or load_registry()
    man_path = path / "manifest.json" if path.is_dir() else path
    raw = json.loads(man_path.read_text(encoding="utf-8"))
    if raw.get("schema") != SYNC_AUDIT_SCHEMA:
        raise SymbolRegistryError(
            f"unsupported sync-audit schema {raw.get('schema')!r}"
        )
    if raw.get("export_ok") is not True:
        raise SymbolRegistryError(
            f"export_ok must be true, got {raw.get('export_ok')!r}"
        )
    broker = _norm_broker(str(raw.get("broker") or ""))
    if broker not in reg.brokers():
        raise SymbolRegistryError(f"dump broker {raw.get('broker')!r} not in registry")
    rows = raw.get("symbols")
    if not isinstance(rows, list) or not rows:
        raise SymbolRegistryError("sync-audit symbols[] is empty")

    errors: list[str] = []
    dump_canons: set[str] = set()
    by_canon: dict[str, dict[str, Any]] = {}
    closed_sets: dict[str, set[str]] = {}
    server_time = _norm_time(raw.get("server_time") or raw.get("time_current"))

    for row in rows:
        if not isinstance(row, dict):
            errors.append("symbol row is not an object")
            continue
        lookup = str(row.get("canonical") or row.get("requested") or "")
        try:
            mapping = resolve(reg, broker, lookup)
        except SymbolRegistryError:
            if str(row.get("error") or "") != "not_in_registry":
                errors.append(
                    f"{lookup!r} is unmapped on {broker} but error="
                    f"{row.get('error')!r} (want not_in_registry)"
                )
            continue
        dump_canons.add(mapping.canonical)
        by_canon[mapping.canonical] = row
        if str(row.get("broker_symbol") or "") != mapping.broker_symbol:
            errors.append(
                f"{mapping.canonical} broker_symbol {row.get('broker_symbol')!r} "
                f"!= registry {mapping.broker_symbol!r}"
            )
        if row.get("selected") is not True:
            errors.append(f"{mapping.canonical} selected is not true")
        if row.get("ok") is not True:
            errors.append(f"{mapping.canonical} ok is not true")
        bars = int(row.get("bars_h1", 0) or 0)
        if bars < 1:
            errors.append(f"{mapping.canonical} bars_h1 < 1")
        first = _norm_time(row.get("first_time"))
        last = _norm_time(row.get("last_time"))
        if not first or not last:
            errors.append(f"{mapping.canonical} missing first_time/last_time")
        stamps = _parse_times(row.get("timestamps"))
        errors.extend(_timestamp_series_errors(mapping.canonical, stamps, bars))
        last_forming = row.get("last_forming") is True
        if (
            last
            and server_time
            and _hour_of(last) == _hour_of(server_time)
            and not last_forming
        ):
            errors.append(
                f"{mapping.canonical} last bar {last} is still forming "
                f"(server_time {server_time}) but last_forming is not true"
            )
        closed = list(stamps)
        if last_forming and closed and closed[-1] == last:
            closed = closed[:-1]
        if stamps:
            if first and stamps[0] != first:
                errors.append(
                    f"{mapping.canonical} timestamps[0] {stamps[0]} != first_time {first}"
                )
            if last and stamps[-1] != last:
                errors.append(
                    f"{mapping.canonical} timestamps[-1] {stamps[-1]} != last_time {last}"
                )
            if first and last:
                slots = _hourly_slots(first, last)
                missing = [s for s in slots if s not in set(stamps)]
                claimed_missing = row.get("n_missing_vs_hourly")
                if claimed_missing is not None and int(claimed_missing) != len(missing):
                    errors.append(
                        f"{mapping.canonical} n_missing_vs_hourly "
                        f"{claimed_missing} != recomputed {len(missing)}"
                    )
            n_spread = int(row.get("n_spread_positive", -1) or -1)
            if n_spread < 0:
                errors.append(f"{mapping.canonical} n_spread_positive missing")
            elif n_spread > bars:
                errors.append(
                    f"{mapping.canonical} n_spread_positive {n_spread} > bars_h1 {bars}"
                )
        # Always include the mapped row in the joint set. A missing series
        # must not drop the symbol from the intersection (HIGH-1).
        closed_sets[mapping.canonical] = set(closed)

    missing = missing_mapped_canonicals(reg, broker, dump_canons)
    if missing:
        errors.append(
            "missing mapped canonical(s) for "
            f"{broker}: {', '.join(missing)}"
        )

    want_joint = set(dump_canons)
    if str(raw.get("source") or "") == "mql5_export":
        want_joint.update(m.canonical for m in mappings_for_broker(reg, broker))
    omitted = sorted(want_joint - set(closed_sets))
    if omitted:
        errors.append(
            "mapped symbol(s) omitted from joint intersection: " + ", ".join(omitted)
        )

    inter: set[str] = set()
    if closed_sets:
        inter = set.intersection(*closed_sets.values())
    if not inter:
        errors.append("joint intersection is empty")
    joint = raw.get("joint") if isinstance(raw.get("joint"), dict) else {}
    claimed_n = joint.get("n_intersection_timestamps") if joint else None
    if claimed_n is not None and int(claimed_n) != len(inter):
        errors.append(
            f"intersection count {len(inter)} != dump joint {claimed_n}"
        )

    pkg: dict[str, Any] | None = None
    if package is not None:
        pkg = (
            load_package_snapshot(package)
            if isinstance(package, Path)
            else package
        )
        if pkg.get("symbols") or pkg.get("n_intersection_timestamps") is not None:
            _compare_package(
                by_canon=by_canon,
                inter=inter,
                package=pkg,
                errors=errors,
            )

    if errors:
        _raise(errors)
    return {
        "ok": True,
        "broker": broker,
        "n_symbols": len(rows),
        "n_mapped": len(dump_canons),
        "n_intersection_timestamps": len(inter),
        "path": str(man_path),
    }
