# Thesis memo — `day_open_reclaim_flat` v2

**Date:** 2026-08-11  
**Status:** FREEZE_ONLY — immutable charter frozen; **no implementation**; **no develop grid inspection**; no sealed r1  
**Branch / worktree:** `research/xau-day-open-reclaim-flat-v1` from `origin/main` @ `f4e891f` (PR #2 merge)  
**Charter:** `results/xau_charters/2026-08-11_day_open_reclaim_flat_v2.json`  
**Supersedes:** v1 SHA `8eafe48b…` (byte-immutable; registry **SUPERSEDED**)

## Standing constraints

- promote=no · live_go=false · PAPER_GO=no · offline only  
- Holdout sealed (`holdout_start=2026-01-01`); never used for selection  
- Dead lines **must not be revived** (rename / filter-on-dead-line forbidden)  
- Closed freezes stay closed (TOD, server_hour, early_server_range_break, prior_day, Donchian, bb_rsi)

## Why v2 (adversarial freeze review BLOCK on v1)

| Finding | v2 freeze |
|---------|-----------|
| Undercut/reclaim same-bar ambiguity | `undercut_seen_before_i = any(low[j] < day_open for j < i)`; same-bar undercut+reclaim **rejected** |
| Capital / cost accounting incomplete | `start_balance=10000`, realized-balance compounding, equity formulas, cost **measured at entry / deducted at exit booking** |
| `null.base_seed` not frozen | `null.base_seed=20260808`; strict harness rejects CLI divergence; sealed wrapper passes seed |
| Freeze SHA test weak | Tests pin exact v2 SHA bytes |

## Market mechanism

On XAUUSD H1 **as stamped by the Vantage server clock** in `xauusd_data.csv`, each calendar day has a **day open** defined as the **open of the first printed H1 bar of that calendar day**.

Thesis: after price **undercuts** that day open on a **prior** same-day bar (`undercut_seen_before_i`), a **reclaim** — first bar `i` in server hours **9–15** whose **close > day_open** while flat — is a long signal that the day-open is acting as recovered support after an earlier dip. Exit with fixed ATR SL/TP or force flat at server hour **≥16** (intraday flat; no overnight).

**Ordering (frozen):** undercut state for bar `i` uses only bars `j < i`. A 09:00 bar with `low < day_open` and `close > day_open` does **not** trade unless some earlier same-day bar already undercut.

Hours are **server labels only**. No London–NY or Tokyo wall-clock claim.

## Expected sign

After Standard STP costs (measured spread in CSV; commission 0; slip 0 unmeasured):

- Soft primary (charter): n≥20, PF≥1.1, NP>0 on the **single** fixed config on develop  
- Soft passers = 0 → **SCREEN_FAIL**, nulls not run, r1 unburned  
- Soft passers ≥1 → external review before any 999-trial null; only then max-stat significance under within-day OHLC-rotate null with **base_seed=20260808**

## Explicit failure modes

1. Day-open reclaim is noise after costs; most reclaims reverse before TP.  
2. Many days never undercut the open on a prior bar → few trades; soft n<20 fails gates.  
3. Edge is pure fixed-clock long bias already falsified by `server_hour_window_flat` / `early_server_range_break_flat` geometries — this rule **requires** a prior same-day undercut of the open, not a range-high break and not a blind hour long.  
4. Soft passers ≥1 but null p>0.05 → **KILL_DAY_OPEN_RECLAIM_FLAT**.

## Why this is not a closed family

| Closed line | Difference |
|-------------|------------|
| `bb_rsi` | Band/RSI mean-reversion; this is **day-open reclaim after undercut**, no BB/RSI |
| Donchian | Multi-day N-bar channel; this is **same-day open** only |
| `prior_day_high_break` | Prior **calendar day high**; this is **today’s open** |
| `tod_london_ny_flat` / `server_hour_window_flat` | Fixed clock long **without** undercut/reclaim condition |
| `early_server_range_break_flat` | Break of **early-block high (hours 1–8)**; this reclaims **day open** after a **low < open** dip, not a range-high breakout |

Not a rename, hour retune, or filter on those lines.

## Free knobs

**Zero.** All geometry fixed in the charter:

- day_open = open of first bar of calendar day  
- undercut_seen_before_i: any prior same-day low < day_open (`j < i`)  
- entry_allowed_hours_server = [9..15]  
- flat_hour_server = 16  
- sl_atr = 1.5 · tp_atr = 2.0 · atr_period = 14 (Wilder)  
- risk_pct = 0.01 · max_lots = 0.5 · long_only · one_entry_per_day  
- start_balance = 10000 · null.base_seed = 20260808  

Search cardinality = 1.

## Execution contract (frozen — implementers must not re-choose)

| Item | Contract |
|------|----------|
| ATR | Wilder via `TR.ewm(alpha=1/14, adjust=False)`; use `atr[i]` at signal close |
| Undercut | `undercut_seen_before_i = any(low[j] < day_open for j < i)` same day |
| Entry | Signal + fill at **close** of bar `i` when reclaim true |
| First exit bar | **`i+1`** (no same-bar exit after close entry) |
| Same-bar exit priority | **Stop before TP before time-flat** |
| Lots | floor to **0.01**, min **0.01**, max **0.5**, risk 1% of **realized balance** |
| Capital | start_balance **10000**; balance compounds only on booked exit pnls |
| Equity open | `balance + (close-entry)*CONTRACT*lots*pos` (cost **not** subtracted until exit) |
| Costs | RT **measured** on entry bar; **deducted** once at exit PnL booking (house) |
| No overnight | Enter only if the calendar day has a bar with hour≥16; day-boundary open pos fail-closed |

Full text: `execution_contract` (+ `capital`) in the charter JSON.

### Required implement-time fixtures (not run at freeze)

1. `same_bar_undercut_reclaim_rejected`  
2. `prior_bar_undercut_reclaim_accepted`  
3. `two_trade_realized_balance_sizing`  
4. `entry_exit_equity_cost_timing`  

Freeze tests encode the **formulas** (pure arithmetic / ordering) so implementers cannot re-choose them.

## Null (session / path-sensitive)

`within_day_ohlc_increment_rotate_v1`, n_trials **999**, **base_seed=20260808**, k∈{0..m−1} including identity.  
Forbidden: day_block_shuffle, circular_day_shift, global_return_shuffle, bare within_day_return_rotate.  
Strict CLI: `--null-seed` must equal charter `null.base_seed`. Sealed cycle passes seed explicitly.

## Data availability (coverage only — no performance)

| Item | Status |
|------|--------|
| `xauusd_data.csv` | Present (~129k rows; H1 + M15) |
| Time span | ~2021-09-03 → 2026-08-07 (server stamps) |
| Develop rule | `time < 2026-01-01` holdout lock |
| Costs | `results/xau_research_costs.json` Standard STP |

No develop PF/NP/DD or passer counts appear in this memo (freeze-before-peek).

## Immediate next

1. ~~Implement family + fixtures~~ **done** (`scripts/xau_family_day_open_reclaim_flat.py`).  
2. **Pending review:** `--strict-charter --screen-only` develop screen under **v2** only (not started).  
3. Zero soft passers → SCREEN_FAIL registry, zero nulls.  
4. ≥1 soft passer → external review → sealed 999 only if approved.

Do **not** inspect develop metrics until screen is explicitly authorized.

## Safety

Implementation + synthetic fixtures are **done** (family module on disk; freeze review passed).  
Still forbidden without explicit authorization: **develop screen**, sealed null r1, paper, live, promote, holdout selection.  
`KILL_DAY_OPEN_RECLAIM_FLAT` is a valid scientific close.  
v1 remains byte-immutable under SUPERSEDED.
