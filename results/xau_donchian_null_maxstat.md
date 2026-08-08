# XAU Donchian null / max-stat test

**Disposition:** `KILL_DONCHIAN_LINE`

Real best-of-Donchian-grid is not distinguishable from return-shuffled nulls (p_max_pf=0.195, p_n_passers=0.293). The gates measured the search, not the market. Do not retune champions; do not promote. promote=no / live_go=false.

## Protocol

- Window: develop only (`time < 2026-01-01 00:00:00+00:00`), 25582 H1 bars (2021-09-03T19:00:00+00:00 → 2025-12-31T23:00:00+00:00)
- Grid: 1201 configs (max_n=1200, seed=42, frozen_prepended=2) — no early exit
- Null: 40 return-shuffle trials, base_seed=20260808, workers=8
- Costs: `{"spread_col": "spread", "point_size": 0.01, "commission_per_lot": 0.0, "slippage_points": 0.0}`
- Soft gates (turtle): PF≥1.5, n≥40, DD≤12, expectancy≥20
- Classic gates: n≥20, PF>1.5, WR>55, DD<10

## Real grid (develop, costed)

Max-stat is gated on `n_trades >= 20` so the PF=99 thin-sample cap cannot dominate.
Primary n_passers = soft (turtle expectancy gates).

| Stat | Value |
|---|---|
| max PF (n≥20) | 1.9955 |
| max net (n≥20) | $33970.53 |
| max PF raw (incl. thin) | 1.9955 |
| n_passers_soft (primary) | 19 |
| n_passers_classic | 1 |
| n with ≥20 trades | 1201 |
| PF p50 / p90 / p99 | 1.291 / 1.609 / 1.847 |
| elapsed | 87s |

Best by PF among n≥20:

```json
{
  "index": 1166,
  "params": {
    "exit_on_exit_channel": true,
    "risk_pct": 0.01,
    "long_only": true,
    "entry_N": 55,
    "exit_N": 20,
    "atr_sl": 2.5,
    "atr_min_pct": 0.5,
    "hours": null,
    "h4_bias": true,
    "be_at_r": null,
    "partial_tp": false,
    "failed_breakout_fade": false,
    "max_entries_per_day": 2,
    "mid_channel_k": 1.0
  },
  "profit_factor": 1.9954976114298113,
  "net_profit": 6088.835853475848,
  "win_rate": 41.1764705882353,
  "max_drawdown_pct": 14.312468196716747,
  "n_trades": 119,
  "expectancy": 51.16668784433486,
  "passes_classic": false,
  "passes_soft": false
}
```

Frozen catalog baselines on same window:

```json
[
  {
    "index": 0,
    "params": {
      "atr_min_pct": null,
      "hours": null,
      "failed_breakout_fade": false,
      "max_entries_per_day": 2,
      "exit_on_exit_channel": true,
      "risk_pct": 0.01,
      "long_only": true,
      "entry_N": 20,
      "exit_N": 10,
      "atr_sl": 1.5,
      "h4_bias": false,
      "mid_channel_k": null,
      "be_at_r": null,
      "partial_tp": false
    },
    "net_profit": 15022.705460238849,
    "win_rate": 32.25108225108225,
    "profit_factor": 1.4862769076106712,
    "max_drawdown_pct": 29.547154747115968,
    "n_trades": 462,
    "wins": 149,
    "losses": 313,
    "expectancy": 32.516678485365475,
    "expectancy_sqrt_n": 698.9195114109572,
    "passes_classic": false,
    "passes_soft": false
  },
  {
    "index": 1,
    "params": {
      "atr_min_pct": null,
      "hours": null,
      "failed_breakout_fade": false,
      "max_entries_per_day": 2,
      "exit_on_exit_channel": true,
      "risk_pct": 0.01,
      "long_only": true,
      "entry_N": 20,
      "exit_N": 8,
      "atr_sl": 1.5,
      "h4_bias": false,
      "mid_channel_k": null,
      "be_at_r": null,
      "partial_tp": false,
      "cooldown": 2
    },
    "net_profit": 15016.643265929426,
    "win_rate": 33.40248962655602,
    "profit_factor": 1.5189981223049582,
    "max_drawdown_pct": 32.77450237573629,
    "n_trades": 482,
    "wins": 161,
    "losses": 321,
    "expectancy": 31.15486154757142,
    "expectancy_sqrt_n": 683.9893580014984,
    "passes_classic": false,
    "passes_soft": false
  }
]
```

## Null distribution (best-of-grid per trial, n≥20 gated PF / soft passers)

| Stat | null max | null p50 | null p90 | p(null ≥ real) |
|---|---|---|---|---|
| max PF (n≥20) | 3.1918 | 1.5265 | 2.3216 | **0.195** |
| n_passers_soft | 308.0 | 0.0 | 90.8 | **0.293** |
| n_passers_classic | 59.0 | 0.0 | 17.6 | **0.341** |

## Decision rule

- Fail (`KILL_DONCHIAN_LINE`) if `p_max_pf > 0.05` **or** `p_n_passers > 0.05` —
  real best-of-grid is typical of noise under the same search.
- Pass (`PASS_KEEP_FROZEN`) only if both p-values ≤ 0.05 — still **not** live_go;
  only permission to keep the frozen Donchian entries (promote=no).
- Do not retune champions from this script.

Elapsed total: 771s

promote=no | live_go=false | quick=False

