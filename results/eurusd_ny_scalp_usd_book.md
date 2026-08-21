# EURUSD NY-scalp specified book (`eurusd_ny_scalp_usd_book_v1`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-20 |
| **Search** | `eurusd_ny_scalp_usd_book_v1` — **not** a retune of the 192-config v1 screen |
| **Lock** | `results/eurusd_ny_scalp_usd_book_lock.json` (frozen before this run) |
| **Book** | $10,000 · **3.0 lots fixed** · TP **$20** · SL **$100** · halt **−$300** |
| **In points** | TP 6.67 pt (0.67 pip) · SL 33.3 pt (3.3 pip) · 3 lots × $1/pt |
| **Friction** | 22 pt × $3 = **$66** round-trip vs **$20** target |
| **Holdout** | 2025-03-01 ET — never reached (account dead in develop) |
| **Grid** | 6 = 3 frozen families × one_per_day |
| **Null** | 10 seeds, **0 eligible** on every seed |
| **Hits** | **0 / 6** eligible · TP fires often, every fill still nets negative |
| **promote / live_go** | **no / false** |

---

## What this is

The user's clarified geometry: TP 0.2% and SL 1% of a **$10k account** ($20 / $100), 3 lots instead of 6, max daily loss $300. Same EURUSD M5 dump, same session, same three families as v1. One exit. Not a search.

Arithmetic that was true before the run, and the run confirmed (regenerated
on `mean_reversion` / one_per_day=false, 141 develop trades):

- Median spread on this sample is **12 points**; TP at 3 lots is **6.7 points**.
- The target is reached often — **89 of 141 develop trades (63%) exit at the
  take-profit.**
- It does not matter: average TP gross is **+$32.91** against **$62.76** of
  cost, so every filled take-profit still nets **−$29.85**.
- Decomposed across all 141 trades: gross **−$8.42**/trade, friction
  **−$62.96**/trade. **88.2% of the loss is cost.**
  (Nominal 22 pt × $3 = $66; realized cost is a shade lower because some
  fills occur on tighter-than-median spreads.)

---

## SCREEN_FAIL

| Family | one/day | Trades | WR | PF | Net | Avg trade | Halt days |
|--------|---------|-------:|---:|---:|----:|----------:|----------:|
| trend_continuation | no | 122 | **0%** | 0 | −$10,101 | −$83 | 23 |
| mean_reversion | no | 141 | **0%** | 0 | −$10,064 | −$71 | 23 |
| breakout | no | 113 | **0%** | 0 | −$10,002 | −$89 | 4 |
| trend_continuation | yes | 118 | **0%** | 0 | −$10,015 | −$85 | 0 |
| mean_reversion | yes | 126 | **0%** | 0 | −$10,056 | −$80 | 0 |
| breakout | yes | 103 | **0%** | 0 | −$10,048 | −$98 | 0 |

Every config blows the $10k book in develop (~100–140 trades). **Take-profits fire on 63% of trades and still lose $29.85 each.** Holdout is empty because there is no account left. Null calibration also prints 0 eligible on all 10 seeds — even randomized returns cannot make a 6.7-point target pay for 22 points of friction.

6 lots would have been worse (TP 3.3 points). 3 lots does not save it.

---

## What this does **not** authorize

- Do **not** promote, `--live`, or attach an order EA.
- Do **not** treat this as a reason to retune v1.
- Do **not** cut spread, drop slippage, or shrink the TP further to manufacture a passer.

`SCREEN_FAIL`. `promote=false`. `live_go=false`.
