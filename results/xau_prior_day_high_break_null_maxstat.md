# XAU family null / max-stat — `prior_day_high_break`

**Disposition:** `KILL_PRIOR_DAY_HIGH_BREAK`

Real best-of-prior_day_high_break-grid is not distinguishable from return-shuffled nulls (p_max_pf=0.463, p_n_passers=1.000). The gates measured the search, not the market. Do not tune further; do not promote.

## Protocol

- Family: `prior_day_high_break` (source=builtin:prior_day_high_break)
- Window: develop only (`time < 2026-01-01 00:00:00+00:00`), 25582 H1 bars (2021-09-03T19:00:00+00:00 → 2025-12-31T23:00:00+00:00)
- Grid: 3 configs (max_n=1200, seed=42) — no early exit
- Null: 40 return-shuffle trials, base_seed=20260808, workers=8
- Costs: `{"spread_col": "spread", "point_size": 0.01, "commission_per_lot": 3.0, "slippage_points": 0.0}`
- Classic gates: n>=20, PF>1.5, WR>55, DD<10
- Soft gates: PF>=1.5, n>=40, DD<=12, expectancy>=20
- Primary n_passers: **soft**
- Max-stat min trades: 20

## Real grid (develop, costed)

Max-stat is gated on `n_trades >= 20` so the PF=99 thin-sample cap cannot dominate.

| Stat | Value |
|---|---|
| max PF (n≥20) | 1.0773 |
| max net (n≥20) | $1252.86 |
| max PF raw (incl. thin) | 1.0773 |
| n_passers (primary=soft) | 0 |
| n_passers_classic | 0 |
| n_passers_soft | 0 |
| n with ≥20 trades | 3 |
| PF p50 / p90 / p99 | 1.024 / 1.067 / 1.076 |
| elapsed | 0s |

Best by PF among n≥20:

```json
{
  "index": 1,
  "params": {
    "sl_atr": 1.5,
    "tp_rr": 2.0,
    "risk_pct": 0.01,
    "max_lots": 0.5,
    "hours": [
      8,
      9,
      10,
      11,
      12,
      13,
      14,
      15,
      16
    ],
    "atr_period": 14,
    "cooldown": 0,
    "long_only": true
  },
  "profit_factor": 1.0772545036841288,
  "net_profit": 1252.8604927644446,
  "win_rate": 36.14035087719298,
  "max_drawdown_pct": 28.293166609020926,
  "n_trades": 285,
  "expectancy": 4.396001728998051,
  "passes_classic": false,
  "passes_soft": false
}
```

## Null distribution (best-of-grid per trial, n≥20 gated PF)

| Stat | null max | null p50 | null p90 | p(null ≥ real) |
|---|---|---|---|---|
| max PF (n≥20) | 1.3081 | 1.0513 | 1.2429 | **0.463** |
| n_passers (primary) | 2.0 | 0.0 | 1.0 | **1.000** |
| n_passers_classic | 0.0 | 0.0 | 0.0 | **1.000** |

## Decision rule

- Fail (`KILL_PRIOR_DAY_HIGH_BREAK`) if `p_max_pf > 0.05` **or** `p_n_passers > 0.05` —
  real best-of-grid is typical of noise under the same search.
- Weak if only one of the two fails; still no promote.
- Pass only if both p-values ≤ 0.05 **and** real n_passers > null p90 — still not
  a live go; only permission to keep researching the family.

Elapsed total: 3s

promote=no | live_go=false | quick=False

