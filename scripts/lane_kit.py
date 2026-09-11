"""lane_kit — shared pre-registered-lane machinery (lock / grid / rank / null).

One home for the bookkeeping every session lane hand-rolls: lock loading and
freeze-refusals, cost-book pinning, data sha verification, lane-local holdout
assertions, grid enumeration with cardinality ceilings, develop-only PF
ranking (``None -> 3.0``), within-day null rotation, and clock admission
(lag-0 vs a UTC-native reference book).

Design rules (from the BTC-NY lane, the richest lock schema in the repo):

- Re-export — never fork — the canonical primitives that already live in
  ``us_index_session_backtest`` (``CostSpec``, ``Trade``, cost math, metrics,
  slim writer, ``read_mt5_hc`` loaders).
- Clock, session boxes, and cost *values* stay lane-owned by design. This
  module never encodes a clock or a holdout date.
- Everything fails closed with ``SystemExit`` messages a human can act on.
- Research layer only: plain ``python3`` (numpy/pandas host-side), never
  imported from ``src/mt5_arch``.

Example lane usage::

    import lane_kit as lk

    lock = lk.load_lane_lock(LOCK_PATH, "my_lane_develop_v1")
    costs = lk.costs_from_lock(lock)
    lk.require_locked_book(lock, costs)
    lk.verify_data_sha256(csv_path, lock["data"]["sha256"])
    hs = lk.assert_lane_holdout(date.fromisoformat(lock["holdout"]["start"]),
                                forbidden=TAKEN_HOLDOUTS)
    grid = lk.assert_cardinality(lk.iter_product_grid(lock), lock)
    rows = [...]  # simulate each config, pack via lk.pack_develop_holdout
    ranked = lk.rank_pf_expectancy(rows)
"""

from __future__ import annotations

import hashlib
import itertools
import json
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Canonical cost/trade/report machinery — single source of truth (do not copy).
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    Trade,
    costs_from_meta,
    hc_to_export_csv,
    load_m5_csv,
    metrics_from_trades,
    parse_meta,
    read_mt5_hc,
    slim_committed_report,
    write_slim_json,
)

__all__ = [
    # canonical re-exports
    "CostSpec",
    "Trade",
    "metrics_from_trades",
    "write_slim_json",
    "slim_committed_report",
    "read_mt5_hc",
    "hc_to_export_csv",
    "load_m5_csv",
    "parse_meta",
    "costs_from_meta",
    # lock layer
    "sha256_file",
    "load_lane_lock",
    "refuse_promote_flips",
    "refuse_pinned",
    "costs_from_lock",
    "require_locked_book",
    "verify_data_sha256",
    "assert_lane_holdout",
    # grid layer
    "iter_product_grid",
    "assert_cardinality",
    "grid_cfg_id",
    # rank layer
    "score_pf_expectancy",
    "rank_pf_expectancy",
    "split_trades_by_holdout",
    "pack_develop_holdout",
    # null layer
    "rotate_returns_within_days",
    "run_null_rotation",
    # clock admission
    "admit_clock_lag0",
]


# ---------------------------------------------------------------------------
# Lock layer
# ---------------------------------------------------------------------------


def sha256_file(path: Path | str) -> str:
    """SHA-256 of a file, streaming (works on multi-hundred-MB .hc caches)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_lane_lock(path: Path | str, expected_search_id: str | None = None) -> dict:
    """Load a lane lock; refuse a ``search_id`` mismatch (wrong lane or stale fork)."""
    lock = json.loads(Path(path).read_text())
    if expected_search_id is not None and lock.get("search_id") != expected_search_id:
        raise SystemExit(
            f"search_id mismatch: lock={lock.get('search_id')!r} expected={expected_search_id!r}"
        )
    return lock


def refuse_promote_flips(lock: Mapping[str, Any]) -> None:
    """A research lock must never flip promote/live_go. Fail closed."""
    if lock.get("promote") is True:
        raise SystemExit("promote must stay false")
    if lock.get("live_go") is True:
        raise SystemExit("live_go must stay false")


def _lock_get(lock: Mapping[str, Any], dotted: str) -> Any:
    node: Any = lock
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


def refuse_pinned(lock: Mapping[str, Any], pinned: Mapping[str, Any]) -> None:
    """Refuse mutations of pinned lock fields.

    ``pinned`` maps a dotted lock path to its required value. Floats compare
    with a 1e-9 tolerance; anything else compares with ``==``. Missing fields
    refuse too (a deleted pin is a mutation).
    """
    for dotted, want in pinned.items():
        got = _lock_get(lock, dotted)
        if isinstance(want, float) or isinstance(got, float):
            ok = got is not None and want is not None and abs(float(got) - float(want)) <= 1e-9
        else:
            ok = got == want
        if not ok:
            raise SystemExit(f"lock field {dotted!r} mutated vs pin (want {want!r}, got {got!r})")


def costs_from_lock(lock: Mapping[str, Any]) -> CostSpec:
    """Build the frozen CostSpec from ``lock['book']`` + ``lock['costs']``."""
    book = lock["book"]
    c = lock["costs"]
    return CostSpec(
        point_size=float(book["point_size"]),
        contract_size=float(book["contract_size"]),
        lots=float(book["lots"]),
        commission_per_lot=float(c["commission_per_lot"]),
        slippage_points=float(c["slippage_points"]),
        max_spread_points=float(c["max_spread_points"]),
    )


def require_locked_book(lock: Mapping[str, Any], costs: CostSpec) -> None:
    """BTC-NY semantics: promote/live_go stay false and the built cost book
    equals the lock's own numbers (lots / slippage / spread cap / point /
    contract). Catches a lock rewritten to match a softer simulator."""
    refuse_promote_flips(lock)
    book = lock.get("book") or {}
    lc = lock.get("costs") or {}
    if float(book.get("lots", costs.lots)) != float(costs.lots):
        raise SystemExit("lots mutated vs lock")
    if abs(float(lc["slippage_points"]) - float(costs.slippage_points)) > 1e-9:
        raise SystemExit("slippage_points mutated vs lock")
    if abs(float(lc["max_spread_points"]) - float(costs.max_spread_points)) > 1e-9:
        raise SystemExit("max_spread_points mutated vs lock")
    if abs(float(book["point_size"]) - float(costs.point_size)) > 1e-12:
        raise SystemExit("point_size mutated vs lock")
    if abs(float(book["contract_size"]) - float(costs.contract_size)) > 1e-12:
        raise SystemExit("contract_size mutated vs lock")


def verify_data_sha256(csv_path: Path | str, expected: str) -> str:
    """Refuse to run a screen on data that is not the locked book."""
    h = sha256_file(csv_path)
    want = str(expected)
    if h != want:
        raise SystemExit(f"data sha256 mismatch: {h} != {want} (refusing to run)")
    return h


def assert_lane_holdout(
    holdout_start: date,
    forbidden: Iterable[date | str] = (),
) -> date:
    """Holdouts are lane-local. Refuse a date another lane already burned."""
    taken = {d if isinstance(d, date) else date.fromisoformat(str(d)) for d in forbidden}
    if holdout_start in taken:
        raise SystemExit(
            f"holdout {holdout_start.isoformat()} already used by another lane "
            f"(taken: {sorted(d.isoformat() for d in taken)})"
        )
    return holdout_start


# ---------------------------------------------------------------------------
# Grid layer
# ---------------------------------------------------------------------------

_GRID_ANNOTATION_KEYS = {"max_configs", "expected_configs", "nfp_window_et"}


def iter_product_grid(
    lock: Mapping[str, Any],
    *,
    family_key: tuple[str, ...] = ("families", "search"),
) -> list[dict]:
    """Enumerate the frozen grid from the lock itself.

    Product of every *list*-valued ``lock['grid']`` entry (in lock order)
    crossed with each family in ``lock[families][search]``. Scalar grid
    entries are annotations, not axes. ``max_configs`` is a hard ceiling —
    widening the grid after locking refuses here.
    """
    g = lock["grid"]
    fams = _lock_get(lock, ".".join(family_key))
    if not fams:
        raise SystemExit("lock has no search families")
    axes = [(k, list(v)) for k, v in g.items() if isinstance(v, list)]
    rows: list[dict] = []
    for combo in itertools.product(fams, *[v for _, v in axes]):
        row: dict = {"family": combo[0]}
        for (key, _), val in zip(axes, combo[1:], strict=True):
            row[key] = val
        rows.append(row)
    ceiling = g.get("max_configs")
    if ceiling is not None and len(rows) > int(ceiling):
        raise SystemExit(f"grid {len(rows)} exceeds max_configs {int(ceiling)}")
    return rows


def assert_cardinality(
    rows: Sequence[Mapping[str, Any]],
    lock: Mapping[str, Any],
    *,
    key: str = "expected_configs",
) -> Sequence[Mapping[str, Any]]:
    """The enumerated grid must equal the lock's committed cardinality."""
    g = lock.get("grid") or {}
    want = g.get(key)
    if want is not None and len(rows) != int(want):
        raise SystemExit(f"grid cardinality {len(rows)} != lock {key} {int(want)}")
    return rows


def grid_cfg_id(cfg: Mapping[str, Any]) -> str:
    """Stable ``family|k0v0|k1v1…`` id for a grid row (lock-order keys)."""
    parts = [str(cfg["family"])]
    for key in cfg:
        if key == "family":
            continue
        val = cfg[key]
        if isinstance(val, bool):
            val = int(val)
        parts.append(f"{key}{val}")
    return "|".join(parts)


# ---------------------------------------------------------------------------
# Rank layer
# ---------------------------------------------------------------------------


def score_pf_expectancy(m: Mapping[str, Any], *, min_trades: int = 40) -> float:
    """BTC-NY / index-v1 develop score: ineligible pins to -1e9.

    Eligible = ``trades >= min_trades`` and ``net_pnl > 0``. ``profit_factor``
    ``None`` (no losing trade) pins to 3.0 so it cannot dominate forever.
    """
    if int(m["trades"]) < min_trades or float(m["net_pnl"]) <= 0:
        return -1e9
    pf = m["profit_factor"]
    pf_v = 3.0 if pf is None else float(pf)
    return pf_v * 1000.0 + float(m["expectancy"])


def rank_pf_expectancy(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Develop-only ranking: PF (None -> 3.0) then expectancy. Holdout keys
    are structurally ignored — never put them in these sort keys."""
    return sorted(
        rows,
        key=lambda r: (
            r["develop"]["profit_factor"] if r["develop"]["profit_factor"] is not None else 3.0,
            r["develop"]["expectancy"],
        ),
        reverse=True,
    )


def split_trades_by_holdout(
    trades: Sequence[Trade], holdout_start: date
) -> tuple[list[Trade], list[Trade]]:
    """Split Trade lists at ``et_date >= holdout_start`` (iso dates on Trade)."""
    pre = [t for t in trades if date.fromisoformat(t.et_date) < holdout_start]
    post = [t for t in trades if date.fromisoformat(t.et_date) >= holdout_start]
    return pre, post


def pack_develop_holdout(trades: Sequence[Trade], holdout_start: date) -> dict[str, Any]:
    """``{"develop": metrics, "holdout": metrics}`` — the two-window report block."""
    pre, post = split_trades_by_holdout(list(trades), holdout_start)
    return {"develop": metrics_from_trades(pre), "holdout": metrics_from_trades(post)}


# ---------------------------------------------------------------------------
# Null layer (within-day circular rotation; EURUSD pattern, BTC-NY usage)
# ---------------------------------------------------------------------------


def rotate_returns_within_days(d: Any, rng: np.random.Generator) -> Any:
    """Circularly rotate log-returns within each lane-day of a bar bundle.

    Duck-typed: ``d`` must be a dataclass exposing ``open/high/low/close``
    (numpy arrays) plus a day key ``et_key``. All other fields pass through
    unchanged. Within-day return product is preserved exactly, so a null run
    keeps the day's realized move while destroying intra-day path structure.
    """
    n = len(d.close)
    o = d.open.copy()
    h = d.high.copy()
    lo = d.low.copy()
    c = d.close.copy()
    i = 0
    while i < n:
        j = i
        k = int(d.et_key[i])
        while j < n and int(d.et_key[j]) == k:
            j += 1
        seg_c = c[i:j]
        r = np.empty(j - i)
        r[0] = np.log(max(seg_c[0], 1e-12) / max(o[i], 1e-12))
        r[1:] = np.diff(np.log(np.maximum(seg_c, 1e-12)))
        off = int(rng.integers(0, j - i))
        r = np.roll(r, off)
        new_c = o[i] * np.exp(np.cumsum(r))
        ratio = new_c / np.maximum(seg_c, 1e-12)
        h[i:j] *= ratio
        lo[i:j] *= ratio
        c[i:j] = new_c
        o[i + 1 : j] = new_c[:-1]
        i = j
    return replace(d, open=o, high=h, low=lo, close=c)


def run_null_rotation(
    seeds: Sequence[int],
    null_metric: Callable[[np.random.Generator], float | None],
    *,
    real_metric: float | None,
) -> dict[str, Any]:
    """Run the frozen null across seeds; report ``frac_null_ge_real``.

    ``null_metric(rng)`` must replay the *a-priori* (or single frozen) config
    on rotated data and return its develop metric — never a winner hunt: the
    null prices the search you pre-registered, not an adaptive one.
    """
    per_seed = []
    for seed in seeds:
        rng = np.random.default_rng(int(seed))
        val = null_metric(rng)
        per_seed.append({"seed": int(seed), "metric": val})
    vals = [rec["metric"] for rec in per_seed if rec["metric"] is not None]
    if real_metric is None:
        frac = None
    elif not vals:
        frac = 0.0
    else:
        frac = float(np.mean([v >= real_metric for v in vals]))
    return {
        "seeds": [int(s) for s in seeds],
        "per_seed": per_seed,
        "real_metric": real_metric,
        "frac_null_ge_real": frac,
    }


# ---------------------------------------------------------------------------
# Clock admission (ny-1330 lag scan)
# ---------------------------------------------------------------------------


def admit_clock_lag0(
    book_close: pd.Series,
    ref_close: pd.Series,
    *,
    max_lag_hours: int = 4,
    floor: float | None = 0.95,
) -> dict[str, Any]:
    """Admit a clock by hourly log-return lag against a UTC-native reference.

    Both inputs are close series with tz-aware UTC DatetimeIndex (resample to
    hourly and align *on the hour* before calling, or pass raw hourly bars).
    Require the correlation argmax at exactly lag 0; ``floor`` (if set) is a
    same-asset minimum for the lag-0 peak. A shifted tape (e.g. a mislabeled
    "UTC" book) peaks at ±1 and fails closed.
    """
    b = pd.Series(book_close).astype(float)
    r = pd.Series(ref_close).astype(float)
    if b.index.tz is None or r.index.tz is None:
        raise SystemExit("admit_clock_lag0 needs tz-aware UTC indexes")
    b = b.tz_convert("UTC").groupby(b.index.tz_convert("UTC").floor("h")).last()
    r = r.tz_convert("UTC").groupby(r.index.tz_convert("UTC").floor("h")).last()
    rb = np.log(b / b.shift(1)).rename("b")
    rr = np.log(r / r.shift(1)).rename("r")
    lags = {}
    for lag in range(-max_lag_hours, max_lag_hours + 1):
        pair = pd.concat([rb, rr.shift(lag)], axis=1, join="inner").dropna()
        if len(pair) < 24:
            lags[lag] = None
            continue
        lags[lag] = float(np.corrcoef(pair["b"], pair["r"])[0, 1])
    scored = {lag: c for lag, c in lags.items() if c is not None}
    if not scored:
        raise SystemExit("admit_clock_lag0: no overlap >= 24 hourly bars")
    peak_lag = max(scored, key=lambda k: scored[k])
    lag0 = scored.get(0)
    others = [abs(c) for lag, c in scored.items() if lag != 0]
    verdict = peak_lag == 0 and lag0 is not None and (floor is None or lag0 >= floor)
    return {
        "lag0_corr": lag0,
        "peak_lag": peak_lag,
        "next_best_abs": max(others) if others else None,
        "n_scored_lags": len(scored),
        "floor": floor,
        "admitted": bool(verdict),
    }
