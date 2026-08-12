# Multi-instrument data readiness (Phase 0 — integrity v6.1 data snapshot)

**Gate:** `PASS_DATA_READY_WITH_IMPUTATION`

**Bar clock contract:** `server_clock_as_stored` (not UTC)

**Develop rule:** `server_time < holdout_start_server` (derived — no stored `*_develop.csv`)

**Publish model:** `current_indirection_v6`

**Package id:** `4f44b452081041f39fc24f03248b8ca8-ea80f1003a1e8958`

**Symbols:** XAUUSD, EURUSD, GBPUSD (full H1)

## Explicitly not done

- No thesis freeze, signals, PF, grids, nulls, paper, or live.

## PR note

Data-only PR: one package + CURRENT + SHA manifests. Pipeline lives in
`research/multi-instrument-pipeline-v1`.
