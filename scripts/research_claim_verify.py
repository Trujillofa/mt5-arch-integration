#!/usr/bin/env python3
"""Read-only research-doc claim verifier (auditor, not researcher).

Reproducible entry point for research-claim-audit:
  python3 scripts/research_claim_verify.py [--inventory PATH] [--out PATH]
  python3 scripts/research_claim_verify.py --negative-controls [--out PATH]

ROOT is derived from `git rev-parse --show-toplevel` (no hardcoded abs path).
Default --out is repo-relative results/research_claim_verify_result.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
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
GENERIC_BRIDGE_SITE = _instr.GENERIC_BRIDGE_SITE
htf_signal_docs_agree = _instr.htf_signal_docs_agree
merge_instruction_into_inventory = _instr.merge_instruction_into_inventory
resolve_consistency = _instr.resolve_consistency


def _git_root(start: Path | None = None) -> Path:
    cwd = start or Path.cwd()
    out = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True
    ).strip()
    return Path(out)


ROOT = _git_root()
INV = ROOT / "results" / "research_claim_inventory.json"
DEFAULT_OUT = ROOT / "results" / "research_claim_verify_result.json"

os.chdir(ROOT)

def run_git_ls_files() -> set[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    files = set(out.decode().split("\0"))
    files.discard("")
    return files


def _is_tracked(rel: str, tracked: set[str]) -> bool:
    rel = rel.strip().rstrip("/")
    if not rel:
        return False
    if "*" in rel:
        prefix = rel.split("*", 1)[0]
        return any(t.startswith(prefix) for t in tracked)
    if rel in tracked:
        return True
    # directory: any tracked child
    return any(t.startswith(rel + "/") for t in tracked)


def _read(rel: str) -> str | None:
    p = ROOT / rel
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def standing_from_loop() -> dict[str, str]:
    text = _read("results/xau_loop_status.md") or ""
    # Prefer the first/current block (top of file)
    next_step = "RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS"
    promote = "no"
    live_go = "false"
    m = re.search(r"\*\*next_step\*\*\s*\|\s*\*\*`?([^`*|]+)`?\*\*", text)
    if m:
        next_step = m.group(1).strip()
    # promote / live_go row forms
    if re.search(r"promote\s*/\s*live_go.*?\bno\b.*?\bfalse\b", text, re.I | re.S):
        promote, live_go = "no", "false"
    m2 = re.search(r"\*\*promote\*\*\s*\|\s*\*\*([^*|]+)\*\*", text)
    if m2:
        promote = m2.group(1).strip().lower()
    m3 = re.search(r"\*\*live_go\*\*\s*\|\s*\*\*([^*|]+)\*\*", text)
    if m3:
        live_go = m3.group(1).strip().lower()
    return {"next_step": next_step, "promote": promote, "live_go": live_go}



def _line_text(rel: str, line: int) -> str:
    txt = _read(rel) or ""
    lines = txt.splitlines()
    if line < 1 or line > len(lines):
        return ""
    return lines[line - 1]


def _is_gitignored(rel: str) -> bool:
    """True when git check-ignore says the path is ignored."""
    rel = rel.strip().rstrip("/")
    if not rel:
        return False
    try:
        r = subprocess.run(
            ["git", "check-ignore", "-q", "--", rel],
            cwd=ROOT,
            check=False,
        )
        return r.returncode == 0
    except OSError:
        return False


def _secrets_context(claim: dict) -> bool:
    line = _line_text(claim.get("file", ""), int(claim.get("line") or 0))
    blob = " ".join(
        [
            line,
            str(claim.get("attribution") or ""),
            str(claim.get("claimed") or ""),
        ]
    )
    return bool(
        re.search(
            r"never commit|do not commit|gitignore|secret|\\.env|wine prefix|installer",
            blob,
            re.I,
        )
    )


def _blocked_for_phrase_component(claim: dict) -> bool:
    """True when claimed disposition is only the trailing token of 'BLOCKED for X'."""
    claimed = claim.get("claimed", "").strip().strip("`")
    if not claimed:
        return False
    line = _line_text(claim.get("file", ""), int(claim.get("line") or 0))
    if not line:
        return False
    # BLOCKED for KEEP / blocked for <DISPOSITION> (tolerate **BLOCKED** markdown)
    stripped = re.sub(r"[_*`]", "", line)
    return bool(
        re.search(
            rf"\bBLOCKED\s+for\s+{re.escape(claimed)}\b",
            stripped,
            re.I,
        )
    )


def resolve_path_or_link(claim: dict, tracked: set[str]) -> tuple[str, str]:
    kind = claim["kind"]
    claimed = claim["claimed"].strip()
    attr = (claim.get("attribution") or "").strip()
    src = claim["file"]

    if kind == "link":
        # Prefer inventory attribution (already resolved)
        target = attr if attr and not attr.startswith("http") else None
        if target is None:
            href = claimed.split("#", 1)[0].split("?", 1)[0]
            if not href or href.startswith(("http://", "https://", "mailto:")):
                return "ok", "external-or-anchor"
            base = (ROOT / src).parent
            try:
                target = str((base / unquote(href)).resolve().relative_to(ROOT.resolve()))
            except Exception:
                target = unquote(href)
        if _is_tracked(target, tracked):
            return "ok", target
        return "drift", f"untracked:{target}"

    # path
    rel = claimed
    if _is_tracked(rel, tracked):
        return "ok", rel
    # common doc shorthand: bare script name → scripts/
    if "/" not in rel and rel.endswith(".py"):
        alt = f"scripts/{rel}"
        if _is_tracked(alt, tracked):
            return "ok", alt
    # MQL5/ install-tree → mql5/ source
    if rel.startswith("MQL5/"):
        alt = "mql5/" + rel[len("MQL5/") :]
        if _is_tracked(alt, tracked):
            return "ok", alt
    # intentional research CSV (gitignored but named in docs)
    if rel == "xauusd_data.csv":
        # not tracked — drift per git ls-files rule
        return "drift", "untracked (gitignored research CSV)"
    if not _is_tracked(rel, tracked):
        # Secrets / never-commit paths that are gitignored are correct precisely
        # because they are untracked. Visible exempt — not silent drop.
        # Secrets context alone does NOT exempt (negative control: secrets context
        # + not gitignored must still drift).
        if _is_gitignored(rel):
            return "exempt_secrets", f"gitignored:{rel}"
        return "drift", f"missing:{rel}" if not (ROOT / rel).exists() else f"untracked:{rel}"
    return "ok", rel


def _sha_candidates(attr: str) -> list[str]:
    names = []
    attr = attr or ""
    for m in re.findall(r"[\w./-]+\.json", attr):
        names.append(m)
    # bare charter filenames
    if attr.endswith(".json") or "flat_v" in attr:
        base = attr.split("/")[-1]
        if not base.endswith(".json"):
            # attribution like early_server_range_break_flat_v2.json already
            pass
        names.append(base)
        names.append(f"results/xau_charters/{base}")
    return names



def _list_charter_sha_files() -> list[Path]:
    d = ROOT / "results" / "xau_charters"
    if not d.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(d.iterdir()):
        name = p.name
        if name.endswith(".json.sha256") or (
            name.endswith(".sha256") and not name.endswith(".json.sha256")
        ):
            out.append(p)
    return out


def _parse_family_version(attr: str) -> list[tuple[str, str]]:
    """Return (family_id, vN) candidates from prose attribution."""
    attr_l = (attr or "").lower()
    found: list[tuple[str, str]] = []
    # Explicit family_id_vN (optional .json)
    for m in re.finditer(r"\b([a-z][a-z0-9_]{5,})_v(\d+)(?:\.json)?\b", attr_l):
        found.append((m.group(1), f"v{m.group(2)}"))
    versions = re.findall(r"\bv(\d+)\b", attr_l)
    if not versions:
        return found
    # Prose like "exog v4 charter" — match charter stems containing the keyword
    tokens = [t for t in re.findall(r"[a-z][a-z0-9_]{2,}", attr_l) if t not in {"charter", "sha", "json", "results", "xau"}]
    for p in _list_charter_sha_files():
        stem = p.name
        # strip date prefix and .json.sha256 / .sha256
        core = stem
        for suf in (".json.sha256", ".sha256"):
            if core.endswith(suf):
                core = core[: -len(suf)]
                break
        # core like 2026-08-15_exog_london_..._v4
        m = re.search(r"_([a-z][a-z0-9_]+)_v(\d+)$", core)
        if not m:
            continue
        fam, ver = m.group(1), f"v{m.group(2)}"
        for ver_n in versions:
            if ver != f"v{ver_n}":
                continue
            for tok in tokens:
                if tok in fam or fam.startswith(tok):
                    found.append((fam, ver))
                    break
    # dedupe preserve order
    seen = set()
    out = []
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _charter_digest_paths_for(family_id: str, version: str) -> list[str]:
    """Locate charter digest sources: .json.sha256 / .sha256 siblings, else the .json."""
    d = ROOT / "results" / "xau_charters"
    if not d.is_dir():
        return []
    sha_paths: list[str] = []
    json_paths: list[str] = []
    needle = f"_{family_id}_{version}"
    for p in d.iterdir():
        name = p.name
        if needle not in name:
            continue
        rel = str(p.relative_to(ROOT))
        if name.endswith(".json.sha256") or (
            name.endswith(".sha256") and not name.endswith(".json.sha256")
        ):
            sha_paths.append(rel)
        elif name.endswith(".json") and not name.endswith(".json.sha256"):
            json_paths.append(rel)
    # Prefer explicit sidecar digests; fall back to hashing the JSON charter.
    return sorted(sha_paths) + sorted(json_paths)


def _digest_from_path(rel: str) -> str | None:
    """Read a .sha256 sidecar or sha256-hash a .json charter file."""
    if rel.endswith(".sha256"):
        txt = _read(rel)
        if not txt:
            return None
        return txt.strip().split()[0].lower()
    p = ROOT / rel
    if p.is_file() and rel.endswith(".json"):
        return hashlib.sha256(p.read_bytes()).hexdigest()
    return None


def resolve_sha(claim: dict, tracked: set[str]) -> tuple[str, str]:
    claimed = claim["claimed"].strip().lower()
    attr = claim.get("attribution") or ""
    attr_l = attr.lower()

    # A) family_id + version → sibling .sha256 (mismatch is DRIFT, not unresolvable)
    fam_vers = _parse_family_version(attr)
    # Also try attribution that is already a charter basename
    for name in _sha_candidates(attr):
        base = Path(name).name
        m = re.search(r"([a-z][a-z0-9_]+)_v(\d+)", base.lower())
        if m:
            fam_vers.append((m.group(1), f"v{m.group(2)}"))
    seen_fv = set()
    for fam, ver in fam_vers:
        if (fam, ver) in seen_fv:
            continue
        seen_fv.add((fam, ver))
        for rel in _charter_digest_paths_for(fam, ver):
            h = _digest_from_path(rel)
            if not h:
                continue
            if h.startswith(claimed) or (
                len(claimed) >= 8 and claimed == h[: len(claimed)]
            ):
                return "ok", f"{rel}:{h}"
            # Located the freeze digest and claim disagrees → drift
            return "drift", f"{rel}:{h}"

    # B) digest-content search across results/xau_charters/*.sha256 sidecars
    for p in _list_charter_sha_files():
        rel = str(p.relative_to(ROOT))
        h = _digest_from_path(rel)
        if not h:
            continue
        if h.startswith(claimed) or (
            len(claimed) >= 8 and claimed == h[: len(claimed)]
        ):
            return "ok", f"{rel}:{h}"

    # C) registry jsonl
    reg = _read("results/xau_charter_disposition_registry.jsonl") or ""
    for line in reg.splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        for key in ("charter_sha256", "superseded_by_sha256", "costs_sha256"):
            h = str(row.get(key) or "").lower()
            if not h:
                continue
            if h.startswith(claimed) or (
                len(claimed) >= 8 and claimed.startswith(h[: len(claimed)])
            ):
                cpath = str(row.get("charter_path") or "")
                return "ok", f"{cpath}:{h}" if cpath else h

    # D) explicit path candidates from attribution (legacy)
    for name in _sha_candidates(attr):
        paths = []
        if name.startswith("results/"):
            paths.append(name)
        else:
            paths.append(f"results/xau_charters/{name}")
            paths.append(name)
        for p in paths:
            for sib in (p + ".sha256", p.replace(".json", ".sha256"), p + ".json.sha256"):
                sib = sib.replace(".json.json", ".json")
                h = _digest_from_path(sib)
                if not h:
                    continue
                if h.startswith(claimed) or (
                    len(claimed) >= 8 and claimed == h[: len(claimed)]
                ):
                    return "ok", f"{sib}:{h}"
                if fam_vers:
                    return "drift", f"{sib}:{h}"
            if p in tracked or (ROOT / p).is_file():
                h = _digest_from_path(p) or hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                if h.startswith(claimed) or (
                    len(claimed) >= 8 and claimed == h[: len(claimed)]
                ):
                    return "ok", f"{p}:{h}"
                if fam_vers and p.endswith(".json"):
                    return "drift", f"{p}:{h}"

    # E) costs / csv / lock digest-content search (non-charter freeze artifacts)
    search_tracked = [
        t
        for t in tracked
        if t.endswith((".sha256", ".json", ".jsonl"))
        and (
            "costs" in t
            or "lock" in t
            or "instrument" in t
            or "csv" in attr_l
            or t.startswith("results/")
        )
    ]
    for t in search_tracked:
        txt = (_read(t) or "").lower()
        if not txt:
            continue
        if t.endswith(".sha256"):
            h = txt.strip().split()[0]
            if h.startswith(claimed) or (
                len(claimed) >= 8 and claimed == h[: len(claimed)]
            ):
                return "ok", f"{t}:{h}"
        elif claimed[:16] in txt.replace('"', ""):
            return "ok", f"{t}:embedded:{claimed[:16]}"

    # F) git commit object
    if re.fullmatch(r"[0-9a-f]{7,40}", claimed):
        try:
            tip = (
                subprocess.check_output(
                    ["git", "rev-parse", "--verify", claimed],
                    cwd=ROOT,
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
                .lower()
            )
            if tip.startswith(claimed):
                return "ok", tip
        except Exception:
            pass
        try:
            subprocess.check_output(
                ["git", "cat-file", "-t", claimed], cwd=ROOT, stderr=subprocess.DEVNULL
            )
            return "ok", f"git-object:{claimed}"
        except Exception:
            pass

    return "unresolvable", f"no file for attr={attr!r}"


def resolve_symbol(claim: dict, tracked: set[str]) -> tuple[str, str]:
    claimed = claim["claimed"].strip()
    attr = (claim.get("attribution") or "").strip()
    src = claim["file"]

    candidates: list[str] = []
    if attr.endswith((".py", ".md", ".sh", ".mq5", ".mqh")) or "/" in attr.split()[0]:
        candidates.append(attr.split()[0])
    mapping = {
        "backtest.py": ["backtest.py"],
        "live_trader.py": ["live_trader.py"],
        "simulate()": ["backtest.py"],
        "forbidden": [src],
        "docs/HOWTO-MT5-AI-MCP.md": ["docs/HOWTO-MT5-AI-MCP.md"],
        "Route C": ["docs/HOWTO-MT5-AI-MCP.md"],
        "xau_sealed_family_cycle.py": ["scripts/xau_sealed_family_cycle.py"],
        "scripts/xau_sealed_family_cycle.py": ["scripts/xau_sealed_family_cycle.py"],
        "xau_charter_protocol": ["scripts/xau_charter_protocol.py"],
        "scripts/signal_edge_diagnostic.py": ["scripts/signal_edge_diagnostic.py"],
        "donchian_turtle": ["scripts/xau_donchian_null_maxstat.py", "backtest.py"],
        "joint_london_open_cosign_fade_flat": [
            "scripts/xau_family_joint_london_open_cosign_fade_flat.py"
        ],
        "us_index_session_core": ["scripts/us_index_session_core.py"],
        "htf_fib_offline_backtest.py": ["scripts/htf_fib_offline_backtest.py"],
        "mt5-arch CLI": ["src/mt5_arch/cli.py"],
        "package loader": ["scripts/xau_exogenous_predictor_core.py", "scripts/xau_multi_instrument_joint_screen.py"],
        "validator": ["scripts/xau_charter_protocol.py"],
        "strict CLI": ["scripts/xau_sealed_family_cycle.py"],
        "develop screen": ["scripts/xau_sealed_family_cycle.py"],
        "proposed family_id/search_id": ["docs/research/EURUSD-MR-LIMIT-FILL-PAPER-GATE-v1.md"],
    }
    for k, vs in mapping.items():
        if k in attr or attr == k:
            candidates.extend(vs)
    candidates.append(src)

    variants = [claimed, claimed.replace("…", "").replace("...", "")]
    if claimed.endswith("()"):
        variants.append(claimed[:-2])

    for path in candidates:
        path = path.lstrip("./")
        txt = _read(path)
        if txt is None:
            continue
        for v in variants:
            v = v.strip()
            if not v:
                continue
            if v in txt:
                return "ok", path
            if "mcp" in v and "mt5-arch" in txt and "mcp" in txt:
                return "ok", path
        tokens = [t for t in re.sub(r"[^\w-]", " ", claimed).split() if len(t) > 2]
        if tokens and all(tok in txt for tok in tokens[:3]):
            return "ok", path

    # broader search for function defs
    needle = claimed[:-2] if claimed.endswith("()") else claimed
    if needle.startswith("--") or needle.replace("_", "").isalnum():
        search_paths = [t for t in tracked if t.endswith((".py", ".md", ".sh"))]
        for path in search_paths:
            if needle in (_read(path) or ""):
                if any(a in path for a in re.findall(r"[a-z0-9_]{4,}", attr.lower())) or not attr:
                    return "ok", path
                if attr in ("forbidden", "backtest", "simulate()") or "simulate" in attr:
                    return "ok", path
    return "unresolvable", f"symbol {claimed!r} not in attr={attr!r}"


def _metric_corpus(attr: str, src: str) -> list[str]:
    files = [
        "docs/research/BACKTEST-RECORD.md",
        "results/xau_loop_status.md",
        "results/xau_charter_disposition_registry.jsonl",
    ]
    attr_l = (attr or "").lower()
    mapping = {
        "asia_box": [
            "results/xau_asia_box_london_sweep_fade_flat_null_maxstat.json",
            "results/xau_asia_box_london_sweep_fade_flat_null_maxstat.md",
        ],
        "bb_rsi": ["results/xau_null_maxstat.md", "results/xau_null_maxstat.json"],
        "donchian": [
            "results/xau_donchian_null_maxstat.md",
            "results/xau_donchian_null_maxstat.json",
        ],
        "walk-forward": ["results/xau_retrain_walkforward_summary.md"],
        "eurusd_ny_scalp_develop": [
            "results/eurusd_ny_scalp_autoresearch.md",
            "results/eurusd_ny_scalp_autoresearch.json",
        ],
        "ny_cash_liquidity": ["results/eurusd_ny_scalp_signal_diagnostic.md", src],
        "m5_zscore": ["results/eurusd_ny_scalp_signal_diagnostic.md", src],
        "mean_reversion": [
            "results/eurusd_ny_scalp_signal_diagnostic.md",
            "results/eurusd_ny_mr_limit_fill_paper_gate_v1.md",
            "results/eurusd_ny_mr_limit_fill_paper_gate_v1.json",
            src,
        ],
        "exog_london": [
            "results/xau_loop_status.md",
            "docs/research/BACKTEST-RECORD.md",
            "results/eurusd_ny_scalp_signal_diagnostic.md",
            src,
        ],
        "xau_holdout": ["results/xau_holdout_lock.json"],
        "htf fib": ["results/htf_fib_offline_lock.json"],
        "us-index": [
            "results/us_index_session_develop_lock.json",
            "results/us_index_session_v4_lock.json",
            "results/us_index_session_v8_lock.json",
        ],
        "eurusd develop": ["results/eurusd_ny_scalp_lock.json"],
        "flatten": [
            "results/us_index_session_scalp_backtest.md",
            "results/us_index_session_scalp_backtest.json",
        ],
        "v2 playbook": ["results/us_index_session_playbook_v2.md"],
        "v3 structure": ["results/us_index_session_structure_v3.md"],
        "cost/size": ["results/us_index_session_v4_cost_size_once.md"],
        "v4": ["results/us_index_session_v4.md"],
        "v5": ["results/us_index_session_v5.md"],
        "v6": ["results/us_index_session_v6.md"],
        "v7": ["results/us_index_session_v7.md"],
        "v8": ["results/us_index_session_v8.md"],
        "thin-n": ["scripts/research_bias_gates.py"],
    }
    for k, vs in mapping.items():
        if k in attr_l:
            files.extend(vs)
    # US-index hit ratios from HOWTO attributions
    if re.search(r"\bv[1-8]\b|playbook|cost/size|eligible|flatten", attr_l):
        files.extend(
            [
                "docs/HOWTO-US-INDEX-SCALP.md",
                "results/us_index_session_playbook_v2.md",
                "results/us_index_session_structure_v3.md",
                "results/us_index_session_v4.md",
                "results/us_index_session_v4_cost_size_once.md",
                "results/us_index_session_v5.md",
                "results/us_index_session_v6.md",
                "results/us_index_session_v7.md",
                "results/us_index_session_v8.md",
                "results/us_index_session_scalp_backtest.md",
                "results/eurusd_ny_scalp_autoresearch.md",
            ]
        )
    files.append(src)
    # dedupe preserve order
    seen = set()
    out = []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out



def _is_iso_date_metric(claimed: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", claimed.strip()))


def _named_result_artifacts(claim: dict) -> list[str]:
    """Extract results/ paths from explicit Write-up/Executed/source/artifact labels near the claim."""
    src = claim.get("file") or ""
    line_no = int(claim.get("line") or 0)
    txt = _read(src) or ""
    if not txt:
        return []
    lines = txt.splitlines()
    lo = max(0, line_no - 25)
    hi = min(len(lines), line_no + 5)
    window = "\n".join(lines[lo:hi])
    found: list[str] = []
    # Only explicit oracle labels — do NOT scoop every backtick results/ path
    # (those are often unrelated citations like xau_loop_status.md).
    for m in re.finditer(
        r"(?i)(?:write-?up|executed|source|artifact)\s*:\s*`?(results/[A-Za-z0-9_./-]+)`?",
        window,
    ):
        found.append(m.group(1).rstrip(").,;"))
    # "reproduced prior write-up" then (`results/...`) possibly on the next line
    for m in re.finditer(
        r"(?i)(?:write-?up|reproduced prior write-up)[^\n`]{0,60}(?:\n[^\n`]{0,20})?`?(results/[A-Za-z0-9_./-]+)`?",
        window,
    ):
        found.append(m.group(1).rstrip(").,;"))
    out: list[str] = []
    seen = set()
    for f in found:
        f = f.strip()
        if f and f not in seen:
            seen.add(f)
            out.append(f)
    return out



def _metric_match(txt: str, claimed: str, *, path: str = "") -> bool:
    """Structured metric match — reject CSV/price-row coincidence and bare float substrings."""
    if not txt:
        return False
    pl = path.replace("\\", "/").lower()
    if pl.endswith(".csv") or "/instrument_data/" in pl or pl.startswith("instrument_data/"):
        return False

    claimed = claimed.strip()
    m = re.fullmatch(r"n\s*=\s*(\d+)", claimed, re.I)
    if m:
        n = m.group(1)
        patterns = [
            rf"\bn_signals\b[^0-9]{{0,20}}\b{n}\b",
            rf"\bn\s*=\s*{n}\b",
            rf"\|\s*{n}\s*\|",
            rf"\bn\s*\*{{0,2}}\s*{n}\b",
        ]
        return any(re.search(p, txt, re.I) for p in patterns)

    m = re.fullmatch(r"t\s*[+]?\s*([0-9]+\.[0-9]+)", claimed, re.I)
    if m:
        num = m.group(1)
        patterns = [
            rf"\bt\s*[+=]?\s*\+?{re.escape(num)}\b",
            rf"\*\*\+?{re.escape(num)}\*\*",
            rf"\|\s*\+?{re.escape(num)}\s*\|",
            rf"(?<![0-9.])\+?{re.escape(num)}(?![0-9])",
        ]
        return any(re.search(p, txt, re.I) for p in patterns)

    m = re.search(r"(?:PF|profit_factor)\s*[~≈]?\s*([0-9]+\.[0-9]+)", claimed, re.I)
    if m:
        num = m.group(1)
        # Markdown / text: exact display forms (rounding handled for JSON walk separately)
        patterns = [
            rf"\bPF\b[^0-9]{{0,10}}{re.escape(num)}\b",
            rf"\*\*{re.escape(num)}\*\*",
            rf"\|\s*{re.escape(num)}\s*\|",
            rf"profit_factor[^\n]{{0,40}}{re.escape(num)}",
        ]
        return any(re.search(p, txt, re.I) for p in patterns)

    m = re.search(r"(?:holdout\s*)?([0-9]+\.[0-9]+)\s*(?:holdout)?", claimed, re.I)
    if m and "holdout" in claimed.lower():
        num = m.group(1)
        if re.search(
            rf"holdout[^\n]{{0,40}}{re.escape(num)}|{re.escape(num)}[^\n]{{0,40}}holdout",
            txt,
            re.I,
        ):
            return True
        return bool(
            re.search(rf"\|\s*Holdout\s*\|[^\n]*\*\*?{re.escape(num)}", txt, re.I)
        )

    m = re.search(r"([+−-]\d+\.\d+)", claimed)
    if m and (
        claimed.startswith(("+", "-", "−", "H", "t", "T"))
        or re.fullmatch(r"[+−-]\d+\.\d+", claimed)
    ):
        num = m.group(1).replace("−", "-")
        norm = txt.replace("−", "-")
        variants = {num, num.replace("-", "−")}
        if num.startswith(("+", "-")):
            variants.add(num[1:])
        for v in variants:
            if re.search(rf"(?<![0-9.]){re.escape(v)}(?![0-9])", norm):
                return True
            if re.search(rf"(?<![0-9.]){re.escape(v)}(?![0-9])", txt):
                return True
        return False

    m = re.fullmatch(r"(\d+)\s*/\s*(\d+)", claimed)
    if m:
        a, b = m.group(1), m.group(2)
        return bool(re.search(rf"\b{a}\s*/\s*{b}\b", txt))

    return claimed in txt


def _text_has_metric(txt: str, claimed: str) -> bool:
    return _metric_match(txt, claimed, path="")


def _tracked_results_files(tracked: set[str]) -> list[str]:
    """All tracked files under results/ at any depth (git ls-files), excluding raw CSVs."""
    out = []
    for f in sorted(tracked):
        if not f.startswith("results/"):
            continue
        fl = f.lower()
        if fl.endswith(".csv") or "/instrument_data/" in fl:
            continue
        if "registry" in fl and fl.endswith(".jsonl"):
            continue
        # Never use the auditor's own outputs as metric oracles
        base = f.rsplit("/", 1)[-1]
        if base.startswith("research_claim"):
            continue
        out.append(f)
    return out


def _attr_tokens(attr: str, src: str = "") -> list[str]:
    """Family/lane tokens used to gate oracle paths."""
    blob = f"{attr} {src}".lower()
    toks = re.findall(r"[a-z][a-z0-9_]{4,}", blob)
    # Drop noise
    noise = {
        "results", "docs", "research", "claim", "metric", "pooled", "profit",
        "factor", "screen", "family", "attribution", "record", "backtest",
        "write", "status", "loop", "charter", "json", "report",
    }
    out = []
    seen = set()
    for t in toks:
        t = re.sub(r"_v\d+$", "", t)
        t = t.rstrip("*")
        if t in noise or len(t) < 5:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    # Aliases so lane jargon ties to artifact paths/search_ids
    extras: list[str] = []
    joined = " ".join(out)
    if "mean_reversion" in joined or "reversion" in joined:
        extras.extend(["ny_mr", "mr_limit", "mean_reversion", "eurusd_ny_mr"])
    if "us100" in joined or "us_index" in joined or "flatten" in joined:
        extras.extend(["us_index", "us100", "scalp_backtest"])
    for t in extras:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _path_tied_to_attr(path: str, tokens: list[str]) -> bool:
    if not tokens:
        return False
    pl = path.lower()
    for t in tokens:
        if t in pl:
            return True
        # prefix of multi-segment family ids (exog_london ⊂ exog_london_fx_...)
        parts = t.split("_")
        if len(parts) >= 2 and "_".join(parts[:2]) in pl and parts[0] in pl:
            return True
    return False


def _content_tied_to_attr(path: str, tokens: list[str]) -> bool:
    """True when artifact text mentions an attribution token (family_id / lane)."""
    if not tokens:
        return False
    txt = (_read(path) or "")[:80000].lower()
    if not txt:
        return False
    return any(t in txt for t in tokens)


def _artifact_tied(path: str, tokens: list[str]) -> bool:
    return _path_tied_to_attr(path, tokens) or _content_tied_to_attr(path, tokens)


def _claimed_float(claimed: str) -> tuple[float, int, str] | None:
    """Return (value, decimals, kind) for numeric metric claims."""
    claimed = claimed.strip()
    m = re.search(r"(?:PF|profit_factor|pooled\s+PF)\s*[~≈]?\s*([0-9]+\.[0-9]+)", claimed, re.I)
    if m:
        s = m.group(1)
        return float(s), len(s.split(".")[-1]), "pf"
    m = re.fullmatch(r"n\s*=\s*(\d+)", claimed, re.I)
    if m:
        return float(m.group(1)), 0, "n"
    m = re.fullmatch(r"t\s*[+]?\s*([0-9]+\.[0-9]+)", claimed, re.I)
    if m:
        s = m.group(1)
        return float(s), len(s.split(".")[-1]), "t"
    m = re.search(r"([+−-]\d+\.\d+)", claimed)
    if m and claimed[0:1] in "+-−HtT":
        s = m.group(1).replace("−", "-")
        return float(s), len(s.split(".")[-1].lstrip("-")), "signed"
    return None


def _round_eq(artifact: float, claimed: float, decimals: int) -> bool:
    return round(artifact, decimals) == round(claimed, decimals)


def _walk_json_numbers(obj: object, prefix: str = "") -> list[tuple[str, float]]:
    """Yield (json_key_path, number) for every numeric leaf."""
    out: list[tuple[str, float]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}/{k}" if prefix else f"/{k}"
            out.extend(_walk_json_numbers(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{prefix}/{i}"
            out.extend(_walk_json_numbers(v, p))
    elif isinstance(obj, bool):
        return out
    elif isinstance(obj, (int, float)):
        out.append((prefix or "/", float(obj)))
    return out


def _json_pf_hit(path: str, claimed: str) -> tuple[bool, str]:
    """Match PF/profit_factor in nested JSON with rounding; return (ok, key_path)."""
    info = _claimed_float(claimed)
    if info is None or info[2] not in {"pf", "n", "t", "signed"}:
        return False, ""
    claimed_v, decimals, kind = info
    try:
        obj = json.loads(_read(path) or "")
    except Exception:
        return False, ""
    numbers = _walk_json_numbers(obj)
    # Prefer semantically matching keys
    preferred = []
    other = []
    for jp, val in numbers:
        jl = jp.lower()
        is_pref = (
            (kind == "pf" and ("profit_factor" in jl or jl.endswith("/pf")))
            or (kind == "n" and ("n_signals" in jl or jl.endswith("/n") or "n_trades" in jl))
            or (kind == "t" and (jl.endswith("/t") or "t_stat" in jl or "/tstat" in jl))
        )
        if is_pref:
            preferred.append((jp, val))
        else:
            other.append((jp, val))
    for jp, val in preferred:
        if _round_eq(val, claimed_v, decimals):
            return True, jp
    # Do NOT fall back to arbitrary numeric leaves — that is cross-field coincidence
    return False, ""


def _rank_results(f: str) -> tuple[int, str]:
    if f.endswith(".json"):
        return (0, f)
    if f.endswith(".jsonl"):
        return (1, f)
    if f.endswith(".md"):
        return (2, f)
    return (5, f)


def resolve_metric(claim: dict, tracked: set[str]) -> tuple[str, str]:
    """Resolve metric claims against the full tracked results/** tree.

    Named write-ups first. Attribution gates which artifacts may resolve a claim.
    Nested JSON is walked by key path; floats round to the claim's precision.
    """
    claimed = claim["claimed"].strip()
    if _is_iso_date_metric(claimed):
        return "skipped_date", "date_not_a_metric"

    attr = claim.get("attribution") or ""
    src = claim["file"]
    # Instruction files restate figures for guidance — never metric oracles.
    # (Repo-root README.md is in INSTRUCTION_FILES; docs/** READMEs remain normal docs.)
    if src in INSTRUCTION_FILES:
        return "unresolvable", "instruction_file_not_metric_oracle"
    tracked = tracked or run_git_ls_files()
    checked: list[str] = []
    tokens = _attr_tokens(attr, "")

    def _is_results_artifact(f: str) -> bool:
        return f.startswith("results/") and f in tracked

    # --- Pass 0: explicitly named write-up (strongest) ---
    named = [f for f in _named_result_artifacts(claim) if _is_results_artifact(f)]
    named_tried: list[str] = []
    for f in named:
        checked.append(f)
        named_tried.append(f)
        if f.endswith(".json"):
            hit, jkey = _json_pf_hit(f, claimed)
            if hit:
                return "ok", f"named:{f}{jkey}"
            # also allow text match inside json (rare)
        txt = _read(f)
        if txt is None:
            continue
        if _metric_match(txt, claimed, path=f):
            return "ok", f"named:{f}"
        # JSON walk miss already handled; md miss → continue other named
        if f.endswith((".md", ".txt")) and not _metric_match(txt, claimed, path=f):
            pass
    if named_tried:
        # All named files missed (ok returns would have exited already).
        return "drift", f"named_writeup_miss:{named_tried[0]}; checked={checked!r}; n_searched={len(checked)}"

    # --- Candidate set: full tracked results/** gated by attribution ---
    all_results = _tracked_results_files(tracked)
    n_results_scope = len(all_results)
    if tokens:
        # Path or content must tie to family_id/lane — full tree is visible to the gate.
        candidates = [f for f in all_results if _artifact_tied(f, tokens)]
    else:
        # No attribution → keep legacy corpus only (do not open full tree ungated)
        corpus = _metric_corpus(attr, src)
        candidates = [f for f in corpus if _is_results_artifact(f) and f in all_results]

    candidates = sorted(set(candidates), key=_rank_results)

    # Pass 1: JSON (nested walk + rounding)
    json_artifacts = [f for f in candidates if f.endswith(".json")]
    for f in json_artifacts:
        checked.append(f)
        hit, jkey = _json_pf_hit(f, claimed)
        if hit:
            return "ok", f"{f}{jkey}"

    # Pass 2: results markdown write-ups
    md_artifacts = [f for f in candidates if f.endswith(".md")]
    for f in md_artifacts:
        checked.append(f)
        if _metric_match(_read(f) or "", claimed, path=f):
            return "ok", f

    src_txt = _read(src) or ""
    src_has = _metric_match(src_txt, claimed, path=src)
    searched_note = f"n_searched={len(checked)}; scope_results={n_results_scope}; sample={checked[:5]!r}"

    if checked and not src_has and _claimed_float(claimed) is not None:
        return "drift", f"results_oracle_miss {searched_note}; claimed={claimed!r}"

    if src_has:
        return "self_referential", f"claiming_file_only {searched_note}"

    return "unresolvable", f"{searched_note}; claimed={claimed!r}"



def _zacks_status() -> str:
    z = _read("docs/research/ZACKS-MCP-OVERLAY-LANE.md") or ""
    m = re.search(r"\*\*Status:\*\*\s*(.+)", z)
    return m.group(1).strip() if m else ""


def disposition_ok(claim: dict, tracked: set[str]) -> tuple[str, str]:
    claimed = claim["claimed"].strip().strip("`")
    attr = (claim.get("attribution") or "").strip()
    src = claim["file"]
    attr_l = attr.lower()
    standing = standing_from_loop()

    # "BLOCKED for KEEP" is ONE status phrase — trailing KEEP is not a claim.
    if _blocked_for_phrase_component(claim):
        return "ok", "blocked_for_phrase_component"

    # Instruction claim: "HTF Fib docs disagree on signal index" — verify agreement.
    if claimed == "HTF Fib docs disagree on signal index":
        agree, detail = htf_signal_docs_agree(ROOT)
        if agree:
            return "drift", f"stale instruction claim; {detail}"
        return "ok", detail

    # Field-name-only keys referencing status
    if claimed in ("promote", "live_go", "next_step"):
        return "ok", f"status-key:{claimed}"

    # Forbidden tokens documented as forbidden
    if claimed in ("promote=true", "live_go=true") and "forbidden" in attr_l:
        return "ok", "documented-forbidden"

    # Standing booleans
    if claimed in ("promote=no", "promote=false"):
        if standing["promote"] in ("no", "false"):
            return "ok", f"standing promote={standing['promote']!r}"
        return "drift", f"standing promote={standing['promote']!r}"
    if claimed == "live_go=false":
        if standing["live_go"] in ("false", "no"):
            return "ok", f"standing live_go={standing['live_go']!r}"
        return "drift", f"standing live_go={standing['live_go']!r}"
    if claimed in ("promote=true", "live_go=true"):
        return "drift", f"standing promote={standing['promote']!r}"

    # Standing next_step
    if claimed == "RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS":
        if standing["next_step"] == claimed:
            return "ok", standing["next_step"]
        return "drift", standing["next_step"]
    if claimed == "RESEARCH_IDLE":
        # Abbreviation of current standing is accepted when standing is the pending thesis idle,
        # and also appears as historical next_step in the status ledger.
        if standing["next_step"].startswith("RESEARCH_IDLE"):
            return "ok", standing["next_step"]
        return "drift", standing["next_step"]

    # Zacks hand-check pair
    if "zacks" in attr_l or src.endswith("ZACKS-MCP-OVERLAY-LANE.md") or (
        src == "docs/README.md" and "zacks" in attr_l
    ):
        st = _zacks_status()
        if claimed == "New edge":
            return "drift", f"Zacks status={st!r} (BLOCKED/SCHEMA_PASS, not New edge)"
        if claimed == "SCHEMA_PASS" and "SCHEMA_PASS" in st:
            return "ok", st
        if claimed == "BLOCKED" and "BLOCKED" in st:
            return "ok", st
        if claimed == "KEEP":
            if "later KEEP" in attr or "KEEP path" in attr:
                return "ok", "later KEEP path (not current status)"
            # Standalone KEEP vs Zacks status (not a BLOCKED-for component — those return earlier)
            if "KEEP" in st and "BLOCKED" in st:
                return "drift", f"status={st!r} (BLOCKED, not KEEP)"
            return "drift", f"status={st!r} (not KEEP)"

    # Family dispositions via registry (latest wins)
    reg = _read("results/xau_charter_disposition_registry.jsonl") or ""
    latest: dict[str, str] = {}
    for line in reg.splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        fid = str(row.get("family_id") or "")
        cpath = str(row.get("charter_path") or "")
        disp = str(row.get("disposition") or "")
        if not disp:
            continue
        key = fid or cpath
        if key:
            latest[key] = disp
        # also index by basename stem
        if cpath:
            latest[Path(cpath).stem] = disp

    # Match attribution to a family. Prefer versioned exact match so v1 SUPERSEDED
    # is not compared to v2 SCREEN_FAIL via a stripped family id.
    versioned_toks = re.findall(r"[a-z0-9_]+_v\d+", attr_l)
    matched_disp = None
    matched_key = None
    if versioned_toks:
        for tok in versioned_toks:
            for key, disp in latest.items():
                key_l = key.lower()
                stem = Path(key_l).stem if "/" in key_l or key_l.endswith(".json") else key_l
                stem = stem.replace(".json", "")
                if tok in (key_l, stem) or tok in key_l or key_l.endswith(tok):
                    matched_disp, matched_key = disp, key
                    break
            if matched_disp is not None:
                break
    if matched_disp is None:
        for key, disp in latest.items():
            key_l = key.lower()
            fam = re.sub(r"_v\d+$", "", key_l)
            if fam and (fam in attr_l or key_l in attr_l):
                matched_disp, matched_key = disp, key
                break

    if matched_disp is not None:
        disp = matched_disp
        if claimed == disp or claimed in disp or disp in claimed:
            return "ok", disp
        if claimed == "SCREEN_FAIL" and disp == "PROTOCOL_NULL_INVALID":
            return "drift", disp
        if claimed.startswith("SCREEN_FAIL") and disp == "SCREEN_FAIL":
            return "ok", disp
        # Explicit terminal / gate dispositions: mismatch is drift (incl. KEEP vs SCREEN_FAIL)
        if claimed in (
            "SUPERSEDED",
            "PROTOCOL_NULL_INVALID",
            "SCREEN_FAIL",
            "ZERO_PRIMARY_PASSERS",
            "KEEP",
            "BLOCKED",
            "SCHEMA_PASS",
            "New edge",
        ):
            if claimed in disp or disp == claimed:
                return "ok", disp
            return "drift", f"{matched_key}:{disp}"

    # Kill lines / triage verdicts — must appear in SoT artifacts
    # Do NOT use this fallback for KEEP/BLOCKED/SCHEMA_PASS/New edge — those must
    # bind to an artifact status (negative controls rely on this).
    if claimed not in ("KEEP", "BLOCKED", "SCHEMA_PASS", "New edge"):
        sot_blob = (
            (_read("docs/research/BACKTEST-RECORD.md") or "")
            + "\n"
            + (_read("results/xau_loop_status.md") or "")
            + "\n"
            + (_read("results/xau_null_maxstat.md") or "")
            + "\n"
            + (_read("results/xau_donchian_null_maxstat.md") or "")
            + "\n"
            + (_read("results/eurusd_ny_mr_limit_fill_paper_gate_v1.md") or "")
            + "\n"
            + (_read(src) or "")
        )
        if claimed in sot_blob or claimed.replace("→", "->") in sot_blob.replace("→", "->"):
            return "ok", f"present-for:{attr or src}"

        if claimed in (_read(src) or ""):
            return "ok", src

    return "unresolvable", f"disposition {claimed!r} attr={attr!r}"



def _load_selfref_allowlist() -> list[dict]:
    p = ROOT / "results" / "research_claim_selfref_allow.json"
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text())
    except Exception:
        return []
    return list(data.get("allow") or [])


def _selfref_allowlisted(row: dict, allow: list[dict]) -> bool:
    for a in allow:
        if (
            a.get("file") == row.get("file")
            and int(a.get("line") or -1) == int(row.get("line") or -2)
            and a.get("kind") == row.get("kind")
            and a.get("claimed") == row.get("claimed")
            and (a.get("reason") or "").strip()
            and int(a.get("n_searched") or 0) > 0
            and isinstance(a.get("searched_sample"), list)
        ):
            # Reject reasons that assert no-artifact without full-tree provenance
            reason = str(a.get("reason") or "").lower()
            if (
                ("no separate results artifact" in reason or "no results artifact" in reason)
                and "full tree" not in reason
                and "n_searched" not in reason
            ):
                continue
            return True
    return False


def verify_claims(claims: list[dict], tracked: set[str] | None = None) -> dict:
    """Resolve a claim list. Returns structured drift[] and exempt_secrets."""
    tracked = tracked if tracked is not None else run_git_ls_files()
    n_ok = n_drift = n_unresolvable = n_exempt_secrets = 0
    n_sha_unresolvable = 0
    n_self_referential = 0
    n_skipped_dates = 0
    evidence: list[str] = []
    drift: list[dict] = []
    unresolvable: list[dict] = []
    exempt_secrets: list[dict] = []
    self_referential: list[dict] = []
    zacks_handcheck: list[str] = []
    allow = _load_selfref_allowlist()

    st = _zacks_status()
    zacks_handcheck.append(f"ZACKS_STATUS={st!r}")

    for cl in claims:
        kind = cl["kind"]
        try:
            if kind in ("path", "link"):
                status, actual = resolve_path_or_link(cl, tracked)
            elif kind == "sha":
                status, actual = resolve_sha(cl, tracked)
            elif kind == "symbol":
                status, actual = resolve_symbol(cl, tracked)
            elif kind == "metric":
                status, actual = resolve_metric(cl, tracked)
            elif kind == "disposition":
                status, actual = disposition_ok(cl, tracked)
            elif kind == "consistency":
                status, actual = resolve_consistency(cl, ROOT)
            else:
                status, actual = "unresolvable", f"unknown_kind={kind}"
        except Exception as e:  # noqa: BLE001 — auditor must not crash a claim
            status, actual = "unresolvable", f"checker error: {e}"

        if cl["kind"] == "disposition" and (
            "zacks" in (cl.get("attribution") or "").lower()
            or cl["file"].endswith("ZACKS-MCP-OVERLAY-LANE.md")
            or (
                cl["file"] == "docs/README.md"
                and "zacks" in (cl.get("attribution") or "").lower()
            )
        ):
            zacks_handcheck.append(
                f"hand:{cl['file']}:{cl['line']}:{cl['claimed']}->{status}:{actual}"
            )

        row = {
            "file": cl.get("file"),
            "line": cl.get("line"),
            "kind": kind,
            "claimed": cl.get("claimed"),
            "actual": actual,
        }
        if status == "skipped_date":
            n_skipped_dates += 1
            evidence.append(
                f"{cl['file']}|{cl['line']}|{cl['kind']}|{cl['claimed']}|SKIPPED_DATE"
            )
            continue
        if status == "ok":
            n_ok += 1
        elif status == "exempt_secrets":
            n_exempt_secrets += 1
            n_ok += 1  # resolves OK; counted visibly in exempt_secrets
            exempt_secrets.append(row)
            evidence.append(
                f"{cl['file']}|{cl['line']}|{cl['kind']}|{cl['claimed']}|EXEMPT_SECRETS:{actual}"
            )
        elif status == "drift":
            n_drift += 1
            drift.append(row)
            evidence.append(
                f"{cl['file']}|{cl['line']}|{cl['kind']}|{cl['claimed']}|{actual}"
            )
        elif status == "self_referential":
            n_self_referential += 1
            self_referential.append(row)
            evidence.append(
                f"{cl['file']}|{cl['line']}|{cl['kind']}|{cl['claimed']}|SELF_REF:{actual}"
            )
        else:
            n_unresolvable += 1
            unresolvable.append(row)
            if kind == "sha":
                n_sha_unresolvable += 1
            evidence.append(
                f"{cl['file']}|{cl['line']}|{cl['kind']}|{cl['claimed']}|UNRESOLVABLE:{actual}"
            )

    # Digest unresolvable is fatal. Self-referential is fatal unless allowlisted.
    n_selfref_unallowlisted = sum(
        1 for r in self_referential if not _selfref_allowlisted(r, allow)
    )
    ok = n_sha_unresolvable == 0 and n_selfref_unallowlisted == 0
    n_results_tracked = len(_tracked_results_files(tracked))
    return {
        "ok": ok,
        "n_ok": n_ok,
        "n_drift": n_drift,
        "n_unresolvable": n_unresolvable,
        "n_sha_unresolvable": n_sha_unresolvable,
        "n_exempt_secrets": n_exempt_secrets,
        "n_self_referential": n_self_referential,
        "n_selfref_unallowlisted": n_selfref_unallowlisted,
        "n_skipped_dates": n_skipped_dates,
        "n_results_tracked": n_results_tracked,
        "n_claims": len(claims),
        "drift": drift,
        "unresolvable": unresolvable,
        "exempt_secrets": exempt_secrets,
        "self_referential": self_referential,
        "zacks_handcheck": zacks_handcheck,
        "evidence": evidence,
    }


def verify_all(
    inventory_path: Path | None = None,
    *,
    refresh_instruction: bool = True,
    write_inventory: bool = True,
) -> dict:
    inv_path = inventory_path or INV
    data = json.loads(inv_path.read_text())
    if refresh_instruction:
        data = merge_instruction_into_inventory(ROOT, data)
        if write_inventory:
            inv_path.write_text(json.dumps(data, indent=2) + "\n")
    report = verify_claims(data["claims"])
    report["n_instruction_claims"] = data.get("n_instruction_claims", 0)
    report["corpus"] = data.get("corpus", {})
    report["instruction_files"] = data.get("instruction_files", list(INSTRUCTION_FILES))
    return report


def resolve_one(claim: dict, tracked: set[str] | None = None) -> tuple[str, str]:
    """Single-claim resolver used by the mutant gate (same predicates as Verify)."""
    tracked = tracked if tracked is not None else run_git_ls_files()
    kind = claim["kind"]
    if kind in ("path", "link"):
        return resolve_path_or_link(claim, tracked)
    if kind == "sha":
        return resolve_sha(claim, tracked)
    if kind == "symbol":
        return resolve_symbol(claim, tracked)
    if kind == "metric":
        return resolve_metric(claim, tracked)
    if kind == "disposition":
        return disposition_ok(claim, tracked)
    if kind == "consistency":
        return resolve_consistency(claim, ROOT)
    return "unresolvable", f"unknown_kind={kind}"


def run_negative_controls() -> dict:
    """Anti-overcorrection gate: four controls that MUST come back RED (drift)."""
    tracked = run_git_ls_files()
    controls = []

    def check(name: str, claim: dict, expect_status: str = "drift") -> None:
        status, actual = resolve_one(claim, tracked)
        ok_red = status == expect_status
        controls.append(
            {
                "name": name,
                "claim": claim,
                "status": status,
                "actual": actual,
                "must_be_red": True,
                "is_red": ok_red,
            }
        )

    # 1) Genuinely missing path in NON-secrets context
    check(
        "missing_path_non_secrets",
        {
            "file": "docs/README.md",
            "line": 40,
            "kind": "path",
            "claimed": "scripts/__negctrl_missing_path_does_not_exist__.sh",
            "attribution": "broker switch",
        },
    )

    # 2) Path named in secrets context that is NOT gitignored → still caught
    # Use README secrets line (69) as context, but a path that is not gitignored.
    check(
        "secrets_context_not_gitignored",
        {
            "file": "docs/README.md",
            "line": 69,
            "kind": "path",
            "claimed": "scripts/__negctrl_secrets_ctx_not_ignored__.py",
            "attribution": "never-commit instruction context",
        },
    )

    # 3) Standalone KEEP (not part of BLOCKED for KEEP phrase)
    # Pick a line that does not contain "BLOCKED for KEEP" — BACKTEST-RECORD header area.
    check(
        "standalone_KEEP",
        {
            "file": "docs/research/BACKTEST-RECORD.md",
            "line": 1,
            "kind": "disposition",
            "claimed": "KEEP",
            "attribution": "asia_box_london_sweep_fade_flat standalone KEEP assertion",
        },
    )

    # 4) Doc asserting KEEP for a family the registry marks SCREEN_FAIL
    check(
        "KEEP_vs_SCREEN_FAIL_family",
        {
            "file": "docs/research/BACKTEST-RECORD.md",
            "line": 20,
            "kind": "disposition",
            "claimed": "KEEP",
            "attribution": "asia_box_london_sweep_fade_flat",
        },
    )

    # 5) Metric that disagrees with its named results/*.md write-up → drift
    check(
        "metric_disagrees_named_writeup",
        {
            "file": "docs/research/US-INDEX-SESSION-SCALP-DESIGN.md",
            "line": 92,
            "kind": "metric",
            "claimed": "PF 9.99",
            "attribution": "US100 all",
        },
    )

    # 6) Named write-up omits the figure entirely → drift (not self_referential)
    check(
        "named_writeup_omits_figure",
        {
            "file": "docs/research/US-INDEX-SESSION-SCALP-DESIGN.md",
            "line": 92,
            "kind": "metric",
            "claimed": "n=424242",
            "attribution": "US100 all",
        },
    )

    # 7) Genuinely self-referential claim → self_referential, never ok
    check(
        "genuine_self_referential",
        {
            "file": "docs/research/SIGNAL-EDGE-TRIAGE.md",
            "line": 50,
            "kind": "metric",
            "claimed": "+70.19",
            "attribution": "exog_london_fx_cosign_xau_follow_flat",
        },
        expect_status="self_referential",
    )

    # 8) Substring in unrelated CSV price rows is NOT a resolution
    csv_paths = [
        t
        for t in tracked
        if t.endswith(".csv") and ("xauusd" in t.lower() or "instrument_data" in t)
    ][:5]
    csv_hit = False
    for cp in csv_paths:
        if _metric_match(_read(cp) or "", "1.20", path=cp):
            csv_hit = True
            break
    # Also ensure resolve_one does not return ok for a PF that only coincides in CSV
    st_csv, act_csv = resolve_one(
        {
            "file": "docs/research/US-INDEX-SESSION-SCALP-DESIGN.md",
            "line": 1,
            "kind": "metric",
            "claimed": "PF 1.20",
            "attribution": "unrelated csv coincidence probe",
        },
        tracked,
    )
    csv_ok = (not csv_hit) and st_csv != "ok"
    controls.append(
        {
            "name": "csv_substring_not_resolution",
            "claim": {"claimed": "1.20", "paths": csv_paths, "resolve_status": st_csv},
            "status": "ok" if not csv_ok else "drift",
            "actual": f"csv_hit={csv_hit}; resolve={st_csv}:{act_csv}",
            "must_be_red": True,
            "is_red": csv_ok,
        }
    )

    # 9) Rounding must not swallow real disagreement at claimed precision
    check(
        "precision_disagreement_not_rounded_away",
        {
            "file": "docs/README.md",
            "line": 1,
            "kind": "metric",
            "claimed": "pooled PF 0.913",
            "attribution": "exog_london_fx_cosign_xau_follow_flat",
        },
    )

    # 10) Cross-family numeric collision is NOT ok
    st_xf, act_xf = resolve_one(
        {
            "file": "docs/README.md",
            "line": 1,
            "kind": "metric",
            "claimed": "pooled PF 0.903",
            "attribution": "asia_box_london_sweep_fade_flat",
        },
        tracked,
    )
    controls.append(
        {
            "name": "cross_family_numeric_collision",
            "claim": {
                "claimed": "pooled PF 0.903",
                "attribution": "asia_box_london_sweep_fade_flat",
            },
            "status": st_xf,
            "actual": act_xf,
            "must_be_red": True,
            "is_red": st_xf != "ok",
        }
    )

    # 11) Untracked results/ file is NOT an oracle
    probe = ROOT / "results" / "_audit_untracked_probe.json"
    probe.write_text(
        json.dumps({"report": {"pooled": {"profit_factor": 0.777123456}}}) + "\n"
    )
    try:
        st_ut, act_ut = resolve_one(
            {
                "file": "docs/README.md",
                "line": 1,
                "kind": "metric",
                "claimed": "pooled PF 0.777",
                "attribution": "exog_london_fx_cosign_xau_follow_flat",
            },
            tracked,
        )
        controls.append(
            {
                "name": "untracked_results_not_oracle",
                "claim": {"claimed": "pooled PF 0.777", "probe": str(probe)},
                "status": st_ut,
                "actual": act_ut,
                "must_be_red": True,
                "is_red": st_ut != "ok",
            }
        )
    finally:
        probe.unlink(missing_ok=True)

    # 12) Instruction-file claim contradicting its target doc → drift
    check(
        "instruction_contradicts_target",
        {
            "file": "CLAUDE.md",
            "line": 67,
            "kind": "disposition",
            "claimed": "HTF Fib docs disagree on signal index",
            "attribution": "mql5/README.md + docs/HOWTO-HTF-FIB.md",
        },
    )

    # 13) Roster broker missing from enumerating site → drift (scratch site without SoT)
    import tempfile

    _td = Path(tempfile.mkdtemp(prefix="claim_neg_roster_"))
    _scratch = _td / "site_no_wsf.sh"
    _scratch.write_text(
        'for d in "Vantage International MT5" "FP Markets MT5 Terminal"; do :; done\n'
    )
    check(
        "roster_broker_missing_from_site",
        {
            "file": "scripts/19-run-htf-fib-backtest.sh",
            "line": 1,
            "kind": "consistency",
            "claimed": "broker_roster_coverage",
            "attribution": "config/brokers/*.env",
            "site": "scripts/19-run-htf-fib-backtest.sh",
            "site_path": str(_scratch),
            "roster": ["fpmarkets", "vantage", "wsf"],
            "generic_ok": False,
        },
    )

    # 14) Metric claim must NOT resolve ok against CLAUDE.md
    st_mo, act_mo = resolve_one(
        {
            "file": "CLAUDE.md",
            "line": 1,
            "kind": "metric",
            "claimed": "PF 0.903",
            "attribution": "exog_london_fx_cosign_xau_follow_flat",
        },
        tracked,
    )
    controls.append(
        {
            "name": "instruction_not_metric_oracle",
            "claim": {"file": "CLAUDE.md", "claimed": "PF 0.903"},
            "status": st_mo,
            "actual": act_mo,
            "must_be_red": True,
            "is_red": st_mo != "ok",
        }
    )

    # 15) Generic overridable default_bridge_dir is NOT missing-broker drift
    check(
        "generic_bridge_not_false_positive",
        {
            "file": GENERIC_BRIDGE_SITE,
            "line": 23,
            "kind": "consistency",
            "claimed": "generic_bridge_default_exempt",
            "attribution": "MT5_BRIDGE_DIR overridable",
            "site": GENERIC_BRIDGE_SITE,
            "roster": ["fpmarkets", "vantage", "wsf"],
            "generic_ok": True,
        },
        expect_status="ok",  # red means: must stay ok (control checks is_red = status==expect)
    )

    n_red = sum(1 for c in controls if c["is_red"])
    all_red = n_red == len(controls)
    return {
        "ok": all_red,
        "all_red": all_red,
        "n_controls": len(controls),
        "n_red": n_red,
        "controls": controls,
        "evidence": "; ".join(
            f"{c['name']}={c['status']}:{'RED' if c['is_red'] else 'GREEN-FAIL'}"
            for c in controls
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--inventory",
        type=Path,
        default=INV,
        help="claim inventory JSON (default: results/research_claim_inventory.json)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="result JSON path (default: results/research_claim_verify_result.json)",
    )
    p.add_argument(
        "--negative-controls",
        action="store_true",
        help="run anti-overcorrection negative controls only",
    )
    p.add_argument(
        "--fail-on-drift",
        action="store_true",
        help=(
            "exit non-zero when n_drift>0 or n_sha_unresolvable>0 or "
            "n_selfref_unallowlisted>0 (CI opt-in). Does not change report['ok'] "
            "semantics (checker-completed). Implies read-only inventory (no write)."
        ),
    )
    args = p.parse_args(argv)

    out_path = args.out
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.negative_controls:
        report = run_negative_controls()
        out_path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: report[k] for k in ("ok", "all_red", "n_controls", "n_red", "evidence")}, indent=2))
        return 0 if report["all_red"] else 1

    inv_path = args.inventory if args.inventory.is_absolute() else ROOT / args.inventory
    report = verify_all(
        inv_path,
        refresh_instruction=True,
        write_inventory=not args.fail_on_drift,
    )
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    try:
        out_disp = str(out_path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        out_disp = str(out_path.resolve())
    summary = {
        "ok": report["ok"],
        "n_ok": report["n_ok"],
        "n_drift": report["n_drift"],
        "n_unresolvable": report["n_unresolvable"],
        "n_sha_unresolvable": report.get("n_sha_unresolvable", 0),
        "n_exempt_secrets": report["n_exempt_secrets"],
        "n_self_referential": report.get("n_self_referential", 0),
        "n_selfref_unallowlisted": report.get("n_selfref_unallowlisted", 0),
        "n_skipped_dates": report.get("n_skipped_dates", 0),
        "n_results_tracked": report.get("n_results_tracked", 0),
        "n_instruction_claims": report.get("n_instruction_claims", 0),
        "n_claims": report["n_claims"],
        "out": out_disp,
    }
    print(json.dumps(summary, indent=2))
    print("---DRIFT---")
    for d in report["drift"]:
        print(f"{d['file']}|{d['line']}|{d['kind']}|{d['claimed']}|{d['actual']}")
    print("---EXEMPT_SECRETS---")
    for d in report["exempt_secrets"]:
        print(f"{d['file']}|{d['line']}|{d['kind']}|{d['claimed']}|{d['actual']}")
    if args.fail_on_drift:
        audit_fail = (
            int(report.get("n_drift") or 0) > 0
            or int(report.get("n_sha_unresolvable") or 0) > 0
            or int(report.get("n_selfref_unallowlisted") or 0) > 0
        )
        return 1 if audit_fail else 0
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
