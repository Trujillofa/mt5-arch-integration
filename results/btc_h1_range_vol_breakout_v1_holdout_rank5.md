# BTC H1 range-vol breakout — holdout eval Config #5 only

Window: `signal_utc_date >= 2026-01-01`. Evaluation, not a new search.
promote / live_go: **no / false**. Holdout is **not virgin** (prior peek).

Data: `results/btc_data/history_BTCUSD_H1.csv` · 29035 bars · 2021-12-20 21:00:00+00:00 → 2026-08-18 15:00:00+00:00
sha256 `c2f87a05eb56d401d292ddcb68a68b6baa6cc22ab0a061c39e573f96e0f062ff` (matches lock).

Frozen row: `range_n=20`, `squeeze_max=0.90`, `expand_min=1.25`, `sl_atr=2.0`, `tp_rr=2.0`, both sides, flatten_weekend=true.
Book: $10k / 0.01 lot / slip 250 pt/side / spread cap 4000 / commission 0.

## Develop reminder (already ranked; not re-selected)

Config #5 develop: n=293, PF=1.1127, NP=+143.97 (soft_pass).

## Holdout 2026 (Config #5 only)

| Field | Value |
|-------|--------|
| n | 37 |
| longs / shorts | 16 / 21 |
| WR | 43.2% |
| PF | 1.1744 (not rounded up) |
| NP | +32.10 |
| DD | 0.60% |
| expectancy | +0.8676 |
| median day | -0.0485% |
| date span | 2026-01-01 → 2026-08-11 |
| first signal | 2026-01-01T16:00:00+00:00 |
| last signal | 2026-08-11T14:00:00+00:00 |

Holdout soft: **FAIL** — n>=40 (n=37 < 40). PF>1 does not pass when n<40. Do not round PF up.

Matches prior peek (n=37, PF ~1.17, +$32, 16L/21S).

## Locked

- Do not retune the frozen 16. Do not score the discarded 15 for selection.
- Do not raise lots or cut slip.
- leftover remains Timescale if this also fails.

