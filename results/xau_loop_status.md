# XAU offline loop status

## 2026-08-11 — MULTI-INSTRUMENT DATA READINESS (Phase 0) · PASS_CLEAN

| Field | Value |
|-------|--------|
| **next_step** | **`FREEZE_MULTI_INSTRUMENT_FAMILY`** (identical 0–1-knob rule across XAU/EUR/GBP; aggregation + joint null) after adversarial design |
| **gate** | **PASS_CLEAN** |
| **branch / worktree** | `research/multi-instrument-data-v1` · worktree `mt5-arch-integration-wt-multi-instr` from `main` @ `9c7ef67` |
| **symbols** | XAUUSD · EURUSD · GBPUSD (Vantage Standard STP) |
| **develop** | `time < 2026-01-01` · common calendar 2021-09-07 → 2025-12-31 |
| **joint intersection H1** | **25558** timestamps (XAU-limited) |
| **costs** | commission **0** · spread = `MqlRates.spread` · slip **UNMEASURED** |
| **scoring** | **not started** (no signals / PF / grids) |
| **promote / live_go / PAPER_GO** | **no / false / no** |

Closed: `day_open_reclaim_flat` v2 **SCREEN_FAIL** on main. Do not retune.

---

## Prior (main @ 9c7ef67)

`day_open_reclaim_flat` v2 SCREEN_FAIL · RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS (superseded by multi-instrument data lane above).
