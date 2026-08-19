# US100 v4 screen (`us_index_session_v4`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Search** | `us_index_session_v4` — vol-regime OR, proxy-CVD, prior-day POC |
| **Lock** | `results/us_index_session_v4_lock.json` |
| **Select** | `et_date < 2026-06-01` |
| **Holdout** | **2026-07-01** onward (new). June 2026 is unused (burned buffer). |
| **Book** | $10,000 / 1 lot. Slippage **kept** at 10 pt/side. |
| **Grid** | 192 configs (~11 s) |
| **Goals** | median trade-day ≥ **1%**, median month ≥ **20%** |
| **Hits** | develop **0 / 105** eligible · top-20 holdout **0 / 20** |
| **True CVD / HMM** | **skipped** |
| **promote / live_go** | **no / false** |

Machine JSON: `results/us_index_session_v4.json`.

Not a retune of v1/v2/v3. No M1/US500 export. No news-drift.

---

## Honest data limits (locked before the run)

**TimescaleDB / tick CVD does not exist in this repo.** Charter excludes it. FP `M5.hc` has `tick_volume` only — no bid/ask aggressor. `tick_proxy_cvd` is `sign(close−open)×tick_volume`, reset each ET day. That is **not** order-flow CVD.

**HMM was not fit.** Regime = fast ATR > slow ATR × k. No sklearn, no hidden states estimated on this CSV.

**POC** is an M5 profile: tick_volume (or TPO +1) spread across each bar’s [low, high] into $2 bins. Not exchange volume, not a true TPO letter chart.

July–August was already inside v1–v3 holdout aggregates. The new holdout date is a cleaner *window*, not virgin data.

---

## Goals missed

Best develop (OR break, ATR 7>28, one/day, to 10:30, ATR 1.0/1.5 exit):

| Window | n | WR | PF | Median day | Median month |
|--------|--:|---:|---:|-----------:|-------------:|
| Develop | 107 | 51% | 1.51 | **0.31%** | **1.50%** |
| Holdout (from 2026-07-01) | 24 | 42% | 1.07 | **−0.40%** | 0.26% |

The whole top 10 is this same family and exit. That is the v1 ATR-exit lesson again, with a vol gate on top. The gate did not create a 1% median day.

| Family | Best develop | Holdout |
|--------|--------------|---------|
| vol_regime_orb | PF 1.51 · 0.31% day | PF 1.07 · **−0.40%** day |
| tick_proxy_cvd | PF 1.28 · **−0.04%** day | PF 0.45 · −0.21% day |
| prior_poc_reversion | PF 1.29 · **−0.35%** day | PF 0.44 · −0.58% day |

Proxy-CVD and POC are net losers on the typical day even in-sample. A lower-ranked orb row (one/day off) printed holdout median day +0.35% — still far from 1%, and it was **not** the select.

Friction was not relaxed. 20 pt round-trip + cache spread is still in the book.

---

## What this does **not** authorize

- Do not promote, `--live`, or attach an order EA.
- Do not treat the locked $10k / 1-lot / 10 pt book as changed.
- Do not treat proxy-CVD as real order flow.
- Do not add TimescaleDB, M1, or US500 as a *search* on this CSV.
- A later *search* is a **new** `search_id` with a new freeze-before-peek.

A one-shot **replay** of already-selected params under alternate books was later locked as `us_index_session_v4_cost_size_once` (not a search; Timescale/M1/US500 still skipped). Write-up: `results/us_index_session_v4_cost_size_once.md`.
