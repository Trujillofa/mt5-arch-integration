# XAU family null / max-stat — `stub`

**Disposition:** `QUICK_SMOKE_ONLY`

Quick mode — not a real disposition. Re-run without --quick.

## Protocol

- Family: `stub` (source=builtin:stub)
- Window: develop only (`time < 2026-01-01 00:00:00+00:00`), 25582 H1 bars (2021-09-03T19:00:00+00:00 → 2025-12-31T23:00:00+00:00)
- Grid: 15 configs (max_n=40, seed=42) — no early exit
- Null: 4 return-shuffle trials, base_seed=20260808, workers=1
- Costs: `{"spread_col": "spread", "point_size": 0.01, "commission_per_lot": 3.0, "slippage_points": 0.0}`
- Classic gates: n>=20, PF>1.5, WR>55, DD<10
- Soft gates: PF>=1.5, n>=40, DD<=12, expectancy>=20
- Primary n_passers: **soft**
- Max-stat min trades: 20

## Real grid (develop, costed)

Max-stat is gated on `n_trades >= 20` so the PF=99 thin-sample cap cannot dominate.

| Stat | Value |
|---|---|
| max PF (n≥20) | 1.1133 |
| max net (n≥20) | $3087.83 |
| max PF raw (incl. thin) | 1.1133 |
| n_passers (primary=soft) | 0 |
| n_passers_classic | 0 |
| n_passers_soft | 0 |
| n with ≥20 trades | 15 |
| PF p50 / p90 / p99 | 1.043 / 1.088 / 1.110 |
| elapsed | 0s |

Best by PF among n≥20:

```json
{
  "index": 8,
  "params": {
    "k": 3,
    "bias": 1.0
  },
  "profit_factor": 1.1133147345015193,
  "net_profit": 3087.8329471451307,
  "win_rate": 50.430023455824866,
  "max_drawdown_pct": 11.08880302726479,
  "n_trades": 1279,
  "expectancy": 2.414255627165857,
  "passes_classic": false,
  "passes_soft": false
}
```

## Null distribution (best-of-grid per trial, n≥20 gated PF)

| Stat | null max | null p50 | null p90 | p(null ≥ real) |
|---|---|---|---|---|
| max PF (n≥20) | 1.1732 | 1.1120 | 1.1583 | **0.600** |
| n_passers (primary) | 0.0 | 0.0 | 0.0 | **1.000** |
| n_passers_classic | 0.0 | 0.0 | 0.0 | **1.000** |

## Decision rule

- Fail (`KILL_STUB_LINE`) if `p_max_pf > 0.05` **or** `p_n_passers > 0.05` —
  real best-of-grid is typical of noise under the same search.
- Weak if only one of the two fails; still no promote.
- Pass only if both p-values ≤ 0.05 **and** real n_passers > null p90 — still not
  a live go; only permission to keep researching the family.

Elapsed total: 1s

promote=no | live_go=false | quick=True

