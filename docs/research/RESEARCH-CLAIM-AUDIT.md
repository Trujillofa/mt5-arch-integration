# RESEARCH-CLAIM-AUDIT

**Date:** 2026-08-24 (mutant-scoring + SHA attribution fix / research-claim-audit-4)  
**Branch:** `research/research-claim-audit`  
**Auditor:** [`scripts/research_claim_verify.py`](../../scripts/research_claim_verify.py) + [`scripts/research_claim_mutant.py`](../../scripts/research_claim_mutant.py) + [`.grok/workflows/research-claim-audit.rhai`](../../.grok/workflows/research-claim-audit.rhai)  
**Inventory:** [`results/research_claim_inventory.json`](../../results/research_claim_inventory.json)  
**Verify result:** [`results/research_claim_verify_result.json`](../../results/research_claim_verify_result.json)  
**Outcome:** **FAIL** — `n_drift=1` (expected residual; drift fails the run, not a warning)

Auditor only. No charter/lock/`xau_loop_status.md`/`strategy_params.json`/`*.sha256` edits. No doc edits to chase green. No retunes, no holdout access, no `--live`, no `OrderSend`, no `src/mt5_arch` edits.

---

## Run 3’s `mutant_caught: true (4/4)` was wrong

Commit `7cb3ce5` / run 3 scored a seed as **caught** whenever status moved off `ok`. Under that criterion, `unresolvable` counted as caught. Real run-3 outcomes:

| seed | status | scored as caught | should count |
|------|--------|:----------------:|:------------:|
| dead_path | `drift` | yes | yes |
| sha_one_char | `unresolvable` | yes | **no** |
| metric_digit | `unresolvable` | yes | **no** |
| inverted_disposition | `drift` | yes | yes |

**True score was 2/4 — the gate should have been red.** `unresolvable` does not fail the audit run; a corrupted charter digest landing there is exactly the integrity gap the mutant gate exists to detect. This pass supersedes run 3’s mutant claim: **`caught` requires `status == "drift"`**.

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

---

## Verify — totals

| Metric | Value |
|--------|------:|
| n_ok | 429 |
| n_drift | **1** |
| n_unresolvable | 0 |
| n_sha_unresolvable | **0** (fatal if >0) |
| n_exempt_secrets | 1 |
| n_self_referential | 6 |
| n_claims | 436 |

Verification completed with `ok=true` (no sha-unresolvable). **Run status is still FAIL because `n_drift > 0`.** On this tree, **`n_drift == 1` is the expected residual**. **`n_drift == 0` would mean checker regression.**

### Drift table (`drift[]`)

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 21 | disposition | `New edge` | Zacks status=`SCHEMA_PASS` / overlay **BLOCKED** for KEEP |

Real drift; belongs to open **PR #42**. Left standing on purpose.

### Exempt secrets

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 69 | path | `config/local.paths` | `gitignored:config/local.paths` |

### SHA integrity (fatal unresolvable)

A `kind=sha` claim that cannot be resolved is an **integrity failure**, not a neutral shrug. Freeze-before-peek is load-bearing; digests must not degrade into the non-fatal `unresolvable` bucket. Result field **`n_sha_unresolvable`**: any value `> 0` fails the run.

**Exog v4 charter SHA** (named check):  
`docs/research/MULTI-INSTRUMENT-THESIS-exog_london_fx_cosign_xau_follow_flat_v1.md:5` claims  
`3dec09efeee0bc11723c93c0e8ed1de683ac6179c176986cd8d4ba53e594edf5`  
→ **OK** against `results/xau_charters/2026-08-15_exog_london_fx_cosign_xau_follow_flat_v4.json.sha256`.

Attribution matching now resolves on `family_id` + `vN` (prose like `exog v4 charter` or `early_server_range_break_flat_v2.json`), accepts `.json.sha256` / `.sha256` sidecars, and falls back to hashing the charter `.json` when no sidecar exists. A located digest that **disagrees** with the claim is **`drift`**, not `unresolvable`.

### Self-referential metrics

Metric claims whose only corroboration is another markdown file (or the claiming doc itself) are reported as **`self_referential`** (`n_self_referential=6`), not folded into `unresolvable`. Prefer `results/*.json` as metric truth. Examples: `SIGNAL-EDGE-TRIAGE.md` `+70.19` / `n=7819` (md-only).

---

## Negative controls (still 4/4 RED)

| Control | Result |
|---------|--------|
| missing path in non-secrets context | **RED** |
| path in secrets context, not gitignored | **RED** |
| standalone `KEEP` (not `BLOCKED for KEEP`) | **RED** |
| `KEEP` vs registry `SCREEN_FAIL` family | **RED** |

---

## Mutant gate (corrected scorer)

| Field | Value |
|-------|-------|
| n_seeded | 4 |
| n_caught | 4 |
| mutant_caught | **true** |
| gate_can_fail | **true** |

Every `caught=true` row has **`status == "drift"`** (no exceptions):

| Seed kind | Kind | Mutant claimed | Status | Caught |
|-----------|------|----------------|--------|:------:|
| dead_path | path | `scripts/__mutant_dead_path_does_not_exist__.sh` | **drift** | yes |
| sha_one_char | sha | one-char corruption of `11099b2a` | **drift** | yes |
| metric_digit | metric | `PF 0.89` (was `PF 0.80` in restating `HOWTO-US-INDEX-SCALP.md`) | **drift** | yes |
| inverted_disposition | disposition | `promote=true` (was `promote=no`) | **drift** | yes |

Metric mutants are seeded in a **restating** doc (not `BACKTEST-RECORD.md`), so the `results/*.json` oracle survives the mutation. Run 3 seeded `BACKTEST-RECORD.md:94` and corrupted its own SoT — `unresolvable` was honest and the seed was untestable by construction.

**`gate_can_fail`:** under the **new** scorer, a broken always-ok verifier yields 0/4 caught (red), then the live verifier is restored. Artifact: `results/research_claim_mutant_result.json`.

---

## Reproducibility

- Tracked auditor scripts + workflow; ROOT via `git rev-parse`; `--out` repo-relative (absolute path emitted if outside ROOT — no crash).
- Phase handoff via `results/*.json` only.
- Lint: `uv run ruff check src tests` and `uv run ruff check scripts/research_claim_verify.py scripts/research_claim_mutant.py` — green.

---

## THIS IS AN AUDIT, NOT AN AUTHORIZATION

- Does **not** change standing `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` / `promote=no` / `live_go=false`.
- Does **not** authorize develop screens, paper, or live.
- Does **not** revive closed `family_id`s.
- `n_drift=1` → this audit run is a **FAIL**, not a soft warning.
- The surviving Zacks `New edge` label is PR #42’s to fix — not this auditor’s to silence.
