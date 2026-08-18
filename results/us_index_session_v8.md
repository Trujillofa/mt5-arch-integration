# US100 v8 screen (`us_index_session_v8`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Search** | `us_index_session_v8` — H1 squeeze-breakout + H4 impulse fib pullback |
| **Lock** | `results/us_index_session_v8_lock.json` |
| **Select** | `et_date < 2026-06-01` |
| **Holdout** | **2026-07-01** onward. June unused (burned). July–August already sat inside the v4–v7 holdout aggregates — cleaner window, **not virgin**. |
| **Book** | $10,000 / 1 lot. Slippage **kept** at 10 pt/side. |
| **Grid** | 32 configs (16 squeeze + 16 fib; 0.28 s) |
| **Goals** | median trade-day ≥ **1%**, median month ≥ **20%** |
| **Hits** | develop **0 / 0** eligible · top-20 holdout **0 / 0** |
| **Eligible by family** | `h1_volatility_squeeze_breakout` **0** · `h4_impulse_fib_pullback` **0** |
| **promote / live_go** | **no / false** |
| **Data** | FP native `H1.hc` / `H4.hc` / `Daily.hc` via `read_mt5_hc` (4828 / 1266 / 212 bars). Not the M5 `export_us_index.request` dump. Live terminal not touched. |

Machine JSON: `results/us_index_session_v8.json`.

Leave M5 scalping. Hunt H1/H4 structural swings. Not a retune of v1–v7. Not an XAU charter. These families stay **Python-only**.

---

## Frozen before any develop metric

| Choice | Lock |
|--------|------|
| Grid | 32 configs locked before peek (16 + 16). Do not wait for a larger grid. |
| Squeeze | BB entirely inside KC on **completed** H1. Wait while squeezed; trade only on release. |
| Donchian | Channel from `i-20..i-1`. Trigger is `close[i]` vs that. Never same-bar high. |
| Daily SMA50 | Completed Daily only (today's D1 is forming). Rising → longs; falling → shorts; flat/NaN → no trade. No SMA200. |
| Pivots / fibs | `htf_fib_core.confirmed_pivots` + `walk_swing_and_fibs` (not re-derived). Pocket 61.8–78.6. |
| Impulse | Unidirectional H4 closes from origin center through extreme center; range > k×ATR14 at confirm. |
| Fill | Next H1 open. No H1 signal until that H1's close ≥ H4 confirm close (H4 open + 4h). |
| Friday | No new weekend gap (Friday last H1). Optional flatten at that open. |
| Book | $10k / 1 lot / 10 pt slip/side / spread cap 200 / commission 0. |

---

## What this is not

| Kept | Rejected |
|------|----------|
| Native FP `H1.hc` / `H4.hc` / `Daily.hc` | M5 request-file dump / `ExportInstrumentHistory` / tester EA |
| `htf_fib_core` pivots (confirm = center + right) | Re-derived pivots / ForexHtfPivotsFib on the live book |
| Thin multi-day H1 walk + locked CostSpec | `simulate_exits` same-ET-day flatten |
| split_v4 (June burned; July–August cleaner, not virgin) | M5 families, M1, US30, XAU, news-drift, Timescale |

---

## Goals missed

**0 / 32** configs are develop-eligible (`net>0` and `trades>=40`). **0** hit both 1% and 20%. There is no promote path.

Best raw develop (not eligible — 6 trades): H1 squeeze, BB k=2.0, KC 1.5, one/day, hold the weekend:

| Window | n | WR | PF | Median day | Median month |
|--------|--:|---:|---:|-----------:|-------------:|
| Develop | 6 | 33% | 1.20 | **−1.09%** | **+0.16%** |
| Holdout (from 2026-07-01) | 2 | 0% | 0.00 | **−1.19%** | **−2.39%** |

Net is slightly positive in-sample because two winners were large. The **median** trade-day is −1.09%. Holdout is two full losers. A 100 pt swing on this book is ~$100 = 1% — that did not show up as a median day after the locked 20-pt round-trip.

| Family | Eligible | Best develop | Holdout |
|--------|----------|--------------|---------|
| h1_volatility_squeeze_breakout | **0 / 16** | 6 trades · PF 1.20 · **−1.09%** day · +$94 | 2 trades · PF 0.00 · **−1.19%** day |
| h4_impulse_fib_pullback | **0 / 16** | 20 trades · PF 0.51 · **−1.74%** day · −$1,518 | 2 trades · PF 0.36 · **−1.04%** day |

Squeeze is starved (Daily SMA50 + release + Donchian close-break). Fib pullbacks fire more and lose money after costs. The unidirectional H4 + golden-pocket story does not pay on this book.

---

## What this does **not** authorize

- Do not promote, `--live`, or attach an order EA.
- Do not put v8 on the overlay.
- Do not revive M5 families, US30, XAU, news-drift, Timescale, or M1.
- Do not cut slippage or raise lots.
- Do not retune these 32 configs. A later idea is a **new** `search_id` with a new freeze-before-peek.
