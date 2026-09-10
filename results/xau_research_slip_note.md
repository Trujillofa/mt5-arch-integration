# XAU research slip — measurement attempt

| Field | Value |
|-------|--------|
| Date | 2026-09-09 |
| Status | **GAP — not measured** |
| Official book | `results/xau_research_costs.json` **slippage_points=0 UNMEASURED** (unchanged) |

Hunted existing deal dumps (read-only) in
`mt5-arch-integration/results/live_book_2026-08-15_2026-09-04`.

| Book | XAU deals | Est. round-trips | Requested price? | Bid/ask at send? |
|------|----------:|-----------------:|:----------------:|:-----------------:|
| FP `XAUUSD.r` (`fp_deals_live.json`) | 24 | 12 | no | no |
| Vantage `XAUUSD` (`vantage_deals.json`) | 22 | 11 | no | no |

Fills have deal price / volume / profit. FP also has commission on some XAU rows.
There is **no** requested price and **no** quote snapshot, so slip in MT5 points
cannot be computed without inventing a mid.

`xau_research_costs.json` was **not** rewritten. The regime official book uses
slip 0 UNMEASURED. This is bookkeeping, not a signal.


---

## Sibling-repo hunt (2026-09-09, read-only)

Hunt of `/home/yderf/Projects/trading` + `.worktrees/` for leftover macro and
tick/slip tracks. No download. No live orders. Official costs unchanged.

### Tick / L1 that actually exists

| Artifact | What it is | XAU? | Overlap live_book fills? |
|----------|------------|:----:|:------------------------:|
| `mt5-arch-integration/results/tick_data/ticks_XAUUSD.r_fpmarkets.csv` (47M, gitignored) | FP `copyticks_csv` L1 bid/ask, n=489 634, **2026-08-18 13:02 → 2026-08-20 01:01 UTC** (~36h) | yes | **no** — FP/Vantage XAU deals start 2026-08-24 |
| Same dir `ticks_BTCUSD_fpmarkets.csv` / `ticks_US100_fpmarkets.csv` | L1, not gold | no | n/a |
| cTrader `data/dukascopy/xauusd_h1_*.csv` (~34M tree) | **H1 OHLC only** (2022-01 → 2026-03). Fetcher *reads* `h_ticks.bi5` then writes bars. **No persisted XAU ticks.** | bars | no |
| `fetch_data.py` Dukascopy fallback | same H1 bars; can synthesize M15 (not ticks) | bars | no |
| file_bridge `Deal` / live_book dumps | fill `price` + (FP) commission; **no requested / bid / ask** | fills | already known GAP |
| Seven Desk | paper adapter computes `slippagePips`; **live WSF path does not persist bid/ask-before-send vs fill** | — | no journal |
| cTrader `paper_pnl_synced.jsonl` | 3 XAUUSD rows; modeled entry/exit; **no `filled_exit_price`** | paper | no |
| OANDA / `mt5.copy_ticks_range` / raw `.bi5` | **no stored dumps** in sibling repos | — | — |

`copyticks_csv` is not a tracked script in-repo (one-off dump). Worktree has **no** `results/tick_data/`.

### Macro leftover (not a new gold host)

Already used: FRED DFII10 + DTWEXBGS (killed β); crypto-agent daily DXY/US10Y/VIX (killed β); XAU H1.

On disk unused: FRED DGS10 / T10YIE / DFII5; tradfi **H1** DXY/10Y/VIX + daily QQQ `equity_risk`; NFP/CPI/FOMC calendar + surprises. Combining those with killed overlays is not an independent costed host.

### Verdict

Sibling **artifact hunt is exhausted**. True request→fill slip still **GAP**.
36h L1 is quoted spread, not fill slip, and does not cover the deal sample.
Do not invent slip from half-spread. Do not retune killed families.
Measuring slip later would make H1 PF *more* conservative; it does not flip
regime/β vs always-long.


## Tool check — ismailfer/dukascopy-api-websocket (2026-09-09)

Inspected at `/tmp/dukascopy-api-websocket` (not vendored, not under trading root).
Java Spring Boot **JForex SDK proxy**. Last commit 2022-08-15.

- Auth: Dukascopy **demo/live username + password** (not a FreeServ key).
- REST `/api/v1/history`: **bars only** (1SEC…DAILY). No `timeFrame=tick`. Calls `getBars`.
- WebSocket `/ticker`: **live** top-of-book / 10-level book. Default instruments have **no XAU**.
- Also exposes **order placement**. Do not stand this up.

**Do not use for the 16-day XAU L1 slip job.** If that job ever runs: keep ticks from
existing `ctrader-trading-agent/scripts/backtest/fetch_dukascopy.py` `.bi5` (bid+ask
already unpacked; currently discarded into M1). No JForex login, no FreeServ key.
Still label fill-vs-quote. Do not rewrite `xau_research_costs.json`.


## Bounded Dukascopy `.bi5` audit (2026-09-09)

Public datafeed `XAUUSD` hour files, ticks **kept**. No JForex, no ismailfer
websocket, no FreeServ. Official `xau_research_costs.json` **unchanged**
(slip 0 UNMEASURED).

| Field | Value |
|-------|--------|
| Window UTC | 2026-08-18 00:00 → 2026-09-02 23:59 |
| Hours | 384 requested · 276 ok · 107 empty (weekends) · 1 fail (2026-08-28 15h) |
| Ticks | **3 270 463** |
| Store | `results/xau_slip_ticks/xauusd_ticks_2026-08-18_2026-09-02.csv.gz` (26M, gitignored) |
| Method | `merge_asof` backward; last tick ≤ fill UTC; max age 2s |
| Clock | live_book trade-server **UTC+3** → UTC |
| Label | **fill-vs-quote** (Dukascopy L1 vs FP/Vantage fill). **Not** request→fill |

| Book | n usable | median pt | mean pt | $ / 0.10 lot (median) | $ / 1.00 lot (median) |
|------|--------:|----------:|--------:|----------------------:|----------------------:|
| All | 45 | **−19.5** | −6.1 | −1.95 | −19.50 |
| FP `XAUUSD.r` | 24 | −24.5 | −10.7 | −2.45 | −24.50 |
| Vantage `XAUUSD` | 21 | −15.5 | −1.0 | −1.55 | −15.50 |

1 deal rejected (tick older than 2s). n≥5 so a number is recorded in
`xau_research_slip.json` as `measured_slippage_points` (−19.5) with
`usable_as_cost_assumption=false`.

Negative median means fills were **better** than Dukascopy touch on this
sample (cross-venue basis), not that trading is free. **Do not** write −19.5
into the cost book — that would gift H1 PF. Right tail reaches +367 pt.
Too few RTs / wrong venue to replace slip 0 UNMEASURED.

Does **not** revive overlays or always-long. Slip-0 H1 PF stays optimistic
as a research cost stance; this sample does not justify a new friction number.
