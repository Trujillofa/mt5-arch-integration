# Thesis memo — `joint_london_open_cosign_fade_flat` v2

**Date:** 2026-08-13
**Status:** FREEZE_ONLY — immutable charter frozen; **no implementation**; **no develop grid inspection**
**Branch:** `research/multi-instrument-joint-london-cosign-flat-v1` from `main@1f21f72`
**Charter:** `results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v2.json`
**Supersedes:** v1 SHA `2d3fda48…` (byte-immutable; registry **SUPERSEDED**)

## Why v2 (adversarial freeze review BLOCK on v1)

| Finding | v2 freeze |
|---------|-----------|
| Nested `gates.per_symbol` / `gates.joint` invisible to `gates_from_charter()` | Top-level `gates.classic` / `gates.soft` / `primary_n_passers=soft` (joint soft). Per-symbol soft lives under `gates.multi_instrument` for dedicated harness only. Validator rejects nested-only layout. |
| Real full-path ATR/exits vs null intersection | **`analysis_calendar.mode=intersection_only`** for signals, ATR, exits, equity, real **and** null |
| Incomplete execution/cost geometry | Entry at **T\*+1 open**; exits start T\*+1; **SL→TP→time-flat**; missing hour-16 → last bar of day; lot min/step/max + floor; per-symbol point/contract (XAU 0.01, FX 1e-5); forbid XAU point on FX |
| Incomplete joint stats | Joint start equity **30000**; MTM on joint I; floating equity definition; DD on joint peak; joint PF; `n_passers` binary joint gate; `max_pf` = joint PF of sole config |
| Shared-k ambiguity | `trial_seed=base_seed+trial_index`; PCG64; ascending days; one `rng.integers(0,m_D)` per day; `m_D` = intersection count |
| Generic single-frame runner | `harness.kind=multi_instrument_joint_v1`; single-frame runners prohibited; validator enforces |

## Mechanism (unchanged intent, tighter geometry)

Joint calendar **I** = timestamp intersection of XAU/EUR/GBP develop H1 from package
`4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd`.

Per day: earliest joint bar T\* with hour ∈ {7,8,9}; co-sign all three nonzero equal;
**fade** all three at **open of T\*+1**; SL 1.5 / TP 2.0 ATR(14 Wilder on I); flat hour ≥16
or last bar of day; no overnight.

**Zero free knobs.**

## Gates

- **Per-symbol soft** (required for joint): n≥20, PF≥1.1, NP>0 each.
- **Joint soft (primary):** all three soft pass **and** joint book n≥60, PF≥1.1, NP>0, DD≤25%.
- **n_passers** ∈ {0,1} binary joint success only.
- Zero passers → **`SCREEN_FAIL`** / **`ZERO_PRIMARY_PASSERS`** · null not run · r1 unburned.

## Explicitly not done

Fixtures, family module, develop screen, sealed null, paper, live. **Stop for adversarial charter review of v2.**
