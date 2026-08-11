# Thesis memo — `early_server_range_break_flat` v1

**Date:** 2026-08-10  
**Status:** FREEZE_ONLY — **v2** is the runnable freeze; **no develop grid inspection**; no sealed r1  
**Branch:** `research/xau-early-server-range-break-v1` (from `main` @ PR #1 merge `e99c925`)  
**Charter (runnable):** `results/xau_charters/2026-08-10_early_server_range_break_flat_v2.json`  
**Charter v1:** `…_v1.json` (SHA `fee8611c…`) — **SUPERSEDED** (left byte-for-byte; incomplete execution semantics)

## Standing constraints

- promote=no · live_go=false · PAPER_GO=no · offline only  
- Holdout sealed (`holdout_start=2026-01-01`); selection never uses holdout  
- Dead lines **must not be revived** (rename / filter-on-dead-line forbidden)  
- Closed freezes stay closed (server_hour v2 SCREEN_FAIL, TOD PROTOCOL_NULL_INVALID, prior_day / Donchian / bb_rsi KILL)

## Market mechanism

On XAUUSD H1 **as stamped by the Vantage server clock** in `xauusd_data.csv`, each calendar day has a thin **early server-hour block** (hours **1–8** inclusive) and a more active later block. The thesis is that the early block’s high–low range is a day-local support/resistance object: a **long break of that same-day early range** during later server hours (entry allowed **9–15**) is a continuation of *intraday range expansion after early-session compression*, not a fixed-clock long and not a multi-day channel.

Exit: SL/TP in fixed ATR multiples, or force flat at server hour **≥16** same day (**intraday flat** — no overnight swap).

Hours are **server labels only**. This memo does **not** claim Tokyo/Asia wall-clock identity or London–NY overlap.

## Expected sign

After Standard STP costs (measured spread in CSV; commission 0; slip 0 unmeasured):

- Soft gates (primary for null n_passers): n≥20, PF≥1.1, NP>0 on develop for the single fixed rule  
- If soft passers ≥1: sealed null must show the max-stat (max PF among configs with n≥20) and soft n_passers outside the within-day OHLC-rotate null (p≤0.05 add-one) before any walk-forward is allowed  

Sign under null: if the break edge is only a reordering of within-day path geometry, null trials that preserve open/ref and TR/ref multisets while breaking path association should match or beat the real max-stat → **KILL**.

## Explicit failure modes

1. Early range is noise; false breaks dominate after spread.  
2. Breaks reverse before TP; forced flat at 16 cuts winners.  
3. Edge is pure *hour-of-day long bias* already falsified by `server_hour_window_flat` (fixed entry 13) — this family requires a **range break**, so zero early-range break days produce no trades.  
4. Soft passers = 0 on develop → **SCREEN_FAIL** without null (r1 unburned).  
5. Soft passers ≥1 but null p>0.05 → **KILL_EARLY_SERVER_RANGE_BREAK_FLAT**.

## Why this is not a closed family

| Closed line | Difference |
|-------------|------------|
| `bb_rsi` | Mean-reversion BB reclaim; this is **breakout of same-day early range** |
| Donchian | Multi-day rolling N-bar channel; this range is **within calendar day only**, hours 1–8 |
| `prior_day_high_break` | Prior **calendar day** high; this is **same-day early block** high |
| `tod_london_ny_flat` / `server_hour_window_flat` | Fixed clock long into a window **without** range condition; this **requires** early-range break and allows entries 9–15 |

Not a rename, filter, or hour retune of those lines.

## Execution contract (v2 — frozen house convention)

Not free knobs; implementers must not re-choose:

| Item | Contract |
|------|----------|
| ATR | Wilder via `TR.ewm(alpha=1/14, adjust=False)`; value at signal close `atr[i]` |
| Entry | Signal + fill at **close** of bar `i`; SL/TP from `atr[i]` |
| First exit bar | **`i+1`** (no same-bar exit after close entry) |
| Same-bar exit priority | **Stop before TP before time-flat** |
| Lots | floor to **0.01**, min **0.01**, max **0.5**, risk 1% |
| Costs | Round-trip on entry bar (spread col + 2×slippage + 2×commission) |

Full text: `execution_contract` in the v2 charter JSON.

## Free knobs

**Zero.** All geometry fixed in the charter:

- early_block_hours = [1..8]  
- entry_allowed_hours = [9..15]  
- flat_hour = 16  
- sl_atr = 1.5 · tp_atr = 2.0 · atr_period = 14  
- risk_pct = 0.01 · max_lots = 0.5 · long_only  

Search cardinality = 1.

## Null (session / path-sensitive)

`within_day_ohlc_increment_rotate_v1`, n_trials **999**, k∈{0..m−1} including identity.  
Forbidden: day_block_shuffle, circular_day_shift, global_return_shuffle, bare within_day_return_rotate.

## Data availability (coverage only — no performance)

| Item | Status |
|------|--------|
| `xauusd_data.csv` | Present (~129k rows; H1 + M15) |
| Time span | ~2021-09-03 → 2026-08-07 (UTC-tagged server stamps) |
| Develop rule | `time < 2026-01-01` holdout lock |
| Costs | `results/xau_research_costs.json` Standard STP (commission 0, spread_col) |

No develop PF/NP/DD or passer counts appear in this memo by design (freeze-before-peek).

## Immediate next (out of this freeze commit)

1. Implement `scripts/xau_family_early_server_range_break_flat.py` + synthetic fixture tests only.  
2. Deterministic develop screen under charter (soft primary).  
3. Zero passers → SCREEN_FAIL registry, zero nulls.  
4. ≥1 passer → external review gate, then sealed 999 null only if approved.

## Safety

No paper, live, promote, holdout selection, or sealed cycle until review after screen.  
`KILL_EARLY_SERVER_RANGE_BREAK_FLAT` is a valid scientific close.
