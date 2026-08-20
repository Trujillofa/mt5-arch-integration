# EURUSD NY-Session Scalp — Design Memo

| Field | Value |
|-------|--------|
| **Date** | 2026-08-20 |
| **Status** | Frozen (lock committed before any metric/signal/simulation) |
| **Family set** | `trend_continuation` · `mean_reversion` · `breakout` (user-specified) |
| **Instrument / TF** | EURUSD **M5** (Vantage Standard STP live export) |
| **Session** | 08:00–17:00 ET entries · 16:45 ET force-flat · Friday ≥ 14:00 ET cutoff |
| **promote / live_go** | **no / false** |
| **Lock** | `results/eurusd_ny_scalp_lock.json` |
| **Base** | branch `research/eurusd-ny-scalp` off `main` (`db579e1b`) |

> Offline research only. No `OrderSend`, no `--live`, no EA attach. `src/mt5_arch` untouched. Not the XAU lane: do not touch `results/xau_loop_status.md` or XAU locks from here.

---

## 1. Why this exists

User request: EURUSD scalping restricted to the NY session, seeded with three strategy
descriptions (VWAP+EMA trend continuation, BB+RSI mean reversion, box/volume breakout),
an initial sizing heuristic (6 lots per $10k, TP 0.2% / SL 1%) and goals (1%/session,
max daily loss 3%). The seeds are **inputs to a search, not frozen strategy** — sizing
was rejected by arithmetic (see §6), exits are searched, session/costs are frozen.

Prior evidence says this is hard: all 8 US-index session screens in this repo missed
median trade-day ≥ 1% / trade-month ≥ 20% (v8: 0/32 develop-eligible), and FX
directional TA (naked ORB, trend-pullback) closed near PF 1.0 in
`manual-trading-agent`. FX has **no cash open**; the 09:30 ET index grammar does not
transfer. `SCREEN_FAIL` is a valid, committable outcome — with pre-registered null
calibration it is *demonstrable* rather than drowned in multiplicity.

## 2. Defects this design encodes (provenance)

This plan survived an adversarial review. Every constraint below was a defect a
previous version actually shipped; IDs match the review:

| ID | Defect | Encoded as |
|----|--------|-----------|
| C1 | constant `server_utc_offset_sec` (10800) puts every US-winter bar 1h early in ET | lane-local DST clock: `et = (server − 7h).tz_localize("America/New_York", ambiguous=True, nonexistent="shift_forward")`; verified on this export (17:00 ET spread spike + 08:30 ET volume spike, JAN **and** JUL); never `load_m5_csv`'s offset path |
| C2 | 6 lots / $10k: RT friction 1.32× daily goal; grid SLs 5–22× the −$300 halt | risk-normalized sizing (§6) with per-fill invariant |
| H1 | deps absent on `research/algo-trading-btc-gold-forex` | branched off `main` |
| H2 | `split_by_holdout` defaults 2026-06-01 | holdout read from lock, passed explicitly, asserted ≠ module default |
| H3 | MaxBars=100000 hardcoded; "~375k bars" premise unmeasured | MAXBARS env knob + export-measure-then-freeze (368,302 bars measured) |
| H4 | ~6,000 configs, no multiplicity correction (precedent: 0/32) | grid ≤ 192 + pre-registered 10-seed null calibration (§7) |
| H5 | MT5 OHLC is bid; raw short TP/SL levels are optimistic on both sides | bid-space short fills (§5) |
| M1 | `require_frozen_cost_book` hard-pins 1.0 lot | lane-local `require_eurusd_cost_book(lock)`; neither frozen-book helper imported |
| M2 | goal metric not in imported module; `pack_metrics` already forked 3× | import only `CostSpec`, `Trade`, `metrics_from_trades`, `write_slim_json`; one lane-local equity-path aggregator |
| M3 | export overwrites frozen instrument-data manifests | snapshot → export → copy → restore → byte-diff (done, verified) |
| M4 | `median_daily_pct` divides by static balance | equity-path normalization (`day_pnl / equity_at_day_start`) |
| M5 | intrabar TP/SL precedence unspecified | SL-first, frozen |
| N1 | single frozen lot size makes half the grid unreachable-by-construction | risk-normalized per-trade sizing from each trade's own SL |
| N2 | export count fallback = hours formula on any TF | `PeriodSeconds()` fix; date-range path confirmed anyway (368k bars over 59 mo) |

## 3. Frozen families (signal side — NOT searched)

All three from the user's strategy descriptions; indicator params frozen, only exits
searched. Signals on the **close** of bar `i`, fill at **open** of `i+1`, same ET day.

1. **`trend_continuation`** — VWAP + EMA 9/21. Long: prior bar pulled back to touch
   EMA9 or session VWAP, signal bar closes back above EMA9, EMA9 > EMA21, close >
   VWAP, continuation-bar volume > 1.2 × rolling-20 mean. Short mirror.
   Session VWAP: typical price × tick_volume (floor 1), anchored at first bar ≥ 08:00 ET.
2. **`mean_reversion`** — BB(20, 2) + RSI(7). Long: close pierces lower band **and**
   RSI7 < 30. Short mirror. Family-native TP = middle band.
3. **`breakout`** — 12-bar consolidation box (bars strictly prior to the signal bar),
   close beyond box extreme, volume ≥ 2 × rolling-20 mean, EMA ribbon 8/10/12/15
   strictly ordered. Short mirror.

Warmup periods produce NaN and never signal. One position at a time.

## 4. Causality

- Every indicator value at bar `i` uses bars `≤ i` only (EMA/RSI/ATR imported from
  `us_index_session_core`, which matches MT5 semantics).
- Rolling volume means exclude the signal bar itself.
- Box levels use bars `[i−12, i−1]`, never the signal bar.
- Forming last bar never signals.
- Tests assert: mutating any bar `≥ i+1` never changes signals at `≤ i`.

## 5. Clock, fills, exits

- **Clock**: server wall clock is ET+7h (tracks US DST). ET = (server − 7h)
  localized to America/New_York; `ambiguous=True` / `nonexistent="shift_forward"`
  (ET 01:00–03:00 transition windows fall outside 08:00–17:00 — FX closed).
- **Session**: entries `[08:00, 17:00)` ET; force-flat at first bar open ≥ 16:45 ET
  (measured rollover spread blowout starts 17:00: top-5 mean-spread minutes are
  17:00–17:20, ~38–42 pts vs 12 median); Friday entries stop at 14:00 ET; same-day only.
- **Fills**: next-bar open; spread gate 30 pts at fill bar (skip, don't widen).
- **Shorts are bid-space**: short TP tests `low ≤ TP − spread`, short SL tests
  `high ≥ SL − spread`, fill at the shifted level; longs unadjusted. One spread per
  round trip is charged in P&L — testing/filling at bid-equivalent levels is not a
  double count.
- **Intrabar precedence**: SL-first (pessimistic) when a bar touches both.

## 6. Book, sizing, risk

| Field | Value |
|-------|-------|
| Balance | $10,000, **equity path** (floor `equity > 0` asserted at every fill) |
| Sizing | `lots = floor_to_step(100 / (sl_points × $1.00), 0.01)`, clamped `[0.01, 2.0]` — computed at entry from **that trade's own SL distance** |
| `min_sl_points` | 80 — stops nearer than this **skip** the trade (no resizing into tight stops) |
| `lot_cap` | 2.0 — defensive; at risk 100 / min 80 pts the max is 1.25 lots, so it cannot bind live |
| Point value | $1.00/pt/lot (1e-5 × 100,000) |
| Halt | −$300 (−3%) realized-day → no new entries that ET day |
| Goals | median trade-day ≥ 1% and median trade-month ≥ 20%, **equity-normalized** (`day_pnl / equity_at_day_start`) |

**Floor, never round**: at SL 0.50% raw size is 0.185 → floor 0.18 ($97.20 risk);
rounding to 0.19 would risk $102.60 and breach the per-fill invariant
(`sl_points × lots × 1.00 ≤ risk_per_trade_usd`), asserted at **every** fill.

**risk_per_trade_usd = 100** (= 1% of book = the daily goal): the goal reads as
"median trade-day ≥ +1R" against a −3R halt — three full losses of room. At 300 the
per-trade risk would equal the halt ("one loss and done" for every config). R:R is
size-invariant, so this changes stake geometry, not ranking.

**Rejected seed** ("6 lots per $10k, TP 0.2% / SL 1%"): at 6 lots, round-trip
friction at median spread is $132 = 1.32× the entire daily goal, and the grid SLs
($1,620–$6,480) are 5.4–22× the halt. Honored once as a replay-only sensitivity at
the frozen best config — never ranked, never searched.

Reference shape at risk 100 (friction 22 pts RT, floored lots): only TP 0.3% / SL
0.25% nets > $100 on a single-trade day ($111.74). That is expected (1.2 R:R at 1R
risk), not a bug. If passers concentrate in the `one_per_day=true` half of the grid,
treat it as a red flag to investigate, not a result.

## 7. Multiplicity: pre-registered null calibration

Best-of-192 selection on a median over ~1,080 develop trade-days will produce a
"winner" whether or not edge exists. Before the real run:

- **Null**: within-ET-day **circular phase rotation** of M5 log returns — per ET day,
  one uniform rotation offset (seeded), returns rolled, OHLC rebuilt from the day's
  first open; volumes/spreads/times unchanged. Preserves intraday distribution shape;
  destroys entry-timing edge.
- 10 fixed seeds `[11, 23, 37, 41, 53, 67, 79, 97, 113, 127]`, full 192-config grid
  per seed, develop-only ranking identical to the real run.
- `max_null_best` = max over seeds of the top-ranked config's develop median
  trade-day %.
- **Gate**: the real run's top-ranked develop config must reach
  `median_trade_day_pct ≥ max_null_best + 0.5 × goal` (0.5pp margin).
- Caveat: max-of-10 is an estimate; rotation is circular (not iid shuffle), so it is
  conservative on signal frequency but is not a full block bootstrap.

## 8. Data audit & holdout (frozen 2026-08-20, post-export, pre-metric)

Export `e2604bb0…` (Vantage Standard STP, `VantageMarkets-Live 5`): **368,302** M5
bars, 2021-09-15 → 2026-08-20, sha256 `ebf0bcd9…3fb1b`, 1,541 ET days, median
288 bars/day, spread p50 12 / p99 43 / max 200, 3 zero bars (8.2e-6, imputation rule
in lock). Date-range `CopyRates` ran (N2 fallback did not).

**`holdout_start = 2025-03-01` (ET session-date)**: develop 1,080 days (70.1%) /
holdout 461 days (29.9%) — the ~70/30 target from the measured span. Selection never
touches holdout; holdout scored only after ranking freezes. The instrument-data
lane's server-clock holdout (2026-01-01 server = 2025-12-31 17:00 ET) is a different
lane and unit — do not mix.

## 9. What this is not

- Not a promote path or live authorization; `promote=false`, `live_go=false`.
- Not a retune of the US-index lane; `is_ny_cash` (09:30–16:00) does not apply to FX.
- Not XAU Phase E; do not touch `results/xau_loop_status.md`.
- Not permission to widen the grid, cut costs, move the holdout, or relax the null
  gate to manufacture a passer — a clean `SCREEN_FAIL` is the deliverable.

## 10. Artifacts

| Artifact | Path |
|----------|------|
| Lock | `results/eurusd_ny_scalp_lock.json` |
| Data (gitignored) | `results/eurusd_data/history_EURUSD.csv` + meta + run JSONs |
| Core | `scripts/eurusd_ny_scalp_core.py` |
| Search | `scripts/eurusd_ny_scalp_autoresearch.py` |
| Tests | `tests/test_eurusd_ny_scalp.py` |
| Result (slim, committed) | `results/eurusd_ny_scalp_autoresearch.json` + `.md` |
| Result (fat, gitignored) | `results/eurusd_ny_scalp_*_full.json` |
