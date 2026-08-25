# RESEARCH-CLAIM-AUDIT

**Date:** 2026-08-25 (metric-oracle scope / research-claim-audit closeout)  
**Branch:** `research/research-claim-audit`  
**Tip:** on top of `5142fd3`  
**Auditor:** [`scripts/research_claim_verify.py`](../../scripts/research_claim_verify.py) + [`scripts/research_claim_mutant.py`](../../scripts/research_claim_mutant.py) + [`.grok/workflows/research-claim-audit.rhai`](../../.grok/workflows/research-claim-audit.rhai)  
**Inventory:** [`results/research_claim_inventory.json`](../../results/research_claim_inventory.json)  
**Verify:** [`results/research_claim_verify_result.json`](../../results/research_claim_verify_result.json)  
**Negative controls:** [`results/research_claim_negative_controls.json`](../../results/research_claim_negative_controls.json)  
**Mutant:** [`results/research_claim_mutant_result.json`](../../results/research_claim_mutant_result.json)  
**Allowlist:** [`results/research_claim_selfref_allow.json`](../../results/research_claim_selfref_allow.json)  
**Outcome:** **FAIL** — `n_drift=1` (expected residual Zacks label; drift fails the run)

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

**True score at `7ac2233` was 2/4 — the gate should have been red.** `unresolvable` does not fail the audit run; a corrupted charter digest landing there is exactly the integrity gap the mutant gate exists to detect. Current rule: **`caught` requires `status == "drift"`**. Live mutant result now: `mutant_caught=true`, `n_caught=5/5`, every row `status=drift`, and `gate_can_fail=true`.

---

## Standing rule — new buckets are fatal by default

**Any new result bucket is fatal by default until explicitly argued otherwise.**

Three consecutive runs failed the same way: a check degraded into a non-fatal bucket
(`unresolvable` in run 3, over-broad `self_referential` in run 4) rather than reporting
drift, and the run still looked green on that axis. This run inherits the rule:
`n_sha_unresolvable > 0` fails; `n_self_referential > 0` fails unless each instance is
in the reviewed allowlist with a per-claim reason. The next bucket added must inherit
fatal-by-default.

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

## Metric-oracle scope fix (this lineage)

**Bug:** `self_referential` treated any markdown corroboration as md-only, including
tracked `results/*.md` write-ups. Repo convention stores run write-ups as markdown
(~66 tracked `results/*.md` files). A doc corroborated by a results artifact that
happens to be `.md` is **verifiable**; only corroboration by the claiming file itself
is self-referential.

**Fixes:**
1. Tracked `results/**` is an artifact regardless of extension (JSON still preferred).
2. Explicit `Write-up:` / `Executed:` / `source:` / `artifact:` / “reproduced prior write-up” labels resolve **that** file first; miss → `drift`.
3. `self_referential` narrowed to claiming-file-only after named + results search.
4. `self_referential` fatal unless allowlisted (`results/research_claim_selfref_allow.json`).
5. ISO dates are not metrics (`n_skipped_dates=10`).
6. Metric match rejects `instrument_data/*.csv` substring coincidence.

### Named check — US-index figures (must be ok)

`docs/research/US-INDEX-SESSION-SCALP-DESIGN.md:92` → `results/us_index_session_scalp_backtest.md`:

| Claimed | Status |
|---------|--------|
| `PF 0.80` | **ok** (`named:results/us_index_session_scalp_backtest.md`) |
| `0.96 holdout` | **ok** (same) |
| `PF 1.20` | **ok** (same) |

(Also `holdout 0.50` → ok against the same write-up.)

---

## Verify — totals

From `results/research_claim_verify_result.json`:

| Metric | Value |
|--------|------:|
| n_ok | 413 |
| n_drift | **1** |
| n_unresolvable | 0 |
| n_sha_unresolvable | **0** |
| n_exempt_secrets | 1 |
| n_self_referential | 12 (all allowlisted; `n_selfref_unallowlisted=0`) |
| n_skipped_dates | 10 |
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

**Checker-bug Fix B (secrets/gitignore exempt):** a path named in a secrets / never-commit context that is **actually gitignored** resolves as visible `exempt_secrets` (not `n_drift`). Secrets context alone does **not** exempt — see negative control `secrets_context_not_gitignored` (must stay RED).

### Checker-bug Fix C — `BLOCKED for KEEP`

**Fix C:** the phrase `BLOCKED for KEEP` / `**BLOCKED** for KEEP` is **one** status string. The trailing `KEEP` is **not** extracted or verified as a standalone disposition claim. A bare `KEEP` claim against a `SCREEN_FAIL` (or otherwise non-KEEP) family must still drift — see negative controls below.

### Exog v4 SHA (still ok)

`3dec09efeee0bc11723c93c0e8ed1de683ac6179c176986cd8d4ba53e594edf5` →
`results/xau_charters/2026-08-15_exog_london_fx_cosign_xau_follow_flat_v4.json.sha256`.

---

## Negative controls — Fix B + Fix C (4/4 RED) + metric-oracle anti-blindfold

From `results/research_claim_negative_controls.json` (`all_red=true`, `n_red=8/8`):

**Four Fix B / Fix C controls (all must stay RED):**

| Control | Name | Result | Guards |
|---------|------|--------|--------|
| missing path in non-secrets context | `missing_path_non_secrets` | **RED** (`drift`) | baseline path catch still works |
| path in secrets context, **not** gitignored | `secrets_context_not_gitignored` | **RED** (`drift`) | Fix B does not over-exempt |
| standalone `KEEP` (not `BLOCKED for KEEP`) | `standalone_KEEP` | **RED** (`drift`) | Fix C does not swallow bare KEEP |
| `KEEP` vs registry `SCREEN_FAIL` family | `KEEP_vs_SCREEN_FAIL_family` | **RED** (`drift`) | disposition equality still bites |

**Metric-oracle anti-blindfold (also all RED):**

| Control | Expected | Result |
|---------|----------|--------|
| metric_disagrees_named_writeup | drift | RED |
| named_writeup_omits_figure | drift | RED |
| genuine_self_referential | self_referential | RED |
| csv_substring_not_resolution | not ok | RED |

Green on any of these means the checker over-corrected.

---

## Mutant gate + `gate_can_fail`

From `results/research_claim_mutant_result.json`:

| Field | Value |
|-------|-------|
| n_seeded | 5 |
| n_caught | 5 |
| mutant_caught | **true** |
| gate_can_fail | **true** |
| broken_caught | 0 |

Every `caught=true` row has **`status == "drift"`** (no exceptions):

| Seed kind | Kind | Mutant claimed | Status | Caught |
|-----------|------|----------------|--------|:------:|
| dead_path | path | `scripts/__mutant_dead_path_does_not_exist__.sh` | **drift** | yes |
| sha_one_char | sha | one-char corruption of `11099b2a` → `11099b20` | **drift** | yes |
| metric_digit | metric | `PF 0.89` (was `PF 0.80`) | **drift** | yes |
| metric_md_writeup | metric | `PF 0.89` (US-INDEX → results/*.md) | **drift** | yes |
| inverted_disposition | disposition | `promote=true` (was `promote=no`) | **drift** | yes |

**`gate_can_fail`:** a broken always-ok verifier yields `broken_caught=0` (0/5) — red under the corrected scorer — then the live verifier is restored. Evidence string confirms both sides.

**Supersedes the STALE `mutant_caught` claim from commit `7ac2233`.**

---

## Allowlist note

`n_self_referential=12` with reasoned entries (triage-table-only CLEARS rows, skeptic
restatements of those t-stats, BACKTEST-RECORD SoT prose, one design narrative).
If this list grows without new write-ups, treat growth as a smell — same failure mode
wearing an allowlist hat.

---

## Reproducibility

- Tracked auditor: `scripts/research_claim_verify.py`, `scripts/research_claim_mutant.py`, `.grok/workflows/research-claim-audit.rhai`, this report, inventory, and verify/mutant/negcontrol JSON results.
- Phase handoff via `results/*.json` only — no `/tmp` dependency for audit evidence.
- Lint: `uv run ruff check src tests` and `uv run ruff check scripts/research_claim_verify.py scripts/research_claim_mutant.py`.

---

## THIS IS AN AUDIT, NOT AN AUTHORIZATION

- Standing stays `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` / `promote=no` / `live_go=false`.
- Does **not** authorize develop screens, paper, or live.
- Does **not** revive closed `family_id`s.
- `n_drift=1` → this audit run is a **FAIL**, not a soft warning.
- The surviving residual drift is the Zacks `New edge` label in `docs/README.md:21` — PR #42 / Zacks lane ownership. This auditor does not silence it by editing those docs.
- Auditor ≠ researcher. Report faithfully; do not retune, peek holdout, or promote.
