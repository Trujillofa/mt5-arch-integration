#!/usr/bin/env python3
"""Paper-gate diagnostic for eurusd_ny_mr_limit_fill_v1 (declaration-bound).

Implements docs/research/EURUSD-MR-LIMIT-FILL-PAPER-GATE-v1.md exactly.
Develop-only. Read-only w.r.t. locks/charters. Writes results JSON/MD only.

Usage:
    python3 scripts/eurusd_mr_limit_fill_paper_gate.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from eurusd_ny_scalp_core import load_eurusd_m5, mean_reversion_signals  # noqa: E402
from signal_edge_diagnostic import HorizonStat  # noqa: E402

POINT = 1e-5
HOLDOUT = date(2025, 3, 1)
HORIZONS = (5, 10, 20, 50, 100)
N_FILLS_MIN = 200
GATE_MEMO = "docs/research/EURUSD-MR-LIMIT-FILL-PAPER-GATE-v1.md"
OUT_JSON = ROOT / "results" / "eurusd_ny_mr_limit_fill_paper_gate_v1.json"
OUT_MD = ROOT / "results" / "eurusd_ny_mr_limit_fill_paper_gate_v1.md"


@dataclass
class PaperResult:
    n_signals: int
    n_fills: int
    fill_rate: float
    median_paper_rt_pts: float
    mean_paper_rt_pts: float
    stats: list[HorizonStat]
    best: HorizonStat | None
    worst: HorizonStat | None
    verdict: str
    pass_gate: bool
    fail_reasons: list[str]


def _t_stat(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    n = x.size
    if n < 2:
        return 0.0
    mu = float(x.mean())
    sd = float(x.std(ddof=1))
    if sd <= 0:
        return 0.0
    return mu / (sd / np.sqrt(n))


def run() -> PaperResult:
    csv = ROOT / "results" / "eurusd_data" / "history_EURUSD.csv"
    d = load_eurusd_m5(csv)
    sig = mean_reversion_signals(d, one_per_day=False)
    et = pd.to_datetime(pd.Series(d.et_key).astype(str))
    develop = (et.dt.date < HOLDOUT).to_numpy()

    n = len(d.close)
    side = np.sign(sig).astype(float)
    is_sig = (sig != 0) & develop
    sig_idx = np.flatnonzero(is_sig)

    fill_i: list[int] = []
    fill_side: list[float] = []
    fill_px: list[float] = []
    fill_rt: list[float] = []

    for i in sig_idx:
        j = i + 1
        if j >= n:
            continue
        # same ET session-date
        if int(d.et_key[j]) != int(d.et_key[i]):
            continue
        s = float(side[i])
        lim = float(d.close[i])
        if s > 0:
            filled = float(d.low[j]) <= lim
        else:
            filled = float(d.high[j]) >= lim
        if not filled:
            continue
        fill_i.append(j)
        fill_side.append(s)
        fill_px.append(lim)
        fill_rt.append(float(d.spread[i]))

    fill_i_a = np.asarray(fill_i, dtype=int)
    fill_side_a = np.asarray(fill_side, dtype=float)
    fill_px_a = np.asarray(fill_px, dtype=float)
    fill_rt_a = np.asarray(fill_rt, dtype=float)

    n_signals = int(sig_idx.size)
    n_fills = int(fill_i_a.size)
    fill_rate = float(n_fills / n_signals) if n_signals else 0.0
    median_rt = float(np.median(fill_rt_a)) if n_fills else float("nan")
    mean_rt = float(np.mean(fill_rt_a)) if n_fills else float("nan")

    stats: list[HorizonStat] = []
    for h in HORIZONS:
        rets = []
        for k in range(n_fills):
            j0 = int(fill_i_a[k])
            j1 = j0 + h
            if j1 >= n:
                continue
            # stay causal; do not require same-day for forward horizon (gate memo)
            r = (float(d.close[j1]) - float(fill_px_a[k])) * float(fill_side_a[k]) / POINT
            rets.append(r)
        arr = np.asarray(rets, dtype=float)
        if arr.size == 0:
            stats.append(HorizonStat(h, 0, float("nan"), float("nan"), 0.0))
        else:
            stats.append(
                HorizonStat(
                    horizon=h,
                    n=int(arr.size),
                    mean_pts=float(arr.mean()),
                    median_pts=float(np.median(arr)),
                    t_stat=_t_stat(arr),
                )
            )

    finite = [s for s in stats if s.n > 0 and np.isfinite(s.mean_pts)]
    best = max(finite, key=lambda s: s.mean_pts) if finite else None
    worst = min(finite, key=lambda s: s.mean_pts) if finite else None

    fail: list[str] = []
    if n_fills < N_FILLS_MIN:
        fail.append(f"n_fills={n_fills} < {N_FILLS_MIN}")
    if best is None or not np.isfinite(median_rt):
        fail.append("no usable best horizon / median RT")
    else:
        if not (best.mean_pts >= median_rt):
            fail.append(
                f"best mean {best.mean_pts:.2f} < median paper RT {median_rt:.2f} (H{best.horizon})"
            )
        if best.t_stat < 2.0:
            fail.append(f"best t {best.t_stat:.2f} < 2.0 (H{best.horizon})")
    if (
        worst is not None
        and worst.mean_pts < 0
        and worst.t_stat <= -2.0
    ):
        fail.append(
            f"ANTI worst H{worst.horizon} mean {worst.mean_pts:.2f} t {worst.t_stat:.2f}"
        )

    # triage-style label for reporting (not the binary gate)
    if best is None:
        label = "EMPTY"
    elif best.mean_pts >= median_rt and best.t_stat >= 2.0:
        label = "CLEARS-PAPER-RT"
    elif worst is not None and worst.mean_pts < 0 and worst.t_stat <= -2.0:
        label = "ANTI"
    elif best.mean_pts > 0 and best.t_stat >= 2.0:
        label = "COST-BOUND-VS-PAPER-RT"
    else:
        label = "DEAD"

    return PaperResult(
        n_signals=n_signals,
        n_fills=n_fills,
        fill_rate=fill_rate,
        median_paper_rt_pts=median_rt,
        mean_paper_rt_pts=mean_rt,
        stats=stats,
        best=best,
        worst=worst,
        verdict=label,
        pass_gate=len(fail) == 0,
        fail_reasons=fail,
    )


def main() -> None:
    r = run()
    payload = {
        "gate_memo": GATE_MEMO,
        "search_id_sketch": "eurusd_ny_mr_limit_fill_v1",
        "holdout_start": HOLDOUT.isoformat(),
        "point": POINT,
        "horizons": list(HORIZONS),
        "n_fills_min": N_FILLS_MIN,
        "n_signals": r.n_signals,
        "n_fills": r.n_fills,
        "fill_rate": r.fill_rate,
        "median_paper_rt_pts": r.median_paper_rt_pts,
        "mean_paper_rt_pts": r.mean_paper_rt_pts,
        "stats": [asdict(s) for s in r.stats],
        "best": asdict(r.best) if r.best else None,
        "worst": asdict(r.worst) if r.worst else None,
        "verdict_label": r.verdict,
        "pass_gate": r.pass_gate,
        "fail_reasons": r.fail_reasons,
        "promote": False,
        "live_go": False,
        "note": "Paper gate only. Does not authorize screen, charter freeze, or revival of eurusd_ny_scalp_develop_v1.",
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# EURUSD MR limit-fill paper gate v1 — result",
        "",
        "| Field | Value |",
        "|-------|--------|",
        f"| **Gate memo** | `{GATE_MEMO}` |",
        f"| **Develop** | `et_date < {HOLDOUT.isoformat()}` |",
        f"| **n_signals** | {r.n_signals} |",
        f"| **n_fills** | {r.n_fills} |",
        f"| **fill_rate** | {r.fill_rate:.3f} |",
        f"| **median paper RT (pts)** | {r.median_paper_rt_pts:.2f} |",
        f"| **pass_gate** | **{'PASS' if r.pass_gate else 'FAIL'}** |",
        f"| **verdict_label** | {r.verdict} |",
        "| **promote / live_go** | false / false |",
        "",
        "## Horizons (filled trades only; edge from limit fill price)",
        "",
        f"{'H':>4} {'n':>7} {'mean':>9} {'median':>9} {'t':>7}",
    ]
    for s in r.stats:
        lines.append(
            f"{s.horizon:>4} {s.n:>7} {s.mean_pts:>9.2f} {s.median_pts:>9.2f} {s.t_stat:>7.2f}"
        )
    lines += ["", "## Fail reasons" if r.fail_reasons else "## Fail reasons", ""]
    if r.fail_reasons:
        for fr in r.fail_reasons:
            lines.append(f"- {fr}")
    else:
        lines.append("- (none)")
    lines += [
        "",
        "## Standing",
        "",
        "- FAIL → stop; do not write a screen; do not retune fill rules after seeing the number.",
        "- PASS → only then consider a full freeze charter (separate authorization).",
        "- Not a revival of `eurusd_ny_scalp_develop_v1`.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))
    print(OUT_MD.read_text())
    print(f"Wrote {OUT_JSON} and {OUT_MD}")
    raise SystemExit(0 if r.pass_gate else 2)


if __name__ == "__main__":
    main()
