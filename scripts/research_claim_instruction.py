#!/usr/bin/env python3
"""Instruction-file claim extraction + broker-roster consistency checks.

CLAUSE: CLAUDE.md / AGENTS.md are read-only sources of claims — never edit them.
Instruction files are never metric oracles.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

INSTRUCTION_FILES = (
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "mql5/README.md",
)

# Sites that enumerate broker → install path (not the generic overridable default).
BROKER_ENUM_SITES = (
    {
        "site": "scripts/19-run-htf-fib-backtest.sh",
        "kind": "search_list",
        "generic_ok": False,
    },
    {
        "site": "fetch_data.py",
        "kind": "hardcoded_paths",
        "generic_ok": False,
    },
)

# Intentionally generic / overridable — must NOT be flagged as missing-broker drift.
GENERIC_BRIDGE_SITE = "src/mt5_arch/file_bridge.py"


def _line_no(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _broker_roster(root: Path) -> list[str]:
    d = root / "config" / "brokers"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.env"))


def extract_instruction_claims(root: Path) -> list[dict[str, Any]]:
    """Extract path/link/symbol/disposition claims from instruction files."""
    claims: list[dict[str, Any]] = []
    for rel in INSTRUCTION_FILES:
        p = root / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        # High-signal repo paths in backticks only (avoid noise from prose).
        allow_prefixes = (
            "scripts/", "src/", "docs/", "mql5/", "config/", "results/", "tests/",
        )
        allow_files = {
            "backtest.py", "fetch_data.py", "live_trader.py", "strategy_params.json",
            "CLAUDE.md", "AGENTS.md", "README.md",
        }
        for i, line in enumerate(lines, 1):
            for m in re.finditer(r"`([^`]+)`", line):
                tok = m.group(1).strip().strip("'\"")
                if not tok or tok.startswith("--") or "(" in tok or "<" in tok:
                    continue
                if tok.startswith("~"):
                    continue  # wine prefixes → consistency claims
                if "*" in tok or "::" in tok or " " in tok:
                    continue  # globs, qualified symbols, flagged commands
                norm = tok[2:] if tok.startswith("./") else tok
                if norm in allow_files or norm.startswith(allow_prefixes):
                    claims.append({
                        "file": rel,
                        "line": i,
                        "kind": "path",
                        "claimed": norm,
                        "attribution": "instruction",
                    })
                elif tok.startswith("mt5-arch") or tok.endswith(".py") and "/" not in tok:
                    claims.append({
                        "file": rel,
                        "line": i,
                        "kind": "symbol",
                        "claimed": tok,
                        "attribution": rel,
                    })

        # HTF Fib disagreement claim (known finding #1)
        for m in re.finditer(
            r"(do not agree|don't agree)[^\n]{0,80}(HTF Fib|signal index)",
            text,
            re.I,
        ):
            claims.append({
                "file": rel,
                "line": _line_no(text, m.start()),
                "kind": "disposition",
                "claimed": "HTF Fib docs disagree on signal index",
                "attribution": "mql5/README.md + docs/HOWTO-HTF-FIB.md",
            })

        # ~/.mt5-* prefixes are covered by consistency claims, not path existence.

    return claims


def build_consistency_claims(root: Path) -> list[dict[str, Any]]:
    """Emit consistency claims: roster brokers must resolve at enumerating sites."""
    roster = _broker_roster(root)
    claims: list[dict[str, Any]] = []
    for site in BROKER_ENUM_SITES:
        claims.append({
            "file": site["site"],
            "line": 1,
            "kind": "consistency",
            "claimed": "broker_roster_coverage",
            "attribution": "config/brokers/*.env",
            "site": site["site"],
            "roster": roster,
            "generic_ok": site["generic_ok"],
        })
    # Explicit CLAUDE/AGENTS claim that exness is in the working model vs roster
    for rel in ("CLAUDE.md", "AGENTS.md"):
        p = root / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"~/\.mt5-exness", text)
        if m:
            claims.append({
                "file": rel,
                "line": _line_no(text, m.start()),
                "kind": "consistency",
                "claimed": "instruction_prefix_in_roster",
                "attribution": "config/brokers/*.env",
                "prefix_broker": "exness",
                "roster": roster,
            })
    # Control target: generic bridge dir must NOT be flagged (emitted for verifier exemption test)
    claims.append({
        "file": GENERIC_BRIDGE_SITE,
        "line": 23,
        "kind": "consistency",
        "claimed": "generic_bridge_default_exempt",
        "attribution": "MT5_BRIDGE_DIR overridable",
        "site": GENERIC_BRIDGE_SITE,
        "roster": roster,
        "generic_ok": True,
    })
    return claims


def resolve_consistency(claim: dict, root: Path) -> tuple[str, str]:
    """Resolve broker-roster consistency claims."""
    claimed = claim.get("claimed", "")
    roster = claim.get("roster") or _broker_roster(root)

    if claimed == "generic_bridge_default_exempt":
        # Always ok — genericity is by design
        return "ok", "default_bridge_dir overridable via MT5_BRIDGE_DIR (exempt)"

    if claimed == "instruction_prefix_in_roster":
        broker = claim.get("prefix_broker") or "exness"
        if broker in roster:
            return "ok", f"roster contains {broker}"
        return "drift", (
            f"instruction names ~/.mt5-{broker} but config/brokers/ has no {broker}.env; "
            f"roster={roster}"
        )

    if claimed == "broker_roster_coverage":
        site = claim.get("site") or ""
        if claim.get("generic_ok"):
            return "ok", f"{site} is generic/overridable (exempt)"
        text = ""
        # Mutant/scratch override: never reads real instruction governance files as site text
        # unless site_path points at an explicit scratch copy.
        site_path = claim.get("site_path")
        p = Path(site_path) if site_path else (root / site)
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
        missing = []
        for broker in roster:
            # Heuristics: broker name or known install-dir fragments
            fragments = {
                "vantage": ["vantage", "Vantage International"],
                "fpmarkets": ["fpmarkets", "FP Markets"],
                "wsf": ["wsf", "WSFmarkets", "WSF"],
                "exness": ["exness", "Exness"],
            }.get(broker, [broker])
            if not any(frag.lower() in text.lower() for frag in fragments):
                missing.append(broker)
        if missing:
            return "drift", (
                f"site={site} missing roster brokers {missing}; "
                f"roster={roster}"
            )
        return "ok", f"site={site} covers roster {roster}"

    return "unresolvable", f"unknown consistency claim {claimed!r}"


def htf_signal_docs_agree(root: Path) -> tuple[bool, str]:
    """True when mql5/README and HOWTO-HTF-FIB agree on signal buffer 8."""
    mql = (root / "mql5/README.md").read_text(encoding="utf-8", errors="replace")
    how = (root / "docs/HOWTO-HTF-FIB.md").read_text(encoding="utf-8", errors="replace")
    mql_8 = bool(re.search(r"HTF Fib\s*=\s*\*\*8\*\*|buffer\s*\*\*8\*\*.*HTF|Signal buffers: \*\*HTF Fib = 8", mql))
    how_8 = bool(re.search(r"signal buffer:\s*`?8`?|buffer \*\*8\*\*|Signal is buffer \*\*8\*\*", how, re.I))
    auth = "Authoritative map (v1.42+)" in mql or "Do not use the old signal-at-7" in mql
    if mql_8 and how_8:
        return True, "mql5/README.md + HOWTO-HTF-FIB.md both document HTF Fib signal buffer 8"
    return False, f"mql_8={mql_8} how_8={how_8} auth={auth}"


def merge_instruction_into_inventory(root: Path, inv: dict) -> dict:
    """Append instruction + consistency claims; recompute corpus stats."""
    claims = list(inv.get("claims") or [])
    # Drop prior instruction/consistency injection (idempotent refresh)
    claims = [
        c for c in claims
        if not (
            c.get("file") in INSTRUCTION_FILES
            or c.get("kind") == "consistency"
            or (
                c.get("kind") == "disposition"
                and c.get("claimed") == "HTF Fib docs disagree on signal index"
            )
        )
    ]
    instr = extract_instruction_claims(root)
    cons = build_consistency_claims(root)
    claims.extend(instr)
    claims.extend(cons)

    corpus: dict[str, int] = {}
    counts: dict[str, int] = {}
    for c in claims:
        corpus[c["file"]] = corpus.get(c["file"], 0) + 1
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
    n_instruction = sum(corpus.get(f, 0) for f in INSTRUCTION_FILES)

    inv = dict(inv)
    inv["claims"] = claims
    inv["n_claims"] = len(claims)
    inv["counts"] = counts
    inv["corpus"] = corpus
    inv["n_instruction_claims"] = n_instruction
    inv["instruction_files"] = list(INSTRUCTION_FILES)
    inv["scope"] = (
        inv.get("scope", "")
        + " + instruction files "
        + ",".join(INSTRUCTION_FILES)
        + " + consistency(broker_roster)"
    )
    return inv
