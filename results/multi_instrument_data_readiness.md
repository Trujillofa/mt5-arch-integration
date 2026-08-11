# Multi-instrument data readiness (Phase 0)

**Frozen at (UTC):** 2026-08-11T21:18:51.659154+00:00
**Gate:** `PASS_CLEAN`
**Holdout / develop rule:** `time < 2026-01-01T00:00:00+00:00`
**Account:** Vantage Standard STP (from `results/xau_research_costs.json`)

## Per-symbol

| Symbol | Status | H1 rows | Develop H1 | Range (full) | Spread median (pts) | Point | Contract | Flags |
|--------|--------|---------|------------|--------------|---------------------|-------|----------|-------|
| XAUUSD | OK_WITH_FLAGS | 29155 | 25558 | 2021-09-07 → 2026-08-11 | 18.0 | 0.01 | 100.0 | ZERO_SPREAD_FILLED=1296,LARGE_GAPS_GT_72H=9 |
| EURUSD | OK_WITH_FLAGS | 30694 | 26901 | 2021-09-07 → 2026-08-12 | 12.0 | 1e-05 | 100000.0 | ZERO_SPREAD_FILLED=1,LARGE_GAPS_GT_72H=3 |
| GBPUSD | OK_WITH_FLAGS | 30694 | 26901 | 2021-09-07 → 2026-08-12 | 12.0 | 1e-05 | 100000.0 | ZERO_SPREAD_FILLED=1,LARGE_GAPS_GT_72H=3 |

## Costs (frozen assumptions)

- **Commission:** 0.0 (Standard STP)
- **Spread:** measured per-bar `MqlRates.spread` (points)
- **Slippage:** **UNMEASURED** (0.0 placeholder; sensitivity points 0/5/10/20 later)

## Common develop window

```json
{
  "status": "OK",
  "common_start": "2021-09-07T01:00:00+00:00",
  "common_end": "2025-12-31T23:00:00+00:00",
  "holdout_start": "2026-01-01T00:00:00+00:00",
  "n_bars_per_symbol": {
    "XAUUSD": 25558,
    "EURUSD": 26901,
    "GBPUSD": 26901
  },
  "bar_count_range": {
    "min": 25558,
    "max": 26901
  },
  "bar_counts_equal": false,
  "bar_count_note": "FX vs XAU H1 counts differ by session calendar; not a hard fail. Joint work uses timestamp intersection.",
  "n_intersection_timestamps": 25558,
  "min_develop_bars_required": 10000,
  "min_intersection_required": 8000,
  "enough_each_symbol": true,
  "enough_joint_intersection": true,
  "per_symbol_develop_start": {
    "XAUUSD": "2021-09-07T01:00:00+00:00",
    "EURUSD": "2021-09-07T01:00:00+00:00",
    "GBPUSD": "2021-09-07T01:00:00+00:00"
  },
  "per_symbol_develop_end": {
    "XAUUSD": "2025-12-31T23:00:00+00:00",
    "EURUSD": "2025-12-31T23:00:00+00:00",
    "GBPUSD": "2025-12-31T23:00:00+00:00"
  }
}
```

## Gate rule

- `PASS_CLEAN` → freeze multi-instrument family charter next (0–1 knob, joint null).
- `FAIL_DATA` → repair exports/meta only; no thesis scoring.

## Explicitly not done

- No signals, PF, grids, parameter inspection, holdout selection, paper, or live.

