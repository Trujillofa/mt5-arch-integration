# Thesis memo — `joint_london_open_cosign_fade_flat` v1

**Date:** 2026-08-13
**Status:** FREEZE_ONLY — design artifacts only; **no implementation**; **no develop grid inspection**; no fixtures; no screen; no sealed r1
**Branch:** `research/multi-instrument-joint-london-cosign-flat-v1` from `origin/main` @ `1f21f72` (PR #5 multi-instrument data merge)
**Charter:** `results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v1.json`
**Data pin:** multi-instrument package `4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd` (Phase 0 closed)

## Standing constraints

- promote=no · live_go=false · PAPER_GO=no · offline only
- Holdout sealed (`holdout_start=2026-01-01` server); **never** used for selection
- Dead lines **must not be revived**
- Closed freezes stay closed (day_open, early_server_range, server_hour, TOD, prior_day, Donchian, bb_rsi)
- Multi-instrument Phase 0 package is **immutable** for this freeze (pin SHAs below)

## Why multi-instrument (genuinely new)

Prior freezes were **single-symbol XAU** (or TOD/server-hour long-only geometries). This family is **joint** across **XAUUSD + EURUSD + GBPUSD** on the **same** content-addressed H1 package:

1. **Signal requires all three symbols** at one shared timestamp (intersection calendar).
2. **Per-symbol soft gates** + **joint aggregation gate** (equal-risk portfolio).
3. **Dependency-preserving joint null:** one shared rotate seed `k` applied to **all three** OHLC paths on the same day (no independent per-symbol nulls that destroy co-movement).

This is **not** a rename of `day_open_reclaim_flat` (no undercut/reclaim of day open), **not** a prior-day high break, **not** a blind fixed-hour long, and **not** three independent XAU-style screens glued with OR.

## Market mechanism

**Clock:** `server_clock_as_stored` from the multi-instrument package (Vantage stamps). Hours are **server labels only** — **not** claimed London wall-clock identity. The label “london_open” names a **fixed server-hour window** used as a co-directional impulse probe after the thin Asia block on this feed.

**Coincident bar `T*` (per server calendar day `D`):**

1. Restrict each symbol’s develop H1 to bars whose server date is `D`.
2. Among timestamps present in the **intersection** of all three symbols for day `D`, take the **earliest** bar with server hour ∈ `{7, 8, 9}` (first hit in that fixed window).
3. If no such intersection timestamp exists → **no signal** that day.

**Co-sign condition at `T*`:**

- Let `r_S = close_S[T*] - open_S[T*]` for `S ∈ {XAUUSD, EURUSD, GBPUSD}`.
- Require `sign(r_XAU) = sign(r_EUR) = sign(r_GBP) ∈ {+1, −1}` (all nonzero, all equal).
- If any bar is flat (`r_S = 0`) or signs disagree → no signal.

**Trade (fade, both directions, per symbol):**

- **Entry:** at **close** of bar `T*` (closed-bar only; no open-of-`T*` entry), direction = **opposite** of co-sign (fade the joint impulse).
- **All three symbols** enter the fade on the same signal day when co-sign holds (identical rule).
- **SL / TP:** fixed ATR multiples identical across symbols: `sl_atr=1.5`, `tp_atr=2.0`, `atr_period=14` Wilder (see execution contract).
- **Flat:** force flat at server hour ≥ **16** same day, or SL/TP earlier; **no overnight**.
- **One entry per symbol per calendar day** maximum.
- **Sizing:** identical risk_pct=0.01, max_lots=0.5, start_balance=10000 per symbol book; joint equity = sum of three books (no cross-margin).

**Costs (pinned):** Standard STP from `results/xau_research_costs.json` — commission 0; slip 0 UNMEASURED; per-bar spread from package `spread` / effective columns as in costed simulate. Point sizes per symbol from package meta (XAU 0.01; FX 0.00001 unless meta says otherwise).

## Free knobs

**Zero.** Search cardinality = 1.

| Item | Frozen value |
|------|----------------|
| Coincident hour window | server hours `{7, 8, 9}`, earliest intersection |
| Co-sign | all three nonzero equal sign at `T*` |
| Direction | fade co-sign |
| Entry | close of `T*` |
| SL / TP / ATR | 1.5 / 2.0 / 14 Wilder |
| Flat hour | 16 server |
| Risk / max lots / capital | 0.01 / 0.5 / 10000 per book |
| null.base_seed | 20260813 |

Not a 1-knob hour search: the hour set is fixed, not optimized on develop.

## Gates (pre-registered)

### Per-symbol soft (primary building block)

On develop, for each symbol’s **single** fixed config, costed:

- `n_trades ≥ 20`
- `profit_factor ≥ 1.1`
- `net_profit > 0`

Classic gates (stricter) are **report-only** for screen narrative; **primary** uses soft.

### Joint aggregation gate (required for “primary passer”)

A **joint primary passer** exists only if **all** of:

1. **All three** symbols pass per-symbol soft gates.
2. **Joint book** (equal-risk sum of the three symbol PNLs, same days) passes soft:
   - `n_trades ≥ 60` (sum of per-symbol trades)
   - `profit_factor ≥ 1.1`
   - `net_profit > 0`
3. Joint max drawdown of the sum equity curve ≤ **25%** (soft joint risk cap; classic 10% remains report-only).

`primary_n_passers` for screen/null accounting is **0 or 1** at the **joint** level (cardinality 1). Soft passers = 0 → **SCREEN_FAIL**, nulls not run, r1 unburned.

### Develop window (pinned)

| Field | Value |
|-------|--------|
| Package | `4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd` |
| Develop | derived `server_time < 2026-01-01 00:00:00` |
| Common intersection | XAU ⊂ FX; joint timestamps = XAU develop count (25557) when XAU ⊂ FX |
| Holdout | sealed `2026-01-01`; **not** for selection |
| Loader | `load_package_snapshot()` once per research op |

## Dependency-preserving joint null

**Method:** `within_day_ohlc_increment_rotate_v1` applied **jointly**:

1. Align the three symbols on the develop **timestamp intersection**.
2. For each null trial, draw (or seed-derive) one `k_d` per calendar day **shared across symbols**.
3. Apply the OHLC increment rotate with that **same** `k_d` to XAU, EUR, and GBP independently in price space but **locked k**.
4. Rebuild co-sign / fade on the rotated triple.

**Forbidden:** independent k per symbol; day_block_shuffle; global_return_shuffle; circular_day_shift; bare within_day_return_rotate; any null that re-samples one symbol conditional on another’s path.

**base_seed:** `20260813` (frozen; no seed shopping).
**n_trials:** 999 when primary joint passers ≥ 1 and review authorizes sealed null.

## Kill rule

| Event | Disposition |
|-------|-------------|
| Soft joint passers = 0 on develop screen | `SCREEN_FAIL` / `ZERO_PRIMARY_PASSERS` · null not run · r1 unburned |
| Joint soft ≥1 then null max-stat fails | **`KILL_JOINT_LONDON_OPEN_COSIGN_FADE_FLAT`** |
| Walk-forward fails after null pass | **`KILL_JOINT_LONDON_OPEN_COSIGN_FADE_FLAT`** |
| Refine loops / knob expansion after freeze | **forbidden** |

## Expected failure modes

1. Co-sign days are rare → n_trades soft fail per symbol.
2. Co-sign is FX-driven; XAU is noisy → not all three soft-pass.
3. Fade of joint impulse is noise after costs.
4. Edge is pure hour bias already killed by server_hour / TOD families — this rule **requires three-symbol co-sign**, not a blind long at hour 7–9.

## Explicitly forbidden until review + later authorization

- Inspect real develop grid metrics before this charter is git-committed and HEAD-matched
- Implement family module / fixtures / screen before adversarial freeze review **approval**
- Retune hours, ATR, or gates after peek
- Independent per-symbol nulls
- Holdout selection
- Paper / live / promote

## Data pin (immutable)

| Item | Value |
|------|--------|
| package_id | `4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd` |
| publish_model | `current_indirection_v6` |
| symbols | XAUUSD, EURUSD, GBPUSD |
| xauusd_h1.csv sha256 | `a0ebeb0bf61902d3c35edf364ab0315a2ec65f127c9c1bf5081559b6420a78da` |
| eurusd_h1.csv sha256 | `545c664624a5346194b7de4c9fa281dbc60ca84fc4496271f8c208835b0e77ab` |
| gbpusd_h1.csv sha256 | `55e522b0d405d5b8ca234670f80b1223fa4ada40b8facd079acc076c0cd7babd` |
| costs | `results/xau_research_costs.json` (Vantage STP 27496181) |
| holdout_lock | `results/xau_holdout_lock.json` |

## Next after adversarial charter review

1. **If BLOCK:** revise freeze (v2) without peaking develop metrics.
2. **If NO BLOCKING:** authorize synthetic fixtures only.
3. **If fixtures pass review:** authorize costed develop screen (`--strict-charter --screen-only`).
4. Null / sealed r1 only if joint primary passers ≥ 1 and separately authorized.

**Stop here for adversarial charter review.**
