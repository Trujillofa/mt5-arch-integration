# XAU offline loop status

## 2026-08-11 — MULTI-INSTRUMENT Phase 0 fail-closed · PASS_DATA_READY_WITH_IMPUTATION

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_DATA_RE_REVIEW`** then freeze multi-instrument family (no scoring yet) |
| **gate** | **`PASS_DATA_READY_WITH_IMPUTATION`** (not PASS_CLEAN) |
| **branch** | `research/multi-instrument-data-v1` · worktree `mt5-arch-integration-wt-multi-instr` |
| **export_run_id** | `bc076afdc470421696f040bf48116824` |
| **login / server** | `27496181` / `VantageMarkets-Live 5` (verified vs costs + common.ini) |
| **clock** | **`server_clock_as_stored`** (not UTC) |
| **joint intersection** | **25558** H1 (XAU = intersection; EUR=GBP calendar; XAU ⊂ FX) |
| **imputation** | XAU develop ~5.07% zero-spread filled; raw/effective/imputed columns preserved |
| **scoring / thesis freeze** | **not authorized** until data re-review OK |
| **promote / live_go / PAPER_GO** | **no / false / no** |

Corrections vs first PASS_CLEAN wave: prefix-scoped kill; fresh-CSV required; export_run provenance; fail-closed DQ; auditable spreads; exact calendar relationships.

---

Closed on main: `day_open_reclaim_flat` v2 SCREEN_FAIL.
