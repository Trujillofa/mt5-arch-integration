# Thesis memo — `joint_london_open_cosign_fade_flat` v3

**Date:** 2026-08-13  
**Status:** FREEZE_ONLY — immutable charter frozen; **no implementation**; **no develop grid inspection**  
**Branch:** `research/multi-instrument-joint-london-cosign-flat-v1`  
**Charter:** `results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v3.json`  
**SHA:** `e88161be27ab09542e2c49b96da32781454436791666570bc6b06d3eecb51c65`  
**Supersedes:** v2 SHA `935534e2…` and v1 SHA `2d3fda48…` (byte-immutable; registry **SUPERSEDED** only)

## Why v3 (adversarial freeze review BLOCK on v2)

| Finding | v3 freeze |
|---------|-----------|
| Sizing used undefined `point_value_per_lot` and double-counted `contract_size`; min-lot clamp conflicted with all-three entry | **USD** account/P&L; `raw_lots = risk_cash_USD / (sl_distance_price * contract_size)`; floor to step, cap at max; **never force lot_min**; any invalid leg → **skip entire joint signal** (all-or-none basket) |
| Single-frame runners did not reject multi-instrument charters | `xau_family_null_maxstat.py` and `xau_sealed_family_cycle.py` raise **`REFUSE_SINGLE_FRAME_RUNNER`** after validate, **before** plugin/data/ledger/fixtures |
| Multi-instrument gate validation fail-open without nested layout | Validator requires complete joint-soft contract for every multi-instrument charter: top-level soft, `primary_n_passers=soft`, `gates.multi_instrument`, harness, intersection calendar, shared-k, PF zero-denom |
| PF zero-denominator unfrozen | House convention pinned: **PF=0** no trades; **PF=99** when gross loss=0 and gross profit>0 (applies to per-symbol, joint, null max-PF) |

## Mechanism (unchanged intent)

Joint calendar **I** = timestamp intersection of XAU/EUR/GBP develop H1 from package  
`4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd`.

Per day: earliest joint bar T\* with hour ∈ {7,8,9}; co-sign all three nonzero equal;  
**fade** all three at **open of T\*+1** only if all three legs have valid ATR + risk-sized lots ≥ lot_min after floor-to-step; SL 1.5 / TP 2.0 ATR(14 Wilder on I); flat hour ≥16 or last bar of day; no overnight.

**Zero free knobs.**

## Gates

- **Per-symbol soft** (required for joint): n≥20, PF≥1.1, NP>0 each.
- **Joint soft (primary):** all three soft pass **and** joint book n≥60, PF≥1.1, NP>0, DD≤25%.
- **n_passers** ∈ {0,1} binary joint success only.
- Zero passers → **`SCREEN_FAIL`** / **`ZERO_PRIMARY_PASSERS`** · null not run · r1 unburned.

## Explicitly not done

Fixtures, family module, develop screen, sealed null, paper, live. **Stop for adversarial charter review of v3.** No fixtures until review AUTHORIZE.
