#!/usr/bin/env python3
"""Immutable family charters, gate provenance, sealed-run bookkeeping.

Phase-0 research protocol (2026-08-10):

* Charters live under ``results/xau_charters/YYYY-MM-DD_<family>_vN.json``
  and are **write-once** (refuse overwrite).
* Soft/classic gates and null method/n_trials come **only** from the charter.
* Each sealed run records charter path, code commit, data SHA-256, cost-file
  SHA-256, null seed, and a unique output directory.
* Program-level family attempts are appended to
  ``results/xau_family_attempts.jsonl`` (never rewritten as a greenwash log).

Historical note: ``results/xau_next_design_charter.json`` freezes
``prior_day_high_break`` (2026-08-08). Do **not** overwrite it; new families
use the charters/ layout only.

SAFETY: offline only — no live orders.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHARTERS_DIR = ROOT / "results" / "xau_charters"
ATTEMPTS_PATH = ROOT / "results" / "xau_family_attempts.jsonl"
DISPOSITION_REGISTRY = ROOT / "results" / "xau_charter_disposition_registry.jsonl"
LEGACY_CHARTER = ROOT / "results" / "xau_next_design_charter.json"

# Defaults when a gate field is missing (should not happen on new charters).
DEFAULT_CLASSIC_GATES = {
    "n_trades_min": 20,
    "profit_factor_min": 1.5,
    "profit_factor_strict_gt": True,
    "win_rate_min": 55.0,
    "win_rate_strict_gt": True,
    "max_drawdown_pct_max": 10.0,
    "max_drawdown_strict_lt": True,
}

# Minimum null trials for a decisive 0.05 test under add-one smoothing.
# p = (hits+1)/(n+1) ≤ 0.05 ⇒ n+1 ≥ 20 when hits=0 ⇒ n ≥ 19 is *not* enough
# resolution for reporting 0.05 cleanly; require ≥199 (p-step ≈ 0.005).
MIN_NULL_TRIALS_PROTOCOL = 199
PREFERRED_NULL_TRIALS_LOW_KNOB = 999

# Terminal dispositions are monotonic: once seen for a SHA, later non-terminal
# records cannot reverse them (append-only integrity).
TERMINAL_DISPOSITIONS = frozenset(
    {
        "PROTOCOL_NULL_INVALID",
        "SCREEN_FAIL",
        "SUPERSEDED",
        "KILL",
        "KILL_BB_RSI_LINE",
        "KILL_DONCHIAN_LINE",
        "KILL_PRIOR_DAY_HIGH_BREAK",
        "KILL_SERVER_HOUR_WINDOW_FLAT",
        "KILL_TOD_LONDON_NY_FLAT",
        "KILL_EARLY_SERVER_RANGE_BREAK_FLAT",
        "KILL_DAY_OPEN_RECLAIM_FLAT",
    }
)

# Session / server-hour families must preregister this exact algorithm id (v2.2+).
CANONICAL_SESSION_NULL = "within_day_ohlc_increment_rotate_v1"
SESSION_NULL_ALIASES = frozenset(
    {
        CANONICAL_SESSION_NULL,
        # accepted only when charter.protocol_version < 2.2 and notes declare v2.2 algo
        "within_day_return_rotate",
    }
)
SESSION_THESIS_CLASSES = frozenset(
    {
        "server_hour_window_fixed",
        "time_of_day_fixed",
        "session_or_breakout_fixed",
        "session_window_fixed",
        "intraday_early_block_range_break",
        "intraday_day_open_reclaim",
    }
)

# Default null base seed when a freeze pins it (house convention; no seed shopping).
DEFAULT_NULL_BASE_SEED = 20260808
# Sentinel for "base_seed key absent" (None is a possible invalid value).
_MISSING_BASE_SEED = object()

# Exact SHA-256 of immutable historical charter *files* that predate seed
# preregistration and may omit null.base_seed. Grandfathering is by content
# hash only — never by self-declared frozen_at (backdating is not a free pass).
# Computed over on-disk JSON bytes; any mutation loses membership.
GRANDFATHERED_NO_SEED_CHARTER_SHA256: frozenset[str] = frozenset(
    {
        # 2026-08-10 freezes (no base_seed)
        "fee8611c11b352314e1b295916189acc0f0f472fd01a99dac29d1c9997f2e102",  # early_server_range_break_flat v1
        "11099b2a7aa0221187c94462361d53070daecfdc7df0be80f82df5ae1954475a",  # early_server_range_break_flat v2
        "6b5811eedf11838e85733179fcecacacd0a58a978860f1811a6aba4a0be8e064",  # server_hour_window_flat v1
        "26ff7532a4cae730f370d350d39df383e83b01f85e0f5de3e1eac9ae283a464e",  # server_hour_window_flat v2
        "e7cd953f998015bbc9aa5ae23ea7f35c45723f82736a273274f41102bac2f4cf",  # tod_london_ny_flat v1
        # day_open_reclaim_flat v1 SUPERSEDED incomplete freeze (no base_seed)
        "8eafe48b5f57746dc64188364bd073058dc4fe320decd45c15ef1cb481deebea",
    }
)
# Rule keys that mark a charter as session-shaped (canonical session null required).
SESSION_RULE_MARKERS = frozenset(
    {
        "entry_hour",
        "entry_hours_server",
        "entry_allowed_hours_server",
        "early_block_hours_server",
        "flat_hour_server",
        "session_active_hours_server",
    }
)

# Tracked paths that must be clean for dispositional sealed runs.
DISPOSITIONAL_PATH_GLOBS = (
    "scripts/xau_null_core.py",
    "scripts/xau_charter_protocol.py",
    "scripts/xau_family_null_maxstat.py",
    "scripts/xau_sealed_family_cycle.py",
    "scripts/xau_family_*.py",
    # Multi-instrument joint screen harness (must not score with uncommitted logic)
    "scripts/xau_multi_instrument_*.py",
    # Exogenous-predictor core + accounting (Phase B+)
    "scripts/xau_exogenous_predictor_*.py",
    "scripts/xau_research_costs.py",
    "results/xau_research_costs.json",
    "results/xau_charters/*.json",
    "results/xau_charter_disposition_registry.jsonl",
    "results/xau_holdout_lock.json",
    "backtest.py",
)


class CharterError(RuntimeError):
    """Invalid or conflicting charter operation."""


class RegistryError(RuntimeError):
    """Corrupt or inconsistent append-only registry / ledger."""


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(repo: Path = ROOT) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def git_dirty_tracked_paths(repo: Path = ROOT) -> list[str]:
    """Return tracked paths with staged or unstaged modifications (fail-closed for sealed runs)."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain", "-uno"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        raise CharterError(f"cannot determine git dirty state: {e}") from e
    dirty: list[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        # XY<path> or XY orig -> path
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        # only tracked changes: first two cols not ??
        xy = line[:2]
        if xy == "??":
            continue
        dirty.append(path)
    return dirty


def assert_clean_dispositional_tree(repo: Path = ROOT) -> dict[str, Any]:
    """Refuse dispositional runs if protocol/family/cost/charter tracked files are dirty."""
    dirty = git_dirty_tracked_paths(repo)
    if not dirty:
        return {"clean": True, "dirty_paths": [], "code_commit": git_head(repo)}
    # filter to dispositional paths
    import fnmatch

    relevant: list[str] = []
    for p in dirty:
        for pat in DISPOSITIONAL_PATH_GLOBS:
            if fnmatch.fnmatch(p, pat) or p == pat:
                relevant.append(p)
                break
    if relevant:
        raise CharterError(
            "dispositional run refused: dirty tracked protocol/family/cost/registry files:\n  - "
            + "\n  - ".join(sorted(set(relevant)))
            + "\nCommit or stash before sealed/--strict-charter runs."
        )
    return {
        "clean": True,
        "dirty_paths": dirty,
        "dirty_ignored_unrelated": True,
        "code_commit": git_head(repo),
    }


def assert_charter_path_for_sealed(path: Path | str, repo: Path = ROOT) -> dict[str, Any]:
    """Sealed charters must live under results/xau_charters/, be git-tracked, match HEAD.

    Refuses:
    - paths outside ``results/xau_charters/``
    - untracked charter files
    - working-tree bytes that differ from ``git show HEAD:<path>``
    """
    p = Path(path).resolve()
    charters = CHARTERS_DIR.resolve()
    try:
        rel = p.relative_to(charters)
    except ValueError as e:
        raise CharterError(
            f"sealed charter must resolve under {CHARTERS_DIR} (got {p})"
        ) from e
    if ".." in rel.parts:
        raise CharterError(f"sealed charter path escapes charters dir: {p}")

    rel_repo = p.relative_to(repo.resolve())
    rel_s = rel_repo.as_posix()

    # Must be tracked
    try:
        tracked = subprocess.check_output(
            ["git", "-C", str(repo), "ls-files", "--error-unmatch", rel_s],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError as e:
        raise CharterError(
            f"sealed charter is not git-tracked: {rel_s}. "
            "Commit the freeze before a dispositional run."
        ) from e
    if not tracked:
        raise CharterError(f"sealed charter is not git-tracked: {rel_s}")

    # Working tree must match HEAD blob
    try:
        head_bytes = subprocess.check_output(
            ["git", "-C", str(repo), "show", f"HEAD:{rel_s}"],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        raise CharterError(
            f"cannot read HEAD blob for {rel_s} (not on HEAD?). Commit the freeze first."
        ) from e
    work_bytes = p.read_bytes()
    if work_bytes != head_bytes:
        raise CharterError(
            f"sealed charter working tree differs from HEAD:{rel_s}. "
            "Commit or restore before dispositional run."
        )
    return {
        "path": rel_s,
        "charter_sha256": hashlib.sha256(work_bytes).hexdigest(),
        "matches_head": True,
        "tracked": True,
    }


def charter_path(family_id: str, *, day: str | None = None, version: int = 1) -> Path:
    """``results/xau_charters/YYYY-MM-DD_<family>_vN.json``."""
    d = day or date.today().isoformat()
    safe = family_id.strip().replace(" ", "_").replace("/", "_")
    return CHARTERS_DIR / f"{d}_{safe}_v{version}.json"


def load_charter(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise CharterError(f"charter not found: {p}")
    return json.loads(p.read_text())


def charter_file_sha256(path: Path | str) -> str:
    return sha256_file(Path(path)) or ""


def _parse_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    """Parse JSONL fail-closed: any malformed non-empty line raises RegistryError."""
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise RegistryError(
                f"corrupt JSONL {path} line {lineno}: {e}. "
                "Refuse to continue (fail closed)."
            ) from e
        if not isinstance(rec, dict):
            raise RegistryError(f"corrupt JSONL {path} line {lineno}: expected object")
        rows.append(rec)
    return rows


def _is_terminal_disposition(d: str | None) -> bool:
    if not d:
        return False
    if d in TERMINAL_DISPOSITIONS:
        return True
    # any KILL_* label is terminal
    return d.startswith("KILL")


def registry_disposition(charter_sha256: str, path: Path = DISPOSITION_REGISTRY) -> dict[str, Any] | None:
    """Effective disposition for a charter SHA (monotonic terminal states).

    Walks append-only history fail-closed. Once a **terminal** disposition is
    recorded for the SHA, later non-terminal records (e.g. PASS) are ignored for
    runnability — they do not reverse the terminal state.
    """
    if not charter_sha256:
        return None
    rows = _parse_jsonl_strict(path)
    terminal: dict[str, Any] | None = None
    latest: dict[str, Any] | None = None
    for rec in rows:
        if rec.get("charter_sha256") != charter_sha256:
            continue
        latest = rec
        d = str(rec.get("disposition") or "")
        if _is_terminal_disposition(d):
            terminal = rec
    # terminal wins if any
    return terminal if terminal is not None else latest


def is_charter_runnable(path: Path | str) -> tuple[bool, str]:
    """False if registry marks this charter SHA as invalid/superseded/killed."""
    p = Path(path)
    try:
        sha = charter_file_sha256(p)
    except Exception as e:
        return False, f"cannot hash charter: {e}"
    try:
        rec = registry_disposition(sha)
    except RegistryError as e:
        return False, str(e)
    if rec is None:
        try:
            ch = load_charter(p)
        except Exception as e:
            return False, f"cannot load charter: {e}"
        d = ch.get("disposition")
        if _is_terminal_disposition(str(d) if d else None) or d in (
            "PROTOCOL_NULL_INVALID",
            "SCREEN_FAIL",
            "SUPERSEDED",
        ):
            return False, f"in-file disposition={d!r} (prefer registry; do not mutate freezes)"
        return True, "ok"
    d = str(rec.get("disposition") or "")
    if _is_terminal_disposition(d) or d in (
        "PROTOCOL_NULL_INVALID",
        "SCREEN_FAIL",
        "SUPERSEDED",
        "KILL",
    ):
        return False, f"registry disposition={d!r} for sha={sha[:12]}…"
    return True, "ok"


def write_charter_once(path: Path, charter: dict[str, Any]) -> Path:
    """Write charter JSON; refuse if the path already exists."""
    path = Path(path)
    if path.exists():
        raise CharterError(
            f"charter already exists (immutable): {path}. "
            "Bump version or change family_id/date — never overwrite."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    # Normalize status
    body = dict(charter)
    body.setdefault("status", "FROZEN")
    path.write_text(json.dumps(body, indent=2, sort_keys=False) + "\n")
    return path


EXOGENOUS_PREDICTOR_HARNESS_KIND = "multi_instrument_exogenous_predictor_v1"
EXOGENOUS_NULL_IMPLEMENTATION_ID = "conditional_fixed_signal_events_fixed_trades_v1"
JOINT_HARNESS_KIND = "multi_instrument_joint_v1"


def multi_instrument_single_frame_refuse_message(charter: dict[str, Any]) -> str | None:
    """If charter is multi-instrument (joint or exogenous), refuse single-frame runners.

    Pure check (no I/O, no data, no plugin). Callers must raise/SystemExit with this
    message *before* family plugin import, data load, fixtures, or ledger append.
    """
    harness = charter.get("harness") or {}
    inst = charter.get("instrument") or {}
    kind = str(harness.get("kind") or "")
    multi = kind in (
        JOINT_HARNESS_KIND,
        EXOGENOUS_PREDICTOR_HARNESS_KIND,
    ) or bool(inst.get("multi_symbol_in_scope"))
    if not multi:
        return None
    if kind == EXOGENOUS_PREDICTOR_HARNESS_KIND:
        return (
            "REFUSE_SINGLE_FRAME_RUNNER: charter requires dedicated "
            f"{EXOGENOUS_PREDICTOR_HARNESS_KIND} harness; single-frame runners "
            "(xau_family_null_maxstat / xau_sealed_family_cycle) are forbidden"
        )
    return (
        "REFUSE_SINGLE_FRAME_RUNNER: charter requires dedicated "
        "multi_instrument_joint_v1 harness; single-frame runners "
        "(xau_family_null_maxstat / xau_sealed_family_cycle) are forbidden "
        "(no plugin/data/ledger for multi-instrument joint)"
    )


def exogenous_joint_screen_refuse_message(charter: dict[str, Any]) -> str | None:
    """If charter is exogenous-predictor kind, refuse joint screen harness."""
    kind = str((charter.get("harness") or {}).get("kind") or "")
    if kind == EXOGENOUS_PREDICTOR_HARNESS_KIND:
        return (
            "REFUSE_JOINT_SCREEN: charter harness.kind="
            f"{EXOGENOUS_PREDICTOR_HARNESS_KIND!r}; use dedicated exogenous harness "
            "(xau_multi_instrument_joint_screen is joint-cosign only)"
        )
    return None


def validate_exogenous_predictor_charter(charter: dict[str, Any]) -> list[str]:
    """Hard errors for multi_instrument_exogenous_predictor_v1 instrument/null/gates."""
    errs: list[str] = []
    harness = charter.get("harness") or {}
    kind = str(harness.get("kind") or "")
    if kind != EXOGENOUS_PREDICTOR_HARNESS_KIND:
        errs.append(
            f"exogenous charter requires harness.kind={EXOGENOUS_PREDICTOR_HARNESS_KIND!r}"
        )
    inst = charter.get("instrument") or {}
    symbols = inst.get("symbols")
    traded = inst.get("traded_symbols")
    predictors = inst.get("predictor_symbols")
    if not isinstance(symbols, list) or not symbols:
        errs.append("exogenous instrument.symbols must be a non-empty list")
        symbols = []
    if not isinstance(traded, list):
        errs.append("exogenous instrument.traded_symbols must be a list of length 1")
        traded = []
    elif len(traded) != 1:
        errs.append(
            f"exogenous instrument.traded_symbols must have exactly one symbol "
            f"(got {len(traded)})"
        )
    if not isinstance(predictors, list) or len(predictors) < 1:
        errs.append(
            "exogenous instrument.predictor_symbols must be a non-empty list "
            "(zero predictors forbidden)"
        )
        predictors = []
    if inst.get("multi_symbol_in_scope") is not True:
        errs.append(
            "exogenous instrument.multi_symbol_in_scope must be true (exact boolean)"
        )
    # partition
    if traded and symbols and traded[0] not in symbols:
        errs.append(
            f"exogenous traded_symbols[0]={traded[0]!r} not in instrument.symbols"
        )
    for p in predictors:
        if p not in symbols:
            errs.append(f"exogenous predictor {p!r} not in instrument.symbols")
    if traded and predictors and set(traded) & set(predictors):
        errs.append("exogenous traded_symbols and predictor_symbols must be disjoint")
    if symbols and traded and predictors:
        union = list(traded) + list(predictors)
        if set(union) != set(symbols) or len(union) != len(symbols):
            errs.append(
                "exogenous traded∪predictors must equal symbols (proper partition)"
            )
        if set(traded) == set(symbols):
            errs.append("exogenous traded must be a proper subset of symbols")
    meta = inst.get("per_symbol_meta") or {}
    if not isinstance(meta, dict):
        errs.append("exogenous instrument.per_symbol_meta must be an object")
        meta = {}
    for s in symbols:
        m = meta.get(s)
        if not isinstance(m, dict):
            errs.append(f"exogenous per_symbol_meta missing object for {s!r}")
            continue
        for k in ("point_size", "contract_size", "digits"):
            if k not in m:
                errs.append(f"exogenous per_symbol_meta[{s!r}] missing {k}")
    cal = charter.get("analysis_calendar") or {}
    if cal.get("mode") != "intersection_only":
        errs.append(
            "exogenous analysis_calendar.mode must be 'intersection_only'"
        )
    gates = charter.get("gates") or {}
    if gates.get("primary_n_passers") != "soft":
        errs.append(
            "exogenous gates.primary_n_passers must be 'soft' "
            f"(got {gates.get('primary_n_passers')!r})"
        )
    soft = gates.get("soft")
    if not isinstance(soft, dict) or not soft:
        errs.append("exogenous gates.soft required (traded-book primary)")
    else:
        for k in (
            "n_trades_min",
            "profit_factor_min",
            "net_profit_gt",
            "max_drawdown_pct_max",
        ):
            if k not in soft:
                errs.append(f"exogenous gates.soft missing required key {k!r}")
    null = charter.get("null") or {}
    impl = str(
        null.get("implementation_id") or null.get("method") or ""
    )
    if impl != EXOGENOUS_NULL_IMPLEMENTATION_ID:
        errs.append(
            "exogenous null.implementation_id (or null.method) must be "
            f"{EXOGENOUS_NULL_IMPLEMENTATION_ID!r}; got {impl!r}"
        )
    # reject alternate sampling enums if present
    for bad_key in ("sampling", "pairing", "strata", "with_replacement"):
        if bad_key in null:
            errs.append(
                f"exogenous null.{bad_key} forbidden (canonical engine only)"
            )
    alt = null.get("forbidden_methods") or []
    if impl and impl in {str(x) for x in alt}:
        errs.append(f"exogenous null method {impl!r} listed in forbidden_methods")
    if null.get("base_seed") is None:
        errs.append("exogenous null.base_seed required")
    n_trials = int(null.get("n_trials") or null.get("min_null_trials") or 0)
    if n_trials < MIN_NULL_TRIALS_PROTOCOL:
        errs.append(
            f"exogenous null n_trials={n_trials} < protocol floor "
            f"{MIN_NULL_TRIALS_PROTOCOL}"
        )
    mult = charter.get("multiplicity") or {}
    if mult.get("paper_live_while_open") is True:
        errs.append(
            "exogenous multiplicity.paper_live_while_open must not be true "
            "while catalog open"
        )
    if mult.get("pass_status") not in (
        None,
        "provisional_while_catalog_open",
        "provisional",
    ):
        # allow omit at early freeze drafts; if set, must be provisional
        if mult.get("pass_status") not in (
            "provisional_while_catalog_open",
            "provisional",
        ):
            errs.append(
                "exogenous multiplicity.pass_status must be provisional while "
                f"catalog open (got {mult.get('pass_status')!r})"
            )
    return errs


def _strict_finite_number(val: Any) -> float | None:
    """Accept only real JSON int/float (not bool, not str); require math.isfinite."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None
    f = float(val)
    if not math.isfinite(f):
        return None
    return f


def _strict_nonneg_int(val: Any) -> int | None:
    """Accept only non-negative JSON int (not bool, not float/str)."""
    if isinstance(val, bool) or not isinstance(val, int):
        return None
    if val < 0:
        return None
    return val


def validate_charter_file(path: Path | str) -> list[str]:
    """Validate an on-disk charter; grandfathering uses the file's SHA-256 bytes."""
    p = Path(path)
    if not p.is_file():
        return [f"charter not found: {p}"]
    body = p.read_bytes()
    file_sha = hashlib.sha256(body).hexdigest()
    try:
        charter = json.loads(body.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return [f"charter JSON invalid: {e}"]
    if not isinstance(charter, dict):
        return ["charter JSON must be an object"]
    return validate_charter(charter, file_sha256=file_sha)


def validate_charter(
    charter: dict[str, Any],
    *,
    file_sha256: str | None = None,
) -> list[str]:
    """Return list of hard errors (empty ⇒ ok to freeze/run).

    ``file_sha256`` is the SHA-256 of the on-disk charter bytes that produced
    ``charter``. Only ``validate_charter_file`` should supply it. In-memory
    copies never receive grandfathering — self-declared ``frozen_at`` alone
    cannot exempt a new/backdated family from seed / protocol rules.
    """
    errs: list[str] = []
    if not charter.get("family_id"):
        errs.append("missing family_id")
    n_knobs = int(charter.get("n_free_knobs", len(charter.get("free_knobs") or [])))
    if n_knobs > 3:
        errs.append(f"n_free_knobs={n_knobs} > 3")
    null = charter.get("null") or charter.get("success", {}).get("null_maxstat") or {}
    n_trials = int(null.get("n_trials") or null.get("min_null_trials") or 0)
    if n_trials < MIN_NULL_TRIALS_PROTOCOL:
        errs.append(
            f"null n_trials={n_trials} < protocol floor {MIN_NULL_TRIALS_PROTOCOL} "
            f"(prefer {PREFERRED_NULL_TRIALS_LOW_KNOB} for 0–1 knob families)"
        )
    method = str(null.get("method") or null.get("null_method") or "")
    if not method:
        errs.append(
            "null.method required (e.g. within_day_ohlc_increment_rotate_v1)"
        )
    forbidden = {str(x) for x in (null.get("forbidden_methods") or [])}
    if method in forbidden:
        errs.append(f"null.method={method!r} is listed in null.forbidden_methods")
    if method in ("day_block_shuffle", "circular_day_shift", "block_shuffle", "circular"):
        errs.append(
            f"null.method={method!r} is PROTOCOL_NULL_INVALID for session-hour "
            f"families; use {CANONICAL_SESSION_NULL}"
        )

    thesis = str(charter.get("thesis_class") or "")
    rule = charter.get("rule") or {}
    is_session = thesis in SESSION_THESIS_CLASSES or any(
        rule.get(k) is not None for k in SESSION_RULE_MARKERS
    )
    proto = float(charter.get("protocol_version") or 0)
    grandfathered = (
        file_sha256 is not None and file_sha256 in GRANDFATHERED_NO_SEED_CHARTER_SHA256
    )
    if is_session:
        if method in (
            "day_block_shuffle",
            "circular_day_shift",
            "global_return_shuffle",
            "block_shuffle",
            "circular",
        ):
            errs.append(
                f"null.method={method!r} is PROTOCOL_NULL_INVALID for session-shaped "
                f"families; use {CANONICAL_SESSION_NULL}"
            )
        if proto >= 2.2:
            if method != CANONICAL_SESSION_NULL:
                errs.append(
                    f"session family requires null.method={CANONICAL_SESSION_NULL!r} "
                    f"(protocol ≥2.2); got {method!r}"
                )
        elif proto >= 2.1:
            # transitional: allow legacy name only if notes pin v2.2 algorithm
            # (grandfathered historical freezes only; new freezes require ≥2.2 below)
            notes = str(null.get("notes") or "")
            if method not in SESSION_NULL_ALIASES:
                errs.append(
                    f"session family null.method={method!r} not in {sorted(SESSION_NULL_ALIASES)}"
                )
            if method == "within_day_return_rotate" and "OHLC" not in notes and "ohlc" not in notes.lower():
                errs.append(
                    "legacy null.method=within_day_return_rotate requires notes that "
                    "preregister complete OHLC-increment algorithm (or bump to "
                    f"{CANONICAL_SESSION_NULL} under protocol 2.2)"
                )

    if not (charter.get("gates") or charter.get("passer_definition_soft")):
        errs.append("gates or passer_definition_soft required")

    # Multi-instrument charters: joint cosign vs exogenous predictor.
    inst = charter.get("instrument") or {}
    harness_kind = str((charter.get("harness") or {}).get("kind") or "")
    multi = bool(inst.get("multi_symbol_in_scope")) or bool(
        isinstance(inst.get("symbols"), list) and len(inst.get("symbols") or []) > 1
    ) or harness_kind in (JOINT_HARNESS_KIND, EXOGENOUS_PREDICTOR_HARNESS_KIND)
    gates = charter.get("gates") or {}
    # Nested-only layout without top-level soft is always invalid
    if (
        (gates.get("per_symbol") is not None or gates.get("joint") is not None)
        and (not isinstance(gates.get("soft"), dict) or not gates.get("soft"))
    ):
        errs.append(
            "multi-instrument/nested joint charter requires top-level gates.soft "
            "(gates.per_symbol/gates.joint alone are invisible to gates_from_charter)"
        )
    if harness_kind == EXOGENOUS_PREDICTOR_HARNESS_KIND:
        errs.extend(validate_exogenous_predictor_charter(charter))
    elif multi:
        # Complete joint-soft contract for every multi-instrument charter.
        # Soft joint keys: n, PF, NP, max DD (DD was fail-open if omitted).
        _joint_soft_required = (
            "n_trades_min",
            "profit_factor_min",
            "net_profit_gt",
            "max_drawdown_pct_max",
        )
        _per_symbol_soft_required = (
            "n_trades_min",
            "profit_factor_min",
            "net_profit_gt",
        )

        def _gate_number_ok(key: str, val: Any) -> str | None:
            """Return error suffix if invalid; None if ok."""
            if key == "n_trades_min":
                if _strict_nonneg_int(val) is None:
                    return (
                        "must be a non-negative JSON integer "
                        "(not bool/float/str/NaN/Inf)"
                    )
                return None
            if _strict_finite_number(val) is None:
                return (
                    "must be a finite JSON int/float "
                    "(not bool/str/NaN/Inf)"
                )
            return None

        if not isinstance(gates.get("soft"), dict) or not gates.get("soft"):
            errs.append(
                "multi-instrument charter requires top-level gates.soft (joint soft primary)"
            )
        else:
            soft = gates["soft"]
            for k in _joint_soft_required:
                if k not in soft:
                    errs.append(f"multi-instrument gates.soft missing required key {k!r}")
                else:
                    why = _gate_number_ok(k, soft.get(k))
                    if why is not None:
                        errs.append(f"multi-instrument gates.soft.{k} {why}")
        if gates.get("primary_n_passers") != "soft":
            errs.append(
                "multi-instrument charter requires gates.primary_n_passers='soft' "
                f"(got {gates.get('primary_n_passers')!r})"
            )
        mi = gates.get("multi_instrument") or {}
        if not isinstance(mi, dict) or not mi:
            errs.append("multi-instrument charter requires gates.multi_instrument object")
        else:
            if mi.get("n_passers_definition") != "binary_joint_gate_success":
                errs.append(
                    "multi-instrument gates.multi_instrument.n_passers_definition "
                    "must be 'binary_joint_gate_success'"
                )
            if mi.get("require_all_symbols_soft_pass") is not True:
                errs.append(
                    "multi-instrument gates.multi_instrument.require_all_symbols_soft_pass "
                    "must be true (exact boolean)"
                )
            if mi.get("joint_soft_is_primary") is not True:
                errs.append(
                    "multi-instrument gates.multi_instrument.joint_soft_is_primary "
                    "must be true (exact boolean)"
                )
            ps = mi.get("per_symbol_soft")
            if not isinstance(ps, dict) or not ps:
                errs.append(
                    "multi-instrument gates.multi_instrument.per_symbol_soft required"
                )
            else:
                for k in _per_symbol_soft_required:
                    if k not in ps:
                        errs.append(
                            "multi-instrument gates.multi_instrument.per_symbol_soft "
                            f"missing required key {k!r}"
                        )
                    else:
                        why = _gate_number_ok(k, ps.get(k))
                        if why is not None:
                            errs.append(
                                "multi-instrument gates.multi_instrument.per_symbol_soft."
                                f"{k} {why}"
                            )
        harness = charter.get("harness") or {}
        if harness.get("kind") != "multi_instrument_joint_v1":
            errs.append(
                "multi-instrument charter requires harness.kind="
                "'multi_instrument_joint_v1' (dedicated joint screen/null harness)"
            )
        cal = charter.get("analysis_calendar") or {}
        if cal.get("mode") != "intersection_only":
            errs.append(
                "multi-instrument charter requires analysis_calendar.mode="
                "'intersection_only' for real and null"
            )
        null = charter.get("null") or {}
        if null.get("joint_dependency_preserving") is not True:
            errs.append(
                "multi-instrument charter requires null.joint_dependency_preserving "
                "true (exact boolean)"
            )
        sk = null.get("shared_k_spec") or {}
        if not isinstance(sk, dict) or not sk.get("trial_seed"):
            errs.append(
                "multi-instrument charter requires null.shared_k_spec.trial_seed "
                "(reproducible shared-k draws)"
            )
        # PF zero-denominator must be pinned for multi-instrument joint PF / null max-PF
        # House convention: PF=0 no trades; PF=99 when gross loss is 0 with gross profit > 0.
        # Reject bool (float(False)==0) — require real int/float numbers.
        js = charter.get("joint_statistics") or {}
        pzd = js.get("profit_factor_zero_denominator") or {}
        if not isinstance(pzd, dict):
            errs.append(
                "multi-instrument charter requires "
                "joint_statistics.profit_factor_zero_denominator object"
            )
        else:
            no_trades_pf = pzd.get("no_trades")
            nt = _strict_finite_number(no_trades_pf)
            if no_trades_pf is None:
                errs.append(
                    "multi-instrument charter requires "
                    "joint_statistics.profit_factor_zero_denominator.no_trades"
                )
            elif nt is None:
                errs.append(
                    "multi-instrument profit_factor_zero_denominator.no_trades "
                    "must be a finite JSON number 0 (not bool/str/NaN/Inf; house convention)"
                )
            elif nt != 0.0:
                errs.append(
                    "multi-instrument profit_factor_zero_denominator.no_trades "
                    "must be 0 (house convention)"
                )
            glz_key = "gross_loss_zero_and_gross_profit_positive"
            glz_pf = pzd.get(glz_key)
            glz = _strict_finite_number(glz_pf)
            if glz_pf is None:
                errs.append(
                    "multi-instrument charter requires "
                    f"joint_statistics.profit_factor_zero_denominator.{glz_key}"
                )
            elif glz is None:
                errs.append(
                    "multi-instrument profit_factor_zero_denominator."
                    f"{glz_key} must be a finite JSON number 99 "
                    "(not bool/str/NaN/Inf; house convention)"
                )
            elif glz != 99.0:
                errs.append(
                    "multi-instrument profit_factor_zero_denominator."
                    f"{glz_key} must be 99 (house convention)"
                )
    costs = (charter.get("fixed") or {}).get("costs") or charter.get("costs") or {}
    if "commission_per_lot" not in costs and "costs_source" not in (charter.get("fixed") or {}):
        errs.append("fixed.costs or fixed.costs_source required")
    # Intraday flat or swap handling (rule already bound above)
    exits = str(rule.get("exit") or "") + str(rule.get("intraday_flat") or "")
    if (
        proto >= 2
        and not rule.get("intraday_flat")
        and "swap" not in exits.lower()
        and "flat" not in exits.lower()
    ):
        errs.append(
            "rule.intraday_flat true required (or explicit swap handling) under protocol v2"
        )

    # frozen_at is mandatory and must parse (missing/malformed fails closed).
    freeze_day = _parse_frozen_at_date(charter.get("frozen_at"))
    if freeze_day is None:
        if charter.get("frozen_at") is None or str(charter.get("frozen_at") or "").strip() == "":
            errs.append("frozen_at required (YYYY-MM-DD or ISO date prefix)")
        else:
            errs.append(
                f"frozen_at malformed (need YYYY-MM-DD or ISO date prefix); "
                f"got {charter.get('frozen_at')!r}"
            )

    # null.base_seed: strict non-negative int when present. When absent, only
    # exact on-disk SHA matches in GRANDFATHERED_NO_SEED_CHARTER_SHA256 may omit
    # it — never self-declared frozen_at (backdating is not grandfathering).
    base_seed_raw = null.get("base_seed", _MISSING_BASE_SEED)
    if base_seed_raw is not _MISSING_BASE_SEED:
        # type(x) is int rejects bool (bool is a subclass of int) and rejects
        # float/str that int() would coerce — no seed shopping via "7" or 1.0.
        if type(base_seed_raw) is not int:
            errs.append(
                "null.base_seed must be a non-negative int "
                f"(got type {type(base_seed_raw).__name__})"
            )
        elif base_seed_raw < 0:
            errs.append("null.base_seed must be >= 0")
    elif not grandfathered:
        errs.append(
            "null.base_seed required (non-negative int); only exact historical "
            "charter file SHAs in GRANDFATHERED_NO_SEED_CHARTER_SHA256 may omit "
            "it (self-declared frozen_at cannot grandfather)"
        )

    # New / non-grandfathered freezes must claim protocol ≥2.2 (backdating to a
    # pre-seed protocol revision is refused).
    if not grandfathered and proto < 2.2:
        errs.append(
            "protocol_version must be >= 2.2 for non-grandfathered freezes "
            f"(got {proto}; refuse protocol downgrade / backdating bypass)"
        )
    return errs


def _parse_frozen_at_date(value: Any) -> date | None:
    """Parse charter frozen_at to a calendar date (YYYY-MM-DD or ISO prefix)."""
    if value is None:
        return None
    s = str(value).strip()
    if len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def run_output_dir(family_id: str, *, day: str | None = None, run_id: str = "r1") -> Path:
    d = day or date.today().isoformat()
    safe = family_id.strip().replace(" ", "_")
    return ROOT / "results" / "xau_runs" / f"{d}_{safe}_{run_id}"


def ensure_fresh_run_dir(path: Path) -> Path:
    if path.exists():
        raise CharterError(
            f"run output directory already exists (refuse overwrite): {path}. "
            "Choose a new run_id."
        )
    path.mkdir(parents=True, exist_ok=False)
    return path


def build_provenance(
    *,
    charter_path: Path,
    costs_path: Path,
    data_path: Path,
    null_seed: int | None,
    n_null: int | None,
    out_dir: Path,
    extra: dict[str, Any] | None = None,
    require_clean_tree: bool = False,
) -> dict[str, Any]:
    """Build run provenance. ``n_null`` is executed null count only.

    Pass ``n_null=None`` when the executed count is unknown (FAILED_RUN /
    UNKNOWN paths). Never substitute the planned trial count for an unknown
    executed count — top-level ``n_null`` must stay JSON null in that case.

    ``null_seed`` may be ``None`` when the reported seed is unknown/invalid —
    never invent ``0`` as a substitute for a missing reported seed.
    """
    dirty_info: dict[str, Any]
    if require_clean_tree:
        dirty_info = assert_clean_dispositional_tree()
    else:
        try:
            dirty = git_dirty_tracked_paths()
        except CharterError:
            dirty = ["<git unavailable>"]
        dirty_info = {
            "clean": len(dirty) == 0,
            "dirty_paths": dirty,
            "code_commit": git_head(),
        }
    # JSON-serializable: int or None (never invent planned-as-executed / seed 0).
    n_null_out: int | None = None if n_null is None else int(n_null)
    null_seed_out: int | None = None if null_seed is None else int(null_seed)
    prov = {
        "charter_path": str(charter_path.relative_to(ROOT)) if charter_path.is_relative_to(ROOT) else str(charter_path),
        "charter_sha256": sha256_file(charter_path),
        "code_commit": dirty_info.get("code_commit") or git_head(),
        "tree_clean": bool(dirty_info.get("clean")),
        "dirty_paths": dirty_info.get("dirty_paths") or [],
        "data_path": str(data_path.relative_to(ROOT)) if data_path.is_relative_to(ROOT) else str(data_path),
        "data_sha256": sha256_file(data_path),
        "costs_path": str(costs_path.relative_to(ROOT)) if costs_path.is_relative_to(ROOT) else str(costs_path),
        "costs_sha256": sha256_file(costs_path),
        "null_seed": null_seed_out,
        "n_null": n_null_out,
        "output_dir": str(out_dir.relative_to(ROOT)) if out_dir.is_relative_to(ROOT) else str(out_dir),
    }
    if extra:
        prov.update(extra)
    return prov


def append_attempt(record: dict[str, Any], path: Path = ATTEMPTS_PATH) -> None:
    """Append one program-level family attempt (multiple-testing ledger)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, default=str)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def count_attempts(family_id: str | None = None, path: Path = ATTEMPTS_PATH) -> int:
    """Count program attempts fail-closed (corrupt lines raise RegistryError).

    STARTED + TERMINAL rows that share ``attempt_id`` count as **one** attempt.
    Legacy rows without ``attempt_id`` each count as one attempt.
    """
    rows = _parse_jsonl_strict(path)
    seen_ids: set[str] = set()
    n_legacy = 0
    for rec in rows:
        if family_id is not None and rec.get("family_id") != family_id:
            continue
        aid = rec.get("attempt_id")
        if aid is None or aid == "":
            n_legacy += 1
            continue
        seen_ids.add(str(aid))
    return len(seen_ids) + n_legacy


def gates_from_charter(charter: dict[str, Any]) -> dict[str, Any]:
    """Normalize classic + soft gate specs for reporting and evaluation."""
    g = dict(charter.get("gates") or {})
    classic = dict(DEFAULT_CLASSIC_GATES)
    classic.update(g.get("classic") or {})

    soft = g.get("soft")
    if soft is None and charter.get("passer_definition_soft"):
        p = charter["passer_definition_soft"]
        soft = {
            "n_trades_min": p.get("n_trades_min", 20),
            "profit_factor_min": p.get("profit_factor_min", 1.2),
            "net_profit_gt": 0.0 if p.get("net_profit") in ("gt_0", ">", 0) else p.get("net_profit_gt"),
            "max_drawdown_pct_max": p.get("max_drawdown_pct_max"),
            "expectancy_min": p.get("expectancy_min"),
            "used_for": p.get("used_for", "null_n_passers"),
        }
    soft = dict(soft or {})

    primary = g.get("primary_n_passers") or charter.get("primary_n_passers") or "soft"
    return {
        "classic": classic,
        "soft": soft,
        "primary_n_passers": primary,
        "description": {
            "classic": _gate_desc(classic, kind="classic"),
            "soft": _gate_desc(soft, kind="soft") if soft else None,
        },
    }


def _gate_desc(g: dict[str, Any], *, kind: str) -> str:
    parts: list[str] = []
    if "n_trades_min" in g:
        parts.append(f"n>={g['n_trades_min']}")
    if "profit_factor_min" in g:
        op = ">" if g.get("profit_factor_strict_gt") else ">="
        parts.append(f"PF{op}{g['profit_factor_min']}")
    if "win_rate_min" in g:
        op = ">" if g.get("win_rate_strict_gt") else ">="
        parts.append(f"WR{op}{g['win_rate_min']}")
    if g.get("max_drawdown_pct_max") is not None:
        op = "<" if g.get("max_drawdown_strict_lt") else "<="
        parts.append(f"DD{op}{g['max_drawdown_pct_max']}")
    if g.get("expectancy_min") is not None:
        parts.append(f"exp>={g['expectancy_min']}")
    if g.get("net_profit_gt") is not None:
        parts.append(f"NP>{g['net_profit_gt']}")
    return ", ".join(parts) if parts else kind


def make_pass_fns(charter: dict[str, Any]) -> tuple[Callable[[Any], bool], Callable[[Any], bool] | None, str]:
    """Build classic/soft pass callables from charter gates (not from module drift)."""
    from xau_null_core import metrics_dict  # local import; scripts on path

    g = gates_from_charter(charter)
    classic_spec = g["classic"]
    soft_spec = g["soft"]

    def classic_pass(m: Any) -> bool:
        md = metrics_dict(m) if not isinstance(m, dict) else m
        pf = float(md["profit_factor"])
        wr = float(md["win_rate"])
        dd = float(md["max_drawdown_pct"])
        n = int(md["n_trades"])
        if n < int(classic_spec.get("n_trades_min", 20)):
            return False
        pf_min = float(classic_spec.get("profit_factor_min", 1.5))
        if classic_spec.get("profit_factor_strict_gt", True):
            if not (pf > pf_min):
                return False
        elif not (pf >= pf_min):
            return False
        wr_min = float(classic_spec.get("win_rate_min", 55.0))
        if classic_spec.get("win_rate_strict_gt", True):
            if not (wr > wr_min):
                return False
        elif not (wr >= wr_min):
            return False
        dd_max = float(classic_spec.get("max_drawdown_pct_max", 10.0))
        if classic_spec.get("max_drawdown_strict_lt", True):
            if not (dd < dd_max):
                return False
        elif not (dd <= dd_max):
            return False
        return True

    soft_fn: Callable[[Any], bool] | None = None
    if soft_spec:

        def _soft(m: Any) -> bool:
            md = metrics_dict(m) if not isinstance(m, dict) else m
            if int(md["n_trades"]) < int(soft_spec.get("n_trades_min", 0) or 0):
                return False
            if "profit_factor_min" in soft_spec and float(md["profit_factor"]) < float(
                soft_spec["profit_factor_min"]
            ):
                return False
            if soft_spec.get("net_profit_gt") is not None and not (
                float(md["net_profit"]) > float(soft_spec["net_profit_gt"])
            ):
                return False
            if soft_spec.get("max_drawdown_pct_max") is not None and float(
                md["max_drawdown_pct"]
            ) > float(soft_spec["max_drawdown_pct_max"]):
                return False
            return not (
                soft_spec.get("expectancy_min") is not None
                and float(md["expectancy"]) < float(soft_spec["expectancy_min"])
            )

        soft_fn = _soft

    primary = str(g["primary_n_passers"])
    return classic_pass, soft_fn, primary


def null_spec_from_charter(charter: dict[str, Any]) -> dict[str, Any]:
    null = dict(charter.get("null") or {})
    legacy = (charter.get("success") or {}).get("null_maxstat") or {}
    for k, v in legacy.items():
        null.setdefault(k, v)
    method = str(null.get("method") or null.get("null_method") or "global_return_shuffle")
    n_trials = int(null.get("n_trials") or null.get("min_null_trials") or MIN_NULL_TRIALS_PROTOCOL)
    block_days = int(null.get("block_days") or null.get("block_size_days") or 1)
    out: dict[str, Any] = {
        "method": method,
        "n_trials": n_trials,
        "block_days": block_days,
        "invariants": null.get("invariants") or [],
        "notes": null.get("notes") or "",
    }
    if "base_seed" in null and null["base_seed"] is not None:
        # Preserve only already-valid ints; callers should validate_charter first.
        raw = null["base_seed"]
        if type(raw) is int and raw >= 0:
            out["base_seed"] = raw
    return out


if __name__ == "__main__":
    print(f"CHARTERS_DIR={CHARTERS_DIR}")
    print(f"LEGACY_CHARTER exists={LEGACY_CHARTER.is_file()}")
    print(f"attempts={count_attempts()}")
