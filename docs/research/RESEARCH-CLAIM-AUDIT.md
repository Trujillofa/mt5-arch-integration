# RESEARCH-CLAIM-AUDIT

**Date:** 2026-08-24  
**Branch:** `research/research-claim-audit`  
**Scope:** `docs/**/*.md` (Extract walk; Verify vs `git ls-files` + artifact predicates)  
**Inventory:** [`results/research_claim_inventory.json`](../../results/research_claim_inventory.json)  
**Outcome:** **FAIL** — `n_drift=3` (drift fails the run, not a warning)

Auditor only. No charter/lock/`xau_loop_status.md`/`strategy_params.json`/`*.sha256` edits. No retunes, no holdout access, no `--live`, no `OrderSend`, no `src/mt5_arch` edits.

---

## Extract — per-kind counts

| Kind | Count |
|------|------:|
| path | 121 |
| link | 71 |
| sha | 25 |
| symbol | 35 |
| metric | 53 |
| disposition | 131 |
| **n_claims** | **436** |

Method: slim inventory `{file,line,kind,claimed,attribution}` from a `docs/**/*.md` walk (minimum `docs/README.md` + `docs/research/*.md` + other `docs/*.md`). Links resolved relative to the containing file.

---

## Verify — totals

| Metric | Value |
|--------|------:|
| n_ok | 431 |
| n_drift | **3** |
| n_unresolvable | 2 |
| n_claims | 436 |

Verification completed (`ok=true` for the checker). **Run status is FAIL because `n_drift > 0`.**

### Drift table

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 21 | disposition | `New edge` | Zacks status=`SCHEMA_PASS` / overlay **BLOCKED** for KEEP (BLOCKED/SCHEMA_PASS, not New edge) |
| `docs/README.md` | 69 | path | `config/local.paths` | untracked (gitignored secrets path) |
| `docs/research/ZACKS-MCP-OVERLAY-LANE.md` | 3 | disposition | `KEEP` | status=`SCHEMA_PASS` / overlay **BLOCKED** for KEEP (BLOCKED, not KEEP) |

Hand-check (Zacks pair): `docs/README.md:21` labels the lane a **New edge** while `docs/research/ZACKS-MCP-OVERLAY-LANE.md:3` states `SCHEMA_PASS` / overlay **BLOCKED** for KEEP — disposition drift, not an authorization to reclassify.

### Unresolvable (with reasons)

| File | Line | Kind | Claimed | Reason |
|------|-----:|------|---------|--------|
| `docs/research/SIGNAL-EDGE-TRIAGE.md` | 50 | metric | `n=885` | UNRESOLVABLE: checked `results/xau_charter_disposition_registry.jsonl`, `results/xau_loop_status.md`, `docs/research/BACKTEST-RECORD.md`, `docs/research/SIGNAL-EDGE-TRIAGE.md`; claimed=`n=885` (no matching artifact value) |
| `docs/research/EURUSD-NY-SCALP-DESIGN.md` | 148 | sha | `ebf0bcd9` | UNRESOLVABLE: no file for attr=`EURUSD history csv` |

Unresolvable ≠ ok and ≠ auto-fixed. Human decides whether to drop the claim, add an attribution target, or leave as documented debt.

---

## Mutant gate

| Field | Value |
|-------|-------|
| n_seeded | 4 |
| n_caught | 4 |
| mutant_caught | **true** |

Seeded (scratch `/tmp` only; worktree docs/research state untouched):

| Seed kind | Kind | Mutant claimed | Status | Caught |
|-----------|------|----------------|--------|:------:|
| dead_path | path | `scripts/__mutant_dead_path_does_not_exist__.sh` | drift | yes |
| sha_one_char | sha | `11099b20` (was `11099b2a`) | unresolvable≠ok | yes |
| metric_digit | metric | `PF 0.559` (was `PF 0.553`) | unresolvable≠ok | yes |
| inverted_disposition | disposition | `promote=true` (was `promote=no`) | drift | yes |

Same Verify predicates (`git ls-files`, SHA prefix, artifact metric, disposition equality) executed via `/tmp/claim_mutant_gate.py`. Gate proves the auditor reports seeded bad claims; it does **not** clear the real `n_drift=3` FAIL.

---

## THIS IS AN AUDIT, NOT AN AUTHORIZATION

- Does **not** change standing: `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` / `promote=no` / `live_go=false`.
- Does **not** authorize screens, paper gates, retunes, family revival, or holdout access.
- Does **not** authorize edits to charters, locks, `results/xau_loop_status.md`, `strategy_params.json`, or `*.sha256`.
- Drift is reported for a human to decide; the auditor does not “fix” research state.
- `n_drift=3` → this audit run is a **FAIL**, not a soft warning and not a green pass.

Standing disposition remains **RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS** / **promote=no** / **live_go=false**.
