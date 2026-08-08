# XAU null / max-stat test

**Disposition:** `KILL_BB_RSI_LINE`

Real best-of-grid is not distinguishable from return-shuffled nulls (p_max_pf=0.854, p_n_passers=0.707). The gates measured the search, not the market. Do not tune further; do not promote. Cross-instrument / knob-cut only make sense after a pass.

## Protocol

- Window: develop only (`time < 2026-01-01 00:00:00+00:00`), 25582 H1 bars (2021-09-03T19:00:00+00:00 → 2025-12-31T23:00:00+00:00)
- Grid: 1205 configs (max_n=1200, seed=42) — no early exit
- Null: 40 return-shuffle trials, base_seed=20260808, workers=8
- Costs: `{"spread_col": "spread", "point_size": 0.01, "commission_per_lot": 0.0, "slippage_points": 0.0}`

## Real grid (develop, costed)

Max-stat is gated on `n_trades >= 20` so the PF=99 thin-sample cap cannot dominate.

| Stat | Value |
|---|---|
| max PF (n≥20) | 2.2420 |
| max search_score (n≥20) | 791.25 |
| max net (n≥20) | $4665.03 |
| max PF raw (incl. thin) | 534.7310 |
| n_passers (gates) | 19 |
| n early-exit eligible | 10 |
| n with ≥20 trades | 536 |
| PF p50 / p90 / p99 | 0.940 / 3.117 / 99.000 |
| elapsed | 94s |

Best by search_score among n≥20:

```json
{
  "index": 683,
  "params": {
    "mode": "rsi_cross",
    "rsi_buy": 40.0,
    "rsi_sell": 55.0,
    "sl_atr": 1.2,
    "tp_atr": 1.2,
    "bb_col": "bb_lo25",
    "trend_col": "ema200",
    "use_macd_filter": true,
    "hours": null,
    "long_only": true,
    "risk_pct": 0.01,
    "cooldown": 2
  },
  "profit_factor": 2.2420483111519816,
  "search_score": 791.2546701888572,
  "net_profit": 1464.1738664990876,
  "win_rate": 70.0,
  "max_drawdown_pct": 2.869773364164289,
  "n_trades": 40,
  "passes": true,
  "would_early_exit_search": true
}
```

Shipped baseline replay (for reference):

```json
{
  "params": {
    "mode": "bb_rsi",
    "rsi_buy": 30.0,
    "rsi_sell": 58.0,
    "sl_atr": 1.0,
    "tp_atr": 1.2,
    "bb_col": "bb_lo15",
    "trend_col": "ema200",
    "use_macd_filter": false,
    "hours": [
      12,
      13,
      14,
      15,
      16,
      17,
      18,
      19,
      20
    ],
    "long_only": true,
    "risk_pct": 0.01,
    "cooldown": 2
  },
  "net_profit": 1188.2678393647006,
  "win_rate": 59.523809523809526,
  "profit_factor": 1.671255765551878,
  "max_drawdown_pct": 3.8383133455421437,
  "n_trades": 42,
  "wins": 25,
  "losses": 17,
  "search_score": 762.8759682765989,
  "passes": true
}
```

## Null distribution (best-of-grid per trial, n≥20 gated)

| Stat | null max | null p50 | null p90 | p(null ≥ real) |
|---|---|---|---|---|
| max PF (n≥20) | 9.7007 | 3.1147 | 6.1952 | **0.854** |
| max score (n≥20) | 921.02 | 814.50 | 860.29 | **0.854** |
| n_passers | 74.0 | 22.0 | 43.3 | **0.707** |
| n early-exit | 56.0 | 12.5 | 28.0 | **0.707** |

## Decision rule

- Fail (kill line) if `p_max_pf > 0.05` **or** `p_n_passers > 0.05` — real best-of-grid
  is typical of noise under the same search.
- Weak if only one of the two fails; still no promote.
- Pass only if both p-values ≤ 0.05 **and** real n_passers > null p90 — still not
  a live go; only permission to keep researching the family (knob cut, cross-instrument).

Elapsed total: 712s

