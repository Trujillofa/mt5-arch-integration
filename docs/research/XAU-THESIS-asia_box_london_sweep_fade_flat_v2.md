# Thesis memo — `asia_box_london_sweep_fade_flat` v2

**Date:** 2026-08-19  
**Status:** **FREEZE_ONLY** — immutable charter frozen; **no implementation**; **no develop grid inspection**; no sealed r1  
**Branch / worktree:** `research/xau-liq-sweep-fade-thesis` @ `../mt5-arch-integration-wt-liq-sweep-fade`  
**Charter:** `results/xau_charters/2026-08-19_asia_box_london_sweep_fade_flat_v2.json`  
**Supersedes:** v1 SHA `7cf9f46fd5ddd44c171f04260f8d4fac167cb005bf3f6d4d03c1c137c1399b7e` (byte-immutable)

## Why v2 (adversarial freeze review F1)

v1 froze next-open entry with **structural** SL/TP (exact box extreme / midline) but left **gap-at-fill** pathologies to the implementer:

| Case | Pathology if undeclared |
|------|-------------------------|
| (a) open beyond own SL | `stop_dist ≤ 0` → nonsense sizing; `stop_dist == 0` → ZeroDivisionError in `raw_lots` |
| (b) open beyond TP | TP unreachable → trade degrades to time-flat scratch |
| (c) `box_high == box_low` | SL = TP = extreme → same zero-distance pathology |

**Remedy (declaration-only):** `rule.entry_gap_policy` — **skip entry** on all three, evaluated at `open[i+1]` before sizing. New fixtures: `entry_gap_open_beyond_sl_skipped`, `entry_gap_open_beyond_tp_skipped`, `entry_gap_degenerate_box_skipped`.

Unchanged from v1 (byte-identical blocks): mechanism, clocks, signal, occupancy, SL/TP levels, costs (Standard STP), null (`within_day_ohlc_increment_rotate_v1`, seed `20260819`, N=999), gates (soft primary), multiplicity (K_prior=9 / K=10 / α=0.005), thin-n SCREEN_FAIL, early_server overlap note, holdout lock.

F2 (Low, note only): `max_lots` duplicated in `fixed` and `sizing` — frozen identical; no churn.

## Standing contract

Full mechanism, not-a-rename table, execution contract, falsifiers, and safety rules: see **v1 memo**  
`docs/research/XAU-THESIS-asia_box_london_sweep_fade_flat_v1.md`  
plus this amendment. **No develop PF/NP/DD** of this rule in either memo.

## Immediate next

1. Re-verify v2 (validators, structural diff vs v1, K/null/costs identity).  
2. On AUTHORIZE: implementation branch + fixtures only.  
3. Develop screen only on explicit separate word.  
4. Thin-n &lt;20 or zero soft passers → SCREEN_FAIL; null unarmed.
