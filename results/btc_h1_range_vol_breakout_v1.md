# BTC H1 range / vol-breakout screen (`btc_h1_range_vol_breakout_v1`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-19 |
| **Search** | `btc_h1_range_vol_breakout_v1` — H1 close-through + squeeze→expand |
| **Lock** | `results/btc_h1_range_vol_breakout_v1_lock.json` |
| **Grill** | `results/btc_h1_range_vol_breakout_v1_grill.md` (frozen before grid) |
| **Select** | `signal_utc_date < 2026-01-01` |
| **Holdout** | **2026-01-01** onward. Never used for selection. |
| **Book** | $10,000 / **0.01 lot** / **250 pt** slip/side / point 0.01 / contract 1 |
| **Grid** | 16 configs (2.99 s) |
| **Soft gate** | n≥40, NP>0, PF≥1.1, DD≤25% (develop). 1%/20% is **not** a gate. |
| **Hits** | develop eligible **4** · soft **1** · top-20 holdout soft **0** |
| **2026 fired** | holdout n>0 on **16 / 16** configs |
| **promote / live_go** | **no / false** |
| **Data** | FP native `H1.hc` via `read_mt5_hc`. H4 not used. Live terminal not touched. |

Machine JSON: `results/btc_h1_range_vol_breakout_v1.json`.
Predecessor: `btc_h1_trend_pullback_v1` (sealed; not retuned).

---

## Frozen before any develop metric

| Choice | Lock |
|--------|------|
| Book | 0.01 lot · 250 pt slip · 4000 pt spread cap · commission 0 |
| HTF / EMA | **Off** (v1 starve mode) |
| Entry | Close-through of prior-N high/low after ATR squeeze + TR expand |
| Fill | Next H1 open |
| Weekend | Flatten Friday last (swap unmodeled) |
| Split | UTC date < 2026-01-01 select; ≥ holdout |

---

## Screen

Best develop (eligible best): `{'family': 'h1_range_vol_breakout', 'range_n': 20, 'squeeze_max': 0.9, 'expand_min': 1.25, 'sl_atr': 2.0, 'tp_rr': 2.0, 'flatten_weekend': True, 'allow_shorts': True}`

| Window | n | WR | PF | Net | DD | Median day |
|--------|--:|---:|---:|----:|---:|-----------:|
| Develop | 293 | 42% | 1.11 | +143.97 | 1.68% | -0.0227% |
| Holdout (from 2026-01-01) | 37 | 43% | 1.17 | +32.10 | 0.60% | -0.0485% |

soft_pass develop = **true** (PF **1.11** — a hair over 1.1; do not round up). Holdout n = **37** (longs 16, shorts 21) — **fails n≥40**, so holdout is **not** a soft pass even though PF 1.17 / NP +32. Median day **−0.023%** develop / **−0.049%** holdout. Not economic.

**1 / 4** develop-eligible configs cleared the soft gate. **0** of the develop-ranked holdouts did. Any-row holdout soft = **1**. Holdout was not used for selection.

---

## Frozen grid (develop rank only; holdout is eval)

| # | N | sq | exp | sl | Dev n | Dev PF | Dev NP | Dev soft | HO n | HO PF | HO NP | HO soft |
|--:|--:|---:|----:|---:|------:|-------:|-------:|:--------:|-----:|------:|------:|:-------:|
| 0 | 20 | 0.75 | 1.25 | 1.5 | 27 | 1.69 | +33.1 | False | 3 | 0.54 | -6.7 | False |
| 1 | 20 | 0.75 | 1.25 | 2.0 | 25 | 2.39 | +67.6 | False | 3 | 0.55 | -8.7 | False |
| 2 | 20 | 0.75 | 1.75 | 1.5 | 19 | 2.40 | +37.5 | False | 3 | 0.54 | -6.7 | False |
| 3 | 20 | 0.75 | 1.75 | 2.0 | 18 | 2.41 | +48.6 | False | 3 | 0.55 | -8.7 | False |
| 4 | 20 | 0.90 | 1.25 | 1.5 | 307 | 0.99 | -10.5 | False | 46 | 1.14 | +26.7 | True |
| 5 | 20 | 0.90 | 1.25 | 2.0 | 293 | 1.11 | +144.0 | True | 37 | 1.17 | +32.1 | False |
| 6 | 20 | 0.90 | 1.75 | 1.5 | 242 | 1.08 | +68.3 | False | 38 | 1.35 | +49.8 | False |
| 7 | 20 | 0.90 | 1.75 | 2.0 | 245 | 0.98 | -17.6 | False | 35 | 1.44 | +68.2 | False |
| 8 | 40 | 0.75 | 1.25 | 1.5 | 13 | 1.28 | +7.5 | False | 2 | 0.00 | -14.6 | False |
| 9 | 40 | 0.75 | 1.25 | 2.0 | 13 | 1.33 | +11.3 | False | 2 | 0.00 | -19.3 | False |
| 10 | 40 | 0.75 | 1.75 | 1.5 | 12 | 1.57 | +12.6 | False | 2 | 0.00 | -14.6 | False |
| 11 | 40 | 0.75 | 1.75 | 2.0 | 12 | 1.64 | +18.0 | False | 2 | 0.00 | -19.3 | False |
| 12 | 40 | 0.90 | 1.25 | 1.5 | 191 | 0.87 | -91.1 | False | 31 | 0.84 | -20.6 | False |
| 13 | 40 | 0.90 | 1.25 | 2.0 | 195 | 0.92 | -78.0 | False | 29 | 0.78 | -34.0 | False |
| 14 | 40 | 0.90 | 1.75 | 1.5 | 155 | 1.07 | +35.0 | False | 25 | 1.09 | +8.6 | False |
| 15 | 40 | 0.90 | 1.75 | 2.0 | 165 | 1.09 | +60.0 | False | 24 | 1.05 | +5.2 | False |

Row 4’s holdout soft is **not selectable** (develop NP −10.5, PF 0.99). DD% on $10k / 0.01 lot is a weak constraint (notional ~$650). Do not pick a new winner from the holdout columns. Do not retune these 16.

**Disposition:** 2026 **did fire** (16/16 holdout n>0) — not v1’s EMA starve. Promote stays **no**: one develop soft passer, that row’s holdout n=37<40, median trade-day still negative, size is not 1%/20%.

---

## What this does **not** authorize

- Do not promote, `--live`, or attach an order EA.
- Do not revive US100, XAU sealed families, Timescale, or M1.
- Do not raise lots to 1.0 or cut slippage to 10 pt to chase 1%/20%.
- Do not retune these 16 configs. A later idea is a **new** `search_id`.
- Do not reopen `btc_h1_trend_pullback_v1` or add an EMA stack.
- Do not edit `results/xau_loop_status.md` from this screen.

