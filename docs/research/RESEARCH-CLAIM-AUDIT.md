# RESEARCH-CLAIM-AUDIT

**Date:** 2026-08-25 (metric-oracle scope / research-claim-audit-5)  
**Branch:** `research/research-claim-audit`  
**Tip:** on top of `e9bd8cf`  
**Auditor:** [`scripts/research_claim_verify.py`](../../scripts/research_claim_verify.py) + [`scripts/research_claim_mutant.py`](../../scripts/research_claim_mutant.py) + [`.grok/workflows/research-claim-audit.rhai`](../../.grok/workflows/research-claim-audit.rhai)  
**Inventory:** [`results/research_claim_inventory.json`](../../results/research_claim_inventory.json)  
**Verify:** [`results/research_claim_verify_result.json`](../../results/research_claim_verify_result.json)  
**Allowlist:** [`results/research_claim_selfref_allow.json`](../../results/research_claim_selfref_allow.json)  
**Outcome:** **FAIL** — `n_drift=1` (expected residual Zacks label; drift fails the run)

Auditor only. No charter/lock/`xau_loop_status.md`/`strategy_params.json`/`*.sha256` edits. No doc edits to chase green.

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

## Metric-oracle scope fix (this run)

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

### Drift table

| File | Line | Kind | Claimed | Actual |
|------|-----:|------|---------|--------|
| `docs/README.md` | 21 | disposition | `New edge` | Zacks `SCHEMA_PASS` / overlay **BLOCKED** |

Zacks label still present. Not edited.

### Exog v4 SHA (still ok)

`3dec09efeee0bc11723c93c0e8ed1de683ac6179c176986cd8d4ba53e594edf5` →
`results/xau_charters/2026-08-15_exog_london_fx_cosign_xau_follow_flat_v4.json.sha256`.

---

## Negative controls (8/8 RED)

Prior B/C controls retained, plus metric-oracle anti-blindfold:

| Control | Expected | Result |
|---------|----------|--------|
| missing_path_non_secrets | drift | RED |
| secrets_context_not_gitignored | drift | RED |
| standalone_KEEP | drift | RED |
| KEEP_vs_SCREEN_FAIL_family | drift | RED |
| metric_disagrees_named_writeup | drift | RED |
| named_writeup_omits_figure | drift | RED |
| genuine_self_referential | self_referential | RED |
| csv_substring_not_resolution | not ok | RED |

---

## Mutant gate (5/5)

| Field | Value |
|-------|-------|
| n_seeded | 5 |
| n_caught | 5 |
| mutant_caught | **true** |
| gate_can_fail | **true** |

Every `caught=true` has `status=drift`:

| Seed | Status |
|------|--------|
| dead_path | drift |
| sha_one_char | drift |
| metric_digit (restating HOWTO) | drift |
| metric_md_writeup (US-INDEX → results/*.md) | drift |
| inverted_disposition | drift |

---

## Allowlist note

`n_self_referential=12` with reasoned entries (triage-table-only CLEARS rows, skeptic
restatements of those t-stats, BACKTEST-RECORD SoT prose, one design narrative).
If this list grows without new write-ups, treat growth as a smell — same failure mode
wearing an allowlist hat.

---

## THIS IS AN AUDIT, NOT AN AUTHORIZATION

- Standing stays `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` / promote=no / live_go=false.
- Does not authorize screens, paper, or live.
- Does not revive closed `family_id`s.
- `n_drift=1` → audit **FAIL**. Zacks `New edge` is PR #42’s to fix.
