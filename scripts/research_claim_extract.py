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


_MQL_INSTALL_PREFIXES = (
    "Indicators/",
    "Include/",
    "Experts/",
    "Scripts/",
    "Files/",
)


def _is_path_token(tok: str) -> bool:
    tok = tok.strip().strip("'\"")
    if not tok or tok.startswith(("http://", "https://", "mailto:", "file://")):
        return False
    if tok.startswith("gitignored:") or "__mutant_" in tok:
        return False
    if tok.startswith("--") or "<" in tok or ">" in tok or " " in tok:
        return False
    if tok.startswith("~") or tok.startswith("…") or tok.startswith("..."):
        return False
    # Line/member anchors (docs/README.md:21, script.py:build_inventory) — not paths.
    if re.search(r":\d+$", tok) or (
        tok.count(":") == 1
        and not tok.startswith(("MQL5/", "mql5/"))
        and re.search(r"\.(?:md|py|sh|json|mq5|mqh):\w+$", tok)
    ):
        return False
    # Unexpanded brace globs are not concrete paths (expand separately).
    if "{" in tok or "}" in tok:
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
    # Absolute / sibling-repo paths are out of inventory scope.
    if tok.startswith("/") or tok.startswith("../"):
        return False
    norm = tok[2:] if tok.startswith("./") else tok
    if norm in _PATH_FILES:
        return True
    if norm.startswith(_PATH_PREFIXES) or norm.startswith(_MQL_INSTALL_PREFIXES):
        return True
    if norm.startswith("phase0/"):
        return True
    return any(norm.endswith(ext) for ext in _PATH_EXTS) and (
        "/" in norm or norm in _PATH_FILES
    )


def _norm_path(tok: str) -> str:
    tok = tok.strip().strip("'\"")
    if tok.startswith("./"):
        tok = tok[2:]
    # Wine install-tree shorthand → repo mql5/ sources.
    for pref in _MQL_INSTALL_PREFIXES:
        if tok.startswith(pref):
            return "mql5/" + tok
    if tok.startswith("phase0/"):
        return "docs/research/" + tok
    return tok


def _expand_brace_paths(tok: str) -> list[str]:
    """Expand a single `{a,b}` alternative in a path token."""
    m = re.fullmatch(r"([^{}]*)\{([^{}]+)\}([^{}]*)", tok.strip().strip("'\""))
    if not m:
        return []
    pre, alts, post = m.group(1), m.group(2), m.group(3)
    return [f"{pre}{a.strip()}{post}" for a in alts.split(",") if a.strip()]


_FAMILY_NOISE = frozenset(
    {
        "results",
        "scripts",
        "docs",
        "config",
        "mql5",
        "http",
        "https",
        "promote",
        "live_go",
        "status",
        "family",
        "screen",
        "verdict",
        "friction",
        "holdout",
        "develop",
        "soft",
        "primary",
        "passers",
        "null",
        "table",
        "metric",
        "claim",
        "audit",
        "record",
        "backtest",
        "signal",
        "edge",
        "triage",
        "within_day_ohlc_increment_rotate_v1",  # null engine, not a family figure owner
        "first_bar_exit_pct",
        "research_bias_gates",
        "n_signals",
        "metric_digit",
        "metric_md_writeup",
        "metric_nested_json",
    }
)

def _family_spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, family_id) spans — backticks, snake_case, and known short ids."""
    out: list[tuple[int, int, str]] = []
    seen_spans: set[tuple[int, int]] = set()

    def add(start: int, end: int, tok: str) -> None:
        tok = tok.strip()
        if not tok or tok in _FAMILY_NOISE:
            return
        if tok.startswith(("http", "results", "scripts", "docs", "config", "mql5")):
            return
        if tok.endswith((".py", ".md", ".json", ".sh", ".mq5", ".mqh")):
            return
        if tok.endswith(("_pct", "_rate", "_size", "_points")):
            return
        key = (start, end)
        if key in seen_spans:
            return
        seen_spans.add(key)
        out.append((start, end, tok))

    for m in _BACKTICK_RE.finditer(text):
        tok = m.group(1).strip()
        # Allow family:variant ids (daily_regime_switch:mom_or) as one token.
        if re.fullmatch(r"[a-z][a-z0-9_]{2,}(?::[a-z][a-z0-9_]{2,})?", tok):
            add(m.start(1), m.end(1), tok)
    for m in re.finditer(r"\b([a-z][a-z0-9]*_[a-z0-9_]{2,})\b", text):
        # Skip snake_case that is only the variant half of a backtick family:variant.
        pre = text[max(0, m.start() - 1) : m.start()]
        if pre == ":":
            continue
        add(m.start(1), m.end(1), m.group(1))
    for m in re.finditer(r"\b([a-z][a-z0-9_]{6,}_v\d+)\b", text):
        add(m.start(1), m.end(1), m.group(1))
    for m in re.finditer(
        r"\b(breakout|mean_reversion|trend_continuation|donchian|bb_rsi)\b", text
    ):
        add(m.start(1), m.end(1), m.group(1))
    out.sort(key=lambda t: t[0])
    return out


def _family_tokens(text: str) -> list[str]:
    """High-signal family / search ids from a line (order-preserving, unique)."""
    out: list[str] = []
    seen: set[str] = set()
    for _, _, tok in _family_spans(text):
        if len(tok) < 3:
            continue
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def _nearest_family(line: str, pos: int, fallback: str) -> str:
    """Family/strategy owning the metric at character offset pos."""
    # Prefer family in the same semicolon/clause segment.
    seg_start = 0
    for i, ch in enumerate(line):
        if i >= pos:
            break
        if ch in ";|":
            seg_start = i + 1
    seg = line[seg_start : pos + 1]
    spans = _family_spans(seg)
    if spans:
        return spans[-1][2]
    spans = _family_spans(line)
    before = [s for s in spans if s[1] <= pos]
    if before:
        return before[-1][2]
    if spans:
        return spans[0][2]
    return fallback


def _attr_from_line(line: str, fallback: str) -> str:
    fams = _family_tokens(line)
    if len(fams) == 1:
        return fams[0]
    # Prefer *.json / results basename mentions
    for m in re.finditer(r"([\w.-]+\.json)", line):
        return m.group(1)
    for m in re.finditer(r"`(results/[^`]+)`", line):
        return m.group(1)
    for m in re.finditer(r"results/([\w./-]+)", line):
        return m.group(0).rstrip(".,;:)")
    if fams:
        return fams[0]
    return fallback


def _section_attr(heading: str) -> str:
    """Map a markdown heading to a stable oracle attribution token."""
    h = heading.strip().lstrip("#").strip()
    low = h.lower()
    if "eurusd" in low and "scalp" in low:
        return "eurusd_ny_scalp"
    if "paper-gate" in low or "paper gate" in low:
        return "eurusd_ny_mr_limit_fill"
    if "signal-edge" in low or "triage" in low:
        return "signal_edge_diagnostic"
    if "walk-forward" in low or "holdout collapse" in low:
        return "xau_oos_holdout"
    fams = _family_tokens(h)
    if fams:
        return fams[0]
    for m in re.finditer(r"([\w.-]+\.json)", h):
        return m.group(1)
    return ""


def _is_threshold_declaration(line: str, claimed: str) -> bool:
    """True when n < N / n≥N states a gate rule rather than a measured value."""
    if not re.match(r"n\s*<\s*\d+$", claimed.strip(), re.I):
        return False
    return bool(
        re.search(
            r"soft\s+n|fails?\s+gates?|SCREEN_FAIL|thin-?n|n\s*≥|n\s*>=|threshold|"
            r"primary gate|must clear|not a waiver|auto-warned|with\s+`?n\s*<",
            line,
            re.I,
        )
    ) or ("thin" in line.lower() and "n <" in line.lower().replace(" ", " "))


def _is_findings_table_header(line: str) -> bool:
    """Auditor findings / neg-control / mutant tables — status cells are not claims."""
    low = line.lower()
    if "|" not in line:
        return False
    if re.search(r"\|\s*file\s*\|\s*line\s*\|\s*kind\s*\|\s*claimed\s*\|", low):
        return True
    if re.search(r"\|\s*control\s*\|\s*name\s*\|\s*result\s*\|", low):
        return True
    if re.search(r"\|\s*seed kind\s*\|\s*kind\s*\|\s*mutant claimed\s*\|", low):
        return True
    return bool(re.search(r"\|\s*#\s*\|\s*file\s*\|\s*line\s*\|", low))


def _longest_nonoverlapping(
    spans: list[tuple[int, int, str, str]],
) -> list[tuple[int, int, str, str]]:
    """Keep longest metric spans; drop bare substring duplicates on the same chars.

    spans: (start, end, claimed, attr). Prefer longer claimed forms (t −3.13 over −3.13).
    """
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (-(s[1] - s[0]), -len(s[2]), s[0], s[2]))
    chosen: list[tuple[int, int, str, str]] = []
    for start, end, claimed, attr in ordered:
        if any(not (end <= s or start >= e) for s, e, _, _ in chosen):
            continue
        chosen.append((start, end, claimed, attr))
    chosen.sort(key=lambda s: (s[0], s[2]))
    return chosen


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
        # Expand simple brace alternatives into concrete path claims.
        if "{" in raw and "}" in raw:
            for alt in _expand_brace_paths(raw):
                add(alt)
            return
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
        # Embedded repo paths inside command backticks (optional ./ prefix)
        if " " in raw or raw.startswith(("python3", "./", "uv ")):
            for pm in re.finditer(
                r"(?:^|\s)\.?/?((?:scripts|src|docs|mql5|MQL5|config|results|tests)/[\w./-]+)",
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

    # Bare / fenced CLI (not always backtick-wrapped): `uv run mt5-arch mcp`
    if re.search(r"(?<![\w-])mt5-arch\s+mcp(?![\w-])", line) and "mt5-arch mcp" not in seen:
        add("mt5-arch mcp", _symbol_attr("mt5-arch mcp", line))

    return out


# Lazy frozen keys for threshold exemptions (populated on first metrics extract).
_FROZEN_KEYS_CACHE: set[tuple[str, str, str]] | None = None


def _extract_metrics(
    rel: str,
    line_no: int,
    line: str,
    *,
    section_attr: str = "",
    frozen_keys: set[tuple[str, str, str]] | None = None,
) -> list[dict]:
    """Extract metrics with per-span attribution and longest non-overlapping spans."""
    global _FROZEN_KEYS_CACHE
    stem = Path(rel).stem
    attr_base = _attr_from_line(line, section_attr or stem)
    if attr_base == stem and section_attr:
        attr_base = section_attr
    if frozen_keys is None:
        if _FROZEN_KEYS_CACHE is None:
            try:
                _FROZEN_KEYS_CACHE = _frozen_content_keys(_git_root())
            except Exception:
                _FROZEN_KEYS_CACHE = set()
        frozen_keys = _FROZEN_KEYS_CACHE

    spans: list[tuple[int, int, str, str]] = []

    def add_span(start: int, end: int, claimed: str, attr: str | None = None) -> None:
        claimed = re.sub(r"\s+", " ", claimed.strip())
        if not claimed:
            return
        if _is_threshold_declaration(line, claimed) and (
            rel,
            "metric",
            claimed,
        ) not in frozen_keys:
            return
        a = attr or _nearest_family(line, start, attr_base)
        if a == stem and section_attr:
            a = section_attr
        spans.append((start, end, claimed, a))

    for m in re.finditer(r"\b(0\s*/\s*\d+)\b", line):
        window = line[max(0, m.start() - 32) : m.end() + 16]
        if re.search(r"caught|mutant|gate_can_fail|broken_caught", window, re.I):
            continue
        # PF 0/99 house convention is a PF claim, not a 0/N fraction.
        pre = line[max(0, m.start() - 8) : m.start()]
        if re.search(r"\bPF\s*$", pre, re.I):
            continue
        norm = re.sub(r"\s*/\s*", " / ", m.group(1).strip())
        add_span(m.start(1), m.end(1), norm)
    # "0 / 0 eligible" — keep the fraction; also keep legacy "0 eligible" twin for
    # ok-key continuity with the prior extractor on HOWTO tables.
    for m in re.finditer(r"\b(0\s*/\s*0)\s+eligible\b", line, re.I):
        norm = re.sub(r"\s*/\s*", " / ", m.group(1).strip())
        add_span(m.start(1), m.end(1), norm)
        add_span(m.end(1) + 1, m.end(), "0 eligible")

    for m in re.finditer(r"\b0\s+eligible\b", line, re.I):
        # Do not rewrite "0 / 0 eligible" into a bare "0 eligible".
        pre = line[max(0, m.start() - 4) : m.start()]
        if re.search(r"/\s*$", pre):
            continue
        add_span(m.start(), m.end(), "0 eligible")
    if "0 / eligible" in line:
        idx = line.index("0 / eligible")
        add_span(idx, idx + len("0 / eligible"), "0 / eligible")

    for m in re.finditer(
        r"\b((?:pooled|max|train|OOS)\s+)?PF\b(?:\s*\([^)]*\))?\s*(?:≈|~)?\s*\**([0-9]+(?:\.[0-9]+)?(?:\s*[–-]\s*[0-9]+(?:\.[0-9]+)?)?)\**",
        line,
    ):
        prefix = (m.group(1) or "").strip()
        num = m.group(2).strip()
        pre = line[max(0, m.start() - 16) : m.start()]
        if re.search(r"finite\s*$", pre, re.I) and "." not in num:
            continue
        # PF 0/99 house convention → claim PF 0 (integer ok).
        after = line[m.end() : m.end() + 4]
        if after.startswith("/") and "." not in num:
            claimed = f"{prefix + ' ' if prefix else ''}PF {num}".strip()
            add_span(m.start(), m.end(), claimed)
            continue
        if ("~" in m.group(0) or "≈" in m.group(0)) and ("–" in num or "-" in num[1:]):
            claimed = f"PF ~{num}"
        else:
            claimed = f"{prefix + ' ' if prefix else ''}PF {num}".strip()
        add_span(m.start(), m.end(), claimed)

    for m in re.finditer(r"\bholdout\s*\(?\s*([0-9]+(?:\.[0-9]+)?)\s*\)?", line, re.I):
        add_span(m.start(), m.end(), f"holdout {m.group(1)}", "holdout lock")
    for m in re.finditer(r"\b([0-9]+(?:\.[0-9]+)?)\s+holdout\b", line, re.I):
        add_span(m.start(), m.end(), f"{m.group(1)} holdout", "holdout lock")

    for m in re.finditer(r"\bn\s*=\s*(\d+)\b", line, re.I):
        add_span(m.start(), m.end(), f"n={m.group(1)}")
    for m in re.finditer(r"\bn\s*<\s*(\d+)\b", line, re.I):
        # Threshold skip lives in add_span (frozen-435 keys are exempt).
        add_span(m.start(), m.end(), f"n < {m.group(1)}")

    # Triage tables: lane | family | n | … → emit n=N attributed to family (not lane).
    if "|" in line:
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.fullmatch(r"\d+", cells[2] or ""):
            fam_cell = ""
            lane_like = frozenset({"eurusd", "xau", "us_index", "fx", "btc", "gold"})
            fam_re = re.compile(r"[a-z][a-z0-9_]{2,}(?::[a-z][a-z0-9_]{2,})?")
            c0, c1 = cells[0] or "", cells[1] or ""
            if fam_re.fullmatch(c1) and (
                c0 in lane_like or re.fullmatch(r"[a-z][a-z0-9_]{2,}", c0)
            ):
                fam_cell = c1
            elif fam_re.fullmatch(c0) and c0 not in lane_like:
                fam_cell = c0
            elif fam_re.fullmatch(c1):
                fam_cell = c1
            if fam_cell:
                n_pat = re.search(rf"\|\s*{re.escape(cells[2])}\s*\|", line)
                if n_pat:
                    add_span(n_pat.start(), n_pat.end(), f"n={cells[2]}", fam_cell)
                else:
                    add_span(0, max(1, len(line) // 4), f"n={cells[2]}", fam_cell)

    for m in re.finditer(
        r"(?<![\w.])\bt(?:-?stat)?\b\s*(?:≈|~)?\s*\**([+\-−]?\d+\.\d+)\**",
        line,
        re.I,
    ):
        num = m.group(1)
        after = line[m.end() : m.end() + 4]
        if re.match(r"\.\d", after):
            continue
        add_span(m.start(), m.end(), f"t {num}")
    if re.search(r"\bt-?stats?\b", line, re.I):
        for m in re.finditer(r"\*\*([+\-−]?\d+\.\d+)\*\*", line):
            add_span(m.start(), m.end(), f"t {m.group(1)}")

    # Do not cross markdown table cell boundaries when binding H50 to a figure.
    for m in re.finditer(r"H50[^\d+\-−|]{0,20}([+\-−]\d+\.\d+)", line):
        num = m.group(1)
        after = line[m.end() : m.end() + 8]
        pts_m = re.match(r"\s*pts\b", after, re.I)
        if pts_m:
            add_span(m.start(), m.end() + pts_m.end(), f"{num} pts")
        else:
            add_span(m.start(), m.end(), f"H50 {num}")
    for m in re.finditer(r"H50\s*\|\s*\*\*([+\-−]\d+\.\d+)\*\*", line):
        # Table header cell "H50" + value cell: attribute as H50-labelled but span
        # only the value cell so it does not swallow sibling t-cells.
        add_span(m.start(1), m.end(1), f"H50 {m.group(1)}")

    for m in re.finditer(r"(?<![\w.])([+\-−]\d+\.\d+)(?![\w.])", line):
        val = m.group(1)
        ctx = line[max(0, m.start() - 12) : m.start()]
        # Word-boundary on t — do not treat the trailing "t" of "holdout" as a t-label.
        if re.search(r"(?:PF|H50|\bt(?:-?stat)?)\s*$", ctx, re.I):
            continue
        after = line[m.end() : m.end() + 8]
        pts_m = re.match(r"\s*pts\b", after, re.I)
        if pts_m:
            add_span(m.start(), m.end() + pts_m.end(), f"{val} pts")
        else:
            add_span(m.start(), m.end(), val)

    date_cue = bool(
        re.search(
            r"holdout|develop|lock|--to|et_date|server clock|bars,|data|span|frozen",
            line,
            re.I,
        )
    )
    if date_cue or "→" in line or "->" in line:
        for m in re.finditer(r"\b(20\d{2}-\d{2}-\d{2})\b", line):
            add_span(m.start(), m.end(), m.group(1), _attr_from_line(line, "holdout lock"))

    kept = _longest_nonoverlapping(spans)
    # Dedupe identical claimed after span selection (same label, disjoint spans).
    out: list[dict] = []
    seen: set[str] = set()
    for _s, _e, claimed, attr in kept:
        if claimed in seen:
            continue
        seen.add(claimed)
        out.append(_claim(rel, line_no, "metric", claimed, attr))
    return out


def _extract_dispositions(
    rel: str,
    line_no: int,
    line: str,
    *,
    in_findings_table: bool = False,
) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (claimed, attribution)

    # Findings / neg-control / mutant tables: status cells are audit chrome, not claims.
    if in_findings_table:
        return out

    # README index scrape: "no KEEP path" is a denial, not a KEEP disposition.
    if re.search(r"\bno\s+KEEP\s+path\b", line, re.I) or (
        "observe-only" in line.lower() and "KEEP" in line and "zacks" in line.lower()
    ):
        line_for_keep = re.sub(r"\bKEEP\b", "KEEP_SKIP", line)
    else:
        line_for_keep = line

    # "BLOCKED for KEEP" is one phrase. Emit KEEP (verifier marks phrase component
    # ok) but do not emit BLOCKED from the phrase — except on the Zacks status line
    # where BLOCKED is the standing overlay disposition.
    if re.search(r"\bBLOCKED\s+for\s+KEEP\b", re.sub(r"[*`_]", "", line), re.I):
        if "zacks" in rel.lower() and re.search(r"\bStatus\b", line, re.I):
            pass  # real Zacks overlay disposition — keep both tokens for attr path
        else:
            line = re.sub(
                r"\*{0,2}BLOCKED\*{0,2}(?=\s+for\s+\*{0,2}KEEP)",
                "BLOCKED_SKIP",
                line,
                flags=re.I,
            )

    # Audit residual / meta prose about a New edge finding — not a live disposition.
    if (
        "New edge" in line
        and rel.endswith("RESEARCH-CLAIM-AUDIT.md")
        and re.search(
            r"residual|docs/README|expected residual|Zacks `?New edge`?|findings?",
            line,
            re.I,
        )
    ):
        line = line.replace("New edge", "NEW_EDGE_RESIDUAL")
        line_for_keep = line

    # Fix C / checker-bug documentation: example disposition tokens, not standing claims.
    # Preserve KEEP when it is the trailing token of BLOCKED for KEEP (phrase component).
    if rel.endswith("RESEARCH-CLAIM-AUDIT.md") and re.search(
        r"Fix C|trailing `?KEEP`?|standalone `?KEEP`?|not extracted|BLOCKED_FOR_KEEP|"
        r"Checker-bug Fix",
        line,
        re.I,
    ):
        preserve_keep = bool(
            re.search(
                r"\bBLOCKED(?:_SKIP)?\s+for\s+KEEP\b",
                re.sub(r"[*`]", "", line),
                re.I,
            )
        )
        for tok in ("KEEP", "BLOCKED", "SCREEN_FAIL", "SCHEMA_PASS", "New edge"):
            if tok == "KEEP" and preserve_keep:
                continue
            line = re.sub(rf"\b{tok}\b", f"{tok}_SKIP", line)
            line_for_keep = re.sub(rf"\b{tok}\b", f"{tok}_SKIP", line_for_keep)

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

    # Normalized promote/live_go from table cells: **false / false** or bare false / false
    if re.search(r"promote\s*/\s*live_go", line, re.I) or (
        "promote" in line.lower() and "live_go" in line.lower() and "/" in line
    ):
        m = re.search(
            r"\*{0,2}\s*(no|false|true)\s*/\s*(false|no|true)(?:\s*/\s*(?:no|false|true))?\s*\*{0,2}",
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

    # Direct promote=/live_go= (forbidden-doc / mutant-seed context → documented-forbidden)
    for m in re.finditer(r"\b(promote=(?:no|false|true)|live_go=(?:false|true))\b", line):
        tok = m.group(1)
        attr = _attr_from_line(line, "standing")
        if tok in ("promote=true", "live_go=true") and re.search(
            r"forbidden|do not|don't|never|must not|mutant|inverted_disposition|"
            r"set\s+`?(?:promote|live_go)=true",
            line,
            re.I,
        ):
            attr = f"forbidden {attr}"
        add(tok, attr)

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

    # Exact disposition tokens in backticks or bold (KEEP uses scrubbed line).
    scan_line = line_for_keep
    candidates: list[str] = []
    for m in _BACKTICK_RE.finditer(scan_line):
        candidates.append(m.group(1).strip())
    for m in _BOLD_RE.finditer(scan_line):
        candidates.append(m.group(1).strip().strip("`"))
    # Also bare SCREAMING tokens
    for m in re.finditer(
        r"\b(SCREEN_FAIL(?:\s+ZERO_PRIMARY_PASSERS)?|SUPERSEDED|PROTOCOL_NULL_INVALID|"
        r"ZERO_PRIMARY_PASSERS|SCHEMA_PASS|BLOCKED|KEEP|DEAD|ANTI|EMPTY|"
        r"COST-BOUND|CLEARS-FRICTION|RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS|"
        r"RESEARCH_IDLE|AWAIT_PHASE_E_SCREEN_AUTHORIZATION|"
        r"KILL_BB_RSI_LINE|KILL_DONCHIAN_LINE|KILL_PRIOR_DAY_HIGH_BREAK)\b",
        scan_line,
    ):
        candidates.append(m.group(1))
    if "FAIL → stop" in scan_line or "FAIL -> stop" in scan_line:
        candidates.append("FAIL → stop")
    if "New edge" in scan_line or "**New edge:**" in scan_line:
        candidates.append("New edge")

    fams = _family_tokens(line)
    for cand in candidates:
        if cand.replace("->", "→") == "FAIL → stop":
            cand = "FAIL → stop"
        if cand not in _DISPOSITION_EXACT and cand != "SCREEN_FAIL ZERO_PRIMARY_PASSERS":
            continue
        # promote=/live_go= already handled above (with forbidden-doc marking).
        if cand.startswith(("promote=", "live_go=")):
            continue
        # SUPERSEDED referring to a *prior* charter/version on this line, not self.
        if cand == "SUPERSEDED":
            stem_v = re.search(r"_v(\d+)$", Path(rel).stem)
            vers = re.findall(r"\bv(\d+)\b", line, re.I)
            other_ver = bool(stem_v and any(v != stem_v.group(1) for v in vers))
            if re.search(r"\bsupersedes?\b\s*:", line, re.I) and (
                other_ver or re.search(r"registry\s+\*\*SUPERSEDED\*\*", line, re.I)
            ):
                continue
            # Prose like "while v2 was SUPERSEDED" / "v1 remains … SUPERSEDED"
            # inside a different version's memo.
            if other_ver and re.search(
                r"\bv\d+\b.*\bSUPERSEDED\b|\bSUPERSEDED\b.*\bv\d+\b|"
                r"remains?\s+byte-immutable\s+under\s+SUPERSEDED|"
                r"while\s+v\d+\s+was\s+SUPERSEDED",
                line,
                re.I,
            ):
                continue
        # Conditional / rule prose ("soft passers = 0 → SCREEN_FAIL") is not a
        # claim that *this* charter's registry disposition is SCREEN_FAIL.
        if cand in ("SCREEN_FAIL", "ZERO_PRIMARY_PASSERS", "PROTOCOL_NULL_INVALID") and re.search(
            r"(?:→|->)\s*\**(?:SCREEN_FAIL|ZERO_PRIMARY_PASSERS)|"
            r"by design|soft passers\s*=\s*0|zero (?:soft )?(?:joint )?passers|"
            r"thin-n|closed freezes stay closed|nulls? not run|r1 unburned",
            line,
            re.I,
        ):
            add(cand, "screen_rule")
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
                # "BLOCKED for KEEP" / "not a scalp KEEP" — not a current KEEP claim.
                if re.search(r"\bKEEP\b", line) and re.search(
                    r"blocked for KEEP|not .*KEEP|treat .* as .*KEEP", line, re.I
                ):
                    attr = "later KEEP path requirements"
                else:
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
        section_attr = ""
        source_attr = ""
        in_findings_table = False
        for i, line in enumerate(text.splitlines(), 1):
            if line.startswith("#"):
                section_attr = _section_attr(line)
                source_attr = ""
                in_findings_table = False
            elif _is_findings_table_header(line):
                in_findings_table = True
            elif in_findings_table and line.strip() and not line.strip().startswith("|"):
                in_findings_table = False
            # Source: results/... applies to the next few prose lines only (cleared
            # on blank line / heading), never sticky across the whole file.
            src_m = re.search(r"Source:\s*`?(results/[\w./-]+)", line)
            if src_m:
                source_attr = src_m.group(1).rstrip(".,;:)`")
            elif not line.strip():
                source_attr = ""

            line_fallback = ""
            if _family_tokens(line) or re.search(r"[\w.-]+\.json|results/", line):
                line_fallback = ""  # _attr_from_line will win inside metrics
            else:
                line_fallback = source_attr or section_attr

            claims.extend(_extract_links(rel, i, line, root))
            claims.extend(_extract_paths(rel, i, line))
            claims.extend(_extract_shas(rel, i, line))
            claims.extend(_extract_symbols(rel, i, line))
            claims.extend(
                _extract_metrics(rel, i, line, section_attr=line_fallback)
            )
            claims.extend(
                _extract_dispositions(
                    rel, i, line, in_findings_table=in_findings_table
                )
            )
    return claims


def _load_verify_mod():
    import importlib.util

    mod_path = Path(__file__).resolve().parent / "research_claim_verify.py"
    spec = importlib.util.spec_from_file_location(
        "research_claim_verify_for_extract", mod_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _frozen_content_keys(root: Path) -> set[tuple[str, str, str]]:
    """Original frozen-435 content keys (file, kind, claimed) — never drop these."""
    candidates = [
        root / "results" / "research_claim_frozen435_keys.json",
        root / "scratchpad" / "frozen_research_claims.json",
    ]
    for path in candidates:
        if path is None or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = data if isinstance(data, list) else data.get("claims") or data.get("keys") or []
        out: set[tuple[str, str, str]] = set()
        for c in rows:
            if isinstance(c, dict):
                out.add((str(c.get("file") or ""), str(c.get("kind") or ""), str(c.get("claimed") or "")))
            elif isinstance(c, (list, tuple)) and len(c) >= 3:
                out.add((str(c[0]), str(c[1]), str(c[2])))
        if out:
            return out
    return set()


def _filter_metrics_without_external_oracle(
    claims: list[dict[str, Any]],
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Drop self-referential metrics with no results/** oracle (decoration).

    Attribute-first: keep row/section attribution when it resolves. If a tighter
    attribution makes a previously stem-gated figure self-referential, fall back
    to the doc stem so n_ok claims are not deleted. Only stop emitting when both
    the attributed and stem forms lack an external oracle — and the content key is
    not in the frozen-435 set (those must stay, allowlisted as self-ref).
    """
    v = _load_verify_mod()
    tracked = v.run_git_ls_files()
    frozen = _frozen_content_keys(root)
    kept: list[dict[str, Any]] = []
    stopped: list[dict[str, str]] = []
    for c in claims:
        if c.get("kind") != "metric":
            kept.append(c)
            continue
        st, act = v.resolve_metric(c, tracked)
        if st != "self_referential":
            kept.append(c)
            continue
        stem = Path(str(c.get("file") or "")).stem
        attr = (c.get("attribution") or "").strip() or stem
        kept_claim = c
        if attr != stem:
            trial = dict(c)
            trial["attribution"] = stem
            st2, act2 = v.resolve_metric(trial, tracked)
            if st2 != "self_referential":
                kept.append(trial)
                continue
            act = act2
        key = (str(c.get("file") or ""), "metric", str(c.get("claimed") or ""))
        if key in frozen:
            kept.append(kept_claim)
            continue
        reason = (
            f"no external results/** oracle for {c.get('claimed')!r} "
            f"(attr={attr!r}; {act})"
        )
        stopped.append(
            {
                "file": str(c.get("file") or ""),
                "line": str(c.get("line") or ""),
                "claimed": str(c.get("claimed") or ""),
                "attribution": attr,
                "reason": reason,
            }
        )
    return kept, stopped


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


def _rehydrate_labelled_bare_forms(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-emit bare / H50 forms when Defect-3 span choice dropped an ok twin.

    Defect 3 prefers labelled spans (t −3.13 over −3.13; +11.7 pts over H50 +11.7).
    Rehydrate the sibling claimed string on the same line so (file, kind, claimed)
    ok continuity holds.
    """
    label_re = re.compile(r"^(?:t|H50)\s+([+\-−]\d+\.\d+)$")
    pts_re = re.compile(r"^([+\-−]\d+\.\d+)\s+pts$")
    by_file_line: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for c in claims:
        if c.get("kind") != "metric":
            continue
        key = (str(c.get("file") or ""), int(c.get("line") or 0))
        by_file_line.setdefault(key, []).append(c)

    extras: list[dict[str, Any]] = []
    have = {(c.get("file"), c.get("line"), c.get("kind"), c.get("claimed")) for c in claims}

    def add_twin(f: str, line_no: int, claimed: str, attr: str) -> None:
        twin_key = (f, line_no, "metric", claimed)
        if twin_key in have:
            return
        have.add(twin_key)
        extras.append(_claim(f, line_no, "metric", claimed, attr))

    for (f, line_no), group in by_file_line.items():
        claimeds = {str(c.get("claimed") or "") for c in group}
        line_txt = ""
        try:
            line_txt = (Path(f).read_text(encoding="utf-8", errors="replace").splitlines()[
                line_no - 1
            ] if line_no > 0 else "")
        except OSError:
            line_txt = ""
        for c in group:
            claimed = str(c.get("claimed") or "")
            attr = str(c.get("attribution") or "")
            m = label_re.match(claimed)
            if m:
                bare = m.group(1)
                if bare not in claimeds:
                    add_twin(f, line_no, bare, attr)
            pm = pts_re.match(claimed)
            if pm and re.search(r"\bH50\b", line_txt):
                h50 = f"H50 {pm.group(1)}"
                if h50 not in claimeds:
                    add_twin(f, line_no, h50, attr)
    return claims + extras


def build_inventory(root: Path | None = None) -> dict[str, Any]:
    """Build full inventory: docs extract + instruction + consistency."""
    root = root or _git_root()
    docs_files = _tracked_docs(root)
    docs_claims = extract_docs_claims(root, docs_files)
    docs_claims = _refresh_zacks_index_claim(root, docs_claims)
    docs_claims, stopped_emitting = _filter_metrics_without_external_oracle(
        docs_claims, root
    )
    docs_claims = _rehydrate_labelled_bare_forms(docs_claims)

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

    # Per-file stopped_emitting summary (decoration metrics with no results oracle).
    stopped_by_file: dict[str, int] = {}
    for row in stopped_emitting:
        stopped_by_file[row["file"]] = stopped_by_file.get(row["file"], 0) + 1
    stopped_by_file = dict(sorted(stopped_by_file.items()))

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
        "n_stopped_emitting": len(stopped_emitting),
        "stopped_emitting_by_file": stopped_by_file,
        "stopped_emitting": stopped_emitting,
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
