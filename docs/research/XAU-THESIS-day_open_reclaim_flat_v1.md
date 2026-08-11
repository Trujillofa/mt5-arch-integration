# Thesis memo — `day_open_reclaim_flat` v1

**Date:** 2026-08-11  
**Status:** FREEZE_ONLY — immutable charter frozen; **no implementation**; **no develop grid inspection**; no sealed r1  
**Branch / worktree:** `research/xau-day-open-reclaim-flat-v1` from `origin/main` @ `f4e891f` (PR #2 merge)  
**Charter:** `results/xau_charters/2026-08-11_day_open_reclaim_flat_v1.json`

## Standing constraints

- promote=no · live_go=false · PAPER_GO=no · offline only  
- Holdout sealed (`holdout_start=2026-01-01`); never used for selection  
- Dead lines **must not be revived** (rename / filter-on-dead-line forbidden)  
- Closed freezes stay closed (TOD, server_hour, early_server_range_break, prior_day, Donchian, bb_rsi)

## Market mechanism

On XAUUSD H1 **as stamped by the Vantage server clock** in `xauusd_data.csv`, each calendar day has a **day open** defined as the **open of the first printed H1 bar of that calendar day**.

Thesis: after price **undercuts** that day open (any same-day bar’s **low &lt; day_open**), a **reclaim** — first later bar in server hours **9–15** whose **close &gt; day_open** while flat — is a long signal that the day-open is acting as recovered support after an early dip. Exit with fixed ATR SL/TP or force flat at server hour **≥16** (intraday flat; no overnight).

Hours are **server labels only**. No London–NY or Tokyo wall-clock claim.

## Expected sign

After Standard STP costs (measured spread in CSV; commission 0; slip 0 unmeasured):

- Soft primary (charter): n≥20, PF≥1.1, NP&gt;0 on the **single** fixed config on develop  
- Soft passers = 0 → **SCREEN_FAIL**, nulls not run, r1 unburned  
- Soft passers ≥1 → external review before any 999-trial null; only then max-stat significance under within-day OHLC-rotate null  

## Explicit failure modes

1. Day-open reclaim is noise after costs; most reclaims reverse before TP.  
2. Many days never undercut the open → few trades; soft n&lt;20 fails gates.  
3. Edge is pure fixed-clock long bias already falsified by `server_hour_window_flat` / `early_server_range_break_flat` geometries — this rule **requires** a prior same-day undercut of the open, not a range-high break and not a blind hour long.  
4. Soft passers ≥1 but null p&gt;0.05 → **KILL_DAY_OPEN_RECLAIM_FLAT**.

## Why this is not a closed family

| Closed line | Difference |
|-------------|------------|
| `bb_rsi` | Band/RSI mean-reversion; this is **day-open reclaim after undercut**, no BB/RSI |
| Donchian | Multi-day N-bar channel; this is **same-day open** only |
| `prior_day_high_break` | Prior **calendar day high**; this is **today’s open** |
| `tod_london_ny_flat` / `server_hour_window_flat` | Fixed clock long **without** undercut/reclaim condition |
| `early_server_range_break_flat` | Break of **early-block high (hours 1–8)**; this reclaims **day open** after a **low &lt; open** dip, not a range-high breakout |

Not a rename, hour retune, or filter on those lines.

## Free knobs

**Zero.** All geometry fixed in the charter:

- day_open = open of first bar of calendar day  
- undercut: any same-day low &lt; day_open  
- entry_allowed_hours_server = [9..15]  
- flat_hour_server = 16  
- sl_atr = 1.5 · tp_atr = 2.0 · atr_period = 14 (Wilder)  
- risk_pct = 0.01 · max_lots = 0.5 · long_only · one_entry_per_day  

Search cardinality = 1.

## Execution contract (frozen at freeze — implementers must not re-choose)

| Item | Contract |
|------|----------|
| ATR | Wilder via `TR.ewm(alpha=1/14, adjust=False)`; use `atr[i]` at signal close |
| Entry | Signal + fill at **close** of bar `i` when reclaim true |
| First exit bar | **`i+1`** (no same-bar exit after close entry) |
| Same-bar exit priority | **Stop before TP before time-flat** |
| Lots | floor to **0.01**, min **0.01**, max **0.5**, risk 1% |
| Costs | RT on entry bar: `(spread + 2×slip)×point×CONTRACT×lots + 2×commission×lots` |
| No overnight | Enter only if the calendar day has a bar with hour≥16; day-boundary open pos fail-closed (no next-day SL/TP) |

Full text: `execution_contract` in the charter JSON.

## Null (session / path-sensitive)

`within_day_ohlc_increment_rotate_v1`, n_trials **999**, k∈{0..m−1} including identity.  
Forbidden: day_block_shuffle, circular_day_shift, global_return_shuffle, bare within_day_return_rotate.

## Data availability (coverage only — no performance)

| Item | Status |
|------|--------|
| `xauusd_data.csv` | Present (~129k rows; H1 + M15) |
| Time span | ~2021-09-03 → 2026-08-07 (server stamps) |
| Develop rule | `time < 2026-01-01` holdout lock |
| Costs | `results/xau_research_costs.json` Standard STP |

No develop PF/NP/DD or passer counts appear in this memo (freeze-before-peek).

## Immediate next (after adversarial review of this freeze)

1. Implement `scripts/xau_family_day_open_reclaim_flat.py` + synthetic fixtures only.  
2. `--screen-only` develop screen under v1 charter.  
3. Zero soft passers → SCREEN_FAIL registry, zero nulls.  
4. ≥1 soft passer → external review → sealed 999 only if approved.

## Safety

No paper, live, promote, holdout selection, implement, or sealed cycle until freeze review passes.  
`KILL_DAY_OPEN_RECLAIM_FLAT` is a valid scientific close.
