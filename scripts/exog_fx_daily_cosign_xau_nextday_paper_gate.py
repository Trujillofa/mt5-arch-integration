#!/usr/bin/env python3
"""Paper gate for exog_fx_daily_cosign_xau_nextday_follow_flat (declaration-bound).

Implements docs/research/EURUSD-GBP-DAILY-COSIGN-XAU-NEXTDAY-PAPER-GATE-v1.md.
Develop-only. Writes results JSON/MD only.

Usage:
    python3 scripts/exog_fx_daily_cosign_xau_nextday_paper_gate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from build_multi_instrument_data_readiness import (  # noqa: E402
    PACKAGE_ROOT,
    load_package_snapshot,
)

PACKAGE_ID = "4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd"
HOLDOUT = pd.Timestamp("2026-01-01", tz="UTC")
POINT = 0.01
CONTRACT = 100.0
LOTS = 0.01
SLIP_BINDING = 5.0
SLIP_SENS = (0.0, 5.0, 10.0)
N_FILLS_MIN = 40
GATE_MEMO = "docs/research/EURUSD-GBP-DAILY-COSIGN-XAU-NEXTDAY-PAPER-GATE-v1.md"
OUT_JSON = ROOT / "results" / "exog_fx_daily_cosign_xau_nextday_paper_gate_v1.json"
OUT_MD = ROOT / "results" / "exog_fx_daily_cosign_xau_nextday_paper_gate_v1.md"


def _to_daily(h1: pd.DataFrame) -> pd.DataFrame:
    d = h1.copy()
    d["time"] = pd.to_datetime(d["time"], utc=True)
    d["day"] = d["time"].dt.strftime("%Y-%m-%d")
    g = d.groupby("day", sort=True)
    out = pd.DataFrame(
        {
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "spread": g["spread"].last() if "spread" in d.columns else 0.0,
        }
    )
    out.index = pd.to_datetime(out.index, utc=True)
    return out


def _t_stat(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if x.size < 2:
        return 0.0
    sd = float(x.std(ddof=1))
    if sd <= 0:
        return 0.0
    return float(x.mean() / (sd / np.sqrt(x.size)))


def run() -> dict:
    snap = load_package_snapshot(PACKAGE_ROOT / PACKAGE_ID)
    hist = snap.read_all_histories()
    daily = {sym: _to_daily(df) for sym, df in hist.items()}
    # normalize keys
    key = {s.upper().replace(".CSV", ""): s for s in daily}
    # histories may be keyed by path stem
    def pick(*names):
        for n in names:
            for k, v in daily.items():
                if n.lower() in str(k).lower():
                    return v
        raise KeyError(names)

    xau = pick("xau")
    eur = pick("eur")
    gbp = pick("gbp")

    # intersection of daily calendars
    idx = xau.index.intersection(eur.index).intersection(gbp.index)
    xau, eur, gbp = xau.loc[idx], eur.loc[idx], gbp.loc[idx]

    develop = idx < HOLDOUT
    days = idx[develop]
    # need D and D+1 both in develop intersection
    edges = []
    rts = {s: [] for s in SLIP_SENS}
    for i in range(len(days) - 1):
        d0 = days[i]
        d1 = days[i + 1]
        # consecutive calendar days in index (may skip weekends — OK if both present)
        s_eur = float(np.sign(eur.loc[d0, "close"] - eur.loc[d0, "open"]))
        s_gbp = float(np.sign(gbp.loc[d0, "close"] - gbp.loc[d0, "open"]))
        if s_eur == 0.0 or s_gbp == 0.0 or s_eur != s_gbp:
            continue
        s = s_eur
        o1 = float(xau.loc[d1, "open"])
        c1 = float(xau.loc[d1, "close"])
        r_pts = (c1 - o1) * s / POINT
        spr = float(xau.loc[d1, "spread"]) if "spread" in xau.columns else 0.0
        if not np.isfinite(spr):
            spr = 0.0
        edges.append(r_pts)
        for slip in SLIP_SENS:
            rts[slip].append(spr + 2.0 * slip)

    edges_a = np.asarray(edges, dtype=float)
    n = int(edges_a.size)
    payload = {
        "gate_memo": GATE_MEMO,
        "family_id_sketch": "exog_fx_daily_cosign_xau_nextday_follow_flat",
        "package_id": PACKAGE_ID,
        "holdout_start": str(HOLDOUT.date()),
        "n_fills": n,
        "n_fills_min": N_FILLS_MIN,
        "point_size": POINT,
        "lots": LOTS,
        "edge_mean_pts": float(edges_a.mean()) if n else None,
        "edge_median_pts": float(np.median(edges_a)) if n else None,
        "edge_t": _t_stat(edges_a) if n else None,
        "by_slip": {},
        "promote": False,
        "live_go": False,
    }

    fail: list[str] = []
    if n < N_FILLS_MIN:
        fail.append(f"n_fills={n} < {N_FILLS_MIN}")

    binding = None
    for slip in SLIP_SENS:
        rt = np.asarray(rts[slip], dtype=float)
        mean_rt = float(rt.mean()) if n else float("nan")
        med_rt = float(np.median(rt)) if n else float("nan")
        mean_e = float(edges_a.mean()) if n else float("nan")
        med_e = float(np.median(edges_a)) if n else float("nan")
        t = _t_stat(edges_a) if n else 0.0
        four = {
            "mean_edge_vs_mean_rt": {
                "edge": mean_e,
                "rt": mean_rt,
                "delta": mean_e - mean_rt,
                "result": "PASS" if mean_e >= mean_rt else "FAIL",
            },
            "mean_edge_vs_median_rt": {
                "edge": mean_e,
                "rt": med_rt,
                "delta": mean_e - med_rt,
                "result": "PASS_MIXED_ONLY" if mean_e >= med_rt else "FAIL",
            },
            "median_edge_vs_mean_rt": {
                "edge": med_e,
                "rt": mean_rt,
                "delta": med_e - mean_rt,
                "result": "PASS" if med_e >= mean_rt else "FAIL",
            },
            "median_edge_vs_median_rt": {
                "edge": med_e,
                "rt": med_rt,
                "delta": med_e - med_rt,
                "result": "PASS" if med_e >= med_rt else "FAIL_BINDING",
            },
        }
        anti = mean_e < 0 and t <= -2.0
        pass_slip = (
            n >= N_FILLS_MIN
            and mean_e >= mean_rt
            and med_e >= med_rt
            and t >= 2.0
            and not anti
        )
        block = {
            "slippage_points": slip,
            "mean_rt_pts": mean_rt,
            "median_rt_pts": med_rt,
            "four_comparisons": four,
            "t": t,
            "anti": anti,
            "pass_gate": pass_slip,
        }
        payload["by_slip"][str(slip)] = block
        if slip == SLIP_BINDING:
            binding = block
            if not pass_slip:
                if n >= N_FILLS_MIN:
                    if mean_e < mean_rt:
                        fail.append(
                            f"mean edge {mean_e:.4f} < mean RT {mean_rt:.4f} (slip={slip})"
                        )
                    if med_e < med_rt:
                        fail.append(
                            f"median edge {med_e:.4f} < median RT {med_rt:.4f} "
                            f"(slip={slip}, binding)"
                        )
                    if t < 2.0:
                        fail.append(f"t={t:.3f} < 2.0")
                    if anti:
                        fail.append(f"ANTI mean={mean_e:.4f} t={t:.3f}")

    payload["pass_gate"] = bool(binding and binding["pass_gate"] and n >= N_FILLS_MIN)
    payload["disposition"] = "PASS" if payload["pass_gate"] else "FAIL"
    payload["fail_reasons"] = fail
    payload["note"] = (
        "Paper gate only. Not a revival of exog_london_fx_cosign_xau_follow_flat. "
        "FAIL → stop. No screen."
    )
    return payload


def main() -> None:
    payload = run()
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")
    b = payload["by_slip"][str(SLIP_BINDING)]
    lines = [
        "# Daily FX cosign → XAU next-day paper gate v1 — result",
        "",
        "| Field | Value |",
        "|-------|--------|",
        f"| **Gate memo** | `{GATE_MEMO}` |",
        f"| **Package** | `{PACKAGE_ID}` |",
        f"| **Develop** | server_date < {HOLDOUT.date()} |",
        f"| **n_fills** | {payload['n_fills']} (min {N_FILLS_MIN}) |",
        f"| **edge mean / median (pts)** | {payload['edge_mean_pts']:.2f} / {payload['edge_median_pts']:.2f} |",
        f"| **t** | {payload['edge_t']:.3f} |",
        f"| **binding slip** | {SLIP_BINDING:g} |",
        f"| **mean / median RT (pts)** | {b['mean_rt_pts']:.2f} / {b['median_rt_pts']:.2f} |",
        f"| **pass_gate / disposition** | **{payload['disposition']}** |",
        "| **promote / live_go** | false / false |",
        "",
        "## Four comparisons (slip=5 binding)",
        "",
        "| Comparison | Edge | RT | Δ | Result |",
        "|------------|-----:|---:|--:|--------|",
    ]
    for k, label in [
        ("mean_edge_vs_mean_rt", "mean vs mean"),
        ("mean_edge_vs_median_rt", "mean vs median"),
        ("median_edge_vs_mean_rt", "median vs mean"),
        ("median_edge_vs_median_rt", "median vs median (binding)"),
    ]:
        c = b["four_comparisons"][k]
        lines.append(
            f"| {label} | {c['edge']:.2f} | {c['rt']:.2f} | {c['delta']:+.2f} | {c['result']} |"
        )
    lines += ["", "## Fail reasons", ""]
    if payload["fail_reasons"]:
        for fr in payload["fail_reasons"]:
            lines.append(f"- {fr}")
    else:
        lines.append("- (none)")
    lines += [
        "",
        "## Slip sensitivity",
        "",
        f"{'slip':>6} {'pass':>6} {'mean_e':>8} {'mean_rt':>8} {'med_e':>8} {'med_rt':>8}",
    ]
    for slip in SLIP_SENS:
        blk = payload["by_slip"][str(slip)]
        lines.append(
            f"{slip:>6.1f} {str(blk['pass_gate']):>6} "
            f"{payload['edge_mean_pts']:>8.2f} {blk['mean_rt_pts']:>8.2f} "
            f"{payload['edge_median_pts']:>8.2f} {blk['median_rt_pts']:>8.2f}"
        )
    lines += [
        "",
        "## Standing",
        "",
        "- **FAIL → stop** (or PASS → separate full freeze auth only).",
        "- Not a revival of `exog_london_fx_cosign_xau_follow_flat`.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))
    print(OUT_MD.read_text())
    raise SystemExit(0 if payload["pass_gate"] else 2)


if __name__ == "__main__":
    main()
