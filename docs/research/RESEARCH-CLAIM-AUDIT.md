# RESEARCH-CLAIM-AUDIT

**Date:** 2026-08-25 (instruction corpus + consistency / research-claim-audit closeout)  
**Branch:** `research/research-claim-audit`  
**Tip base:** `52c6baf`  
**Auditor:** [`scripts/research_claim_verify.py`](../../scripts/research_claim_verify.py) + [`scripts/research_claim_instruction.py`](../../scripts/research_claim_instruction.py) + [`scripts/research_claim_mutant.py`](../../scripts/research_claim_mutant.py) + [`.grok/workflows/research-claim-audit.rhai`](../../.grok/workflows/research-claim-audit.rhai)  
**Inventory:** [`results/research_claim_inventory.json`](../../results/research_claim_inventory.json)  
**Verify:** [`results/research_claim_verify_result.json`](../../results/research_claim_verify_result.json)  
**Negative controls:** [`results/research_claim_negative_controls.json`](../../results/research_claim_negative_controls.json)  
**Mutant:** [`results/research_claim_mutant_result.json`](../../results/research_claim_mutant_result.json)  
**Allowlist:** [`results/research_claim_selfref_allow.json`](../../results/research_claim_selfref_allow.json)  
**Outcome:** **FAIL** — `n_drift=6` (1 expected residual Zacks `New edge` + 5 instruction/consistency findings reported, never repaired)

Auditor only. No charter/lock/`xau_loop_status.md`/`strategy_params.json`/`*.sha256` edits. No doc edits to chase green. No retunes, no holdout access, no `--live`, no `OrderSend`, no `src/mt5_arch` edits. Instruction files are **read-only sources of claims**.

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

**True score at `7ac2233` was 2/4 — the gate should have been red.** `unresolvable` does not fail the audit run; a corrupted charter digest landing there is exactly the integrity gap the mutant gate exists to detect. Current rule: **`caught` requires `status == "drift"`**. Live mutant result now: `mutant_caught=true`, `n_caught=8/8`, every row `status=drift`, and `gate_can_fail=true`.

---

## Standing rules

1. **New result buckets are fatal by default** until explicitly argued otherwise.
2. **An allowlist entry is only as true as the search behind it** — re-derive allowlists whenever the search scope changes.
3. **The auditor never edits the files that govern it — instruction drift is reported, never repaired.**

### Instruction-file integrity

```text
git diff --exit-code CLAUDE.md AGENTS.md  → exit 0 (byte-identical to pre-run state)
```

---

## Extract — per-kind counts

From `results/research_claim_inventory.json` (`n_claims=532`):

| Kind | Count |
|------|------:|
| path | 192 |
| disposition | 133 |
| link | 71 |
| symbol | 53 |
| metric | 53 |
| sha | 25 |
| consistency | 5 |
| **n_claims** | **532** |
| **n_instruction_claims** | **93** |
| **n_results_tracked** | **184** |

Corpus includes `docs/**` plus instruction files (`CLAUDE.md`, `AGENTS.md`, `README.md`, `mql5/README.md`) and consistency(broker_roster) claims. Instruction files are **not** metric oracles.

### Consistency kind

- **Authority:** `config/brokers/*.env` roster (`fpmarkets`, `vantage`, `wsf`)
- **Enumerating sites:** `scripts/19-run-htf-fib-backtest.sh`, `fetch_data.py`
- **Exempt:** `src/mt5_arch/file_bridge.py::default_bridge_dir` (generic, `MT5_BRIDGE_DIR`)

---

## Verify — totals

From `results/research_claim_verify_result.json`:

| Metric | Value |
|--------|------:|
| n_ok | 506 |
| n_drift | **6** |
| n_unresolvable | 0 |
| n_sha_unresolvable | **0** |
| n_exempt_secrets | **3** |
| n_self_referential | 10 (all allowlisted; `n_selfref_unallowlisted=0`) |
| n_skipped_dates | 10 |
| n_results_tracked | **184** |
| n_instruction_claims | **93** |
| n_claims | 532 |

Verification completed with `ok=true` (no sha-unresolvable / no unallowlisted selfref). **Run status is still FAIL because `n_drift > 0`.**

**Faithful residual note:** on the docs-only tree the **expected residual drift == 1** (Zacks `New edge` in `docs/README.md:21`). This run reports **`n_drift=6`** because instruction + consistency claims are now in corpus — five additional findings are **reported, never repaired**. `n_drift == 0` would still mean checker regression on the Zacks residual.

### Drift table (`drift[]`)

| # | File | Line | Kind | Claimed | Actual |
|---|------|-----:|------|---------|--------|
| 1 | `docs/README.md` | 21 | disposition | `New edge` | Zacks status=`SCHEMA_PASS` / overlay **BLOCKED** for KEEP (BLOCKED/SCHEMA_PASS, not New edge) |
| 2 | `CLAUDE.md` | 67 | disposition | `HTF Fib docs disagree on signal index` | stale instruction claim; `mql5/README.md` + `HOWTO-HTF-FIB.md` both document HTF Fib signal buffer **8** |
| 3 | `AGENTS.md` | 63 | disposition | `HTF Fib docs disagree on signal index` | (same as #2) |
| 4 | `fetch_data.py` | 1 | consistency | `broker_roster_coverage` | site missing roster brokers `['fpmarkets', 'wsf']`; roster=`['fpmarkets', 'vantage', 'wsf']` |
| 5 | `CLAUDE.md` | 52 | consistency | `instruction_prefix_in_roster` | instruction names `~/.mt5-exness` but `config/brokers/` has no `exness.env` |
| 6 | `AGENTS.md` | 48 | consistency | `instruction_prefix_in_roster` | (same as #5) |

**Per-kind drift counts:** disposition=3, consistency=3.

- **#1** = expected residual (Zacks lane / `docs/README.md` ownership — auditor does **not** edit that doc or the Zacks lane doc).
- **#2–#6** = instruction/consistency disagreements for a human to resolve; this workflow does **not** edit `CLAUDE.md` / `AGENTS.md` / `fetch_data.py` to clear them.

### Exempt secrets (`exempt_secrets[]`) — Fix B

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 69 | path | `config/local.paths` | `gitignored:config/local.paths` |
| `CLAUDE.md` | 87 | path | `config/local.paths` | `gitignored:config/local.paths` |
| `AGENTS.md` | 78 | path | `config/local.paths` | `gitignored:config/local.paths` |

**Checker-bug Fix B (secrets/gitignore exempt):** a path named in a secrets / never-commit context that is **actually gitignored** resolves as visible `exempt_secrets` (counts toward `n_exempt_secrets`, not `n_drift`). Secrets context alone does **not** exempt — see negative control `secrets_context_not_gitignored` (must stay RED).

### Checker-bug Fix C — `BLOCKED for KEEP`

**Fix C:** the phrase `BLOCKED for KEEP` / `**BLOCKED** for KEEP` is **one** status string. The trailing `KEEP` is **not** extracted or verified as a standalone disposition claim. A bare `KEEP` claim against a `SCREEN_FAIL` (or otherwise non-KEEP) family must still drift — see negative controls below.

---

## Negative controls — Fix B + Fix C (4/4 RED)

From `results/research_claim_negative_controls.json` (`all_red=true`, `n_controls=15`, `n_red=15`).

**Four Fix B / Fix C controls (all must stay RED):**

| Control | Name | Result | Guards |
|---------|------|--------|--------|
| missing path in non-secrets context | `missing_path_non_secrets` | **RED** (`drift`) | baseline path catch still works |
| path in secrets context, **not** gitignored | `secrets_context_not_gitignored` | **RED** (`drift`) | Fix B does not over-exempt |
| standalone `KEEP` (not `BLOCKED for KEEP`) | `standalone_KEEP` | **RED** (`drift`) | Fix C does not swallow bare KEEP |
| `KEEP` vs registry `SCREEN_FAIL` family | `KEEP_vs_SCREEN_FAIL_family` | **RED** (`drift`) | disposition equality still bites |

All four must stay RED. Green on any of these means the checker over-corrected.

Additional anti-blindfold controls (also RED): `metric_disagrees_named_writeup`, `named_writeup_omits_figure`, `genuine_self_referential`, `csv_substring_not_resolution`, `precision_disagreement_not_rounded_away`, `cross_family_numeric_collision`, `untracked_results_not_oracle`, `instruction_contradicts_target`, `roster_broker_missing_from_site`, `instruction_not_metric_oracle`, `generic_bridge_not_false_positive`.

---

## Mutant gate + `gate_can_fail`

From `results/research_claim_mutant_result.json`:

| Field | Value |
|-------|-------|
| n_seeded | 8 |
| n_caught | 8 |
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
| instruction_stale | path | scratch claim only — real `CLAUDE.md` untouched | **drift** | yes |
| consistency_broker | consistency | scratch site copy with FP Markets removed | **drift** | yes |

**`gate_can_fail`:** a broken always-ok verifier yields `broken_caught=0` (0/8) — red under the corrected scorer — then the live verifier is restored. Evidence string confirms both sides.

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
- `n_drift=6` → this audit run is a **FAIL**, not a soft warning.
- Expected residual on docs alone remains **1** (Zacks `New edge` in `docs/README.md:21`). The other five findings are instruction/consistency disagreements — reported, never repaired by this auditor.
- This auditor does **not** silence drift by editing `docs/README.md`, the Zacks lane doc, `CLAUDE.md`, or `AGENTS.md`.
- Auditor ≠ researcher. Report faithfully; do not retune, peek holdout, or promote.
