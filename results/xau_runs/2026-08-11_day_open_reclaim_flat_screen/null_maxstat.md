# XAU family null / max-stat — `day_open_reclaim_flat`

**Disposition:** `SCREEN_FAIL`

ZERO_PRIMARY_PASSERS: real grid primary passers=0. For any planned n_null, each null trial has n_passers ≥ 0 = real, so hits=n_null and p_n_passers=(n_null+1)/(n_null+1)=1.0 under add-one smoothing. Null trials not executed (planned=999, executed=0). p_max_pf not evaluated. Do not retune; freeze a new family_id.

## Protocol

- Family: `day_open_reclaim_flat` (source=xau_family_day_open_reclaim_flat)
- Window: develop only (`time < 2026-01-01 00:00:00+00:00`), 25582 H1 bars (2021-09-03T19:00:00+00:00 → 2025-12-31T23:00:00+00:00)
- Grid: 1 configs (max_n=1200, seed=42) — no early exit
- Null planned/executed: 999/0 (method=`within_day_ohlc_increment_rotate_v1`)
- Costs: `{"spread_col": "spread", "point_size": 0.01, "commission_per_lot": 0.0, "slippage_points": 0.0}` (slippage may be 0/unmeasured — not fully live-matched)
- Classic gates (from charter if provided): n>=20, PF>1.5, WR>55.0, DD<10.0
- Soft gates (from charter if provided): n>=20, PF>=1.1, NP>0.0
- Primary n_passers: **soft**
- Max-stat min trades: 20
- Charter: results/xau_charters/2026-08-11_day_open_reclaim_flat_v2.json
- Attempt type: `DETERMINISTIC_SCREEN`

## Real grid (develop, costed)

Max-stat is gated on `n_trades >= 20` so the PF=99 thin-sample cap cannot dominate.

| Stat | Value |
|---|---|
| max PF (n≥20) | 1.0348 |
| max net (n≥20) | $1251.52 |
| max PF raw (incl. thin) | 1.0348 |
| n_passers (primary=soft) | 0 |
| n_passers_classic | 0 |
| n_passers_soft | 0 |
| n with ≥20 trades | 1 |
| PF p50 / p90 / p99 | 1.035 / 1.035 / 1.035 |
| elapsed | 0s |

Best by PF among n≥20:

```json
{
  "index": 0,
  "params": {
    "flat_hour": 16,
    "sl_atr": 1.5,
    "tp_atr": 2.0,
    "risk_pct": 0.01,
    "max_lots": 0.5,
    "entry_allowed_hours": [
      9,
      10,
      11,
      12,
      13,
      14,
      15
    ]
  },
  "profit_factor": 1.034782378562991,
  "net_profit": 1251.5199898934925,
  "win_rate": 47.30538922155689,
  "max_drawdown_pct": 31.076497549683204,
  "n_trades": 835,
  "expectancy": 1.4988263352017874,
  "passes_classic": false,
  "passes_soft": false
}
```

## Null distribution

**Skipped:** `ZERO_PRIMARY_PASSERS` (planned=999, executed=0).

- p_n_passers: **1.0** (implied_1.0_zero_real_passers)
- p_max_pf: **None** (not_evaluated)

## Decision rule

- Fail (`KILL_DAY_OPEN_RECLAIM_FLAT`) if `p_max_pf > 0.05` **or** `p_n_passers > 0.05` —
  real best-of-grid is typical of noise under the same search.
- **SCREEN_FAIL** if real primary passers=0 (null not run; p_n_passers implied 1.0).
- Weak if only one of the two fails; still no promote.
- Pass only if both p-values ≤ 0.05 **and** real n_passers > null p90 — still not
  a live go; only permission to keep researching the family.

Elapsed total: 1s

promote=no | live_go=false | quick=False

