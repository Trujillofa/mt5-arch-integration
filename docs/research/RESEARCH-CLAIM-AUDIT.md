# RESEARCH-CLAIM-AUDIT

**Date:** 2026-08-25 (oracle search scope / research-claim-audit-6)  
**Branch:** `research/research-claim-audit`  
**Tip base:** `541deb9`  
**Auditor:** [`scripts/research_claim_verify.py`](../../scripts/research_claim_verify.py) + [`scripts/research_claim_mutant.py`](../../scripts/research_claim_mutant.py)  
**Verify:** [`results/research_claim_verify_result.json`](../../results/research_claim_verify_result.json)  
**Allowlist:** [`results/research_claim_selfref_allow.json`](../../results/research_claim_selfref_allow.json)  
**Outcome:** **FAIL** — `n_drift=1` (Zacks residual)

Auditor only. No charter/lock/status/params/`.sha256`/`results/xau_runs/` edits. No doc edits toward green.

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

Run 5 searched only top-level `results/` files (plus hardcoded `xau_charters/` for SHAs). That partial search produced allowlist reasons asserting “no separate results artifact” for claims whose oracles lived under `results/xau_runs/…` — **false justifications**. This run deletes and regenerates the allowlist after the full-tree search.

---

## Corrected resolutions — BACKTEST-RECORD pooled PF

| Claim | Status | Artifact | JSON key |
|-------|--------|----------|----------|
| `BACKTEST-RECORD.md:95` `pooled PF 0.903` | **ok** | `results/xau_runs/2026-08-18_exog_london_fx_cosign_xau_follow_flat_screen_r1/report.json` | `/report/pooled/profit_factor` (= 0.902687… → rounds to 0.903) |
| `BACKTEST-RECORD.md:133` `pooled PF 0.90` | **ok** | same | `/report/pooled/profit_factor` (rounds to 0.90) |

These two left the allowlist.

---

## Verify — totals

| Metric | Value |
|--------|------:|
| n_ok | 415 |
| n_drift | **1** |
| n_unresolvable | 0 |
| n_sha_unresolvable | **0** |
| n_exempt_secrets | 1 |
| n_self_referential | 10 (all allowlisted; each has `n_searched` + sample) |
| n_selfref_unallowlisted | 0 |
| n_skipped_dates | 10 |
| n_results_tracked | **184** |
| n_claims | 436 |

### Drift table

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 21 | disposition | `New edge` | Zacks `SCHEMA_PASS` / **BLOCKED** |

Zacks label still present.

### US-index named write-up (still ok)

`docs/research/US-INDEX-SESSION-SCALP-DESIGN.md:92` → `PF 0.80` / `0.96 holdout` / `PF 1.20` against `results/us_index_session_scalp_backtest.md`.

---

## Negative controls (11/11 RED)

Run-5 eight retained, plus:

| Control | Result |
|---------|--------|
| precision_disagreement_not_rounded_away (`0.913` vs `0.9026`) | RED (drift) |
| cross_family_numeric_collision (exog PF under asia_box attribution) | RED (not ok) |
| untracked_results_not_oracle | RED (not ok) |

---

## Mutant gate (6/6)

| Seed | Status |
|------|--------|
| dead_path | drift |
| sha_one_char | drift |
| metric_digit | drift |
| metric_md_writeup | drift |
| **metric_nested_json** (`pooled PF 0.903`→`0.909` vs nested report.json) | **drift** |
| inverted_disposition | drift |

`mutant_caught=true`, `gate_can_fail=true`.

---

## Allowlist (regenerated)

10 entries after full-tree search — triage-table-only CLEARS rows, skeptic restatements, thin-n prose, one design narrative. Each carries `n_searched` and `searched_sample`. No entry claims “no artifact” on a top-level-only search.

---

## THIS IS AN AUDIT, NOT AN AUTHORIZATION

Standing unchanged (`RESEARCH_IDLE…` / promote=no / live_go=false). No screens/paper/live. `n_drift=1` → audit **FAIL**.
