# RESEARCH-CLAIM-AUDIT

**Date:** 2026-08-25 (instruction corpus + consistency / research-claim-audit-7)  
**Branch:** `research/research-claim-audit`  
**Base:** `6b43f25`  
**Auditor:** [`scripts/research_claim_verify.py`](../../scripts/research_claim_verify.py) + [`scripts/research_claim_instruction.py`](../../scripts/research_claim_instruction.py) + [`scripts/research_claim_mutant.py`](../../scripts/research_claim_mutant.py)  
**Verify:** [`results/research_claim_verify_result.json`](../../results/research_claim_verify_result.json)  
**Outcome:** **FAIL** — `n_drift=6` (Zacks + instruction/consistency findings)

Auditor only. Instruction files are **read-only sources of claims**.

---

## Standing rules

1. New result buckets are fatal by default until explicitly argued otherwise.
2. An allowlist entry is only as true as the search behind it — re-derive when search scope changes.
3. **The auditor never edits the files that govern it — instruction drift is reported, never repaired.**

### Instruction-file integrity

```text
git diff --exit-code CLAUDE.md AGENTS.md  → exit 0 (byte-identical to pre-run state)
```

---

## Corpus

| Source | Claims |
|--------|------:|
| `CLAUDE.md` | 47 |
| `AGENTS.md` | 40 |
| `README.md` (root) | 4 |
| `mql5/README.md` | 2 |
| `docs/**` | 436 |
| **n_claims** | **532** |
| **n_instruction_claims** | **93** |
| **n_results_tracked** | **184** (unchanged from run 6) |

Instruction files are **not** metric oracles.

### Consistency kind

- **Authority:** `config/brokers/*.env` roster (`fpmarkets`, `vantage`, `wsf`)
- **Enumerating sites:** `scripts/19-run-htf-fib-backtest.sh`, `fetch_data.py`
- **Exempt:** `src/mt5_arch/file_bridge.py::default_bridge_dir` (generic, `MT5_BRIDGE_DIR`)

---

## Drift table (known findings named)

| # | File:line | Kind | Finding |
|---|-----------|------|---------|
| 1 | `CLAUDE.md:67` (also `AGENTS.md:63`) | disposition | **HTF Fib claim stale** — says docs disagree on signal index; both `mql5/README.md` and `docs/HOWTO-HTF-FIB.md` document buffer **8** (authoritative map v1.42+) |
| 2 | `CLAUDE.md:52` (also `AGENTS.md:48`) | consistency | **Broker roster gap** — instruction names `~/.mt5-exness` but `config/brokers/` has no `exness.env` (roster = fpmarkets, vantage, wsf) |
| 3 | `fetch_data.py:1` | consistency | **fetch_data asymmetry** — missing roster brokers `fpmarkets`, `wsf` (Vantage-only paths) |
| 4 | `docs/README.md:21` | disposition | **Zacks** `New edge` vs lane `SCHEMA_PASS` / **BLOCKED** |

`n_drift=6` (findings 1–2 each appear in CLAUDE + AGENTS).

---

## Verify totals

| Metric | Value |
|--------|------:|
| n_ok | 506 |
| n_drift | **6** |
| n_unresolvable | 0 |
| n_sha_unresolvable | 0 |
| n_self_referential | 10 (allowlisted; `n_searched` intact) |
| n_selfref_unallowlisted | 0 |
| n_results_tracked | **184** |
| n_instruction_claims | **93** |

Run-6 invariants preserved.

---

## Negative controls (15/15)

Run-6 eleven retained, plus:

| Control | Pass criterion |
|---------|----------------|
| instruction_contradicts_target | drift |
| roster_broker_missing_from_site | drift |
| instruction_not_metric_oracle | not ok |
| generic_bridge_not_false_positive | ok (exemption holds) |

---

## Mutant (8/8, all `status=drift`)

| Seed | Notes |
|------|-------|
| dead_path / sha_one_char / metric_* / inverted_disposition | prior |
| metric_nested_json | `results/xau_runs/*/report.json` |
| **instruction_stale** | scratch claim only — real `CLAUDE.md` untouched |
| **consistency_broker** | scratch site copy with FP Markets removed |

`mutant_caught=true`, `gate_can_fail=true`.

---

## THIS IS AN AUDIT, NOT AN AUTHORIZATION

Standing unchanged. Findings 1–3 are disagreements for a human to resolve (doc vs roster vs code) — this workflow does not edit `CLAUDE.md` / `AGENTS.md` to clear them.
