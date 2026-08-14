"""Explicit broker → symbol registry. No fuzzy first-match.

Source of truth: ``config/symbols/registry.json``.
The generated MQL5 include must stay byte-identical (see ``write_mql5_include``).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mt5_arch.brokers import repo_root

SCHEMA = "mt5-symbol-registry/v1"
CAPABILITY_SCHEMA = "mt5-symbol-capabilities/v1"
REGISTRY_REL = Path("config") / "symbols" / "registry.json"
INCLUDE_REL = Path("mql5") / "Include" / "FxSymbolRegistry.mqh"


class SymbolRegistryError(Exception):
    """Unknown broker, unknown symbol, or ambiguous mapping."""


@dataclass(frozen=True, slots=True)
class SymbolMapping:
    broker: str
    canonical: str
    broker_symbol: str
    expect: dict[str, float | int]
    evidence: str


@dataclass(frozen=True, slots=True)
class SymbolRegistry:
    schema: str
    evidence: str
    canonical: tuple[str, ...]
    mappings: tuple[SymbolMapping, ...]
    empty_brokers: tuple[str, ...] = ()

    def brokers(self) -> tuple[str, ...]:
        return tuple(sorted({m.broker for m in self.mappings} | set(self.empty_brokers)))


def registry_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / REGISTRY_REL


def include_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / INCLUDE_REL


def _norm_broker(name: str) -> str:
    return str(name or "").strip().lower()


def _norm_symbol(name: str) -> str:
    return str(name or "").strip().upper()


def load_registry(path: Path | None = None) -> SymbolRegistry:
    loc = path or registry_path()
    raw = json.loads(loc.read_text(encoding="utf-8"))
    if raw.get("schema") != SCHEMA:
        raise SymbolRegistryError(
            f"unsupported registry schema {raw.get('schema')!r} (need {SCHEMA})"
        )
    canonical = tuple(_norm_symbol(s) for s in raw.get("canonical") or [])
    if not canonical:
        raise SymbolRegistryError("registry.canonical is empty")
    brokers_raw = raw.get("brokers")
    if not isinstance(brokers_raw, dict) or not brokers_raw:
        raise SymbolRegistryError("registry.brokers must be a non-empty object")

    mappings: list[SymbolMapping] = []
    empty: list[str] = []
    seen_pair: set[tuple[str, str]] = set()
    seen_broker_symbol: set[tuple[str, str]] = set()
    for broker_name, entries in brokers_raw.items():
        broker = _norm_broker(broker_name)
        if not broker:
            raise SymbolRegistryError("empty broker name")
        if not isinstance(entries, dict):
            raise SymbolRegistryError(f"brokers.{broker} must be an object")
        if not entries:
            empty.append(broker)
            continue
        this_broker: list[tuple[str, str]] = []
        for canon, spec in entries.items():
            c = _norm_symbol(canon)
            if c not in canonical:
                raise SymbolRegistryError(
                    f"brokers.{broker}.{c} is not in registry.canonical"
                )
            if not isinstance(spec, dict):
                raise SymbolRegistryError(f"brokers.{broker}.{c} must be an object")
            broker_symbol = str(spec.get("broker_symbol") or "").strip()
            if not broker_symbol:
                raise SymbolRegistryError(
                    f"brokers.{broker}.{c}.broker_symbol is required"
                )
            pair = (broker, c)
            if pair in seen_pair:
                raise SymbolRegistryError(f"duplicate mapping {broker}/{c}")
            seen_pair.add(pair)
            bs_key = (broker, broker_symbol)
            if bs_key in seen_broker_symbol:
                raise SymbolRegistryError(
                    f"ambiguous broker_symbol {broker_symbol!r} on {broker} "
                    "(two canonicals; refuse first-match)"
                )
            seen_broker_symbol.add(bs_key)
            this_broker.append((c, broker_symbol))
            expect_raw = spec.get("expect") or {}
            if expect_raw and not isinstance(expect_raw, dict):
                raise SymbolRegistryError(f"brokers.{broker}.{c}.expect must be an object")
            expect: dict[str, float | int] = {}
            for key in ("digits", "contract_size", "point"):
                if key in expect_raw:
                    expect[key] = expect_raw[key]
            mappings.append(
                SymbolMapping(
                    broker=broker,
                    canonical=c,
                    broker_symbol=broker_symbol,
                    expect=expect,
                    evidence=str(spec.get("evidence") or ""),
                )
            )
        canon_on_broker = {c for c, _ in this_broker}
        for c, bs in this_broker:
            bs_n = _norm_symbol(bs)
            if bs_n != c and bs_n in canon_on_broker:
                raise SymbolRegistryError(
                    f"ambiguous collision: {broker}.{c} broker_symbol {bs!r} "
                    f"is another canonical on {broker}"
                )
    return SymbolRegistry(
        schema=str(raw.get("schema")),
        evidence=str(raw.get("evidence") or ""),
        canonical=canonical,
        mappings=tuple(mappings),
        empty_brokers=tuple(sorted(empty)),
    )


def known_broker(registry: SymbolRegistry, broker: str) -> bool:
    name = _norm_broker(broker)
    return name in registry.brokers()


def mappings_for_broker(registry: SymbolRegistry, broker: str) -> tuple[SymbolMapping, ...]:
    """Return every explicit mapping for ``broker`` (empty if the broker is listed blank)."""
    b = _norm_broker(broker)
    return tuple(m for m in registry.mappings if m.broker == b)


def missing_mapped_canonicals(
    registry: SymbolRegistry, broker: str, present: set[str]
) -> list[str]:
    """Canonicals mapped for ``broker`` that do not appear in ``present``."""
    want = {m.canonical for m in mappings_for_broker(registry, broker)}
    have = {_norm_symbol(s) for s in present}
    return sorted(want - have)


def resolve(registry: SymbolRegistry, broker: str, requested: str) -> SymbolMapping:
    """Return the unique mapping for (broker, canonical or broker_symbol).

    Refuses unknown brokers, unmapped symbols, and ambiguous hits.
    Does not append suffixes or pick the first SymbolSelect success.
    """
    b = _norm_broker(broker)
    req = _norm_symbol(requested)
    if not b:
        raise SymbolRegistryError("broker is required")
    if not known_broker(registry, b):
        raise SymbolRegistryError(f"unknown broker {broker!r}")
    if not req:
        raise SymbolRegistryError("symbol is required")

    by_canonical = [m for m in registry.mappings if m.broker == b and m.canonical == req]
    by_broker_sym = [
        m for m in registry.mappings if m.broker == b and m.broker_symbol.upper() == req
    ]
    hits = {id(m): m for m in by_canonical + by_broker_sym}
    found = list(hits.values())
    if len(found) > 1:
        raise SymbolRegistryError(
            f"ambiguous {requested!r} on {b}: "
            + ", ".join(f"{m.canonical}->{m.broker_symbol}" for m in found)
        )
    if len(found) == 1:
        return found[0]
    raise SymbolRegistryError(f"no mapping for {b}/{requested!r} (no suffix walk)")


def canonical_from_broker_symbol(
    registry: SymbolRegistry, broker_symbol: str, *, broker: str | None = None
) -> str:
    """Inverse lookup. Without broker, all hits must share one canonical."""
    req = _norm_symbol(broker_symbol)
    if not req:
        raise SymbolRegistryError("symbol is required")
    if broker:
        return resolve(registry, broker, req).canonical
    canons = {m.canonical for m in registry.mappings if m.broker_symbol.upper() == req}
    if len(canons) == 1:
        return next(iter(canons))
    if not canons:
        raise SymbolRegistryError(
            f"no inverse mapping for {broker_symbol!r} (no suffix strip)"
        )
    raise SymbolRegistryError(
        f"ambiguous inverse {broker_symbol!r}: {sorted(canons)}"
    )


def _expect_ok(mapping: SymbolMapping, row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if "digits" in mapping.expect and int(row.get("digits", -1)) != int(
        mapping.expect["digits"]
    ):
        errors.append(
            f"{mapping.canonical} digits {row.get('digits')} != "
            f"expect {mapping.expect['digits']}"
        )
    if "contract_size" in mapping.expect:
        got = float(row.get("contract_size", 0) or 0)
        want = float(mapping.expect["contract_size"])
        if not math.isfinite(got) or abs(got - want) > 1e-6:
            errors.append(
                f"{mapping.canonical} contract_size {got} != expect {want}"
            )
    if "point" in mapping.expect:
        got = float(row.get("point", 0) or 0)
        want = float(mapping.expect["point"])
        if not math.isfinite(got) or abs(got - want) > 1e-12:
            errors.append(f"{mapping.canonical} point {got} != expect {want}")
    return errors


def verify_capability_dump(
    path: Path, registry: SymbolRegistry | None = None
) -> dict[str, Any]:
    """Validate a read-only ExportSymbolCapabilities dump against the registry."""
    reg = registry or load_registry()
    man_path = path / "manifest.json" if path.is_dir() else path
    raw = json.loads(man_path.read_text(encoding="utf-8"))
    if raw.get("schema") != CAPABILITY_SCHEMA:
        raise SymbolRegistryError(
            f"unsupported capability schema {raw.get('schema')!r}"
        )
    if raw.get("export_ok") is not True:
        raise SymbolRegistryError(
            f"export_ok must be true, got {raw.get('export_ok')!r}"
        )
    broker = _norm_broker(str(raw.get("broker") or ""))
    if not known_broker(reg, broker):
        raise SymbolRegistryError(f"dump broker {raw.get('broker')!r} not in registry")
    rows = raw.get("symbols")
    if not isinstance(rows, list) or not rows:
        raise SymbolRegistryError("capability dump symbols[] is empty")
    errors: list[str] = []
    mapped_ok = 0
    dump_canons: set[str] = set()
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
        if str(row.get("broker_symbol") or "") != mapping.broker_symbol:
            errors.append(
                f"{mapping.canonical} broker_symbol {row.get('broker_symbol')!r} "
                f"!= registry {mapping.broker_symbol!r}"
            )
        if row.get("selected") is not True:
            errors.append(f"{mapping.canonical} selected is not true")
        digits = int(row.get("digits", 0) or 0)
        point = float(row.get("point", 0) or 0)
        contract = float(row.get("contract_size", 0) or 0)
        if digits <= 0 or point <= 0 or contract <= 0:
            errors.append(
                f"{mapping.canonical} missing digits/point/contract_size"
            )
        if int(row.get("bars_h1", 0) or 0) < 1:
            errors.append(f"{mapping.canonical} bars_h1 < 1")
        errors.extend(_expect_ok(mapping, row))
        mapped_ok += 1
    if mapped_ok == 0 and broker not in reg.empty_brokers:
        errors.append(f"no mapped symbols succeeded for {broker}")
    if str(raw.get("source") or "") == "mql5_export":
        missing = missing_mapped_canonicals(reg, broker, dump_canons)
        if missing:
            errors.append(
                "mql5_export missing mapped canonical(s) for "
                f"{broker}: {', '.join(missing)}"
            )
    if errors:
        preview = "\n  ".join(errors[:20])
        extra = f" (+{len(errors) - 20} more)" if len(errors) > 20 else ""
        raise SymbolRegistryError(f"{len(errors)} capability error(s):\n  {preview}{extra}")
    return {"ok": True, "broker": broker, "n_symbols": len(rows), "path": str(man_path)}


def render_mql5_include(registry: SymbolRegistry) -> str:
    """Generate FxSymbolRegistry.mqh from the JSON registry (lockstep)."""
    lines = [
        "//+------------------------------------------------------------------+",
        "//| FxSymbolRegistry.mqh                                             |",
        "//| GENERATED from config/symbols/registry.json — do not hand-edit.  |",
        "//| python3 -c \"from mt5_arch.symbol_registry import write_mql5_include; write_mql5_include()\"",
        "//| Explicit maps only. No suffix walk. No first-match. No OrderSend.|",
        "//+------------------------------------------------------------------+",
        "#ifndef FX_SYMBOL_REGISTRY_MQH",
        "#define FX_SYMBOL_REGISTRY_MQH",
        "",
        "#define FX_SYMBOL_REGISTRY_SCHEMA \"mt5-symbol-registry/v1\"",
        "",
        "void FxRegNormBroker(string &s)",
        "  {",
        "   StringTrimLeft(s);",
        "   StringTrimRight(s);",
        "   StringToLower(s);",
        "  }",
        "",
        "void FxRegNormSymbol(string &s)",
        "  {",
        "   StringTrimLeft(s);",
        "   StringTrimRight(s);",
        "   StringToUpper(s);",
        "  }",
        "",
        "bool FxRegistryLookup(const string broker, const string requested,",
        "                      string &canonical, string &broker_symbol)",
        "  {",
        "   string b = broker;",
        "   string r = requested;",
        "   FxRegNormBroker(b);",
        "   FxRegNormSymbol(r);",
        "   if(StringLen(b) == 0 || StringLen(r) == 0)",
        "      return false;",
    ]
    by_broker: dict[str, list[SymbolMapping]] = {}
    for m in registry.mappings:
        by_broker.setdefault(m.broker, []).append(m)
    for broker in sorted(by_broker):
        lines.append(f'   if(b == "{broker}")')
        lines.append("     {")
        for m in by_broker[broker]:
            bs = m.broker_symbol
            lines.append(
                f'      if(r == "{m.canonical}" || r == "{bs.upper()}")'
            )
            lines.append("        {")
            lines.append(f'         canonical = "{m.canonical}";')
            lines.append(f'         broker_symbol = "{bs}";')
            lines.append("         return true;")
            lines.append("        }")
        lines.append("      return false;")
        lines.append("     }")
    lines += [
        "   return false;",
        "  }",
        "",
        "string FxResolveSymbol(const string broker, const string requested)",
        "  {",
        "   string canonical = \"\";",
        "   string broker_symbol = \"\";",
        "   if(!FxRegistryLookup(broker, requested, canonical, broker_symbol))",
        "      return \"\";",
        "   if(!SymbolSelect(broker_symbol, true))",
        "      return \"\";",
        "   return broker_symbol;",
        "  }",
        "",
        "string FxCanonicalFromBrokerSymbol(const string broker, const string broker_symbol)",
        "  {",
        "   string canonical = \"\";",
        "   string mapped = \"\";",
        "   if(!FxRegistryLookup(broker, broker_symbol, canonical, mapped))",
        "      return \"\";",
        "   return canonical;",
        "  }",
        "",
        "string FxCanonicalFromBrokerSymbolAny(const string broker_symbol)",
        "  {",
        "   string r = broker_symbol;",
        "   FxRegNormSymbol(r);",
        "   string hit = \"\";",
        "   int n = 0;",
    ]
    # Unique inverse: collect distinct (broker_symbol.upper -> canonical)
    inverse: dict[str, set[str]] = {}
    for m in registry.mappings:
        inverse.setdefault(m.broker_symbol.upper(), set()).add(m.canonical)
    for bs, canons in sorted(inverse.items()):
        if len(canons) != 1:
            continue
        canon = next(iter(canons))
        lines.append(f'   if(r == "{bs}")')
        lines.append("     {")
        lines.append(f'      hit = "{canon}";')
        lines.append("      n++;")
        lines.append("     }")
    lines += [
        "   if(n != 1)",
        "      return \"\";",
        "   return hit;",
        "  }",
        "",
        "#endif // FX_SYMBOL_REGISTRY_MQH",
        "",
    ]
    return "\n".join(lines)


def write_mql5_include(root: Path | None = None) -> Path:
    dest = include_path(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_mql5_include(load_registry(registry_path(root))), encoding="utf-8")
    return dest
