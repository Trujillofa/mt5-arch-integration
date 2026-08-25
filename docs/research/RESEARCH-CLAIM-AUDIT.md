# RESEARCH-CLAIM-AUDIT

**Date:** 2026-08-25 (oracle search scope / research-claim-audit closeout)  
**Branch:** `research/research-claim-audit`  
**Tip base:** `c682288`  
**Auditor:** [`scripts/research_claim_verify.py`](../../scripts/research_claim_verify.py) + [`scripts/research_claim_mutant.py`](../../scripts/research_claim_mutant.py) + [`.grok/workflows/research-claim-audit.rhai`](../../.grok/workflows/research-claim-audit.rhai)  
**Inventory:** [`results/research_claim_inventory.json`](../../results/research_claim_inventory.json)  
**Verify:** [`results/research_claim_verify_result.json`](../../results/research_claim_verify_result.json)  
**Negative controls:** [`results/research_claim_negative_controls.json`](../../results/research_claim_negative_controls.json)  
**Mutant:** [`results/research_claim_mutant_result.json`](../../results/research_claim_mutant_result.json)  
**Allowlist:** [`results/research_claim_selfref_allow.json`](../../results/research_claim_selfref_allow.json)  
**Outcome:** **FAIL** — `n_drift=1` (expected residual Zacks `New edge`; drift fails the run)

Auditor only. No charter/lock/`xau_loop_status.md`/`strategy_params.json`/`*.sha256` edits. No doc edits to chase green. No retunes, no holdout access, no `--live`, no `OrderSend`, no `src/mt5_arch` edits.

---

## STALE prior mutant claim (commit `7ac2233`) — superseded

Commit **`7ac2233`** (`docs(research): research-claim-audit FAIL (n_drift=3)`) reported `mutant_caught: true (4/4)`. **That `mutant_caught` claim is STALE and is superseded by this audit.**

Under the run-`7ac2233` / early scorer, a seed counted as **caught** whenever status moved off `ok`. That let `unresolvable` masquerade as a catch:

| seed | status at `7ac2233` | scored as caught then | counts as caught now |
|------|---------------------|:---------------------:|:--------------------:|
| dead_path | `drift` | yes | yes |
| sha_one_char | `unresolvable` | yes | **no** |
| metric_digit | `unresolvable` | yes | **no** |
| inverted_disposition | `drift` | yes | yes |

**True score at `7ac2233` was 2/4 — the gate should have been red.** `unresolvable` does not fail the audit run; a corrupted charter digest landing there is exactly the integrity gap the mutant gate exists to detect. Current rule: **`caught` requires `status == "drift"`**. Live mutant result now: `mutant_caught=true`, `n_caught=6/6`, every row `status=drift`, and `gate_can_fail=true`.

---

## Standing rules

1. **New result buckets are fatal by default** until explicitly argued otherwise.
2. **An allowlist entry is only as true as the search behind it** — re-derive allowlists whenever the search scope changes. An entry may not assert “no results artifact exists” unless the search covered the full tracked tree (record `n_searched`).

---

## Search scope (recorded property of this audit)

| Property | Value |
|----------|------:|
| Scope | tracked `results/**` via `git ls-files results/` |
| **n_results_tracked** | **184** (csv / `instrument_data/` / `research_claim_*` excluded) |
| Nested previously invisible | includes `results/xau_runs/*/report.json` |
| Preference | JSON over `.md` when both carry the figure |
| Attribution gate | path or content must tie to claimed `family_id` / lane |

Earlier partial searches (top-level `results/` only) produced allowlist reasons asserting “no separate results artifact” for claims whose oracles lived under `results/xau_runs/…` — **false justifications**. This run regenerates the allowlist after the full-tree search.

---

## Extract — per-kind counts

From `results/research_claim_inventory.json` (`n_claims=436`):

| Kind | Count |
|------|------:|
| disposition | 131 |
| path | 121 |
| link | 71 |
| metric | 53 |
| symbol | 35 |
| sha | 25 |
| **n_claims** | **436** |

---

## Corrected resolutions — BACKTEST-RECORD pooled PF

| Claim | Status | Artifact | JSON key |
|-------|--------|----------|----------|
| `BACKTEST-RECORD.md:95` `pooled PF 0.903` | **ok** | `results/xau_runs/2026-08-18_exog_london_fx_cosign_xau_follow_flat_screen_r1/report.json` | `/report/pooled/profit_factor` (= 0.902687… → rounds to 0.903) |
| `BACKTEST-RECORD.md:133` `pooled PF 0.90` | **ok** | same | `/report/pooled/profit_factor` (rounds to 0.90) |

These two left the allowlist.

---

## Verify — totals

From `results/research_claim_verify_result.json`:

| Metric | Value |
|--------|------:|
| n_ok | 415 |
| n_drift | **1** |
| n_unresolvable | 0 |
| n_sha_unresolvable | **0** |
| n_exempt_secrets | 1 |
| n_self_referential | 10 (all allowlisted; `n_selfref_unallowlisted=0`) |
| n_skipped_dates | 10 |
| n_results_tracked | **184** |
| n_claims | 436 |

Verification completed with `ok=true` (no sha-unresolvable). **Run status is still FAIL because `n_drift > 0`.** On this tree, **`n_drift == 1` is the expected residual** (Zacks `New edge`). **`n_drift == 0` would mean checker regression.**

### Drift table (`drift[]`)

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 21 | disposition | `New edge` | Zacks status=`SCHEMA_PASS` / overlay **BLOCKED** for KEEP (BLOCKED/SCHEMA_PASS, not New edge) |

Real drift; Zacks lane ownership. Left standing on purpose — this auditor does **not** edit `docs/README.md` or the Zacks lane doc to make the run green.

### US-index named write-up (still ok)

`docs/research/US-INDEX-SESSION-SCALP-DESIGN.md:92` → `PF 0.80` / `0.96 holdout` / `PF 1.20` against `results/us_index_session_scalp_backtest.md`.

### Exempt secrets (`exempt_secrets[]`) — Fix B

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 69 | path | `config/local.paths` | `gitignored:config/local.paths` |

**Checker-bug Fix B (secrets/gitignore exempt):** a path named in a secrets / never-commit context that is **actually gitignored** resolves as visible `exempt_secrets` (not `n_drift`). Secrets context alone does **not** exempt — see negative control `secrets_context_not_gitignored` (must stay RED).

### Checker-bug Fix C — `BLOCKED for KEEP`

**Fix C:** the phrase `BLOCKED for KEEP` / `**BLOCKED** for KEEP` is **one** status string. The trailing `KEEP` is **not** extracted or verified as a standalone disposition claim. A bare `KEEP` claim against a `SCREEN_FAIL` (or otherwise non-KEEP) family must still drift — see negative controls below.

---

## Negative controls — Fix B + Fix C (4/4 RED)

From `results/research_claim_negative_controls.json` (`all_red=true`, `n_controls=11`, `n_red=11`).

**Four Fix B / Fix C controls (all must stay RED):**

| Control | Name | Result | Guards |
|---------|------|--------|--------|
| missing path in non-secrets context | `missing_path_non_secrets` | **RED** (`drift`) | baseline path catch still works |
| path in secrets context, **not** gitignored | `secrets_context_not_gitignored` | **RED** (`drift`) | Fix B does not over-exempt |
| standalone `KEEP` (not `BLOCKED for KEEP`) | `standalone_KEEP` | **RED** (`drift`) | Fix C does not swallow bare KEEP |
| `KEEP` vs registry `SCREEN_FAIL` family | `KEEP_vs_SCREEN_FAIL_family` | **RED** (`drift`) | disposition equality still bites |

All four must stay RED. Green on any of these means the checker over-corrected.

Additional anti-blindfold controls (also RED): `metric_disagrees_named_writeup`, `named_writeup_omits_figure`, `genuine_self_referential`, `csv_substring_not_resolution`, `precision_disagreement_not_rounded_away`, `cross_family_numeric_collision`, `untracked_results_not_oracle`.

---

## Mutant gate + `gate_can_fail`

From `results/research_claim_mutant_result.json`:

| Field | Value |
|-------|-------|
| n_seeded | 6 |
| n_caught | 6 |
| mutant_caught | **true** |
| gate_can_fail | **true** |
| broken_caught | 0 |

Every `caught=true` row has **`status == "drift"`** (no exceptions):

| Seed kind | Kind | Mutant claimed | Status | Caught |
|-----------|------|----------------|--------|:------:|
| dead_path | path | `scripts/__mutant_dead_path_does_not_exist__.sh` | **drift** | yes |
| sha_one_char | sha | one-char corruption of `11099b2a` → `11099b20` | **drift** | yes |
| metric_digit | metric | `PF 0.89` (was `PF 0.80`) | **drift** | yes |
| metric_md_writeup | metric | `PF 0.89` (was `PF 0.80`) | **drift** | yes |
| metric_nested_json | metric | `pooled PF 0.909` (was `0.903`) | **drift** | yes |
| inverted_disposition | disposition | `promote=true` (was `promote=no`) | **drift** | yes |

**`gate_can_fail`:** a broken always-ok verifier yields `broken_caught=0` (0/6) — red under the corrected scorer — then the live verifier is restored. Evidence string confirms both sides.

**Supersedes the STALE `mutant_caught` claim from commit `7ac2233`.**

---

## Allowlist (regenerated)

10 entries after full-tree search — triage-table-only CLEARS rows, skeptic restatements, thin-n prose, one design narrative. Each carries `n_searched` and `searched_sample`. No entry claims “no artifact” on a top-level-only search.

---

## Reproducibility

- Tracked auditor: `scripts/research_claim_verify.py`, `scripts/research_claim_mutant.py`, `.grok/workflows/research-claim-audit.rhai`, this report, inventory, and verify/mutant/negcontrol JSON results.
- Phase handoff via `results/*.json` only — no `/tmp` dependency for audit evidence.
- Lint: `uv run ruff check src tests` and `uv run ruff check scripts/research_claim_verify.py scripts/research_claim_mutant.py`.

---

## THIS IS AN AUDIT, NOT AN AUTHORIZATION

- Does **not** change standing `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` / `promote=no` / `live_go=false`.
- Does **not** authorize develop screens, paper, or live.
- Does **not** revive closed `family_id`s.
- `n_drift=1` → this audit run is a **FAIL**, not a soft warning.
- The surviving residual drift is the Zacks `New edge` label in `docs/README.md:21` — Zacks lane ownership. This auditor does not silence it by editing `docs/README.md` or the Zacks lane doc.
- Auditor ≠ researcher. Report faithfully; do not retune, peek holdout, or promote.
