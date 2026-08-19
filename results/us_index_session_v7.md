# US100 v7 screen (`us_index_session_v7`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Search** | `us_index_session_v7` — 60m IB false-break fade + M5 z-score / tick-vol exhaustion |
| **Lock** | `results/us_index_session_v7_lock.json` |
| **Select** | `et_date < 2026-06-01` |
| **Holdout** | **2026-07-01** onward. June unused (burned). July–August already sat inside the v4–v6 holdout aggregates — cleaner window, **not virgin**. |
| **Book** | $10,000 / 1 lot. Slippage **kept** at 10 pt/side. |
| **Grid** | 40 configs (8 IB + 32 z-score; ~2.3 s) |
| **Goals** | median trade-day ≥ **1%**, median month ≥ **20%** |
| **Hits** | develop **0 / 13** eligible · top-20 holdout **0 / 13** |
| **Eligible by family** | `ib_false_breakout_fade` **0** · `m5_zscore_tick_vol_exhaustion` **13** |
| **promote / live_go** | **no / false** |

Machine JSON: `results/us_index_session_v7.json`.

Architectural pivot after v6 starvation. Not a retune. Not an XAU charter. These families stay **Python-only**.

---

## Frozen before any develop metric

| Choice | Lock |
|--------|------|
| Z-window | Prior W closed M5 bars **excluding** bar `i` (`i-W .. i-1`). Bar `i` is not inside μ, σ, or Vμ. |
| Z bars | Consecutive M5 (all hours). Session gate is the entry window only. |
| σ | Sample std (`ddof=1`). Require σ > 0. |
| Exit μ | Running typical-price μ on the same exclude-`j` window. Including `j` would leak `close[j]` into μ while tagging high/low. |
| IB | `opening_range_at(..., or_minutes=60)`. Complete only when bar open ≥ **10:30 ET**. Not stamped during 09:30–10:30. |
| IB trigger | Sweep bar, then the **next** M5 must close back inside. Same-bar close-back does not count. |
| Fill | Next-bar open. Signals on closed bars only (`exclude_forming`). |
| Friday | No new entries ≥ 14:00 ET. Flatten 15:45 if still open. Emergency SL ATR 1.0. |

Grid is the product of the listed knobs (40). Tighter than v5/v6 on purpose — two new predicates, no padding.

---

## What this is not

| Kept | Rejected |
|------|----------|
| Causal 60m IB via `opening_range_at(..., or_minutes=60)` | v1 15m OR close-break / v1–v6 winners |
| `simulate_exits` kind=`vwap` (IB mid / opposite IB / rolling μ) | Daily Hurst/ADX/ATR AND-gate (v6 starved) |
| Tick-volume spike vs the same causal window as Z | v3 same-bar wick fade / FVG / US100–US30 divergence |
| split_v4 (June burned; July–August cleaner, not virgin) | US30 predictor, XAU `{7,8,9}`, news-drift, Timescale / M1 / US500 |
| | H4 / Donchian / XAU / regime AND with these families |

---

## Goals missed

Best develop (z-score 2.5, vol_k 1.5, window 12, [09:45, 15:00), one/day, exit = running μ + ATR 1.0 SL + flatten 15:45):

| Window | n | WR | PF | Median day | Median month |
|--------|--:|---:|---:|-----------:|-------------:|
| Develop | 52 | 65% | 2.98 | **+0.17%** | **+1.05%** |
| Holdout (from 2026-07-01) | 16 | 38% | 1.48 | **−0.28%** | +0.92% |

Net is positive and the PF is fine. The **median** trade-day is 0.17%, not 1%. 6% of develop days were ≥1%. Holdout median day flips negative.

| Family | Eligible | Best develop | Holdout |
|--------|----------|--------------|---------|
| m5_zscore_tick_vol_exhaustion | 13 / 32 | PF 2.98 · **+0.17%** day · 52 trades | PF 1.48 · **−0.28%** day |
| ib_false_breakout_fade | **0 / 8** | 147 trades · PF 0.93 · **−0.32%** day (opposite IB, to 12:00, one/day off) | 30 trades · PF 0.92 · **−0.46%** day |

IB fade has plenty of trades and loses money. The stop-run-that-fails-to-hold story does not pay on this book after 10 pt slippage.

**0 / 13** develop-eligible configs hit both 1% and 20%. **0** of the ranked holdouts did either. There is no promote path.

---

## What this does **not** authorize

- Do not promote, `--live`, or attach an order EA.
- Do not put IB false-break or the z-score family on the overlay.
- Do not revive daily regime, US30, XAU `{7,8,9}`, news-drift, Timescale, M1, or US500.
- Do not cut slippage or raise lots.
- Do not retune these 40 configs. A later idea is a **new** `search_id` with a new freeze-before-peek.
