# Grid Scalper MA — March 2024 ruin study

**Not a `family_id`. Not the Market `.ex5`. `promote=no`.**

Lock: `results/grid_scalper_ma_ruin_lock.md` (frozen before this run).
Machine: `results/grid_scalper_ma_ruin_2024-03.json`.
Tape: `xauusd_data.csv` M15, 2024-03-01 → 2024-04-01 (1 840 bars, 2039.05–2236.20).

Official download did not land. Wine has `mql5buy://` registered without a working handoff into a community-logged terminal; FP Toolbox has no Market tab. This run is the **published default state machine** (Price vs MA 21, 1.5× grid, no SL, no cap, 2-digit `$11` step, 0.01 start lot, $10k / 1:100) on M15 OHLC.

## Result

| Metric | Value |
|---|---|
| Stop-out | **No** |
| Net | **+$56.03** |
| Baskets | 26 (25 wins / 1 loss) |
| Max DD | **$240 (2.4% of deposit)** |
| Max lots / levels | 0.2081 / 6 |

## Allowed reading

This is the **advertisement shape**: many small basket wins, one small scratch, tiny DD, while gold ran ~$197. At **0.01** on **$10k**, six grid levels are only ~$440 margin. March 2024 does not kill the default lot. It does not show an edge.

Intra-bar ticks would add levels faster than this M15 OHLC proxy. A larger start lot, overlapping baskets, or a cleaner one-way stretch is a **new lock**, not a retune of this one.

Do not treat +$56 / 25–1 as a screen pass.
