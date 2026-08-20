# EURUSD NY-session scalp develop screen (`eurusd_ny_scalp_develop_v1`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-20 |
| **Search** | `eurusd_ny_scalp_develop_v1` (new lane, not a retune) |
| **Lock** | `results/eurusd_ny_scalp_lock.json` (frozen before any metric) |
| **Holdout** | **2025-03-01** ET session-date — never used for selection (develop 1,080 d / holdout 461 d) |
| **Book** | $10,000 equity path, risk-normalized $100/trade, lot floor-to-step 0.01, min_sl 80 skip, lot_cap 2.0 defensive |
| **Costs** | measured spread + 5 pt slippage/side (assumption), commission 0, gate 30 pt |
| **Data** | Vantage Standard STP M5 export, 368,302 bars (2021-09-15 → 2026-08-20), sha256 `ebf0bcd9…3fb1b` |
| **Grid** | 192 configs = 3 families × 32 exits × one_per_day (195 s including 10-seed null) |
| **Goals** | median trade-day ≥ **1%**, median month ≥ **20%**, equity-normalized |
| **Null** | 10-seed within-ET-day phase rotation; `max_null_best` = **0.075%/day** |
| **Gate** | develop winner must clear `max_null_best + 0.5pp` — **no winner to gate** |
| **Hits** | develop **0 / 192** eligible · **0** hit either goal |
| **promote / live_go** | **no / false** |

Machine JSON: `results/eurusd_ny_scalp_autoresearch.json`. Full trade dump stays local (`*_full.json`, gitignored).

---

## What was searched

Three user-specified families with **frozen** signal params, **searched** exits:

| Family | Frozen signal |
|--------|----------------|
| `trend_continuation` | EMA 9/21 + session VWAP pullback, volume > 1.2× rolling-20 |
| `mean_reversion` | BB(20,2) pierce AND RSI(7) <30 / >70 |
| `breakout` | 12-bar box break, volume ≥ 2× rolling-20, EMA 8/10/12/15 fan |

32 exits: 15 pct TP×SL, 6 ATR, 3 structure-TP, 2 bars time-stop, 6 flatten-at-11:30/14:00 × SL. All force-flat 16:45 ET. Session `[08:00, 17:00)` ET, Friday ≥ 14:00 blocked. Bid-space shorts, SL-first, −$300 day halt.

Eligible = develop net > 0 **and** ≥ 40 trades. Rank = profit factor (None pinned to 3.0) then expectancy. Holdout scored only after ranking froze.

---

## SCREEN_FAIL

**0 of 192** configs are develop-eligible. **0** have `net_pnl > 0`. The gate never fires because there is no develop winner to compare to `max_null_best`.

| Bucket | n |
|--------|--:|
| Grid | 192 |
| Bankrupt (equity ≤ 0 mid-run) | 44 |
| ≥ 40 develop trades | 148 |
| net_pnl > 0 | **0** |
| hit 1%/day and 20%/month | **0** |

Surviving (non-bankrupt) develop P&L: median **−$2,312**, worst **−$8,642** on a $10k book. Trade counts are not the problem (median 502 develop trades; max 3,238) — the edge is.

By family (64 configs each):

| Family | Median trades | Median net | Max net |
|--------|-------------:|-----------:|--------:|
| trend_continuation | 613 | −$3,097 | $0 (bankrupt empty) |
| mean_reversion | 896 | −$2,181 | $0 |
| breakout | 464 | −$2,045 | $0 |

This is not a sizing problem to paper over. Risk is already $100/trade (1R = the daily goal) against a −3R halt. Larger lots would scale both P&L and drawdown; they would not invent a positive expectancy from a uniformly negative book. The rejected 6-lot seed is **not** replayed — there is no frozen best config to replay it against.

---

## Null calibration (ran first)

Within-ET-day circular phase rotation of M5 log returns, 10 locked seeds, full 192-config grid per seed, develop-only ranking identical to the real run.

| Seed | Eligible | Best develop median day |
|-----:|---------:|------------------------:|
| 11 | 32 | 0.071% |
| 23 | 77 | 0.023% |
| 37 | 36 | 0.032% |
| 41 | 48 | 0.072% |
| 53 | 46 | **0.075%** |
| 67 | 46 | 0.030% |
| 79 | 75 | 0.074% |
| 97 | 48 | 0.030% |
| 113 | 56 | 0.032% |
| 127 | 37 | 0.023% |

`max_null_best` = **0.075%/day**. Even best-of-192 selection on *phase-randomized* returns never reaches 0.08%/day — 13× short of the 1% goal, and the +0.5pp gate threshold would have been 0.57% anyway. The real book producing 0 eligible configs is therefore **not** an artefact of a too-lenient gate: noise itself cannot print the goal on this book, and the real families print worse than noise (uniformly negative).

Caveat (from the lock): max-of-10 is an estimate; rotation is circular (not iid shuffle), so it is conservative on signal frequency but is not a full block bootstrap.

---

## What this does **not** authorize

- Do **not** promote, `--live`, or attach an order EA.
- Do **not** widen the grid, cut costs, move the holdout, or relax the null gate to manufacture a passer.
- Do **not** revive the rejected 6-lot / TP 0.2% / SL 1% seed as a search.
- A different family, if ever wanted, is a **new** `search_id` with a new freeze-before-peek — not another pass on this CSV.

`SCREEN_FAIL` is the deliverable. `promote=false`. `live_go=false`.
