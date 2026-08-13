# Thesis memo — `joint_london_open_cosign_fade_flat` v4

**Date:** 2026-08-13
**Status:** FREEZE_ONLY — immutable charter frozen; **no implementation**; **no develop grid inspection**
**Branch:** `research/multi-instrument-joint-london-cosign-flat-v1`
**Charter:** `results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json`
**SHA:** `e29b26931b93443d7c903ddd034dfcabbeffde8761c41ad77b70e8292700b994`
**Supersedes:** v3 SHA `e88161be…` (and earlier SUPERSEDED v2/v1; byte-immutable)

## Why v4 (adversarial freeze review BLOCK on v3)

| Finding | v4 freeze |
|---------|-----------|
| v3 forbade implementation until “approval of v2” while v2 was SUPERSEDED | Authorization text pins **this charter version (v4)** only |
| Gate validation fail-open: missing joint max DD; `joint_soft_is_primary=false`; incomplete per-symbol soft; `no_trades=False` accepted via `float(False)==0` | Protocol requires complete joint soft keys (incl. `max_drawdown_pct_max`), exact `joint_soft_is_primary=true`, full per-symbol soft keys as non-boolean numbers, PF zero-denom as non-boolean numbers |
| Memo whitespace / knob note said “v2” | Clean memo; knob note says v4 |

## Mechanism (unchanged from v3 science)

Joint calendar **I** = timestamp intersection of XAU/EUR/GBP develop H1 from package
`4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd`.

Per day: earliest joint bar T\* with hour ∈ {7,8,9}; co-sign all three nonzero equal;
**fade** all three at **open of T\*+1** only if all three legs have valid ATR + risk-sized lots ≥ lot_min after floor-to-step; SL 1.5 / TP 2.0 ATR(14 Wilder on I); flat hour ≥16 or last bar of day; no overnight.

**USD sizing:** `raw_lots = risk_cash_USD / (sl_distance_price * contract_size)`; floor step; cap max; never force lot_min; all-or-none basket.

**PF zero-denom (house):** 0 no trades; 99 when gross loss is 0 and gross profit > 0.

**Zero free knobs.** Single-frame runners refuse `multi_instrument_joint_v1`.

## Gates

- **Per-symbol soft** (required for joint): n≥20, PF≥1.1, NP>0 each.
- **Joint soft (primary):** all three soft pass **and** joint book n≥60, PF≥1.1, NP>0, DD≤25%.
- **n_passers** ∈ {0,1} binary joint success only.
- Zero passers → **`SCREEN_FAIL`** / **`ZERO_PRIMARY_PASSERS`** · null not run · r1 unburned.

## Explicitly not done

Fixtures, family module, develop screen, sealed null, paper, live.
**Stop for adversarial charter review of v4.** No fixtures until review AUTHORIZE **this** version.
