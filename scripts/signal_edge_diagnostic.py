#!/usr/bin/env python3
"""Signal-edge diagnostic — does a family carry information worth its friction?

Offline research only. Read-only: writes nothing, ranks nothing, selects nothing.
promote / live_go are not concepts here — this tool cannot produce a config.

WHY THIS EXISTS
---------------
An exit-grid screen answers "did any config make money". It cannot separate the
two reasons a screen fails:

  (a) the entry carries no directional information at all, or
  (b) the entry carries information, but less of it than the round trip costs.

Those need opposite responses. (a) means abandon the family. (b) means the
family is real and the execution model / timeframe / cost book is what has to
change. The EURUSD NY-scalp v1 screen conflated them: pooled gross PF was ~1.00,
which reads as (a), but per-family the pool was hiding a genuinely predictive
mean-reversion family, a reliably ANTI-predictive trend family, and noise.

WHAT IT MEASURES
----------------
For every signal bar, the signed forward return from the bar the simulator
would actually fill on (the open of i+1), at several horizons, in points:

    r_h = (close[i + 1 + h] - open[i + 1]) * side / point

Reported against the round-trip friction of the lock's cost book. The decision
rule is a comparison, not a search:

    max_h mean(r_h)  <  friction_points   =>  family is dead before exits.

No exit, no stop, no sizing, no compounding enters this number, so it cannot be
tuned. Run it BEFORE building an exit grid, not after.

CAUSALITY
---------
Inherited from whatever produces `signals`: this module never builds a signal.
It only shifts by +1 bar to the fill and looks forward from there. A family
whose signals are causal stays causal here.

WINDOWS
-------
`mask` restricts to develop. Holdout is not special-cased and not excluded on
your behalf — pass the develop mask. Reporting a diagnostic on holdout data is
still a peek; this tool will not stop you, the caller's discipline must.

Usage:
    python3 scripts/signal_edge_diagnostic.py                  # EURUSD lane
    python3 scripts/signal_edge_diagnostic.py --horizons 5,20,50 --by-year
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

DEFAULT_HORIZONS = (5, 10, 20, 50, 100)


@dataclass(frozen=True)
class HorizonStat:
    horizon: int
    n: int
    mean_pts: float
    median_pts: float
    t_stat: float


@dataclass
class EdgeResult:
    name: str
    n_signals: int
    friction_pts: float
    stats: list[HorizonStat] = field(default_factory=list)

    @property
    def best(self) -> HorizonStat | None:
        return max(self.stats, key=lambda s: s.mean_pts) if self.stats else None

    @property
    def worst(self) -> HorizonStat | None:
        return min(self.stats, key=lambda s: s.mean_pts) if self.stats else None

    @property
    def verdict(self) -> str:
        """CLEARS-FRICTION / ANTI / COST-BOUND / DEAD. Never a recommendation.

        Order matters. A family can be significantly negative at one horizon and
        trivially positive at another (trend_continuation is +0.06 pts at H5 and
        -11.85 at H50); calling that COST-BOUND because the max is above zero
        would invert its meaning, so ANTI is tested before the positive cases.
        """
        b, w = self.best, self.worst
        if b is None or w is None or self.n_signals == 0:
            return "EMPTY"
        if b.mean_pts >= self.friction_pts and b.t_stat >= 2.0:
            return "CLEARS-FRICTION"
        if w.mean_pts < 0 and w.t_stat <= -2.0:
            return "ANTI"
        if b.mean_pts > 0 and b.t_stat >= 2.0:
            return "COST-BOUND"
        return "DEAD"


def forward_edge(
    open_: np.ndarray,
    close: np.ndarray,
    signals: np.ndarray,
    mask: np.ndarray,
    *,
    point: float,
    friction_pts: float,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    name: str = "family",
) -> EdgeResult:
    """Signed forward return from the fill bar, in points, per horizon.

    `signals` is -1 / 0 / +1 on the DECISION bar i. The fill is open[i+1], which
    is what the simulator uses, so the diagnostic and the backtest share an entry.
    """
    n = len(close)
    if not (len(open_) == len(signals) == len(mask) == n):
        raise ValueError("open_/close/signals/mask must be the same length")
    if point <= 0:
        raise ValueError("point must be positive")

    idx = np.flatnonzero((np.asarray(signals) != 0) & np.asarray(mask))
    idx = idx[idx + 1 < n]
    res = EdgeResult(name=name, n_signals=int(idx.size), friction_pts=float(friction_pts))
    if idx.size == 0:
        return res

    fill = np.asarray(open_, dtype=float)[idx + 1]
    side = np.asarray(signals, dtype=float)[idx]
    for h in horizons:
        j = np.minimum(idx + 1 + h, n - 1)
        r = (np.asarray(close, dtype=float)[j] - fill) * side / point
        sd = float(r.std(ddof=1)) if r.size > 1 else 0.0
        t = float(r.mean() / (sd / np.sqrt(r.size))) if sd > 0 else 0.0
        res.stats.append(
            HorizonStat(
                horizon=int(h),
                n=int(r.size),
                mean_pts=float(r.mean()),
                median_pts=float(np.median(r)),
                t_stat=t,
            )
        )
    return res


def format_table(results: list[EdgeResult], horizons: tuple[int, ...]) -> str:
    """One row per family. Friction is printed once — it is the decision line."""
    if not results:
        return "(no families)\n"
    fr = results[0].friction_pts
    head = f"{'family':>22} {'n':>7} " + "".join(f"{'H' + str(h):>9}" for h in horizons)
    head += f"{'best':>7}{'t':>7}{'worst':>8}{'t':>7}  verdict"
    out = ["Signed forward return from the fill bar, in POINTS.",
           f"Round-trip friction = {fr:.1f} pts — a family must beat this to be tradeable.",
           "",
           head,
           "-" * len(head)]
    for r in results:
        if not r.stats:
            out.append(f"{r.name:>22} {0:>7} " + " " * (9 * len(horizons)) + f"{'':>9}  EMPTY")
            continue
        by_h = {s.horizon: s for s in r.stats}
        row = f"{r.name:>22} {r.n_signals:>7,} "
        row += "".join(f"{by_h[h].mean_pts:>9.2f}" if h in by_h else f"{'':>9}" for h in horizons)
        b, w = r.best, r.worst
        row += f"{b.mean_pts:>7.1f}{b.t_stat:>7.2f}{w.mean_pts:>8.1f}{w.t_stat:>7.2f}  {r.verdict}"
        out.append(row)
    return "\n".join(out) + "\n"


# --- EURUSD NY-scalp lane wiring ---------------------------------------------


def _eurusd_families(csv_path: Path, holdout_iso: str, one_per_day: bool):
    """Import the frozen lane and return (data, {name: signals}, develop mask)."""
    from datetime import date

    import pandas as pd
    from eurusd_ny_scalp_core import build_context, load_eurusd_m5

    d = load_eurusd_m5(csv_path)
    ho = date.fromisoformat(holdout_iso)
    et = pd.to_datetime(pd.Series(d.et_key).astype(str))
    develop = (et.dt.date < ho).to_numpy()
    years = et.dt.year.to_numpy()
    ctx = build_context(d, one_per_day=one_per_day)
    return d, {k: v.signals for k, v in ctx.items()}, develop, years


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", default="results/eurusd_data/history_EURUSD.csv")
    ap.add_argument("--holdout", default="2025-03-01", help="ET date; develop is strictly before")
    ap.add_argument("--horizons", default="5,10,20,50,100")
    ap.add_argument("--point", type=float, default=1e-5)
    ap.add_argument(
        "--friction-pts",
        type=float,
        default=22.0,
        help="round trip: median spread + 2 x slippage (lock cost book)",
    )
    ap.add_argument("--one-per-day", action="store_true")
    ap.add_argument("--by-year", action="store_true", help="also break the best horizon out by year")
    args = ap.parse_args()

    horizons = tuple(int(x) for x in args.horizons.split(","))
    root = Path(__file__).resolve().parent.parent
    csv = Path(args.csv)
    if not csv.is_absolute():
        csv = root / csv

    d, fams, develop, years = _eurusd_families(csv, args.holdout, args.one_per_day)
    results = [
        forward_edge(
            d.open, d.close, sig, develop,
            point=args.point, friction_pts=args.friction_pts,
            horizons=horizons, name=name,
        )
        for name, sig in fams.items()
    ]
    print(f"develop = et_date < {args.holdout}   bars {int(develop.sum()):,} / {len(develop):,}")
    print()
    print(format_table(results, horizons))

    if args.by_year:
        h = 50 if 50 in horizons else horizons[-1]
        print(f"Per-year stability at H{h} (develop only):")
        print(f"{'family':>22} {'year':>6} {'n':>7} {'mean':>9} {'median':>9} {'t':>7}")
        for name, sig in fams.items():
            for y in sorted(set(years[develop])):
                sub = develop & (years == y)
                r = forward_edge(
                    d.open, d.close, sig, sub,
                    point=args.point, friction_pts=args.friction_pts,
                    horizons=(h,), name=name,
                )
                if r.n_signals < 50:
                    continue
                s = r.stats[0]
                print(
                    f"{name:>22} {y:>6} {s.n:>7,} {s.mean_pts:>9.2f} "
                    f"{s.median_pts:>9.2f} {s.t_stat:>7.2f}"
                )
            print()

    print("Reading: CLEARS-FRICTION = worth an exit grid. COST-BOUND = real signal,")
    print("too small to pay for itself — change execution/timeframe, not exits.")
    print("DEAD = no information. ANTI = reliably wrong (do NOT invert post hoc).")


if __name__ == "__main__":
    main()
