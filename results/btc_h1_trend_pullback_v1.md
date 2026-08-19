# BTC H1 trend-pullback screen (`btc_h1_trend_pullback_v1`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-19 |
| **Search** | `btc_h1_trend_pullback_v1` — H4 EMA stack + H1 reclaim |
| **Lock** | `results/btc_h1_trend_pullback_v1_lock.json` |
| **Select** | `signal_utc_date < 2026-01-01` |
| **Holdout** | **2026-01-01** onward. Never used for selection. |
| **Book** | $10,000 / **0.01 lot** / **250 pt** slip/side / point 0.01 / contract 1 |
| **Grid** | 16 configs (3.17 s) |
| **Soft gate** | n≥40, NP>0, PF≥1.1, DD≤25% (develop). 1%/20% is **not** a gate. |
| **Hits** | develop eligible **8** · soft **5** · top-20 holdout soft **0** |
| **promote / live_go** | **no / false** |
| **Data** | FP native `H1.hc` / `H4.hc` via `read_mt5_hc`. Live terminal not touched. |

Machine JSON: `results/btc_h1_trend_pullback_v1.json`.
Pivot grill: `results/next_search_pivot.md`.

---

## Frozen before any develop metric

| Choice | Lock |
|--------|------|
| Book | 0.01 lot · 250 pt slip · 4000 pt spread cap · commission 0 |
| HTF | Native completed H4 (open+4h ≤ H1 open) |
| Entry | Closed H1 reclaim / optional continuation; edge-trigger |
| Fill | Next H1 open |
| Weekend | Flatten Friday last (swap unmodeled) |
| Split | UTC date < 2026-01-01 select; ≥ holdout |

---

## Screen

Best develop (eligible best): `{'family': 'h1_htf_ema_pullback', 'allow_continuation': True, 'allow_shorts': False, 'max_pullback_pct': 0.01, 'sl_atr': 1.5, 'tp_rr': 2.0, 'flatten_weekend': True}`

| Window | n | WR | PF | Net | DD | Median day |
|--------|--:|---:|---:|----:|---:|-----------:|
| Develop | 56 | 45% | 1.32 | +115.11 | 0.62% | -0.0202% |
| Holdout (from 2026-01-01) | 0 | 0% | 0.00 | +0.00 | 0.00% | +0.0000% |

soft_pass develop = **true**. Median day % is diagnostic only — not a 1% gate.

**5 / 8** develop-eligible configs cleared the soft gate. **0** of the develop-ranked holdouts did. Any-row holdout soft = **0**. Holdout was not used for selection.

---

## Frozen grid (develop rank only; holdout is eval)

| # | cont | shorts | pb | sl | Dev n | Dev PF | Dev NP | Dev soft | HO n | HO PF | HO NP | HO soft |
|--:|:----:|:------:|---:|---:|------:|-------:|-------:|:--------:|-----:|------:|------:|:-------:|
| 0 | True | True | 0.010 | 1.5 | 162 | 1.16 | +141.5 | True | 25 | 0.83 | -35.7 | False |
| 1 | True | True | 0.010 | 2.0 | 144 | 0.97 | -35.9 | False | 18 | 1.09 | +16.7 | False |
| 2 | True | True | 0.015 | 1.5 | 169 | 1.06 | +58.3 | False | 25 | 0.83 | -35.7 | False |
| 3 | True | True | 0.015 | 2.0 | 150 | 0.98 | -24.3 | False | 18 | 1.09 | +16.7 | False |
| 4 | True | False | 0.010 | 1.5 | 56 | 1.32 | +115.1 | True | 0 | 0.00 | +0.0 | False |
| 5 | True | False | 0.010 | 2.0 | 53 | 1.21 | +90.2 | True | 0 | 0.00 | +0.0 | False |
| 6 | True | False | 0.015 | 1.5 | 58 | 1.24 | +91.6 | True | 0 | 0.00 | +0.0 | False |
| 7 | True | False | 0.015 | 2.0 | 54 | 1.18 | +78.5 | True | 0 | 0.00 | +0.0 | False |
| 8 | False | True | 0.010 | 1.5 | 54 | 1.09 | +32.2 | False | 7 | 1.09 | +4.3 | False |
| 9 | False | True | 0.010 | 2.0 | 49 | 1.05 | +18.3 | False | 6 | 1.48 | +22.3 | False |
| 10 | False | True | 0.015 | 1.5 | 77 | 0.91 | -44.2 | False | 10 | 0.62 | -32.1 | False |
| 11 | False | True | 0.015 | 2.0 | 71 | 0.88 | -66.3 | False | 8 | 0.84 | -13.4 | False |
| 12 | False | False | 0.010 | 1.5 | 23 | 1.15 | +29.3 | False | 0 | 0.00 | +0.0 | False |
| 13 | False | False | 0.010 | 2.0 | 22 | 1.10 | +21.7 | False | 0 | 0.00 | +0.0 | False |
| 14 | False | False | 0.015 | 1.5 | 31 | 1.02 | +5.1 | False | 0 | 0.00 | +0.0 | False |
| 15 | False | False | 0.015 | 2.0 | 29 | 1.02 | +6.3 | False | 0 | 0.00 | +0.0 | False |

Long-only rows printed **0 holdout signals** in 2026 (not a date bug; 3928 H1 bars exist after 2026-01-01). That is a 2021–25 bull-stack starve. DD% on $10k / 0.01 lot is a weak constraint (notional ~$650). Median trade-day on the develop winner is **negative**. Do not pick a new winner from the holdout columns.

---

## What this does **not** authorize

- Do not promote, `--live`, or attach an order EA.
- Do not revive US100, XAU sealed families, Timescale, or M1.
- Do not raise lots to 1.0 or cut slippage to 10 pt to chase 1%/20%.
- Do not retune these 16 configs. A later idea is a **new** `search_id`.
- Do not edit `results/xau_loop_status.md` from this screen.

