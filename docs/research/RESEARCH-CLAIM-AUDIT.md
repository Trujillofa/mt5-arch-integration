# RESEARCH-CLAIM-AUDIT

**Date:** 2026-08-24 (claim-audit closeout / n_drift=1 residual)  
**Branch:** `research/research-claim-audit`  
**Auditor:** [`scripts/research_claim_verify.py`](../../scripts/research_claim_verify.py) + [`scripts/research_claim_mutant.py`](../../scripts/research_claim_mutant.py) + [`.grok/workflows/research-claim-audit.rhai`](../../.grok/workflows/research-claim-audit.rhai)  
**Inventory:** [`results/research_claim_inventory.json`](../../results/research_claim_inventory.json)  
**Verify result:** [`results/research_claim_verify_result.json`](../../results/research_claim_verify_result.json)  
**Negative controls:** [`results/research_claim_negative_controls.json`](../../results/research_claim_negative_controls.json)  
**Mutant result:** [`results/research_claim_mutant_result.json`](../../results/research_claim_mutant_result.json)  
**Outcome:** **FAIL** — `n_drift=1` (expected residual; drift fails the run, not a warning)

Auditor only. No charter/lock/`xau_loop_status.md`/`strategy_params.json`/`*.sha256` edits. No doc edits to chase green. No retunes, no holdout access, no `--live`, no `OrderSend`, no `src/mt5_arch` edits.

---

## STALE prior mutant claim (commit `7ac2233`) — superseded

Commit **`7ac2233`** (`docs(research): research-claim-audit FAIL (n_drift=3)`) reported `mutant_caught: true (4/4)`. **That mutant_caught claim is STALE and is superseded by this audit.**

Under the run-`7ac2233` / run-`7cb3ce5` scorer, a seed counted as **caught** whenever status moved off `ok`. That let `unresolvable` masquerade as a catch:

| seed | status at `7ac2233` | scored as caught then | counts as caught now |
|------|---------------------|:---------------------:|:--------------------:|
| dead_path | `drift` | yes | yes |
| sha_one_char | `unresolvable` | yes | **no** |
| metric_digit | `unresolvable` | yes | **no** |
| inverted_disposition | `drift` | yes | yes |

**True score at `7ac2233` was 2/4 — the gate should have been red.** `unresolvable` does not fail the audit run; a corrupted charter digest landing there is exactly the integrity gap the mutant gate exists to detect. Current rule: **`caught` requires `status == "drift"`**. Live mutant result now: `mutant_caught=true`, `n_caught=4/4`, every row `status=drift`, and `gate_can_fail=true`.

---

## Extract — per-kind counts

From `results/research_claim_inventory.json` (`n_claims=436`):

| Kind | Count |
|------|------:|
| path | 121 |
| link | 71 |
| sha | 25 |
| symbol | 35 |
| metric | 53 |
| disposition | 131 |
| **n_claims** | **436** |

---

## Verify — totals

From `results/research_claim_verify_result.json`:

| Metric | Value |
|--------|------:|
| n_ok | 429 |
| n_drift | **1** |
| n_unresolvable | 0 |
| n_sha_unresolvable | **0** (fatal if >0) |
| n_exempt_secrets | 1 |
| n_self_referential | 6 |
| n_claims | 436 |

Verification completed with `ok=true` (no sha-unresolvable). **Run status is still FAIL because `n_drift > 0`.** On this tree, **`n_drift == 1` is the expected residual** (Zacks `New edge`). **`n_drift == 0` would mean checker regression.**

### Drift table (`drift[]`)

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 21 | disposition | `New edge` | Zacks status=`SCHEMA_PASS` / overlay **BLOCKED** for KEEP (BLOCKED/SCHEMA_PASS, not New edge) |

Real drift; belongs to open **PR #42** / the Zacks lane doc. Left standing on purpose — this auditor does **not** edit `docs/README.md` or the Zacks lane doc to make the run green.

### Exempt secrets (`exempt_secrets[]`) — Fix B

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 69 | path | `config/local.paths` | `gitignored:config/local.paths` |

**Checker-bug Fix B (secrets/gitignore exempt):** a path named in a secrets / never-commit context that is **actually gitignored** resolves as visible `exempt_secrets` (counts toward `n_ok`, not `n_drift`). Secrets context alone does **not** exempt — see negative control `secrets_context_not_gitignored` (must stay RED).

### Checker-bug Fix C — `BLOCKED for KEEP`

**Fix C:** the phrase `BLOCKED for KEEP` / `**BLOCKED** for KEEP` is **one** status string. The trailing `KEEP` is **not** extracted or verified as a standalone disposition claim. A bare `KEEP` claim against a `SCREEN_FAIL` (or otherwise non-KEEP) family must still drift — see negative controls below.

### SHA integrity (fatal unresolvable)

A `kind=sha` claim that cannot be resolved is an **integrity failure**, not a neutral shrug. Result field **`n_sha_unresolvable`**: any value `> 0` fails the run. Current run: **0**.

**Named check — exog v4 charter SHA:**  
`docs/research/MULTI-INSTRUMENT-THESIS-exog_london_fx_cosign_xau_follow_flat_v1.md:5` claims  
`3dec09efeee0bc11723c93c0e8ed1de683ac6179c176986cd8d4ba53e594edf5`  
→ **OK** against `results/xau_charters/2026-08-15_exog_london_fx_cosign_xau_follow_flat_v4.json.sha256`  
(attribution prose `exog v4 charter` resolved via `family_id` + `vN`; this was `unresolvable` under run 3).

Attribution matching resolves on `family_id` + `vN`, accepts `.json.sha256` / `.sha256` sidecars, and falls back to hashing the charter `.json` when no sidecar exists. A located digest that **disagrees** with the claim is **`drift`**, not `unresolvable`.

### Self-referential metrics

Metric claims whose only corroboration is another markdown file are reported as **`self_referential`** (`n_self_referential=6`), not folded into `unresolvable`. Prefer `results/*.json` as metric truth.

---

## Negative controls — Fix B + Fix C (all 4 RED)

From `results/research_claim_negative_controls.json` (`all_red=true`, `n_red=4/4`):

| Control | Name | Result | Guards |
|---------|------|--------|--------|
| missing path in non-secrets context | `missing_path_non_secrets` | **RED** (`drift`) | baseline path catch still works |
| path in secrets context, **not** gitignored | `secrets_context_not_gitignored` | **RED** (`drift`) | Fix B does not over-exempt |
| standalone `KEEP` (not `BLOCKED for KEEP`) | `standalone_KEEP` | **RED** (`drift`) | Fix C does not swallow bare KEEP |
| `KEEP` vs registry `SCREEN_FAIL` family | `KEEP_vs_SCREEN_FAIL_family` | **RED** (`drift`) | disposition equality still bites |

All four must stay RED. Green on any of these means the checker over-corrected.

---

## Mutant gate + `gate_can_fail`

From `results/research_claim_mutant_result.json`:

| Field | Value |
|-------|-------|
| n_seeded | 4 |
| n_caught | 4 |
| mutant_caught | **true** |
| gate_can_fail | **true** |
| broken_caught | 0 |

Every `caught=true` row has **`status == "drift"`** (no exceptions):

| Seed kind | Kind | Mutant claimed | Status | Caught |
|-----------|------|----------------|--------|:------:|
| dead_path | path | `scripts/__mutant_dead_path_does_not_exist__.sh` | **drift** | yes |
| sha_one_char | sha | one-char corruption of `11099b2a` → `11099b20` | **drift** | yes |
| metric_digit | metric | `PF 0.89` (was `PF 0.80`) | **drift** | yes |
| inverted_disposition | disposition | `promote=true` (was `promote=no`) | **drift** | yes |

**`gate_can_fail`:** a broken always-ok verifier yields `broken_caught=0` (0/4) — red under the corrected scorer — then the live verifier is restored. Evidence string confirms both sides.

Supersedes the STALE `mutant_caught` claim from commit **`7ac2233`**.

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
- The surviving residual drift is the Zacks `New edge` label in `docs/README.md:21` — PR #42 / Zacks lane ownership. This auditor does not silence it by editing those docs.
- Auditor ≠ researcher. Report faithfully; do not retune, peek holdout, or promote.
