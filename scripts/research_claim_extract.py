#!/usr/bin/env python3
"""Deterministic research-doc claim extractor (stdlib-only).

Primary entry for rebuilding results/research_claim_inventory.json:
  python3 scripts/research_claim_extract.py
  python3 scripts/research_claim_extract.py --out PATH
  python3 scripts/research_claim_extract.py --dry-run   # print summary; no write

Walks tracked docs/**/*.md, emits slim {file,line,kind,claimed,attribution}
for path/link/sha/symbol/metric/disposition, then merges instruction + consistency
claims from research_claim_instruction.py. Sort key: (file, line, kind, claimed,
attribution) for byte-identical output.

Schema remains research_claim_inventory/v1 (slim claim shape unchanged).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote


def _load_instruction_mod():
    import importlib.util

    mod_path = Path(__file__).resolve().parent / "research_claim_instruction.py"
    spec = importlib.util.spec_from_file_location("research_claim_instruction", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_instr = _load_instruction_mod()
INSTRUCTION_FILES = _instr.INSTRUCTION_FILES
extract_instruction_claims = _instr.extract_instruction_claims
build_consistency_claims = _instr.build_consistency_claims
_refresh_zacks_index_claim = _instr._refresh_zacks_index_claim

SCHEMA = "research_claim_inventory/v1"
METHOD = "scripts/research_claim_extract.py:build_inventory"
ENTRY_POINT = "build_inventory"
SCOPE_DOCS = "docs/**/*.md"

# Repo-relative path-ish tokens worth auditing when backtick-wrapped.
_PATH_PREFIXES = (
    "scripts/",
    "src/",
    "docs/",
    "mql5/",
    "MQL5/",
    "config/",
    "results/",
    "tests/",
)
_PATH_FILES = frozenset(
    {
        "backtest.py",
        "fetch_data.py",
        "live_trader.py",
        "strategy_params.json",
        "xauusd_data.csv",
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "us_index_session_backtest.py",
        "us_index_session_autoresearch.py",
    }
)
_PATH_EXTS = (
    ".py",
    ".sh",
    ".md",
    ".json",
    ".jsonl",
    ".mq5",
    ".mqh",
    ".env",
    ".csv",
    ".so",
    ".paths",
)

_DISPOSITION_EXACT = frozenset(
    {
        "SCREEN_FAIL",
        "SUPERSEDED",
        "PROTOCOL_NULL_INVALID",
        "ZERO_PRIMARY_PASSERS",
        "SCHEMA_PASS",
        "BLOCKED",
        "KEEP",
        "DEAD",
        "ANTI",
        "EMPTY",
        "COST-BOUND",
        "CLEARS-FRICTION",
        "RESEARCH_IDLE",
        "RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS",
        "AWAIT_PHASE_E_SCREEN_AUTHORIZATION",
        "KILL_BB_RSI_LINE",
        "KILL_DONCHIAN_LINE",
        "KILL_PRIOR_DAY_HIGH_BREAK",
        "FAIL → stop",
        "SCREEN_FAIL ZERO_PRIMARY_PASSERS",
        "New edge",
        "promote=no",
        "promote=false",
        "promote=true",
        "live_go=false",
        "live_go=true",
        "promote",
        "live_go",
        "next_step",
    }
)

_SYMBOL_EXACT = frozenset(
    {
        "--live",
        "--unbounded",
        "--save",
        "--strict-charter",
        "--screen-only",
        "--null-seed",
        "--charter",
        "--allow-cost-override",
        "--no-rsi-ma-filter",
        "--json",
        "mt5-arch mcp",
        "signal_fn",
        "simulate()",
        "simulate_donchian()",
        "simulate_joint()",
        "score_row",
        "load_package_snapshot()",
        "gates_from_charter()",
        "eurusd_ny_mr_limit_fill_v1",
    }
)

_SHA_RE = re.compile(
    r"(?<![0-9a-fA-F])([0-9a-fA-F]{64}|[0-9a-fA-F]{8}|[0-9a-fA-F]{7})(?![0-9a-fA-F])"
)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def _git_root(start: Path | None = None) -> Path:
    cwd = start or Path.cwd()
    out = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True
    ).strip()
    return Path(out)


def _tracked_docs(root: Path) -> list[str]:
    out = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "docs"],
        cwd=root,
    )
    files = [f for f in out.decode().split("\0") if f.endswith(".md")]
    files.sort()
    return files


def _resolve_link_target(src: str, href: str, root: Path) -> str:
    href = href.split("#", 1)[0].split("?", 1)[0].strip()
    if not href:
        return ""
    try:
        return str((root / src).parent.joinpath(unquote(href)).resolve().relative_to(root.resolve()))
    except Exception:
        return unquote(href)


def _is_path_token(tok: str) -> bool:
    tok = tok.strip().strip("'\"")
    if not tok or tok.startswith(("http://", "https://", "mailto:")):
        return False
    if tok.startswith("--") or "<" in tok or ">" in tok or " " in tok:
        return False
    if tok.startswith("~"):
        return False
    # allow results/xau_charters/* style; reject other globs
    if (
        "*" in tok
        and not tok.endswith("/*")
        and "/**" not in tok
        and tok[-1] != "*"
        and "/*" not in tok
    ):
        return False
    if "::" in tok:
        return False
    norm = tok[2:] if tok.startswith("./") else tok
    if norm in _PATH_FILES:
        return True
    if norm.startswith(_PATH_PREFIXES):
        return True
    return any(norm.endswith(ext) for ext in _PATH_EXTS) and (
        "/" in norm or norm in _PATH_FILES
    )


def _norm_path(tok: str) -> str:
    tok = tok.strip().strip("'\"")
    if tok.startswith("./"):
        tok = tok[2:]
    return tok


def _family_tokens(text: str) -> list[str]:
    """High-signal family / search ids from a line (order-preserving, unique)."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _BACKTICK_RE.finditer(text):
        tok = m.group(1).strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{4,}", tok):
            continue
        if tok.startswith(("http", "results", "scripts", "docs", "config", "mql5")):
            continue
        if tok.endswith((".py", ".md", ".json", ".sh")):
            continue
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    # bare family_id_vN in prose / tables
    for m in re.finditer(r"\b([a-z][a-z0-9_]{6,}_v\d+)\b", text):
        tok = m.group(1)
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def _attr_from_line(line: str, fallback: str) -> str:
    fams = _family_tokens(line)
    if len(fams) == 1:
        return fams[0]
    # Prefer *.json / results basename mentions
    for m in re.finditer(r"([\w.-]+\.json)", line):
        return m.group(1)
    for m in re.finditer(r"`(results/[^`]+)`", line):
        return m.group(1)
    if fams:
        return fams[0]
    return fallback


def _claim(
    file: str,
    line: int,
    kind: str,
    claimed: str,
    attribution: str,
) -> dict[str, Any]:
    return {
        "file": file,
        "line": line,
        "kind": kind,
        "claimed": claimed,
        "attribution": attribution,
    }


def _extract_links(rel: str, line_no: int, line: str, root: Path) -> list[dict]:
    out: list[dict] = []
    for m in _MD_LINK_RE.finditer(line):
        href = m.group(2).strip()
        if href.startswith(("http://", "https://", "mailto:")):
            continue
        if href.startswith("#"):
            continue
        target = _resolve_link_target(rel, href, root)
        if not target:
            continue
        out.append(_claim(rel, line_no, "link", href, target))
    return out


def _path_attr(claimed: str) -> str:
    if claimed.startswith("results/"):
        return "results artifact"
    if claimed.startswith("scripts/"):
        return "script"
    if claimed.startswith("config/"):
        return "config"
    if claimed.startswith(("mql5/", "MQL5/")):
        return "mql5"
    if claimed.startswith("docs/"):
        return "docs"
    if claimed in ("backtest.py", "fetch_data.py", "live_trader.py"):
        return claimed
    return "doc path"


def _extract_paths(rel: str, line_no: int, line: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        raw = raw.strip().strip("'\"")
        # Strip qualified MQL/Python member: path.py::symbol
        if "::" in raw:
            raw = raw.split("::", 1)[0]
        if not _is_path_token(raw):
            return
        claimed = _norm_path(raw)
        if claimed in seen:
            return
        seen.add(claimed)
        out.append(_claim(rel, line_no, "path", claimed, _path_attr(claimed)))

    for m in _BACKTICK_RE.finditer(line):
        raw = m.group(1).strip()
        pre = line[: m.start()].lower()
        if re.search(r"\bno\b\s*$", pre) or "there is no" in pre:
            continue
        add(raw)
        # Embedded repo paths inside command backticks
        if " " in raw or raw.startswith("python3"):
            for pm in re.finditer(
                r"(?:^|\s)((?:scripts|src|docs|mql5|MQL5|config|results|tests)/[\w./-]+)",
                raw,
            ):
                add(pm.group(1))
            for pm in re.finditer(
                r"(?:^|\s)(backtest\.py|fetch_data\.py|live_trader\.py|strategy_params\.json)",
                raw,
            ):
                add(pm.group(1))
    return out


def _extract_shas(rel: str, line_no: int, line: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    # Skip pure date-looking 8-hex that aren't hex digests in context? Keep SHA near
    # SHA/sha256/digest/commit/@ markers or in backticks / charter tables.
    for m in _SHA_RE.finditer(line):
        claimed = m.group(1).lower()
        if claimed in seen:
            continue
        # Avoid matching plain numbers-only-looking short tokens that are not hex digests
        # in non-hash context: require nearby cue OR length 64 OR backtick wrap.
        start, end = m.span(1)
        window = line[max(0, start - 24) : end + 12]
        in_bt = bool(re.search(r"`[^`]*" + re.escape(m.group(1)) + r"[^`]*`", line))
        cue = bool(
            re.search(
                r"SHA|sha256|digest|commit|main@|supersede|charter|\.json",
                window,
                re.I,
            )
        )
        if len(claimed) < 64 and not (in_bt or cue):
            continue
        # Drop YYYYMMDD-like if no hash cue (e.g. 20260813 alone)
        if len(claimed) == 8 and claimed.isdigit() and not cue:
            continue
        seen.add(claimed)
        attr = _attr_from_line(line, "digest")
        # Prefer charter/json name near the sha
        near = line[max(0, start - 80) : end + 40]
        jm = re.search(r"([\w.-]+\.json)", near)
        if jm:
            attr = jm.group(1)
        elif "main@" in line or "main base" in line.lower() or "commit" in near.lower():
            attr = "main base commit"
        out.append(_claim(rel, line_no, "sha", claimed, attr))
    return out


def _symbol_attr(tok: str, line: str) -> str:
    if tok == "--live" and "forbid" in line.lower():
        return "forbidden"
    if tok == "simulate()":
        return "backtest"
    if tok.startswith("simulate"):
        return _attr_from_line(line, tok)
    if tok == "score_row":
        return "us_index_session_core"
    if tok == "mt5-arch mcp":
        return "docs/HOWTO-MT5-AI-MCP.md"
    if tok == "eurusd_ny_mr_limit_fill_v1":
        return "proposed family_id/search_id"
    if tok == "load_package_snapshot()":
        return "package loader"
    if tok == "gates_from_charter()":
        return "validator"
    if "xau_sealed_family_cycle" in line:
        return "xau_sealed_family_cycle.py"
    if "htf_fib_offline" in line:
        return "htf_fib_offline_backtest.py"
    if "backtest.py" in line:
        return "backtest.py"
    return _attr_from_line(line, tok)


def _extract_symbols(rel: str, line_no: int, line: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()

    def add(claimed: str, attr: str) -> None:
        if claimed in seen:
            return
        seen.add(claimed)
        out.append(_claim(rel, line_no, "symbol", claimed, attr))

    for m in _BACKTICK_RE.finditer(line):
        tok = m.group(1).strip()
        if tok in _SYMBOL_EXACT:
            add(tok, _symbol_attr(tok, line))
        # Flags embedded in multi-token backticks: `--strict-charter --screen-only`
        for sym in sorted(s for s in _SYMBOL_EXACT if s.startswith("--")):
            if re.search(rf"(?<![\w-]){re.escape(sym)}(?![\w-])", tok):
                add(sym, _symbol_attr(sym, line))
        if tok.startswith("python3 "):
            add(tok, _attr_from_line(line, tok))
        if tok == "python3 backtest.py":
            add(tok, "backtest.py")

    for sym in sorted(_SYMBOL_EXACT):
        if (
            sym.startswith("--")
            and sym in line
            and sym not in seen
            and (f"`{sym}`" in line or f"**{sym}**" in line or f" {sym}" in line)
        ):
            add(sym, _symbol_attr(sym, line))

    for m in re.finditer(
        r"`(python3 scripts/xau_sealed_family_cycle\.py --charter …)`", line
    ):
        add(m.group(1), "scripts/xau_sealed_family_cycle.py")
    for m in re.finditer(
        r"`(python3 scripts/signal_edge_diagnostic\.py --lane all --by-year)`", line
    ):
        add(m.group(1), "scripts/signal_edge_diagnostic.py")

    return out


def _extract_metrics(rel: str, line_no: int, line: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    attr_base = _attr_from_line(line, Path(rel).stem)

    def add(claimed: str, attr: str | None = None) -> None:
        if claimed in seen:
            return
        seen.add(claimed)
        out.append(_claim(rel, line_no, "metric", claimed, attr or attr_base))

    for m in re.finditer(r"\b(0\s*/\s*\d+)\b", line):
        norm = re.sub(r"\s*/\s*", " / ", m.group(1).strip())
        add(norm)

    if re.search(r"\b0\s+eligible\b", line, re.I) or "0 eligible" in line:
        add("0 eligible")
    if "0 / eligible" in line:
        add("0 / eligible")

    # PF with optional parenthetical / markdown between label and figure:
    # "max PF (n≥20) **2.242**", "pooled PF **0.903**", "train PF **1.837** → OOS PF **0.588**"
    for m in re.finditer(
        r"\b((?:pooled|max|train|OOS)\s+)?PF\b(?:\s*\([^)]*\))?\s*(?:≈|~)?\s*\**([0-9]+(?:\.[0-9]+)?(?:\s*[–-]\s*[0-9]+(?:\.[0-9]+)?)?)\**",
        line,
    ):
        prefix = (m.group(1) or "").strip()
        num = m.group(2).strip()
        if ("~" in m.group(0) or "≈" in m.group(0)) and ("–" in num or "-" in num[1:]):
            add(f"PF ~{num}")
        else:
            claimed = f"{prefix + ' ' if prefix else ''}PF {num}".strip()
            add(re.sub(r"\s+", " ", claimed))

    # holdout X.XX / holdout (0.50) / X.XX holdout
    for m in re.finditer(r"\bholdout\s*\(?\s*([0-9]+(?:\.[0-9]+)?)\s*\)?", line, re.I):
        add(f"holdout {m.group(1)}")
    for m in re.finditer(r"\b([0-9]+(?:\.[0-9]+)?)\s+holdout\b", line, re.I):
        add(f"{m.group(1)} holdout")

    for m in re.finditer(r"\bn\s*=\s*(\d+)\b", line, re.I):
        add(f"n={m.group(1)}")
    for m in re.finditer(r"\bn\s*<\s*(\d+)\b", line, re.I):
        add(f"n < {m.group(1)}")

    # Triage / record tables: family in backticks + bare n in a column → n=N
    if "|" in line and _family_tokens(line):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.fullmatch(r"\d+", cells[2] or ""):
            add(f"n={cells[2]}")

    for m in re.finditer(r"t\s*(?:≈|~|stat)?[^\d+\-−]{0,12}([+\-−]?\d+\.\d+)", line, re.I):
        add(f"t {m.group(1)}")
    # "t-stats: **2.44** … and **2.24**"
    if re.search(r"t-?stats?", line, re.I):
        for m in re.finditer(r"\*\*([+\-−]?\d+\.\d+)\*\*", line):
            add(f"t {m.group(1)}")

    for m in re.finditer(r"H50[^\d+\-−]{0,20}([+\-−]\d+\.\d+)", line):
        add(f"H50 {m.group(1)}")
    for m in re.finditer(r"H50\s*\|\s*\*\*([+\-−]\d+\.\d+)\*\*", line):
        add(f"H50 {m.group(1)}")

    # signed edges / pts (1+ decimal places)
    for m in re.finditer(r"(?<![\w.])([+\-−]\d+\.\d+)(?![\w.])", line):
        val = m.group(1)
        ctx = line[max(0, m.start() - 12) : m.start()]
        if re.search(r"PF\s*$", ctx, re.I):
            continue
        after = line[m.end() : m.end() + 8]
        if re.match(r"\s*pts\b", after, re.I):
            add(f"{val} pts")
        else:
            add(val)

    # Dates: holdout/lock cues OR explicit data-range arrows
    date_cue = bool(
        re.search(
            r"holdout|develop|lock|--to|et_date|server clock|bars,|data|span|frozen",
            line,
            re.I,
        )
    )
    if date_cue or "→" in line or "->" in line:
        for m in re.finditer(r"\b(20\d{2}-\d{2}-\d{2})\b", line):
            add(m.group(1), _attr_from_line(line, "holdout lock"))

    return out


def _extract_dispositions(rel: str, line_no: int, line: str) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (claimed, attribution)

    def add(claimed: str, attr: str) -> None:
        key = (claimed, attr)
        if key in seen:
            return
        if claimed not in _DISPOSITION_EXACT and claimed not in {
            "FAIL → stop",
            "SCREEN_FAIL ZERO_PRIMARY_PASSERS",
        }:
            return
        seen.add(key)
        out.append(_claim(rel, line_no, "disposition", claimed, attr))

    # Normalized promote/live_go from table cells: **no / false** / **false / false**
    if re.search(r"promote\s*/\s*live_go", line, re.I) or (
        "promote" in line.lower() and "live_go" in line.lower() and "/" in line
    ):
        m = re.search(
            r"\*\*\s*(no|false|true)\s*/\s*(false|no|true)(?:\s*/\s*(?:no|false|true))?\s*\*\*",
            line,
            re.I,
        )
        if m:
            p, lg = m.group(1).lower(), m.group(2).lower()
            attr = _attr_from_line(line, "standing")
            if p == "no":
                add("promote=no", attr)
            else:
                add(f"promote={p}", attr)
            if lg in ("false", "no"):
                add("live_go=false", attr)
            else:
                add(f"live_go={lg}", attr)

    # Direct promote=/live_go=
    for m in re.finditer(r"\b(promote=(?:no|false|true)|live_go=(?:false|true))\b", line):
        add(m.group(1), _attr_from_line(line, "standing"))

    # Field-name-only mentions (do not flip promote / live_go / next_step)
    if (
        re.search(r"\bpromote\b", line)
        and "promote=" not in line
        and re.search(r"do not flip|flip `promote`|flip promote", line, re.I)
    ):
        add("promote", _attr_from_line(line, "results/xau_loop_status.md"))
    if (
        re.search(r"\blive_go\b", line)
        and "live_go=" not in line
        and re.search(r"do not flip|flip `live_go`|flip live_go", line, re.I)
    ):
        add("live_go", _attr_from_line(line, "results/xau_loop_status.md"))
    if re.search(r"\bnext_step\b", line) and (
        "do not flip" in line.lower()
        or "next_step is" in line.lower()
        or "next_step |" in line.lower()
        or "Strategy-edge next_step" in line
    ):
        add("next_step", _attr_from_line(line, "RESEARCH_IDLE"))

    # Exact disposition tokens in backticks or bold
    candidates: list[str] = []
    for m in _BACKTICK_RE.finditer(line):
        candidates.append(m.group(1).strip())
    for m in _BOLD_RE.finditer(line):
        candidates.append(m.group(1).strip().strip("`"))
    # Also bare SCREAMING tokens
    for m in re.finditer(
        r"\b(SCREEN_FAIL(?:\s+ZERO_PRIMARY_PASSERS)?|SUPERSEDED|PROTOCOL_NULL_INVALID|"
        r"ZERO_PRIMARY_PASSERS|SCHEMA_PASS|BLOCKED|KEEP|DEAD|ANTI|EMPTY|"
        r"COST-BOUND|CLEARS-FRICTION|RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS|"
        r"RESEARCH_IDLE|AWAIT_PHASE_E_SCREEN_AUTHORIZATION|"
        r"KILL_BB_RSI_LINE|KILL_DONCHIAN_LINE|KILL_PRIOR_DAY_HIGH_BREAK)\b",
        line,
    ):
        candidates.append(m.group(1))
    if "FAIL → stop" in line or "FAIL -> stop" in line:
        candidates.append("FAIL → stop")
    if "New edge" in line or "**New edge:**" in line:
        candidates.append("New edge")

    fams = _family_tokens(line)
    for cand in candidates:
        if cand.replace("->", "→") == "FAIL → stop":
            cand = "FAIL → stop"
        if cand not in _DISPOSITION_EXACT and cand != "SCREEN_FAIL ZERO_PRIMARY_PASSERS":
            continue
        if cand == "SCREEN_FAIL" and len(fams) > 1:
            for fam in fams:
                add(cand, fam)
            continue
        attr = _attr_from_line(line, Path(rel).stem)
        if cand in ("KEEP", "BLOCKED", "SCHEMA_PASS", "New edge") and "zacks" in rel.lower():
            if "later KEEP" in line or "KEEP path" in line:
                attr = "later KEEP path requirements"
            elif cand == "KEEP":
                attr = "Zacks overlay"
            elif cand == "SCHEMA_PASS":
                attr = "Zacks MCP overlay lane"
            else:
                attr = "Zacks overlay KEEP"
        if cand.startswith("KILL_"):
            attr = _attr_from_line(line, cand)
        add(cand, attr)

    # Pointer to standing XAU disposition (doc defers to results/xau_loop_status.md)
    if (
        "xau_loop_status.md" in line
        and re.search(r"disposition|XAU", line)
        and "RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS" not in line
    ):
        add("RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS", "XAU disposition")

    return out


def extract_docs_claims(root: Path, docs: list[str] | None = None) -> list[dict[str, Any]]:
    """Extract research-doc claims from tracked docs/**/*.md."""
    docs = docs if docs is not None else _tracked_docs(root)
    claims: list[dict[str, Any]] = []
    for rel in docs:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            claims.extend(_extract_links(rel, i, line, root))
            claims.extend(_extract_paths(rel, i, line))
            claims.extend(_extract_shas(rel, i, line))
            claims.extend(_extract_symbols(rel, i, line))
            claims.extend(_extract_metrics(rel, i, line))
            claims.extend(_extract_dispositions(rel, i, line))
    return claims


def _sort_key(c: dict[str, Any]) -> tuple:
    return (
        str(c.get("file") or ""),
        int(c.get("line") or 0),
        str(c.get("kind") or ""),
        str(c.get("claimed") or ""),
        str(c.get("attribution") or ""),
    )


def _dedupe(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable dedupe on full slim record (+ consistency extras ignored for docs)."""
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for c in claims:
        key = (
            c.get("file"),
            c.get("line"),
            c.get("kind"),
            c.get("claimed"),
            c.get("attribution"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _slim(c: dict[str, Any]) -> dict[str, Any]:
    """Keep inventory claim shape; preserve consistency extras when present."""
    base = {
        "file": c["file"],
        "line": c["line"],
        "kind": c["kind"],
        "claimed": c["claimed"],
        "attribution": c.get("attribution") or "",
    }
    for extra in ("site", "roster", "generic_ok", "prefix_broker", "site_path"):
        if extra in c:
            base[extra] = c[extra]
    return base


def build_inventory(root: Path | None = None) -> dict[str, Any]:
    """Build full inventory: docs extract + instruction + consistency."""
    root = root or _git_root()
    docs_files = _tracked_docs(root)
    docs_claims = extract_docs_claims(root, docs_files)
    docs_claims = _refresh_zacks_index_claim(root, docs_claims)

    instr = extract_instruction_claims(root)
    cons = build_consistency_claims(root)

    claims = [_slim(c) for c in docs_claims + instr + cons]
    claims = _dedupe(claims)
    claims.sort(key=_sort_key)

    corpus: dict[str, int] = {}
    counts: dict[str, int] = {}
    for c in claims:
        corpus[c["file"]] = corpus.get(c["file"], 0) + 1
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
    # Stable key order for corpus/counts
    corpus = dict(sorted(corpus.items()))
    counts = dict(sorted(counts.items()))
    n_instruction = sum(corpus.get(f, 0) for f in INSTRUCTION_FILES)

    scope = (
        f"{SCOPE_DOCS} + instruction files "
        + ",".join(INSTRUCTION_FILES)
        + " + consistency(broker_roster)"
    )
    return {
        "schema": SCHEMA,
        "method": METHOD,
        "scope": scope,
        "n_claims": len(claims),
        "n_instruction_claims": n_instruction,
        "instruction_files": list(INSTRUCTION_FILES),
        "counts": counts,
        "corpus": corpus,
        "claims": claims,
    }


def research_doc_claim_count(inv: dict[str, Any]) -> int:
    """Count claims whose source file is under docs/ (frozen baseline subset)."""
    return sum(1 for c in inv.get("claims") or [] if str(c.get("file", "")).startswith("docs/"))


def main(argv: list[str] | None = None) -> int:
    root = _git_root()
    default_out = root / "results" / "research_claim_inventory.json"
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=default_out,
        help="inventory JSON path (default: results/research_claim_inventory.json)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="build inventory and print summary; do not write",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="like --dry-run: never write; exit 1 if research-doc claims < 435",
    )
    args = p.parse_args(argv)

    inv = build_inventory(root)
    n_docs = research_doc_claim_count(inv)
    summary = {
        "ok": n_docs >= 435,
        "schema": inv["schema"],
        "method": inv["method"],
        "n_claims": inv["n_claims"],
        "n_research_doc_claims": n_docs,
        "n_instruction_claims": inv["n_instruction_claims"],
        "counts": inv["counts"],
        "n_corpus_files": len(inv["corpus"]),
    }
    print(json.dumps(summary, indent=2))

    if args.dry_run or args.check:
        return 0 if summary["ok"] else 1

    out_path = args.out if args.out.is_absolute() else root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(inv, indent=2) + "\n", encoding="utf-8")
    try:
        disp = str(out_path.resolve().relative_to(root.resolve()))
    except ValueError:
        disp = str(out_path)
    print(json.dumps({"wrote": disp, "n_claims": inv["n_claims"]}, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
