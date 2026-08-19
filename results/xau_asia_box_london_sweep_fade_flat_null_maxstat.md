# XAU family null / max-stat — `asia_box_london_sweep_fade_flat`

**Disposition:** `SCREEN_FAIL`

ZERO_PRIMARY_PASSERS: real grid primary passers=0. For any planned n_null, each null trial has n_passers ≥ 0 = real, so hits=n_null and p_n_passers=(n_null+1)/(n_null+1)=1.0 under add-one smoothing. Null trials not executed (planned=999, executed=0). p_max_pf not evaluated. Do not retune; freeze a new family_id.

## Protocol

- Family: `asia_box_london_sweep_fade_flat` (source=xau_family_asia_box_london_sweep_fade_flat)
- Window: develop only (`time < 2026-01-01 00:00:00+00:00`), 25582 H1 bars (2021-09-03T19:00:00+00:00 → 2025-12-31T23:00:00+00:00)
- Grid: 1 configs (max_n=1200, seed=42) — no early exit
- Null planned/executed: 999/0 (method=`within_day_ohlc_increment_rotate_v1`)
- Costs: `{"spread_col": "spread", "point_size": 0.01, "commission_per_lot": 0.0, "slippage_points": 0.0}` (slippage may be 0/unmeasured — not fully live-matched)
- Classic gates (from charter if provided): n>=20, PF>1.5, WR>55.0, DD<10.0
- Soft gates (from charter if provided): n>=20, PF>=1.1, DD<=25.0, NP>0.0
- Primary n_passers: **soft**
- Max-stat min trades: 20
- Charter: results/xau_charters/2026-08-19_asia_box_london_sweep_fade_flat_v2.json
- Attempt type: `DETERMINISTIC_SCREEN`

## Real grid (develop, costed)

Max-stat is gated on `n_trades >= 20` so the PF=99 thin-sample cap cannot dominate.

| Stat | Value |
|---|---|
| max PF (n≥20) | 0.5531 |
| max net (n≥20) | $-8141.58 |
| max PF raw (incl. thin) | 0.5531 |
| n_passers (primary=soft) | 0 |
| n_passers_classic | 0 |
| n_passers_soft | 0 |
| n with ≥20 trades | 1 |
| PF p50 / p90 / p99 | 0.553 / 0.553 / 0.553 |
| elapsed | 0s |

Best by PF among n≥20:

```json
{
  "index": 0,
  "params": {
    "flat_hour": 13,
    "risk_pct": 0.01,
    "max_lots": 0.5,
    "box_hours": [
      1,
      2,
      3,
      4,
      5,
      6,
      7
    ],
    "hunt_hours": [
      8,
      9,
      10,
      11,
      12,
      13
    ]
  },
  "profit_factor": 0.5530594935840234,
  "net_profit": -8141.580000000056,
  "win_rate": 26.119402985074625,
  "max_drawdown_pct": 82.12196526759618,
  "n_trades": 670,
  "expectancy": -12.151611940298592,
  "passes_classic": false,
  "passes_soft": false
}
```

## Null distribution

**Skipped:** `ZERO_PRIMARY_PASSERS` (planned=999, executed=0).

- p_n_passers: **1.0** (implied_1.0_zero_real_passers)
- p_max_pf: **None** (not_evaluated)

## Decision rule

- Fail (`KILL_ASIA_BOX_LONDON_SWEEP_FADE_FLAT`) if `p_max_pf > 0.05` **or** `p_n_passers > 0.05` —
  real best-of-grid is typical of noise under the same search.
- **SCREEN_FAIL** if real primary passers=0 (null not run; p_n_passers implied 1.0).
- Weak if only one of the two fails; still no promote.
- Pass only if both p-values ≤ 0.05 **and** real n_passers > null p90 — still not
  a live go; only permission to keep researching the family.

Elapsed total: 1s

promote=no | live_go=false | quick=False

