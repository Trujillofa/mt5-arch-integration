# Multi-instrument data readiness (Phase 0 — integrity v2)

**Report generated (UTC wall clock):** 2026-08-11T22:29:04.430990+00:00
**Gate:** `PASS_DATA_READY_WITH_IMPUTATION`
**Bar clock contract:** `server_clock_as_stored` (not UTC)
**Develop rule:** server_time `< 2026-01-01 00:00:00`

## Per-symbol

| Symbol | Status | Published | H1 | Develop | Hard errors | Flags |
|--------|--------|-----------|----|---------|-------------|-------|
| XAUUSD | OK_WITH_IMPUTATION | True | 29155 | 25557 | — | ZERO_SPREAD_IMPUTED=1296;LARGE_GAPS_GT_72H=9 |
| EURUSD | OK_WITH_IMPUTATION | True | 30694 | 26900 | — | ZERO_SPREAD_IMPUTED=1;LARGE_GAPS_GT_72H=3 |
| GBPUSD | OK_WITH_IMPUTATION | True | 30694 | 26900 | — | ZERO_SPREAD_IMPUTED=1;LARGE_GAPS_GT_72H=3 |

## Export provenance errors

`[]`

## Common develop window

```json
{
  "status": "OK",
  "clock_contract": "server_clock_as_stored",
  "common_start_server": "2021-09-07 02:00:00",
  "common_end_server": "2025-12-31 23:00:00",
  "holdout_start_server": "2026-01-01 00:00:00",
  "n_bars_per_symbol": {
    "XAUUSD": 25557,
    "EURUSD": 26900,
    "GBPUSD": 26900
  },
  "n_intersection_timestamps": 25557,
  "fx_calendars_identical": true,
  "xau_subset_of_fx": true,
  "intersection_equals_xau_count": true,
  "hard_errors": [],
  "bar_count_note": "FX vs XAU bar counts differ by session; joint pool is timestamp intersection (must equal XAU count when XAU \u2282 FX).",
  "per_symbol_develop_start_server": {
    "XAUUSD": "2021-09-07 02:00:00",
    "EURUSD": "2021-09-07 02:00:00",
    "GBPUSD": "2021-09-07 02:00:00"
  },
  "per_symbol_develop_end_server": {
    "XAUUSD": "2025-12-31 23:00:00",
    "EURUSD": "2025-12-31 23:00:00",
    "GBPUSD": "2025-12-31 23:00:00"
  }
}
```

## Gate labels

- `PASS_DATA_READY_WITH_IMPUTATION` / `PASS_DATA_READY`
- `FAIL_DATA` — hard error; repair only

## Explicitly not done

- No thesis freeze, signals, PF, grids, nulls, paper, or live.

