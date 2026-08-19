# Thesis memo — `asia_box_london_sweep_fade_flat` v1

**Date:** 2026-08-19  
**Status:** **FREEZE_ONLY** — immutable charter frozen; **no implementation**; **no develop grid inspection**; no sealed r1  
**Branch / worktree:** `research/xau-liq-sweep-fade-thesis` @ `../mt5-arch-integration-wt-liq-sweep-fade` off `origin/main` @ `c376e93`  
**Charter:** `results/xau_charters/2026-08-19_asia_box_london_sweep_fade_flat_v1.json`

## Standing constraints

- promote=no · live_go=false · PAPER_GO=no · offline only  
- Holdout sealed (`holdout_start=2026-01-01`); never used for selection  
- Dead / closed lines **must not be revived** (rename / filter-on-dead-line forbidden)  
- Closed freezes stay closed: TOD, server_hour, early_server_range_break, day_open_reclaim, joint FX cosign fade, exog FX→XAU follow, bb_rsi, Donchian, prior_day_high_break

## Market mechanism

On XAUUSD H1 **as stamped by the Vantage server clock** in `xauusd_data.csv` / the develop package (NY-close-aligned server: daily gap at `00:00`, London ≈ `10:00`, NY data ≈ `15:30+` — **literal `server_clock_as_stored` constants; no DST conversion**):

1. **Asia box (completed before hunt):** for each calendar day,  
   `box_high = max(high)`, `box_low = min(low)` over bars with server hour in **`01:00–07:59`** (hours `{1,2,3,4,5,6,7}`).  
   Box starts at `01:00` because hour `00` has **no bars** (rollover gap). Box ends `07:59` at the quiet-block edge before the European ramp.
2. **Hunt window (eligibility scaffolding only):** server hours **`08:00–13:59`** (hours `{8..13}`). Starts immediately after the box completes (captures pre-Frankfurt probes); ends before the `14:00` pre-NY ramp and `15:30` data spike so the claim stays **Europe-vs-Asia liquidity**, not NY-open.
3. **Signal (the alpha — event-gated):** on a **closed** H1 bar `i` in the hunt window, with the day’s box fully defined:  
   - **Long:** `low[i] < box_low` **and** `close[i] > box_low` (pierce then close back inside, same bar).  
   - **Short:** `high[i] > box_high` **and** `close[i] < box_high`.  
   No sweep-reclaim event → **no trade**, regardless of hour. **Flat-while-unswept** is what makes this not `server_hour_window_flat`.
4. **Entry:** next H1 **open** after signal bar `i`, same calendar day, only if `hour[i+1] ≤ 13` (else skip — hunt closed / no overnight invent).
5. **Occupancy:** **one entry per calendar day**, first qualifying event only.
6. **Exit:** SL at the **exact** swept extreme (`box_low` long / `box_high` short); TP at box midline `(box_high+box_low)/2`; force flat at close of hour-`13` bar (`13:59`). Intraday flat; no overnight.

**Hours are eligibility scaffolding, not the alpha.** Chosen as clock instrumentation (bar presence + session topology on the stored server clock). **Not** fit on PF/NP/DD or trade counts of this rule. Hours are frozen; re-picking after any screen metric is forbidden.

## Expected sign

After **Standard STP** house costs (verbatim `results/xau_research_costs.json`: login `27496181`, `commission_per_lot=0.0`, `slippage_points=0.0`, `spread_col=spread`, `cost_label=account_matched_spread_commission_only`, document SHA `4c78c45c95bf6410fa2d5e90ac50dec438779eb9e3d7f0e1d2fdde60f1a42879` — **byte-identical costs identity to exog follow-flat v4** for catalog comparability; RAW `$3` is a declared sensitivity alternative only, never the base):

- Soft primary: n≥20, PF≥1.1, NP>0, DD≤25% on the **single** fixed config on develop  
- Soft passers = 0 → **SCREEN_FAIL**, nulls not run, r1 unburned  
- Soft passers ≥1 → external review before any 999-trial null; only then max-stat under `within_day_ohlc_increment_rotate_v1` with **base_seed=20260819**

### Thin-n (frozen up front)

This predicate is expected to yield **materially fewer** events than the ~885-trade multi-instrument families. If develop-eligible trades **&lt; `gates.soft.n_trades_min` (20)**, that is **SCREEN_FAIL** by design — **not** a waiver, **not** grounds to lower `n_trades_min`, **not** a free knob.

## Explicit failure modes

1. Stop-run wicks reverse through the extreme → SL at exact box edge scratches out; after costs NP≤0 / PF&lt;1.1.  
2. Midline TP starves (shallow sweeps) → winners too small vs losers.  
3. Too few completed box+hunt days with a same-bar pierce+reclaim → thin-n SCREEN_FAIL.  
4. Apparent edge is only “be long/short in Europe hours” — falsified if removing the sweep-reclaim event (flat-while-unswept) collapses the edge; skeptic defense must hold in fixtures.  
5. Soft passers ≥1 but null p &gt; α/K → **KILL_ASIA_BOX_LONDON_SWEEP_FADE_FLAT**.

## Why this is not a closed family

| Closed line | Difference |
|-------------|------------|
| `tod_london_ny_flat` / `server_hour_window_flat` | Fixed clock exposure **without** an event. This stays **flat while unswept**; hours only gate when an event may fire. |
| `day_open_reclaim_flat` | Pool = **day open**; sticky prior undercut; long-only close entry. This pool = **Asia box 01–07 extremes**; same-bar pierce+close-inside; **both** sides; next-open entry; SL/TP geometric to box. |
| `early_server_range_break_flat` | **Overlap note (declare, do not hide):** both use an early server block as a day-local object. **Differences (frozen):** (1) **pool** — early_server uses hours **1–8 high only** as a breakout level; this uses **01–07 high *and* low** as a liquidity box; (2) **trigger** — early_server is **close above early high** (continuation/break); this is **pierce beyond then close back inside** (reject/fade); (3) **direction** — early_server **long-only breakout**; this is **fade both ways**; (4) **hunt** — early_server 9–15 / flat 16; this 8–13 / flat 13; (5) **risk** — early_server ATR SL/TP; this **exact extreme SL + midline TP**. Not a rename, hour retune, or filter on that line. |
| `joint_london_open_cosign_fade_flat` | Multi-symbol FX+XAU cosign fade. This is **single-symbol XAU** path geometry only. |
| `exog_london_fx_cosign_xau_follow_flat` | FX predictor → XAU **follow**. This has **no exogenous predictor**; opposite economic claim (fade stop-run, not follow cosign). |
| `bb_rsi` / Donchian / `prior_day_high_break` | Different indicators / multi-day channel / prior-day high breakout. |

## Free knobs

**Zero.** Search cardinality = 1.

Frozen constants: box hours `{1..7}`, hunt `{8..13}`, flat_hour `13`, same-bar pierce+reclaim, next-open fill with hour≤13 gate, 1 entry/day, SL=exact extreme, TP=midline, Standard STP costs block above, null method + seed below.

## Execution contract (frozen — implementers must not re-choose)

| Item | Contract |
|------|----------|
| Box | Completed hours `{1..7}` same calendar day; undefined → no trade that day |
| Signal | Evaluated at **close** of bar `i` in hunt hours only |
| Fill | **Open** of `i+1` if same day and `hour[i+1] ≤ 13`; else skip |
| First exit bar | Entry bar `i+1` (open entry → SL/TP may trigger same bar) |
| Same-bar exit priority | **1 stop · 2 TP · 3 time-flat** at close if `hour ≥ 13` |
| SL / TP | Long: SL=`box_low`, TP=mid; Short: SL=`box_high`, TP=mid |
| Lots | floor to **0.01**, min **0.01**, max **0.5**, risk **1%** of **realized balance** |
| Capital | `start_balance=10000`; compounds only on booked exit pnls |
| Costs | RT **measured** on **entry** bar; **deducted** once at exit booking (house) |
| No overnight | Day-boundary open position fail-closed |

### Required implement-time fixtures (not run at freeze)

1. `same_bar_pierce_close_inside_long_accepted`  
2. `same_bar_pierce_close_inside_short_accepted`  
3. `pierce_without_close_inside_rejected`  
4. `flat_while_unswept_no_trade_in_hunt` (skeptic defense vs server-hour flat)  
5. `box_incomplete_no_trade`  
6. `hour13_signal_fill_at_14_skipped`  
7. `one_entry_per_day_second_event_ignored`  
8. `early_server_overlap_contrast` (breakout-above-high ≠ fade-back-inside; document relation)  
9. `thin_n_below_min_is_screen_fail_not_waiver` (accounting/docs fixture)  
10. `two_trade_realized_balance_sizing` + `entry_exit_equity_cost_timing` (house capital)

## Null (session / path-sensitive)

`within_day_ohlc_increment_rotate_v1`, n_trials **999**, **base_seed=20260819** (freeze-date convention).  
Forbidden: day_block_shuffle, circular_day_shift, global_return_shuffle, bare within_day_return_rotate.  
Strict CLI: `--null-seed` must equal charter `null.base_seed`.

## Multiplicity

Open catalog Bonferroni: `K_prior=9`, `K=10`, `α=0.05`, `α/K=0.005`.  
Priors (9): `tod_london_ny_flat`, `server_hour_window_flat`, `early_server_range_break_flat`, `day_open_reclaim_flat`, `joint_london_open_cosign_fade_flat`, `bb_rsi`, `Donchian`, `prior_day_high_break`, `exog_london_fx_cosign_xau_follow_flat`.  
Pass status provisional while catalog open; paper/live while open = false.

## Data availability (coverage only — no performance)

| Item | Status |
|------|--------|
| `xauusd_data.csv` / develop H1 | Present on research host |
| Develop rule | `time < 2026-01-01` holdout lock |
| Costs | `results/xau_research_costs.json` Standard STP (SHA above) |

**No develop PF/NP/DD or passer counts of this rule appear in this memo (freeze-before-peek).** Median H–L-by-hour notes used only as **clock instrumentation** for choosing box/hunt edges; they are not evidence of edge.

## Immediate next

1. Adversarial freeze review of this memo + charter.  
2. Only after review: implement family module + fixtures (no develop peek).  
3. Separate explicit **AUTHORIZE SCREEN** before any develop run.  
4. Zero soft passers **or** thin-n &lt;20 → SCREEN_FAIL, null unarmed, r1 unburned.  
5. ≥1 soft passer → external review → sealed 999 only if separately authorized.

## Safety

Forbidden without explicit authorization: develop screen, sealed null r1, paper, live, promote, holdout selection, retune hours / `n_trades_min` / SL buffer after seeing metrics.  
`KILL_ASIA_BOX_LONDON_SWEEP_FADE_FLAT` is a valid scientific close.
