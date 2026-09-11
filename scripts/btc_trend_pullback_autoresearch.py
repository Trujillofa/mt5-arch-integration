"""btc_trend_pullback_develop_v1 screen — lock-driven, develop-only rank.

Freeze-before-peek: grid, costs, holdout, families, and the a-priori cell
come from ``results/btc_trend_pullback_lock.json``. Holdout never enters a
sort key. Null prices the a-priori cell, never a winner hunt.

Run with plain python3 (host numpy/pandas), never uv run::

    python3 scripts/btc_trend_pullback_autoresearch.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import lane_kit as lk  # noqa: E402
from btc_trend_pullback_core import (  # noqa: E402
    LOCK_PATH,
    TAKEN_HOLDOUTS,
    H1Book,
    family_signals,
    load_btc_h1,
    rebuild_indicators,
)
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    Trade,
    _round_trip_cost,
)

SEARCH_ID = "btc_trend_pullback_develop_v1"
MIN_TRADES = 40


def holdout_start_from_lock(lock: dict) -> date:
    hs = date.fromisoformat(lock["holdout"]["start"])
    forbidden = list(TAKEN_HOLDOUTS) + [
        date.fromisoformat(s) for s in lock["holdout"].get("assert_not", [])
    ]
    return lk.assert_lane_holdout(hs, forbidden)


def simulate_exits(
    b: H1Book,
    signals: np.ndarray,
    costs: CostSpec,
    *,
    sl_atr: float,
    tp_r: float,
    time_stop_bars: int,
) -> list[Trade]:
    """Signal on close of i, fill open of i+1, SL-first, one position.

    Cross-ET-day fills allowed (H1 swing; weekend gaps are real). Time-stop
    exits at the open of ``fill + time_stop_bars``. Shorts use the BTC-NY
    bid-space convention (SL/TP shifted by spread × point).
    """
    trades: list[Trade] = []
    n = len(b.close)
    blocked = -1
    point = costs.point_size
    for i in (int(x) for x in np.flatnonzero(signals)):
        if i >= n - 1 or i <= blocked:
            continue
        sig = int(signals[i])
        fill = i + 1
        spr = float(b.spread[fill])
        if costs.max_spread_points > 0 and spr > costs.max_spread_points:
            continue
        entry = float(b.open[fill])
        at = float(b.atr[i]) if np.isfinite(b.atr[i]) else 0.0
        if at <= 0.0:
            continue
        sl = entry - sig * at * float(sl_atr)
        r = abs(entry - sl)
        tp = entry + sig * r * float(tp_r)
        limit = fill + int(time_stop_bars)
        j = fill
        exit_i: int | None = None
        exit_px = 0.0
        reason = "book_end"
        while j < n and j <= limit:
            if sl is not None:
                lvl = sl - spr * point if sig < 0 else sl
                hit = b.high[j] >= lvl if sig < 0 else b.low[j] <= lvl
                if hit:
                    op_j = float(b.open[j])
                    fill_px = min(lvl, op_j) if sig > 0 else max(lvl, op_j)
                    exit_i, exit_px, reason = j, fill_px, "sl"
                    break
            if tp is not None:
                lvl = tp - spr * point if sig < 0 else tp
                hit = b.low[j] <= lvl if sig < 0 else b.high[j] >= lvl
                if hit:
                    exit_i, exit_px, reason = j, lvl, "tp"
                    break
            if j == limit:
                exit_i, exit_px, reason = j, float(b.open[j]), f"bars{time_stop_bars}"
                break
            j += 1
        if exit_i is None:
            last = n - 1
            if last <= fill:
                continue
            exit_i, exit_px, reason = last, float(b.open[last]), "book_end"
        cost = _round_trip_cost(spr, costs)
        pnl = (exit_px - entry) * sig * costs.contract_size * costs.lots - cost
        wh = b.high[fill : exit_i + 1]
        wl = b.low[fill : exit_i + 1]
        if sig > 0:
            mae = float(entry - np.min(wl))
            mfe = float(np.max(wh) - entry)
        else:
            mae = float(np.max(wh) - entry)
            mfe = float(entry - np.min(wl))
        trades.append(
            Trade(
                side=sig,
                signal_i=i,
                fill_i=fill,
                exit_i=int(exit_i),
                entry=entry,
                exit=float(exit_px),
                reason=reason,
                et_date=str(b.et_date[fill]),
                signal_time=str(b.et_date[i]),
                fill_time=str(b.et_date[fill]),
                exit_time=str(b.et_date[exit_i]),
                spread_pts=spr,
                cost=cost,
                pnl=float(pnl),
                mae=mae,
                mfe=mfe,
            )
        )
        blocked = int(exit_i)
    return trades


def _cfg_signals(b: H1Book, c: dict) -> np.ndarray:
    return family_signals(
        b,
        c["family"],
        min_atr_pct=float(c["min_atr_pct"]),
        long_only=bool(c["long_only"]),
        one_per_day=bool(c["one_per_day"]),
    )


def _run_cell(b: H1Book, c: dict, costs: CostSpec, hs: date) -> dict:
    sigs = _cfg_signals(b, c)
    trades = simulate_exits(
        b,
        sigs,
        costs,
        sl_atr=float(c["sl_atr"]),
        tp_r=float(c["tp_r"]),
        time_stop_bars=int(c["time_stop_bars"]),
    )
    packed = lk.pack_develop_holdout(trades, hs)
    packed.update(
        {
            "family_id": c["family"],
            "params": {
                "sl_atr": float(c["sl_atr"]),
                "tp_r": float(c["tp_r"]),
                "time_stop_bars": int(c["time_stop_bars"]),
                "min_atr_pct": float(c["min_atr_pct"]),
                "one_per_day": bool(c["one_per_day"]),
                "long_only": bool(c["long_only"]),
            },
            "promote": False,
            "live_go": False,
            "id": lk.grid_cfg_id(c),
        }
    )
    packed["develop_score"] = lk.score_pf_expectancy(packed["develop"], min_trades=MIN_TRADES)
    packed["eligible"] = packed["develop_score"] > -1e8
    return packed


def run_screen(lock: dict) -> dict:
    costs = lk.costs_from_lock(lock)
    lk.require_locked_book(lock, costs)
    hs = holdout_start_from_lock(lock)
    csv = _ROOT / lock["data"]["path"]
    b = load_btc_h1(csv, expected_sha256=lock["data"]["sha256"])
    grid = lk.assert_cardinality(lk.iter_product_grid(lock), lock)

    rows = [_run_cell(b, c, costs, hs) for c in grid]
    eligible = [r for r in rows if r["eligible"]]
    ranked = lk.rank_pf_expectancy(eligible)
    winner = ranked[0] if ranked else None

    a_priori = lock["grid"]["a_priori_cell"]
    real_cell = next(
        (
            r
            for r in rows
            if r["family_id"] == a_priori["family"]
            and r["params"]["sl_atr"] == a_priori["sl_atr"]
            and r["params"]["tp_r"] == a_priori["tp_r"]
            and r["params"]["time_stop_bars"] == a_priori["time_stop_bars"]
            and r["params"]["min_atr_pct"] == a_priori["min_atr_pct"]
            and r["params"]["one_per_day"] == a_priori["one_per_day"]
            and r["params"]["long_only"] == a_priori["long_only"]
        ),
        None,
    )
    real_pf = None if real_cell is None else real_cell["develop"]["profit_factor"]

    def null_metric(rng: np.random.Generator) -> float | None:
        rotated = lk.rotate_returns_within_days(b, rng)
        rebuilt = rebuild_indicators(rotated)
        packed = _run_cell(rebuilt, a_priori, costs, hs)
        return packed["develop"]["profit_factor"]

    seeds = [int(s) for s in lock["null_calibration"]["seeds"]]
    null = lk.run_null_rotation(seeds, null_metric, real_metric=real_pf)

    disposition = "SCREEN_PASS_CANDIDATE" if winner else "SCREEN_FAIL"
    best_of_family = {}
    for fam in lock["families"]["search"]:
        fam_rows = [r for r in rows if r["family_id"] == fam]
        if not fam_rows:
            continue
        best = max(fam_rows, key=lambda r: r["develop_score"])
        d = best["develop"]
        best_of_family[fam] = {
            "n": d["trades"],
            "win_rate": d["win_rate"],
            "profit_factor": d["profit_factor"],
            "net_pnl": d["net_pnl"],
            "eligible": best["eligible"],
        }

    return {
        "search_id": lock["search_id"],
        "disposition": disposition,
        "n_configs": len(rows),
        "n_eligible": len(eligible),
        "overlay_default": lock["a_priori_overlay_default"],
        "holdout_start": hs.isoformat(),
        "promote": False,
        "live_go": False,
        "best_develop": None
        if winner is None
        else {
            "id": winner["id"],
            "family_id": winner["family_id"],
            "params": winner["params"],
            "develop": winner["develop"],
            "holdout": winner["holdout"],
        },
        "best_of_family": best_of_family,
        "a_priori_cell": None if real_cell is None else real_cell["develop"],
        "null": {
            "seeds": null["seeds"],
            "frac_null_ge_real": null["frac_null_ge_real"],
            "real_metric": null["real_metric"],
        },
        "digests": {
            "lock_sha256": lk.sha256_file(LOCK_PATH),
            "data_sha256": lock["data"]["sha256"],
        },
        "rows_slim": [
            {
                "id": r["id"],
                "family_id": r["family_id"],
                "eligible": r["eligible"],
                "n": r["develop"]["trades"],
                "win_rate": r["develop"]["win_rate"],
                "profit_factor": r["develop"]["profit_factor"],
                "net_pnl": r["develop"]["net_pnl"],
                "holdout_n": r["holdout"]["trades"],
                "holdout_pf": r["holdout"]["profit_factor"],
            }
            for r in rows
        ],
    }


def write_md(report: dict, path: Path) -> None:
    d = report
    lines = [
        f"# BTC trend-pullback develop screen (`{d['search_id']}`)",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Search** | `{d['search_id']}` |",
        f"| **Disposition** | **{d['disposition']}** |",
        f"| **Overlay default** | `{d['overlay_default']}` |",
        f"| **Configs** | {d['n_configs']} (eligible {d['n_eligible']}) |",
        f"| **Holdout** | `{d['holdout_start']}` unused for selection |",
        "| **promote / live_go** | no / false |",
        "",
        "Machine JSON: `results/btc_trend_pullback_autoresearch.json`.",
        "",
        "## Best develop",
        "",
    ]
    if d["best_develop"] is None:
        lines.append("No develop-eligible config (`trades>=40` and `net_pnl>0`). SCREEN_FAIL.")
    else:
        w = d["best_develop"]
        m = w["develop"]
        lines.append(
            f"`{w['id']}` develop n={m['trades']} WR {m['win_rate']:.1%} "
            f"PF {m['profit_factor']} net={m['net_pnl']:.2f}."
        )
        h = w["holdout"]
        lines.append(
            f"Holdout (eval only) n={h['trades']} WR {h['win_rate']:.1%} "
            f"PF {h['profit_factor']} net={h['net_pnl']:.2f}."
        )
    lines += [
        "",
        "## Null (a-priori full_grammar cell)",
        "",
        f"frac_null_ge_real = {d['null']['frac_null_ge_real']} over "
        f"{len(d['null']['seeds'])} seeds.",
        "",
        "Do not promote. Do not reopen closed theses. Do not edit `results/xau_loop_status.md`.",
        "",
        "## Best-of-family (develop)",
        "",
        "| Family | n | WR | PF | Net | eligible |",
        "|--------|--:|---:|---:|----:|:--------:|",
    ]
    for fam, rec in d["best_of_family"].items():
        wr = rec["win_rate"]
        pf = rec["profit_factor"]
        lines.append(
            f"| `{fam}` | {rec['n']} | {wr:.1%} | {pf} | {rec['net_pnl']:.2f} | {rec['eligible']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lock", type=Path, default=LOCK_PATH)
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "results" / "btc_trend_pullback_autoresearch.json",
    )
    p.add_argument(
        "--md",
        type=Path,
        default=_ROOT / "results" / "btc_trend_pullback_autoresearch.md",
    )
    args = p.parse_args(argv)
    lock = lk.load_lane_lock(args.lock, SEARCH_ID)
    report = run_screen(lock)
    lk.write_slim_json(args.out, report)
    write_md(report, args.md)
    print("wrote", args.out)
    print("wrote", args.md)
    print(report["disposition"], "eligible", report["n_eligible"], "/", report["n_configs"])
    if report["best_develop"]:
        print("winner", report["best_develop"]["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
