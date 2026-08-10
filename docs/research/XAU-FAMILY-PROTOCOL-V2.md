# XAU family research protocol v2.2 (enforcement complete)

**Date:** 2026-08-10  
**Status:** active  
**PR #1:** Draft head includes protocol work — **scope expanded** (v2 / v2.1 / v2.2). Not a clean research-only PR.

## Active freeze

| Charter | Status |
|---------|--------|
| `…/server_hour_window_flat_v2.json` | **FROZEN** protocol 2.2 · null=`within_day_ohlc_increment_rotate_v1` · n_null=999 |
| `…/server_hour_window_flat_v1.json` | **SUPERSEDED** (registry; file immutable; SHA `6b5811ee…`) |
| `…/tod_london_ny_flat_v1.json` | **PROTOCOL_NULL_INVALID** (registry; file immutable; SHA `e7cd953f…`) |

r1 **not burned**. promote=no / live_go=false.

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

## Optional sealed run (after review)

```bash
python3 scripts/xau_sealed_family_cycle.py \
  --charter results/xau_charters/2026-08-10_server_hour_window_flat_v2.json \
  --family server_hour_window_flat \
  --run-id r1
```
