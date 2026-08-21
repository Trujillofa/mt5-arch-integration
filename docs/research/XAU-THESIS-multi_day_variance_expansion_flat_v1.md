# Thesis memo — `multi_day_variance_expansion_flat` v1

**Date:** 2026-08-20  
**Status:** IMPLEMENT_FIXTURES — family module + synthetic pytest; **no develop grid inspection**; no sealed r1  
**Branch:** `research/xau-multi-day-variance-expansion-flat` from `origin/main`  
**Charter:** `results/xau_charters/2026-08-20_multi_day_variance_expansion_flat_v1.json`

## Standing constraints

- promote=no · live_go=false · PAPER_GO=no · offline only
- Holdout sealed (`holdout_start=2026-01-01`); never used for selection
- **K_prior=10** (asia-box look consumed). This is family 11 in the open catalog (`K=11`)
- Dead lines **must not be revived** (rename / filter-on-dead-line forbidden)
- Family module + fixtures authorized; **no develop peek / sealed r1 / paper / live**

## Rejected candidate (recycle)

**Intraday liquidity imbalance: Asia-box extremes vs early London displacement** is **not** this family. That geometry is `asia_box_london_sweep_fade_flat` (SCREEN_FAIL 2026-08-19, PF 0.553, n=670) and sits next to `early_server_range_break_flat` / `prior_day_high_break`. Do not freeze, rename, or flip-direction it.

## Market mechanism

On XAUUSD H1 **as stamped by the Vantage server clock** in `xauusd_data.csv` (`server_clock_as_stored`; no DST conversion):

1. For each **completed** calendar day `D`, take the last printed H1 **close** `C_D`.
2. Daily return `r_D = ln(C_D / C_{D-1})` (skip if `C_{D-1}<=0`).
3. At the start of a new day `T` (before any `T` bar is used in the state), compute **sample variance** (`ddof=1`) of the last **5** completed daily returns (`short_var`) and the last **20** completed daily returns (`long_var`). Days in `{T}` are excluded.
4. **Expansion** iff `long_var > 0` and `short_var / long_var >= 1.5`.
5. **Fade** yesterday’s close-to-close sign: if `C_{T-1} > C_{T-2}` → **short**; if `C_{T-1} < C_{T-2}` → **long**; if equal → skip.
6. Signal at the **close of the first printed H1 of day T**; fill `open[i+1]` same calendar day if `hour[i+1] <= 16`.
7. SL distance = `|C_{T-1} - O_{T-1}|` where `O_{T-1}` is the **open of the first H1 of day T-1**. TP = `2 ×` that distance. Force-flat at close of hour **≥16**. **Intraday flat** (swap unmodeled). One entry per day.

Hours are **flatten / fill eligibility only**. The alpha is the **multi-day realized-variance ratio + fade of the last daily close-to-close**, not a clock window, not EMA/MACD/ORB, not volume, not ATR/Donchian highs.

## Expected sign

After Standard STP costs (measured spread; commission 0; slip 0 unmeasured):

- Soft primary (this freeze): n≥**40**, PF≥**1.2**, NP>0, max DD≤**15%** on the **single** fixed config on develop (`time < 2026-01-01`)
- Soft passers = 0 → **SCREEN_FAIL**, nulls not run, r1 unburned
- Soft passers ≥1 → external review before any 999-trial null

## Explicit failure modes

1. After a vol spike, fading yesterday’s close-to-close is just paying spread (expectancy ≈ −RT).
2. Thin n: expansion days are rare → n<40 is SCREEN_FAIL, not a waiver.
3. `|C-O|` of the prior day is tiny → skip or microscopic stops that costs eat.
4. Soft passers ≥1 but null p>0.05 → **KILL_MULTI_DAY_VARIANCE_EXPANSION_FLAT**.

## Why this is not a closed family

| Closed line | Difference |
|-------------|------------|
| `bb_rsi` | Band/RSI mean-reversion; this is **daily close-to-close variance ratio**, no BB/RSI |
| Donchian / turtle | N-bar **high/low** channel ride; this **fades** last daily close-to-close after a **variance ratio**, no channel |
| `prior_day_high_break` | Break prior **day high**; this does not use prior high/low |
| `tod_*` / `server_hour_*` | Fixed clock long **without** a variance state |
| `early_server_range_break_flat` | Early-block **high** breakout; no 01–08 box here |
| `day_open_reclaim_flat` | Same-day open undercut/reclaim; this uses **completed multi-day returns** |
| `asia_box_london_sweep_fade_flat` | Asia 01–07 box pierce+reclaim; **rejected** as the other Stage-2 candidate |
| `joint_london_*` / `exog_london_fx_*` | FX cosign / follow; **XAU-only**, no EUR/GBP |
| US-index ORB / z-score / Fib | Different instrument; 1%/20% **archived** |

Not a rename, hour retune, or filter on those lines. **Ride** (continuation) of the same expansion is **not** this freeze — that neighborhood is Donchian / prior-day break.

## Free knobs

**Zero.** Cardinality 1. All geometry fixed: short=5, long=20, ratio≥1.5, fade only, SL=`|C-O|` prior day, TP=2R, first-bar signal, flat hour 16.

## Execution / null

See charter `execution_contract` and `null`. Canonical session null `within_day_ohlc_increment_rotate_v1`, n_trials **999**, `base_seed=20260820`.

## Do not

Peek develop metrics, run sealed r1, paper, live, or promote until a later AUTHORIZE. Family module + synthetic fixtures are in place.
