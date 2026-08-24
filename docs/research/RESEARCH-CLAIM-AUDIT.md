# RESEARCH-CLAIM-AUDIT

**Date:** 2026-08-24 (harden pass / research-claim-audit-3)  
**Branch:** `research/research-claim-audit`  
**Auditor:** [`scripts/research_claim_verify.py`](../../scripts/research_claim_verify.py) + [`scripts/research_claim_mutant.py`](../../scripts/research_claim_mutant.py) + [`.grok/workflows/research-claim-audit.rhai`](../../.grok/workflows/research-claim-audit.rhai)  
**Inventory:** [`results/research_claim_inventory.json`](../../results/research_claim_inventory.json)  
**Verify result:** [`results/research_claim_verify_result.json`](../../results/research_claim_verify_result.json)  
**Outcome:** **FAIL** — `n_drift=1` (expected residual; drift fails the run, not a warning)

Auditor only. No charter/lock/`xau_loop_status.md`/`strategy_params.json`/`*.sha256` edits. No doc edits to chase green. No retunes, no holdout access, no `--live`, no `OrderSend`, no `src/mt5_arch` edits.

---

## Supersedes prior `mutant_caught: true`

Commit `7ac2233` reported `mutant_caught: true (4/4)`, but that result is **STALE**. The Mutant phase in that run was still effectively unproven: the pre-fix path did not demonstrate that seeded claims fail when the checker is broken (`gate_can_fail` was absent), and phase handoff depended on `/tmp` (Verify’s result died with the agent session). **This harden pass supersedes that gate claim.** Fresh evidence below requires both `mutant_caught: true` and `gate_can_fail: true` from `scripts/research_claim_mutant.py` in a single run.

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

Slim inventory `{file,line,kind,claimed,attribution}` under `results/research_claim_inventory.json`. Verifier-side rule C collapses `BLOCKED for KEEP` phrase components so a trailing `KEEP` token on that status line is not treated as an independent disposition claim.

---

## Verify — totals

| Metric | Value |
|--------|------:|
| n_ok | 432 |
| n_drift | **1** |
| n_unresolvable | 3 |
| n_exempt_secrets | 1 |
| n_claims | 436 |

Verification completed. **Run status is FAIL because `n_drift > 0`.** On this tree, **`n_drift == 1` is the expected residual** (Zacks README label). **`n_drift == 0` would mean checker regression** — investigate, do not celebrate.

### Drift table (`drift[]`)

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 21 | disposition | `New edge` | Zacks status=`SCHEMA_PASS` / overlay **BLOCKED** for KEEP (BLOCKED/SCHEMA_PASS, not New edge) |

This is real drift and belongs to open **PR #42**. This run deliberately leaves it standing as live proof the detector still fires. Docs were not edited to clear it.

### Exempt secrets (visible, not silent)

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 69 | path | `config/local.paths` | `gitignored:config/local.paths` |

### Unresolvable (non-fatal)

Recorded in `results/research_claim_verify_result.json` under `unresolvable[]` (metric/sha attribution gaps). Human decides whether to narrow extract or add attribution targets — not auto-ok.

---

## Checker-bug fixes (B, C) + anti-overcorrection (D)

### B — secrets-context / gitignored paths

**Bug:** `docs/README.md:69` (`config/local.paths`) was flagged as drift because it is not in `git ls-files`. The line is a never-commit instruction; the path is gitignored at `.gitignore:3`. Flagging it would push deleting a security instruction.

**Fix:** untracked path claims resolve as `exempt_secrets` when `git check-ignore` matches. Counted in `n_exempt_secrets` (visible). Secrets-looking prose alone does **not** exempt a path that is not gitignored.

### C — `BLOCKED for KEEP` over-extraction

**Bug:** `**Status:** SCHEMA_PASS / overlay **BLOCKED** for KEEP` is one phrase meaning blocked from reaching KEEP. The inventory also emitted a trailing `KEEP` claim that the checker treated as a standalone disposition.

**Fix:** verifier treats `BLOCKED for <DISPOSITION>` (markdown-tolerant) as a single phrase; the trailing token is `blocked_for_phrase_component` (ok), not an independent KEEP claim.

### D — negative controls (all must be RED)

From `results/research_claim_negative_controls.json`:

| Control | Result |
|---------|--------|
| missing path in non-secrets context | **RED** (drift) |
| path in secrets context that is **not** gitignored | **RED** (drift) |
| standalone `KEEP` (not part of `BLOCKED for KEEP`) | **RED** (drift) |
| `KEEP` asserted for a family the registry marks `SCREEN_FAIL` | **RED** (drift) |

`all_red: true`. If any control had gone green, B/C would be a blindfold and this run would stop with `ok=false`.

---

## Mutant gate (E)

| Field | Value |
|-------|-------|
| n_seeded | 4 |
| n_caught | 4 |
| mutant_caught | **true** |
| gate_can_fail | **true** |

Seeded (scratch only; worktree docs/research state untouched), routed through **`scripts/research_claim_verify.resolve_one`** (same predicates Verify uses):

| Seed kind | Kind | Mutant claimed | Status | Caught |
|-----------|------|----------------|--------|:------:|
| dead_path | path | `scripts/__mutant_dead_path_does_not_exist__.sh` | drift | yes |
| sha_one_char | sha | one-char corruption of `11099b2a` | unresolvable≠ok | yes |
| metric_digit | metric | flipped digit in `PF 0.553` | unresolvable≠ok | yes |
| inverted_disposition | disposition | `promote=true` (was `promote=no`) | drift | yes |

**`gate_can_fail`:** the mutant runner temporarily replaces `resolve_one` with an always-ok stub; seeded claims then report **0/4 caught**. That red outcome is required before restoring the live verifier and accepting `mutant_caught: true`. Without `gate_can_fail: true`, `mutant_caught` is not evidence.

Artifact: `results/research_claim_mutant_result.json`.

---

## Reproducibility (A)

- Verifier lives at `scripts/research_claim_verify.py` (not `/tmp`).
- ROOT from `git rev-parse --show-toplevel` (no hardcoded absolute worktree path).
- `--out` defaults to repo-relative `results/research_claim_verify_result.json`.
- Result JSON includes a populated `drift` array of `{file,line,kind,claimed,actual}`.
- Workflow `.rhai` and verifier/mutant scripts are tracked in git.
- Phase handoff uses `results/*.json` only — no `/tmp` persistence assumption.

Lint: `uv run ruff check src tests` and `uv run ruff check scripts/research_claim_verify.py scripts/research_claim_mutant.py` — green.

---

## THIS IS AN AUDIT, NOT AN AUTHORIZATION

- Does **not** change standing `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` / `promote=no` / `live_go=false`.
- Does **not** authorize develop screens, paper, or live.
- Does **not** revive closed `family_id`s.
- `n_drift=1` → this audit run is a **FAIL**, not a soft warning and not a green pass.
- The surviving Zacks `New edge` label is PR #42’s to fix — not this auditor’s to silence.
