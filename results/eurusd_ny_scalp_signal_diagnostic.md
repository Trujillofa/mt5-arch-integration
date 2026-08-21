# EURUSD NY-scalp signal-edge diagnostic

| Field | Value |
|-------|--------|
| **Date** | 2026-08-20 |
| **Tool** | `scripts/signal_edge_diagnostic.py` (read-only; writes nothing, ranks nothing, selects nothing) |
| **Lane** | `eurusd_ny_scalp_develop_v1` — frozen families, unchanged |
| **Window** | develop only, `et_date < 2025-03-01` (258,314 of 368,302 bars) |
| **Holdout** | **not touched** |
| **Status** | diagnostic on a closed lane. No new search, no new lock, no config produced |

Reproduce:

```bash
python3 scripts/signal_edge_diagnostic.py --by-year
```

---

## Why this exists

The v1 screen (`results/eurusd_ny_scalp_autoresearch.md`) returned 0/192 develop-eligible
and pooled gross PF ≈ 1.00. That pooled number reads as *"the entries carry no
information"* — and it is wrong. Pooling three families averaged a genuinely
predictive one against a reliably anti-predictive one, and they cancelled.

An exit-grid screen cannot separate the two reasons a lane fails:

- **(a)** the entry carries no directional information, or
- **(b)** the entry carries information, but less of it than the round trip costs.

Those demand opposite responses. (a) means abandon the family. (b) means the
family is real and the **execution model, timeframe, or cost book** is what has
to change — not the exits. This lane is emphatically (b).

## Method

For every signal bar, the signed forward return measured from the bar the
simulator actually fills on (the open of `i+1`), in points:

```
r_h = (close[i + 1 + h] - open[i + 1]) * side / point
```

Compared against the lock's round-trip friction: median spread 12 pts +
2 × 5 pts slippage = **22 pts**. No exit, stop, sizing, halt, or compounding
enters this number, so there is nothing in it to tune. Causality is inherited
from the frozen signal functions — the tool never builds a signal.

## Result

```
                family       n        H5      H10      H20      H50     H100   best      t   worst      t  verdict
    trend_continuation   5,379      0.06    -1.12    -9.37   -11.85    -7.99    0.1   0.03   -11.8  -3.13  ANTI
        mean_reversion   7,819      4.61     3.21     6.98    11.75    11.60   11.7   4.14     3.2   1.91  COST-BOUND
              breakout     764      4.29     7.76    -2.18   -19.18   -12.29    7.8   1.12   -19.2  -1.68  DEAD
```

Per-year at H50, develop only:

| Family | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|
| `trend_continuation` | −9.08 | **−18.25** (t −2.28) | +2.58 | **−17.01** (t −3.08) | −24.20 |
| `mean_reversion` | −6.44 | **+20.94** (t 3.18) | +4.44 | **+14.26** (t 3.60) | +19.73 |
| `breakout` | −32.49 | −42.32 | +20.08 | −16.83 | — |

## Reading

**`mean_reversion` has a real edge that is roughly half its own transaction cost.**
Positive sign in 4 of 5 develop years, medians positive as well as means (so it is
not outlier-driven), t = 3.18 and 3.60 in the two largest years. The edge builds
with horizon — 4.6 pts at H5, 7.0 at H20 — and plateaus near **11.7 pts around H50**
(~4 hours). Friction is 22 pts. In no single year does the edge clear it. That
single ratio is why the lane failed, and no exit grid, sizing rule, or halt can
change it.

**`trend_continuation` is reliably wrong, not merely useless.** −9 to −24 pts,
negative in 4 of 5 years, t = −3.13 at its worst horizon. It buys tops and sells
bottoms. Inverting it would yield +9 to +24 pts gross — still at or under the
22-pt friction, and post-hoc inversion of a rule that lost is textbook overfitting.
**Do not invert it.** If the reverse hypothesis is genuinely interesting it is a
new `search_id` with its own freeze, stated before looking.

**`breakout` is undersampled noise.** 764 signals across 3½ years, no significant
horizon, sign flipping year to year.

## Consequences for the lane

1. **The execution model is mismatched to the only family that works.** The
   simulator fills market-on-next-open, which is why 10 of the 22 friction points
   are a slippage *assumption* the lock explicitly flags as unmeasured. A
   BB-pierce + RSI<30 entry is naturally a **limit** order — price is coming to
   you. A resting limit pays no slippage and can earn the spread. Run the number
   before getting excited: at zero slippage friction is ~12 pts against an ~11.7 pt
   edge — **break-even at best**, not a business.

2. **The exit geometry never matched the edge.** The edge materialises over ~50
   bars, but the grid's take-profits are 108–324 pts against a median 50-bar move
   of 101 pts. Trying to capture an 11.7-pt drift with a 108-pt target and a
   270–1080-pt stop makes the stop, not the signal, decide the outcome.

3. **The binding constraint is a ratio, and the timeframe is the lever.** Cost is
   fixed per round trip; edge grows with holding horizon. M5 FX scalping is the
   worst corner of that trade-off. The same mean-reversion logic on a higher
   timeframe faces the same ~22 pts against much larger moves.

## Standing recommendation

Run this diagnostic **before** building an exit grid, not after. It costs seconds,
charges no costs, uses no exits, and touches no holdout. On this lane it would
have reported up front that `trend_continuation` is anti-predictive,
`breakout` is noise, and `mean_reversion` has about half the edge it needs —
before 192 configs and a 10-seed null calibration were spent.

Gate to adopt: **if `max_h mean(r_h) < friction_points` at every horizon, the
family is dead before exits are considered and no search is warranted.**

## What this does not authorize

- No promote, no `--live`, no order EA. `promote=false`, `live_go=false` stand.
- Does **not** reopen `eurusd_ny_scalp_develop_v1`. That screen is closed at
  SCREEN_FAIL and its result is unchanged by this diagnostic.
- Does **not** license slicing the 7,819 mean-reversion signals for a
  higher-edge subset (extreme pierces, specific hours, high-range days). Such a
  subset very likely exists **by chance** — that is precisely the multiplicity
  trap the null calibration was built to catch. If pursued: new `search_id`, new
  freeze, conditioning variables named *before* looking.
