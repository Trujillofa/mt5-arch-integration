"""Family module: exog_london_fx_cosign_xau_follow_flat (charter v3).

Harness: multi_instrument_exogenous_predictor_v1 (Phase B core).
Phase D scope: synthetic evaluation only — no develop package load, no screen,
no null, no sealed cycle.

OPEN SPEC / CHARTER-COMPLETENESS (do not treat as settled):
  Per-stratum max_drawdown_pct is computed as the drawdown of that stratum's own
  ordered pnl subsequence via metrics_from_pnls (start_balance from charter,
  equity reconstructed from the subsequence alone). The charter requires
  per-stratum DD and inherits gates.soft.max_drawdown_pct_max, but does not
  define path-dependent DD on a subsequence of the pooled MTM equity. A v4
  declaration may be needed before any develop screen.

Stratified labels are reporting-only (predicate_isolation): computed AFTER the
real path from event.t_star_idx; they never enter admission, side, sizing,
ATR, SL/TP, or exit.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from xau_charter_protocol import (  # noqa: E402
    validate_charter,
    validate_exogenous_predictor_charter,
)
from xau_exogenous_predictor_core import (  # noqa: E402
    HARNESS_KIND,
    NULL_IMPLEMENTATION_ID,
    Event,
    ProtocolError,
    RealPathResult,
    TradeResult,
    admit_and_simulate_real,
    day_ids_from_times,
    metrics_from_pnls,
    size_lots,
    soft_pass_traded,
    wilder_atr,
)

# Re-export Phase B helpers named in the Phase D import contract (used by fixtures).
__all__ = [
    "FAMILY_ID",
    "HARNESS_KIND",
    "NULL_IMPLEMENTATION_ID",
    "Event",
    "TradeResult",
    "RealPathResult",
    "ProtocolError",
    "admit_and_simulate_real",
    "day_ids_from_times",
    "metrics_from_pnls",
    "size_lots",
    "soft_pass_traded",
    "wilder_atr",
    "run_family",
    "evaluate_stratified",
    "build_signal_sides",
    "align_intersection",
    "load_charter",
    "report_dict",
    "refuse_prohibited_runner",
    "STRATUM_DD_CONVENTION",
]

FAMILY_ID = "exog_london_fx_cosign_xau_follow_flat"
TRADED_SYMBOL = "XAUUSD"
PREDICTOR_SYMBOLS = ("EURUSD", "GBPUSD")
SYMBOLS = (TRADED_SYMBOL, *PREDICTOR_SYMBOLS)

DEFAULT_CHARTER_PATH = (
    ROOT
    / "results"
    / "xau_charters"
    / "2026-08-15_exog_london_fx_cosign_xau_follow_flat_v3.json"
)

STRATUM_COSIGN = "xau_cosign_at_tstar"
STRATUM_NOT_COSIGN = "xau_not_cosign_at_tstar"
STRATA = (STRATUM_COSIGN, STRATUM_NOT_COSIGN)

# Documented convention — NOT a charter-settled definition (see module docstring).
STRATUM_DD_CONVENTION = (
    "stratum_ordered_pnl_subsequence_via_metrics_from_pnls"
)


class EmptyIntersectionError(ValueError):
    """Raised when the three-symbol intersection calendar I is empty."""


class StratifiedEvaluationError(ProtocolError):
    """Fail-closed: stratified evaluation absent, empty, or unreportable."""


@dataclass
class StratifiedMetrics:
    pooled: dict[str, float | int]
    by_stratum: dict[str, dict[str, float | int]]
    soft_pass_pooled: bool
    soft_pass_fresh: bool
    soft_passers: int
    disposition: str
    null_armed: bool
    r1_burned: bool
    trade_stratum: dict[int, str]  # event_id -> stratum
    event_stratum: dict[int, str]
    dd_convention: str = STRATUM_DD_CONVENTION
    note: str = (
        "Per-stratum DD uses metrics_from_pnls on the stratum's ordered pnl "
        "subsequence (not pooled MTM equity). Charter-completeness gap — "
        "may warrant v4 before screen."
    )


@dataclass
class FamilyResult:
    charter: dict[str, Any]
    real: RealPathResult
    stratified: StratifiedMetrics
    signal_sides: np.ndarray
    times: np.ndarray
    frames_on_i: dict[str, pd.DataFrame]
    extras: dict[str, Any] = field(default_factory=dict)


def load_charter(path: Path | str | None = None) -> dict[str, Any]:
    """Load charter JSON and refuse wrong family / harness / null / status."""
    p = Path(path) if path is not None else DEFAULT_CHARTER_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProtocolError(f"charter must be a JSON object: {p}")
    return assert_family_charter(raw, path=p)


def assert_family_charter(ch: dict[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    """Refuse any charter that is not this family's frozen exogenous charter."""
    fid = ch.get("family_id")
    if fid != FAMILY_ID:
        raise ProtocolError(
            f"REFUSE_WRONG_FAMILY: expected family_id={FAMILY_ID!r}, got {fid!r}"
            + (f" ({path})" if path else "")
        )
    status = ch.get("status")
    if status != "FROZEN":
        raise ProtocolError(
            f"REFUSE_NOT_FROZEN: status must be 'FROZEN', got {status!r}"
        )
    harness = ch.get("harness") or {}
    kind = harness.get("kind") if isinstance(harness, dict) else None
    if kind != HARNESS_KIND:
        raise ProtocolError(
            f"REFUSE_WRONG_HARNESS: expected harness.kind={HARNESS_KIND!r}, got {kind!r}"
        )
    null = ch.get("null") or {}
    impl = null.get("implementation_id") if isinstance(null, dict) else None
    method = null.get("method") if isinstance(null, dict) else None
    if impl != NULL_IMPLEMENTATION_ID or method != NULL_IMPLEMENTATION_ID:
        raise ProtocolError(
            f"REFUSE_WRONG_NULL: expected implementation_id/method="
            f"{NULL_IMPLEMENTATION_ID!r}, got impl={impl!r} method={method!r}"
        )
    errs = validate_charter(ch)
    if errs:
        raise ProtocolError(f"validate_charter failed: {errs}")
    errs_x = validate_exogenous_predictor_charter(ch)
    if errs_x:
        raise ProtocolError(f"validate_exogenous_predictor_charter failed: {errs_x}")
    return ch


def refuse_prohibited_runner(runner: str, charter: dict[str, Any] | None = None) -> None:
    """Refuse invocation through any runner listed in harness.prohibited_runners."""
    ch = charter if charter is not None else load_charter()
    prohibited = list((ch.get("harness") or {}).get("prohibited_runners") or [])
    # Normalize bare names and path suffixes
    needle = str(runner).replace("\\", "/")
    bare = Path(needle).name
    for p in prohibited:
        p_s = str(p).replace("\\", "/")
        if needle == p_s or bare == Path(p_s).name or needle.endswith(p_s):
            raise ProtocolError(
                f"REFUSE_PROHIBITED_RUNNER: {runner!r} is listed in "
                f"harness.prohibited_runners ({p_s})"
            )


def prepare_frame(raw: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    """Normalize one symbol frame; refuse tz-aware time and bad/missing spread."""
    if not isinstance(raw, pd.DataFrame):
        raise ProtocolError(f"{symbol}: frame must be a DataFrame")
    d = raw.copy()
    if "time" not in d.columns:
        raise ProtocolError(f"{symbol}: frame requires time column")
    t = pd.to_datetime(d["time"])
    if getattr(t.dtype, "tz", None) is not None:
        raise ProtocolError(
            f"{symbol}: time must be timezone-naive server_clock_as_stored "
            "(do not label server bars as UTC)"
        )
    d["time"] = t
    for col in ("open", "high", "low", "close"):
        if col not in d.columns:
            raise ProtocolError(f"{symbol}: frame requires {col} column")
        d[col] = d[col].astype(float)
    if "spread" not in d.columns:
        raise ProtocolError(
            f"{symbol}: missing spread column; refuse evaluation (never impute)"
        )
    spr = d["spread"].astype(float).to_numpy()
    if not np.all(np.isfinite(spr)):
        raise ProtocolError(
            f"{symbol}: spread contains NaN/Inf; refuse evaluation"
        )
    if np.any(spr < 0):
        raise ProtocolError(
            f"{symbol}: spread contains negative points; refuse evaluation"
        )
    d["spread"] = spr
    # Detect duplicates / out-of-order before intersection (fail closed)
    t_ns = d["time"].astype("int64").to_numpy()
    if t_ns.size >= 2 and np.any(np.diff(t_ns) <= 0):
        raise ProtocolError(
            f"{symbol}: timestamps must be strictly increasing and unique "
            "(duplicate or out-of-order time)"
        )
    d["hour"] = d["time"].dt.hour.astype(int)
    return d.reset_index(drop=True)


def align_intersection(
    frames: dict[str, pd.DataFrame],
    *,
    symbols: tuple[str, ...] = SYMBOLS,
) -> dict[str, pd.DataFrame]:
    """Ordered intersection calendar I across all symbols; refuse empty I."""
    missing = set(symbols) - set(frames)
    if missing:
        raise ProtocolError(f"missing symbols: {sorted(missing)}")
    prepared = {s: prepare_frame(frames[s], symbol=s) for s in symbols}
    sets = [set(prepared[s]["time"].tolist()) for s in symbols]
    common = sets[0].intersection(*sets[1:])
    if not common:
        raise EmptyIntersectionError(
            "EMPTY_INTERSECTION: no common timestamps across "
            f"{list(symbols)}; refuse evaluation (not a zero-trade result)"
        )
    common_list = sorted(common)
    out: dict[str, pd.DataFrame] = {}
    for s in symbols:
        d = prepared[s]
        d = d.loc[d["time"].isin(common_list)].sort_values("time").reset_index(drop=True)
        out[s] = d
    # Identity check: all symbols share identical ordered timestamps on I
    t0 = out[symbols[0]]["time"].reset_index(drop=True)
    for s in symbols[1:]:
        ts = out[s]["time"].reset_index(drop=True)
        if not ts.equals(t0):
            raise ProtocolError(
                f"misaligned timestamps for {s} after intersection "
                "(refuse silent join / already-shifted predictors)"
            )
    if len(t0) == 0:
        raise EmptyIntersectionError(
            "EMPTY_INTERSECTION: zero rows on I; refuse evaluation"
        )
    return out


def validate_aligned_frames(
    frames: dict[str, pd.DataFrame],
    *,
    symbols: tuple[str, ...] = SYMBOLS,
) -> None:
    """Refuse already-aligned callers that bypass the intersection contract."""
    missing = set(symbols) - set(frames)
    if missing:
        raise ProtocolError(f"missing symbols for aligned frames: {sorted(missing)}")
    for s in symbols:
        prepare_frame(frames[s], symbol=s)  # also validates spread/tz
    ref = frames[symbols[0]]
    t0 = pd.to_datetime(ref["time"]).reset_index(drop=True)
    if getattr(t0.dtype, "tz", None) is not None:
        raise ProtocolError("aligned time must be timezone-naive server_clock_as_stored")
    n = len(ref)
    if n == 0:
        raise EmptyIntersectionError(
            "EMPTY_INTERSECTION: aligned frames have zero rows"
        )
    for s in symbols[1:]:
        d = frames[s]
        if len(d) != n:
            raise ProtocolError(
                f"aligned row count mismatch: {s} has {len(d)}, expected {n}"
            )
        ts = pd.to_datetime(d["time"]).reset_index(drop=True)
        if not ts.equals(t0):
            raise ProtocolError(
                f"aligned timestamps not identical for {s} "
                "(intersection calendar required; refuse shifted predictors)"
            )


def _sign_nonzero(x: float) -> int:
    if not np.isfinite(x) or x == 0.0:
        return 0
    return 1 if x > 0.0 else -1


def build_signal_sides(
    frames_on_i: dict[str, pd.DataFrame],
    *,
    coincident_hours: list[int],
) -> np.ndarray:
    """FX cosign at earliest hour-in-set bar per day → signal_sides on XAU-on-I.

    XAU's own T* open→close is intentionally unused (predicate isolation).
    """
    xau = frames_on_i[TRADED_SYMBOL]
    eur = frames_on_i["EURUSD"]
    gbp = frames_on_i["GBPUSD"]
    n = len(xau)
    if not (len(eur) == n and len(gbp) == n):
        raise ProtocolError("signal_sides: frame length mismatch on I")
    hours_set = {int(h) for h in coincident_hours}
    sides = np.zeros(n, dtype=np.int64)
    times = pd.to_datetime(xau["time"])
    day_keys = times.dt.strftime("%Y-%m-%d").to_numpy()
    hours = xau["hour"].to_numpy(dtype=int)
    # First index per day whose hour is in coincident set
    seen_day: set[str] = set()
    for i in range(n):
        d = str(day_keys[i])
        if d in seen_day:
            continue
        if int(hours[i]) not in hours_set:
            continue
        seen_day.add(d)
        r_eur = float(eur["close"].iloc[i]) - float(eur["open"].iloc[i])
        r_gbp = float(gbp["close"].iloc[i]) - float(gbp["open"].iloc[i])
        s_eur = _sign_nonzero(r_eur)
        s_gbp = _sign_nonzero(r_gbp)
        if s_eur != 0 and s_eur == s_gbp:
            sides[i] = int(s_eur)
        # else leave 0 — disagree / zero leg / no candidate
    return sides


def _params_from_charter(ch: dict[str, Any]) -> dict[str, Any]:
    """Pull every numeric simulation parameter from the charter (no hardcodes)."""
    rule = ch["rule"]
    fixed = ch["fixed"]
    costs = fixed["costs"]
    meta = ch["instrument"]["per_symbol_meta"][TRADED_SYMBOL]
    return {
        "coincident_hours": [int(h) for h in rule["coincident_hours_server"]],
        "sl_atr": float(rule["sl_atr_fixed"]),
        "tp_atr": float(rule["tp_atr_fixed"]),
        "atr_period": int(rule["atr_period"]),
        "h": int(rule["H"]),
        "risk_pct": float(fixed["risk_pct"]),
        "lot_min": float(fixed["lot_min"]),
        "lot_step": float(fixed["lot_step"]),
        "lot_max": float(fixed["lot_max"]),
        "start_balance": float(fixed["start_balance"]),
        "commission_per_lot": float(costs["commission_per_lot"]),
        "slippage_points": float(costs["slippage_points"]),
        "spread_col": str(costs["spread_col"]),
        "point_size": float(meta["point_size"]),
        "contract_size": float(meta["contract_size"]),
        "soft": dict(ch["gates"]["soft"]),
        "atr_reference_bar": str(rule["atr_reference_bar"]),
    }


def label_event_stratum(event: Event, *, open_: np.ndarray, close: np.ndarray) -> str:
    """Reporting label only — ternary variable → binary strata (v3 definition)."""
    i = int(event.t_star_idx)
    if i < 0 or i >= len(open_):
        raise StratifiedEvaluationError(
            f"event_id={event.event_id}: t_star_idx={i} out of range"
        )
    ret = float(close[i]) - float(open_[i])
    s_xau = _sign_nonzero(ret)
    side = int(event.side)
    if s_xau != 0 and s_xau == side:
        return STRATUM_COSIGN
    return STRATUM_NOT_COSIGN


def evaluate_stratified(
    real: RealPathResult,
    *,
    open_: np.ndarray,
    close: np.ndarray,
    soft: dict[str, Any],
    start_balance: float,
) -> StratifiedMetrics:
    """Apply v3 resolution_order; fail closed if labels missing/uncomputable.

    Per-stratum DD convention: metrics_from_pnls on the stratum's ordered pnl
    subsequence (see module docstring / STRATUM_DD_CONVENTION).
    """
    if real is None:
        raise StratifiedEvaluationError("stratified evaluation absent: real path is None")
    event_stratum: dict[int, str] = {}
    for ev in real.events:
        lab = label_event_stratum(ev, open_=open_, close=close)
        if lab not in STRATA:
            raise StratifiedEvaluationError(
                f"event_id={ev.event_id}: unrecognised stratum label {lab!r}"
            )
        event_stratum[int(ev.event_id)] = lab
    if len(event_stratum) != len(real.events):
        raise StratifiedEvaluationError("event stratum map size mismatch")
    if any(eid not in event_stratum for eid in (int(e.event_id) for e in real.events)):
        raise StratifiedEvaluationError("unlabelled event")

    trade_stratum: dict[int, str] = {}
    pnls_by: dict[str, list[float]] = {STRATUM_COSIGN: [], STRATUM_NOT_COSIGN: []}
    for tr in real.trades:
        eid = int(tr.event_id)
        if eid not in event_stratum:
            raise StratifiedEvaluationError(
                f"trade event_id={eid} has no stratum label (fail closed)"
            )
        lab = event_stratum[eid]
        trade_stratum[eid] = lab
        pnls_by[lab].append(float(tr.pnl))

    # Pooled metrics: prefer real.metrics (full MTM equity path) when present
    pooled = dict(real.metrics)
    for k in ("n_trades", "profit_factor", "net_profit", "max_drawdown_pct"):
        if k not in pooled:
            raise StratifiedEvaluationError(f"pooled metrics missing {k!r}")

    by_stratum: dict[str, dict[str, float | int]] = {}
    start_bal = float(start_balance)
    for lab in STRATA:
        m = metrics_from_pnls(
            pnls_by[lab],
            equity=None,
            start_balance=start_bal,
        )
        # Keep metrics_from_pnls keys only; convention lives on StratifiedMetrics
        by_stratum[lab] = m

    if STRATUM_NOT_COSIGN not in by_stratum or STRATUM_COSIGN not in by_stratum:
        raise StratifiedEvaluationError(
            "stratified evaluation empty/incomplete; refuse pooled-only degrade"
        )

    soft_pooled = soft_pass_traded(pooled, soft)
    soft_fresh = soft_pass_traded(by_stratum[STRATUM_NOT_COSIGN], soft)

    if soft_pooled and soft_fresh:
        soft_passers = 1
        disposition = "SOFT_PASS"
        null_armed = True
        r1_burned = False  # null not executed in Phase D; arming only
    else:
        # Resolution: stratum fail (or pooled fail) => SCREEN_FAIL; null not armed
        soft_passers = 0
        disposition = "SCREEN_FAIL"
        null_armed = False
        r1_burned = False

    # Pooled-only pass must never be reported as a passer
    if soft_pooled and not soft_fresh:
        assert soft_passers == 0
        assert disposition == "SCREEN_FAIL"
        assert null_armed is False

    return StratifiedMetrics(
        pooled=pooled,
        by_stratum=by_stratum,
        soft_pass_pooled=bool(soft_pooled),
        soft_pass_fresh=bool(soft_fresh),
        soft_passers=int(soft_passers),
        disposition=disposition,
        null_armed=bool(null_armed),
        r1_burned=bool(r1_burned),
        trade_stratum=trade_stratum,
        event_stratum=event_stratum,
        dd_convention=STRATUM_DD_CONVENTION,
    )


def run_family(
    frames: dict[str, pd.DataFrame],
    *,
    charter: dict[str, Any] | None = None,
    charter_path: Path | str | None = None,
    already_aligned: bool = False,
) -> FamilyResult:
    """Align → signal_sides → admit_and_simulate_real → stratified evaluation."""
    ch = (
        assert_family_charter(charter)
        if charter is not None
        else load_charter(charter_path)
    )
    params = _params_from_charter(ch)
    if params["atr_reference_bar"] != "T_star":
        raise ProtocolError(
            f"REFUSE: rule.atr_reference_bar must be 'T_star' "
            f"(got {params['atr_reference_bar']!r})"
        )

    if already_aligned:
        validate_aligned_frames(frames)
        frames_i = {
            s: prepare_frame(frames[s], symbol=s) for s in SYMBOLS
        }
        # Re-validate identity after prepare
        validate_aligned_frames(frames_i)
    else:
        frames_i = align_intersection(frames)

    spread_col = params["spread_col"]
    for s, d in frames_i.items():
        if spread_col != "spread" and spread_col in d.columns:
            # charter names the column; our prepare always requires 'spread'
            pass
        if "spread" not in d.columns:
            raise ProtocolError(f"{s}: missing cost column {spread_col!r}")

    signal_sides = build_signal_sides(
        frames_i, coincident_hours=params["coincident_hours"]
    )
    xau = frames_i[TRADED_SYMBOL]
    open_ = xau["open"].to_numpy(dtype=float)
    high = xau["high"].to_numpy(dtype=float)
    low = xau["low"].to_numpy(dtype=float)
    close = xau["close"].to_numpy(dtype=float)
    spread = xau["spread"].to_numpy(dtype=float)
    times = xau["time"].to_numpy()
    day_id = day_ids_from_times(times)

    real = admit_and_simulate_real(
        open_=open_,
        high=high,
        low=low,
        close=close,
        spread=spread,
        day_id=day_id,
        signal_sides=signal_sides,
        sl_atr=params["sl_atr"],
        tp_atr=params["tp_atr"],
        risk_pct=params["risk_pct"],
        lot_min=params["lot_min"],
        lot_step=params["lot_step"],
        lot_max=params["lot_max"],
        contract_size=params["contract_size"],
        point_size=params["point_size"],
        commission_per_lot=params["commission_per_lot"],
        slippage_points=params["slippage_points"],
        start_balance=params["start_balance"],
        h=params["h"],
        atr_period=params["atr_period"],
    )

    stratified = evaluate_stratified(
        real,
        open_=open_,
        close=close,
        soft=params["soft"],
        start_balance=params["start_balance"],
    )

    return FamilyResult(
        charter=ch,
        real=real,
        stratified=stratified,
        signal_sides=signal_sides,
        times=times,
        frames_on_i=frames_i,
        extras={
            "params_from_charter": {
                k: v for k, v in params.items() if k != "soft"
            },
            "dd_convention": STRATUM_DD_CONVENTION,
        },
    )


def report_dict(result: FamilyResult) -> dict[str, Any]:
    """Emit n/PF/NP/DD for pooled and both strata + per-trade stratum labels."""
    st = result.stratified

    def _slim(m: dict[str, float | int]) -> dict[str, float | int]:
        return {
            "n": int(m["n_trades"]),
            "n_trades": int(m["n_trades"]),
            "profit_factor": float(m["profit_factor"]),
            "net_profit": float(m["net_profit"]),
            "max_drawdown_pct": float(m["max_drawdown_pct"]),
        }

    return {
        "family_id": FAMILY_ID,
        "disposition": st.disposition,
        "soft_passers": st.soft_passers,
        "soft_pass_pooled": st.soft_pass_pooled,
        "soft_pass_fresh_stratum": st.soft_pass_fresh,
        "null_armed": st.null_armed,
        "r1_burned": st.r1_burned,
        "pooled": _slim(st.pooled),
        "strata": {
            lab: _slim(st.by_stratum[lab]) for lab in STRATA
        },
        "trade_stratum": {str(k): v for k, v in st.trade_stratum.items()},
        "event_stratum": {str(k): v for k, v in st.event_stratum.items()},
        "dd_convention": st.dd_convention,
        "dd_convention_note": st.note,
        "n_events": len(result.real.events),
        "n_trades": len(result.real.trades),
    }


def simulate(d: pd.DataFrame, **_params: Any) -> Any:
    """Single-frame entrypoint — always refuse (wrong harness)."""
    raise RuntimeError(
        "REFUSE_SINGLE_FRAME_SIMULATE: use run_family(frames) for "
        f"{FAMILY_ID} under {HARNESS_KIND}"
    )


def build_grid() -> list[dict[str, Any]]:
    """Zero free knobs → cardinality 1 (params live in the charter)."""
    ch = load_charter()
    if int(ch["n_free_knobs"]) != 0 or list(ch["free_knobs"]) != []:
        raise ProtocolError("charter must have n_free_knobs=0 and free_knobs=[]")
    if int(ch["search_cardinality"]) != 1:
        raise ProtocolError("charter search_cardinality must be 1")
    return [{"family_id": FAMILY_ID, "n_free_knobs": 0}]


def grid(max_n: int = 1, seed: int = 0) -> list[dict[str, Any]]:
    del max_n, seed
    return build_grid()


def dry_plan(charter_path: Path | str | None = None) -> dict[str, Any]:
    """Validate charter and print plan — no data load."""
    ch = load_charter(charter_path)
    params = _params_from_charter(ch)
    return {
        "family_id": FAMILY_ID,
        "charter_version": ch.get("charter_version"),
        "harness.kind": HARNESS_KIND,
        "null.implementation_id": NULL_IMPLEMENTATION_ID,
        "coincident_hours_server": params["coincident_hours"],
        "H": params["h"],
        "sl_atr": params["sl_atr"],
        "tp_atr": params["tp_atr"],
        "atr_period": params["atr_period"],
        "atr_reference_bar": params["atr_reference_bar"],
        "n_free_knobs": ch["n_free_knobs"],
        "search_cardinality": ch["search_cardinality"],
        "prohibited_runners": list((ch.get("harness") or {}).get("prohibited_runners") or []),
        "stratified_required": True,
        "soft": params["soft"],
        "dd_convention": STRATUM_DD_CONVENTION,
        "phase": "D_fixtures_only_no_screen",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Dry plan for exog_london_fx_cosign_xau_follow_flat (Phase D). "
            "Does not load develop data."
        )
    )
    ap.add_argument(
        "--charter",
        default=str(DEFAULT_CHARTER_PATH),
        help="path to frozen charter JSON (default: v3)",
    )
    args = ap.parse_args(argv)
    plan = dry_plan(args.charter)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
