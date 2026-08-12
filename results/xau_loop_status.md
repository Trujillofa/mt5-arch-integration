# XAU offline loop status

## 2026-08-12 — MULTI-INSTRUMENT Phase 0 integrity **v6.1 close** · PASS_DATA_READY_WITH_IMPUTATION

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_DATA_RE_REVIEW`** (v6.1) → family freeze only if approved; then open PR after data hygiene |
| **gate** | **`PASS_DATA_READY_WITH_IMPUTATION`** |
| **package** | single CURRENT content-addressed package; superseded ad5ba removed |
| **digest** | **read-only** (lock never unlinked; excluded from content id) |
| **lock schema** | exact SYMBOLS; PASS gate; publish_model=current_indirection_v6; path + run-id prefix |
| **consumer** | **`load_package_snapshot()`** pins package_dir once for multi-symbol IO |
| **thesis freeze** | **not authorized** |
| **promote / live_go** | **no / false** |

v6.1 closes: lock-redefines-universe, verify mutates package, cross-flip consumer reads.

---

## 2026-08-12 — MULTI-INSTRUMENT Phase 0 integrity **v6** · PASS_DATA_READY_WITH_IMPUTATION

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_DATA_RE_REVIEW`** (integrity v6) → multi-instrument family freeze only if approved |
| **gate** | **`PASS_DATA_READY_WITH_IMPUTATION`** |
| **export_run_id** | `4f44b452081041f39fc24f03248b8ca8` |
| **package_id** | content-addressed; immutable |
| **live roots** | **static** `…/packages/CURRENT/{instrument_data,manifests,report}` |
| **atomic switch** | **only CURRENT** symlink replaced |
| **pre-switch** | `verify_package_artifacts` (lock/SHA/counts/id) before CURRENT flip |
| **post-switch fail** | CURRENT rolled back to previous package |
| **CURRENT id** | content-ID format only; path escape rejected |
| **thesis freeze** | **not authorized** |
| **promote / live_go** | **no / false** |

Integrity v6 closes: multi-root non-atomic switch, post-promotion validation without rollback, CURRENT path escape.

---

## 2026-08-12 — MULTI-INSTRUMENT Phase 0 integrity **v5** · PASS_DATA_READY_WITH_IMPUTATION

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_DATA_RE_REVIEW`** (integrity v5) → multi-instrument family freeze only if approved |
| **gate** | **`PASS_DATA_READY_WITH_IMPUTATION`** |
| **export_run_id** | `4f44b452081041f39fc24f03248b8ca8` (MQL challenge-bound) |
| **package_id** | content-addressed `run_id-content16` (immutable; never overwrite different content) |
| **publish** | **atomic live symlinks** into CURRENT package dir (not per-file copy) |
| **rollback** | preflight resolves CURRENT package before mutation; dangling CURRENT aborts |
| **fail evidence** | `multi_instrument_data_readiness.FAIL.md` only — never clobbers package report |
| **lock** | full + develop SHA/count; live roots resolve under package |
| **thesis freeze / scoring** | **not authorized** |
| **promote / live_go / PAPER_GO** | **no / false / no** |

Integrity v5 closes: rollback source destruction, non-atomic consumer boundary, FAIL report clobbering package equality.

---

## 2026-08-12 — MULTI-INSTRUMENT Phase 0 integrity **v4** · PASS_DATA_READY_WITH_IMPUTATION

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_DATA_RE_REVIEW`** (integrity v4) → multi-instrument family freeze only if approved |
| **gate** | **`PASS_DATA_READY_WITH_IMPUTATION`** |
| **export_run_id** | `4f44b452081041f39fc24f03248b8ca8` (MQL challenge-bound) |
| **MQL complete** | connected + login/server match costs; **challenge_echo exact-compare** |
| **publish** | **versioned package + CURRENT pointer**; set-atomic install with complete rollback |
| **attest/consume** | **canonical bridge_dir paths only** (export_run.path divergence fails) |
| **lock** | full **and develop** SHA/count for {XAU,EUR,GBP}; mutation of develop fails verify |
| **costs** | required file; commission 0; slip UNMEASURED; login/server enforced |
| **thesis freeze / scoring** | **not authorized** |
| **promote / live_go / PAPER_GO** | **no / false / no** |

Integrity v4 closes: attested≠consumed split-brain, presence-only challenge echo, non-set-atomic publish.

---

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
