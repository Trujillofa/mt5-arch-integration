# XAU family research protocol v2.2

**Date:** 2026-08-10  
**Status:** active for new families  
**PR #1:** Draft head includes protocol work — **scope expanded**; review as joint research+protocol.

## Standing research disposition

| Item | Status |
|------|--------|
| bb_rsi / Donchian / prior_day_high_break | KILL (prior work) |
| `tod_london_ny_flat` v1 | **PROTOCOL_NULL_INVALID** (registry; charter file immutable) |
| r1 sealed run | **not burned** |
| promote / live_go | no / false |

Invalidation of freezes: append-only `results/xau_charter_disposition_registry.jsonl` keyed by **charter SHA-256**. Do **not** edit frozen charter JSON for disposition.

## Null methods (v2.2)

| Method | Use |
|--------|-----|
| **`within_day_return_rotate`** | **Required for server-hour / session rules.** Per day: rotate complete normalized OHLC bar increments; k ∈ {0,…,m−1} includes identity; rebase continuous path; preserve open/ref and TR/ref multisets. |
| `global_return_shuffle` | Legacy global close-return shuffle (non-session claims only). |
| `day_block_shuffle` / `circular_day_shift` | **PROTOCOL_NULL_INVALID** for hour rules (absolute-price paste, hour misalign). |

## Charter rules

1. Write-once under `results/xau_charters/YYYY-MM-DD_<family>_vN.json`.
2. Gates, null method, n_trials (≥199; 999 for 0–1 knobs) from charter only under sealed/`--strict-charter`.
3. Family id, costs, null method/count must match runtime; fixture smoke is **blocking**.
4. Intraday flat (or explicit swap handling); slip sensitivity report-only.
5. Clock: server hours as stored unless external offset proven.

## Active freeze (optional next sealed run)

`results/xau_charters/2026-08-10_server_hour_window_flat_v1.json`  
— server-hour labels only; **not** London–NY claim; null=`within_day_return_rotate`; n_null=999.

```bash
# Only when ready to spend an attempt — not automatic
python3 scripts/xau_sealed_family_cycle.py \
  --charter results/xau_charters/2026-08-10_server_hour_window_flat_v1.json \
  --family server_hour_window_flat \
  --run-id r1
```

## Superseded / invalid candidates

| Family | Note |
|--------|------|
| Multi-instrument | Deferred (data) |
| EMA20 + H4 pullback | Removed (dead htf_pullback) |
| tod_london_ny_flat | Registry INVALID — do not run |
