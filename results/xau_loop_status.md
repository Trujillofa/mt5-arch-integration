# XAU offline loop status

## 2026-08-11 — MULTI-INSTRUMENT Phase 0 integrity **v3** · PASS_DATA_READY_WITH_IMPUTATION

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_DATA_RE_REVIEW`** (integrity v3) → multi-instrument family freeze only if approved |
| **gate** | **`PASS_DATA_READY_WITH_IMPUTATION`** |
| **export_run_id** | `4f44b452081041f39fc24f03248b8ca8` (MQL challenge-bound) |
| **MQL complete** | connected + login/server match costs; challenge_echo present |
| **publish** | **atomic staging** → final only after provenance + 3-symbol + common + lock verify |
| **lock** | full **and develop** SHA/count for {XAU,EUR,GBP}; mutation of develop fails verify |
| **costs** | required file; commission 0; slip UNMEASURED; login/server enforced |
| **thesis freeze / scoring** | **not authorized** |
| **promote / live_go / PAPER_GO** | **no / false / no** |

Integrity v3 closes: develop lock verification, no publish before global gate, strict MQL run_id binding, mandatory costs.

---

Closed on main: day_open_reclaim_flat v2 SCREEN_FAIL.
