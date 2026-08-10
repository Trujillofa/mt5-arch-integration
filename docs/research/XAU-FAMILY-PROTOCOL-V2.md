# XAU family research protocol v2.2 (enforcement complete)

**Date:** 2026-08-10  
**Status:** active  
**PR #1:** Draft head includes protocol work — **scope expanded** (v2 / v2.1 / v2.2). Not a clean research-only PR.

## Standing loop disposition

**`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`** · promote=no · live_go=false · r1 unburned

## Freezes (registry)

| Charter | Status |
|---------|--------|
| `…/server_hour_window_flat_v2.json` | **SCREEN_FAIL** ZERO_PRIMARY_PASSERS (SHA `26ff7532…`) — r1 not burned |
| `…/server_hour_window_flat_v1.json` | **SUPERSEDED** (SHA `6b5811ee…`) |
| `…/tod_london_ny_flat_v1.json` | **PROTOCOL_NULL_INVALID** (SHA `e7cd953f…`) |

## Screen-fail rule (deterministic)

> If the real develop grid has **zero primary passers**, terminate as **`SCREEN_FAIL`**
> **without null trials**. Correct p-value logic: every null trial has
> `n_passers ≥ 0 = real`, so `hits = n_null` and
> `p_n_passers = (n_null+1)/(n_null+1) = 1.0`. **`p_max_pf` is not_evaluated**
> (not reported as 1.0). Accounting fields:
> `n_null_planned`, `n_null_executed=0`, `attempt_type=DETERMINISTIC_SCREEN`,
> `family_screen_attempt=true`, `sealed_null_attempt=false`.

## Screen-fail rule (deterministic)

> If the real develop grid has **zero primary passers**, terminate as **`SCREEN_FAIL`**
> **without null trials**. Under add-one smoothing, `p_n_passers` is necessarily
> **1.0** when passers=0 and nulls are skipped (and always fails a 0.05 bar if
> nulls were run with zero real passers). This is arithmetic, not optional stopping.

## Canonical session null

**`within_day_ohlc_increment_rotate_v1`**

1. Per calendar day, `ref_0 = open[0]`, `ref_j = close[j-1]`.  
2. `inc_j = (open,high,low,close)/ref_j`.  
3. Circular rotate by `k ∈ {0,…,m−1}` (**identity included**).  
4. Rebuild continuous path from day open; timestamps/spreads fixed.  

Invariants: open/ref multiset, TR/ref multiset, per-day bar counts, continuity.

**Invalid for session families:** `day_block_shuffle`, `circular_day_shift`, `global_return_shuffle`, and bare `within_day_return_rotate` under protocol ≥2.2 (name without preregistered OHLC algorithm).

## Enforcement

| Guard | Behavior |
|-------|----------|
| Session thesis | Must set `null.method=within_day_ohlc_increment_rotate_v1` (protocol ≥2.2) |
| `null.forbidden_methods` | Method listed there is rejected |
| Registry JSONL | Fail closed on malformed lines; terminal dispositions are **monotonic** |
| Dispositional tree | Sealed / `--strict-charter` refuse dirty tracked protocol/family/cost/charter files |
| Provenance | Records `code_commit` + `tree_clean` / `dirty_paths` |

## Next family (not server-hour / TOD)

New `family_id` · freeze under `results/xau_charters/` · git-tracked · match HEAD ·  
freeze **before** inspecting real grid · null only if primary passers ≥ 1.

## Sealed path requirements

- Charter under `results/xau_charters/`
- Git-tracked and byte-identical to `HEAD` blob
- Clean dispositional tree (includes disposition registry)
- Charter runnable (registry not terminal)
