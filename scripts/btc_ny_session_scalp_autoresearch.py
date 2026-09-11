#!/usr/bin/env python3
"""Develop screen for btc_ny_session_scalp_develop_v1.

Lock first. Rank develop only. Holdout unused for selection.
96 configs (3 families x 2 sl x 2 tp x 2 ts x 2 nfp x 2 atr).
10-seed within-day return rotation null.
SCREEN_FAIL is a valid, committable outcome.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from btc_ny_session_scalp_backtest import (  # noqa: E402
    LOCK_PATH,
    costs_from_lock,
    holdout_start_from_lock,
    load_lock,
    pack_slices,
    require_btc_cost_book,
    run_family,
    run_transfers,
    simulate_exits,
    split_by_holdout,
)
from us_index_session_backtest import metrics_from_trades, write_slim_json  # noqa: E402
from btc_ny_session_scalp_core import (  # noqa: E402
    FLAT_MIN,
    SEARCH_FAMILIES,
    family_signals,
    load_btc_m5,
    rotate_returns_within_days,
)

MIN_TRADES = 40
NULL_SEEDS = 10


def score_row(m: dict) -> float:
    if int(m["trades"]) < MIN_TRADES or float(m["net_pnl"]) <= 0:
        return -1e9
    pf = m["profit_factor"]
    pf_v = 3.0 if pf is None else float(pf)
    return pf_v * 1000.0 + float(m["expectancy"])


def iter_grid(lock: dict) -> list[dict]:
    g = lock["grid"]
    fams = list(lock["families"]["search"])
    rows = []
    for fam, sl, tp, ts, nfp, atr in itertools.product(
        fams,
        g["sl_atr"],
        g["tp_r"],
        g["time_stop_bars"],
        g["nfp_blackout"],
        g["min_atr_pct"],
    ):
        rows.append(
            {
                "family": fam,
                "sl_atr": float(sl),
                "tp_r": float(tp),
                "time_stop_bars": int(ts),
                "nfp_blackout": bool(nfp),
                "min_atr_pct": float(atr),
            }
        )
    if len(rows) > int(g["max_configs"]):
        raise SystemExit(f"grid {len(rows)} exceeds max_configs {g['max_configs']}")
    return rows


def cfg_key(c: dict) -> str:
    return (
        f"{c['family']}|sl{c['sl_atr']}|tp{c['tp_r']}|ts{c['time_stop_bars']}"
        f"|nfp{int(c['nfp_blackout'])}|atr{c['min_atr_pct']}"
    )


def run_screen(lock: dict) -> dict:
    costs = costs_from_lock(lock)
    require_btc_cost_book(lock, costs)
    hs = holdout_start_from_lock(lock)
    csv = _ROOT / lock["data"]["path"]
    d = load_btc_m5(csv, expected_sha256=lock["data"]["sha256"])
    grid = iter_grid(lock)
    sig_cache: dict[tuple, object] = {}

    def _sigs(fam: str, min_atr: float, nfp: bool):
        key = (fam, float(min_atr), bool(nfp))
        if key not in sig_cache:
            sig_cache[key] = family_signals(
                d, fam, min_atr_pct=float(min_atr), nfp_blackout=bool(nfp)
            )
        return sig_cache[key]

    rows = []
    for c in grid:
        sigs = _sigs(c["family"], c["min_atr_pct"], c["nfp_blackout"])
        trades = simulate_exits(
            d,
            sigs,
            costs,
            sl_atr=c["sl_atr"],
            tp_r=c["tp_r"],
            time_stop_bars=c["time_stop_bars"],
            flatten_min=FLAT_MIN,
        )
        packed = pack_slices(trades, hs)
        packed.update(
            {
                "family_id": c["family"],
                "params": {
                    "sl_atr": c["sl_atr"],
                    "tp_r": c["tp_r"],
                    "time_stop_bars": c["time_stop_bars"],
                    "min_atr_pct": c["min_atr_pct"],
                    "nfp_blackout": c["nfp_blackout"],
                },
                "promote": False,
                "live_go": False,
            }
        )
        packed["develop_score"] = score_row(packed["develop"])
        packed["eligible"] = packed["develop_score"] > -1e8
        packed["id"] = cfg_key(c)
        rows.append(packed)

    eligible = [r for r in rows if r["eligible"]]
    ranked = sorted(
        eligible,
        key=lambda r: (
            r["develop"]["profit_factor"] if r["develop"]["profit_factor"] is not None else 3.0,
            r["develop"]["expectancy"],
        ),
        reverse=True,
    )
    winner = ranked[0] if ranked else None

    # null on a-priori default family at first grid cell (not a winner hunt)
    g0 = lock["grid"]
    null_cfg = {
        "family": lock["a_priori_overlay_default"],
        "sl_atr": float(g0["sl_atr"][0]),
        "tp_r": float(g0["tp_r"][0]),
        "time_stop_bars": int(g0["time_stop_bars"][0]),
        "min_atr_pct": float(g0["min_atr_pct"][0]),
        "nfp_blackout": False,
    }
    null_scores = []
    for seed in range(NULL_SEEDS):
        rng = np.random.default_rng(seed)
        nd = rotate_returns_within_days(d, rng)
        sigs = family_signals(
            nd,
            null_cfg["family"],
            min_atr_pct=null_cfg["min_atr_pct"],
            nfp_blackout=False,
        )
        trades = simulate_exits(
            nd,
            sigs,
            costs,
            sl_atr=null_cfg["sl_atr"],
            tp_r=null_cfg["tp_r"],
            time_stop_bars=null_cfg["time_stop_bars"],
            flatten_min=FLAT_MIN,
        )
        pre, _ = split_by_holdout(trades, hs)
        m = metrics_from_trades(pre)
        null_scores.append(score_row(m))

    real_default, _ = run_family(
        d,
        lock,
        costs,
        null_cfg["family"],
        sl_atr=null_cfg["sl_atr"],
        tp_r=null_cfg["tp_r"],
        time_stop_bars=null_cfg["time_stop_bars"],
        min_atr_pct=null_cfg["min_atr_pct"],
        nfp_blackout=False,
    )
    real_score = score_row(real_default["develop"])
    null_beat = sum(1 for s in null_scores if s >= real_score) / max(len(null_scores), 1)

    transfers = run_transfers(d, lock, costs)
    disposition = "SCREEN_PASS_CANDIDATE" if winner else "SCREEN_FAIL"
    overlay_default = (
        winner["family_id"] if winner else lock["a_priori_overlay_default"]
    )
    return {
        "search_id": lock["search_id"],
        "promote": False,
        "live_go": False,
        "disposition": disposition,
        "overlay_default": overlay_default,
        "holdout_start": lock["holdout"]["start"],
        "n_configs": len(rows),
        "n_eligible": len(eligible),
        "best_develop": (
            {
                "id": winner["id"],
                "family_id": winner["family_id"],
                "params": winner["params"],
                "develop": winner["develop"],
                "holdout": winner["holdout"],
            }
            if winner
            else None
        ),
        "top5_develop": [
            {
                "id": r["id"],
                "family_id": r["family_id"],
                "params": r["params"],
                "develop": r["develop"],
            }
            for r in ranked[:5]
        ],
        "by_family_best": _best_per_family(rows),
        "null": {
            "family": null_cfg["family"],
            "seeds": NULL_SEEDS,
            "real_develop_score": real_score,
            "null_scores": null_scores,
            "frac_null_ge_real": null_beat,
        },
        "transfers": transfers,
        "costs": costs.__dict__,
        "bars": len(d),
        "note": "Holdout unused for selection. Transfers never ranked. Not permission to --live.",
        "rows_slim": [
            {
                "id": r["id"],
                "family_id": r["family_id"],
                "eligible": r["eligible"],
                "develop_trades": r["develop"]["trades"],
                "develop_pf": r["develop"]["profit_factor"],
                "develop_net": r["develop"]["net_pnl"],
                "holdout_pf": r["holdout"]["profit_factor"],
            }
            for r in rows
        ],
    }


def _best_per_family(rows: list[dict]) -> dict:
    out: dict = {}
    for r in rows:
        fid = r["family_id"]
        cur = out.get(fid)
        key = (
            r["develop"]["profit_factor"] if r["develop"]["profit_factor"] is not None else 3.0,
            r["develop"]["expectancy"],
        )
        if cur is None or key > cur["_k"]:
            out[fid] = {
                "_k": key,
                "id": r["id"],
                "params": r["params"],
                "develop": r["develop"],
                "eligible": r["eligible"],
            }
    for v in out.values():
        v.pop("_k", None)
    return out


def write_md(report: dict, path: Path) -> None:
    best = report["best_develop"]
    lines = [
        "# BTC NY-desk overlap develop screen (`btc_ny_session_scalp_develop_v1`)",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| **Search** | `{report['search_id']}` |",
        f"| **Disposition** | **{report['disposition']}** |",
        f"| **Overlay default** | `{report['overlay_default']}` |",
        f"| **Configs** | {report['n_configs']} (eligible {report['n_eligible']}) |",
        f"| **Holdout** | `{report['holdout_start']}` unused for selection |",
        f"| **promote / live_go** | no / false |",
        "",
        "Machine JSON: `results/btc_ny_session_scalp_autoresearch.json`.",
        "",
        "## Best develop",
        "",
    ]
    if best is None:
        lines.append("No develop-eligible config (`trades>=40` and `net_pnl>0`). SCREEN_FAIL.")
    else:
        d = best["develop"]
        h = best["holdout"]
        lines += [
            f"Winner `{best['id']}` (holdout eval only).",
            "",
            f"| Slice | n | WR | PF | Net |",
            f"|-------|--:|---:|---:|----:|",
            f"| develop | {d['trades']} | {d['win_rate']:.1%} | {d['profit_factor']} | {d['net_pnl']:.2f} |",
            f"| holdout | {h['trades']} | {h['win_rate']:.1%} | {h['profit_factor']} | {h['net_pnl']:.2f} |",
        ]
    lines += [
        "",
        "## Transfers (never ranked)",
        "",
    ]
    for name, block in report["transfers"].items():
        dv = block["develop"]
        lines.append(
            f"- `{name}` develop n={dv['trades']} PF={dv['profit_factor']} net={dv['net_pnl']:.2f}"
        )
    nu = report["null"]
    lines += [
        "",
        "## Null (a-priori VWAP+EMA cell)",
        "",
        f"frac_null_ge_real = {nu['frac_null_ge_real']:.2f} over {nu['seeds']} seeds.",
        "",
        "Do not promote. Do not reopen closed theses. Do not edit `results/xau_loop_status.md`.",
        "",
    ]
    path.write_text("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lock", type=Path, default=LOCK_PATH)
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "results" / "btc_ny_session_scalp_autoresearch.json",
    )
    p.add_argument(
        "--md",
        type=Path,
        default=_ROOT / "results" / "btc_ny_session_scalp_autoresearch.md",
    )
    args = p.parse_args(argv)
    lock = load_lock(args.lock)
    if lock.get("search_id") != "btc_ny_session_scalp_develop_v1":
        raise SystemExit("search_id mismatch")
    report = run_screen(lock)
    write_slim_json(args.out, report)
    write_md(report, args.md)
    print("wrote", args.out)
    print("wrote", args.md)
    print(report["disposition"], "eligible", report["n_eligible"], "/", report["n_configs"])
    if report["best_develop"]:
        print("winner", report["best_develop"]["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
