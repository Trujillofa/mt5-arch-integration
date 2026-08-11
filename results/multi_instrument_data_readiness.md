# Multi-instrument data readiness (Phase 0 — fail-closed)

**Report generated (UTC wall clock):** 2026-08-11T21:33:27.672784+00:00
**Gate:** `PASS_DATA_READY_WITH_IMPUTATION`
**Bar clock contract:** `server_clock_as_stored` (not UTC; MT5 server stamps, offset-free)
**Develop rule:** server_time `< 2026-01-01 00:00:00`
**Account:** verified via export_run.json vs `results/xau_research_costs.json`

## Per-symbol

| Symbol | Status | H1 | Develop | Server range | Eff. spread med | Point | Contract | Hard errors | Flags |
|--------|--------|----|---------|--------------|-----------------|-------|----------|-------------|-------|
| XAUUSD | OK_WITH_IMPUTATION | 29155 | 25558 | 2021-09-07 → 2026-08-11 | 18.0 | 0.01 | 100.0 | — | ZERO_SPREAD_IMPUTED=1296;LARGE_GAPS_GT_72H=9 |
| EURUSD | OK_WITH_IMPUTATION | 30694 | 26901 | 2021-09-07 → 2026-08-12 | 12.0 | 1e-05 | 100000.0 | — | ZERO_SPREAD_IMPUTED=1;LARGE_GAPS_GT_72H=3 |
| GBPUSD | OK_WITH_IMPUTATION | 30694 | 26901 | 2021-09-07 → 2026-08-12 | 12.0 | 1e-05 | 100000.0 | — | ZERO_SPREAD_IMPUTED=1;LARGE_GAPS_GT_72H=3 |

## Costs

- **Commission:** 0.0 (Standard STP)
- **Spread:** `spread_raw_pts` + `spread_effective_pts` + `spread_imputed` (auditable)
- **Slippage:** **UNMEASURED** (0.0 placeholder)

## Export provenance errors

`[]`

## Common develop window

```json
{
  "status": "OK",
  "clock_contract": "server_clock_as_stored",
  "common_start_server": "2021-09-07 01:00:00",
  "common_end_server": "2025-12-31 23:00:00",
  "holdout_start_server": "2026-01-01 00:00:00",
  "n_bars_per_symbol": {
    "XAUUSD": 25558,
    "EURUSD": 26901,
    "GBPUSD": 26901
  },
  "n_intersection_timestamps": 25558,
  "fx_calendars_identical": true,
  "xau_subset_of_fx": true,
  "intersection_equals_xau_count": true,
  "hard_errors": [],
  "bar_count_note": "FX vs XAU bar counts differ by session; joint pool is timestamp intersection (must equal XAU count when XAU \u2282 FX).",
  "per_symbol_develop_start_server": {
    "XAUUSD": "2021-09-07 01:00:00",
    "EURUSD": "2021-09-07 01:00:00",
    "GBPUSD": "2021-09-07 01:00:00"
  },
  "per_symbol_develop_end_server": {
    "XAUUSD": "2025-12-31 23:00:00",
    "EURUSD": "2025-12-31 23:00:00",
    "GBPUSD": "2025-12-31 23:00:00"
  }
}
```

## Gate labels

- `PASS_DATA_READY_WITH_IMPUTATION` — hard DQ OK; some zero-spreads imputed (auditable)
- `PASS_DATA_READY` — hard DQ OK; no imputation
- `FAIL_DATA` — hard error; repair export/provenance/DQ only

## Explicitly not done

- No signals, PF, grids, thesis freeze, holdout selection, paper, or live.

