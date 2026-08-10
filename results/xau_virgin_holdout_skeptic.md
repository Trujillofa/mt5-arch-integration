# XAU Virgin Holdout — Hostile Quant Skeptic Review

**Date:** 2026-08-06  
**Stance:** Fail closed. `real=true` survivors only under hard gates **and** a true virgin window. Soft / underpowered / contaminated / skipped ≠ promote.  
**Pipeline phase:** Virgin sealed holdout of frozen champions (post develop KEEP_OPTIMIZING exhaust).

**Artifacts reviewed:**

| Path | Role |
|------|------|
| `results/xau_data_frontier.json` | Refresh + virgin bar frontier |
| `results/xau_frozen_champions_catalog.json` | 8 frozen configs (baseline + refined_develop) |
| `results/xau_virgin_holdout_eval.json` | Sealed virgin eval or explicit skip |
| `results/xau_lane_deep_opt_summary.md` | Prior deep-opt summary + contamination notes |
| `results/xau_lane_deep_opt_skeptic.md` | Prior hostile review (contaminated HO) |
| `results/xau_lane_survivors.json` | Prior (non-virgin) hard_pass survivor list |
| `results/xau_lane_opt_charter.json` | Doctrine; `prior_contamination_note` |
| `results/xau_loop_status.md` | Develop program complete; blocked on virgin data |
| `results/xau_preregistered_skeptic.md` | Design-level peek of 2026-01+ window |
| `xauusd_data.csv` | Ground-truth H1 end timestamps |

**Not present (expected when skipped):** `results/xau_virgin_survivors.json` — correctly absent; no survivor file fabricated.

---

## Executive summary

| Question | Verdict |
|----------|---------|
| Was a true virgin window available? | **NO** — `n_virgin_bars=2` H1; threshold ≥24 |
| Was virgin eval skipped for the right reason? | **YES** — `insufficient bars after last_peeked_end` |
| Any fake promote / fake survivor? | **NO** — `n_evaluated=0`; no candidate rewrite from virgin |
| Prior hard_pass count as virgin? | **NO** — 2026-01+ holdout is design-contaminated |
| `real=true` virgin hard_pass survivors | **0** |
| Disposition | **WAIT_DATA** |

**One-line:** Data refreshed; frontier measured; virgin window still empty of usable sample; catalog frozen offline; **no evaluation, no promote — wait for ≥24 H1 bars strictly after 2026-08-06 18:00 UTC.**

---

## 1. Was the virgin window truly unused before?

### 1.1 Definition (this pipeline)

From workflow / frontier contract:

| Field | Value |
|-------|--------|
| `last_peeked_end` | **2026-08-06 18:00:00+00:00** (prior shortlist / deep-opt / refine data end) |
| `virgin_start` | **2026-08-06 19:00:00+00:00** (first bar strictly after last peek) |
| `virgin_available` | `(max_H1 > last_peeked_end)` **and** `(n_H1 with time > last_peeked_end) ≥ 24` |
| User criterion | bars **after 2026-08-06 only** for promotion-grade virgin claims |

### 1.2 Measured frontier (`xau_data_frontier.json`)

| Field | Value |
|-------|--------|
| `before_max` | 2026-08-06 18:00:00+00:00 |
| `after_max` | 2026-08-06 20:00:00+00:00 |
| `n_h1` | 11637 |
| `n_virgin_bars` | **2** |
| `virgin_available` | **false** |
| `refresh_ok` | true |

### 1.3 Ground-truth H1 bars after peek (from `xauusd_data.csv`)

Only **two** H1 bars exist past last peek — still on calendar day 2026-08-06:

| time (UTC) | note |
|------------|------|
| 2026-08-06 19:00 | first post-peek bar |
| 2026-08-06 20:00 | latest H1 in file |

- Bars with `time > 2026-08-06 23:59:59 UTC` (strictly **after** calendar 2026-08-06): **0**
- Bars usable as a trade sample for n≥20 hard gates: **none** (2 H1 bars cannot produce n≥20 closed trades under any frozen catalog strategy)

### 1.4 Independence / “unused before” audit

| Claim | Status |
|-------|--------|
| Bars **after** 2026-08-06 18:00 never used in develop search / refine | **YES** — develop searches used `time < 2026-01-01`; refine runs develop-only |
| Bars after 2026-08-06 18:00 never used in prior sealed 2026-01+ holdout | **YES** — prior holdout ends at data available then; those peeks were of **2026-01 → ~2026-08-06 18:00**, not the two new hours |
| Calendar day **after** 2026-08-06 exists in file | **NO** — zero post-calendar-day bars |
| Enough virgin sample to evaluate | **NO** |

**Skeptic nuance:** The two 19:00–20:00 bars are *technically* post-peek and were not optimized on. They are **not** a virgin *window* in any statistical sense. Calling them “unused” is true; calling them “evaluable virgin holdout” would be false. Prior contamination of **2026-01+** remains fully in force for any recycle of that window.

### 1.5 Prior contamination (why virgin is required at all)

From charter + prior skeptics (not re-litigated; binding for promote):

> `prior_contamination_note`: *“2026-01+ window already used in prior shortlist OOS; any future promote claim needs virgin holdout or explicit contamination disclosure.”*

- Preregistered holdout + deep-opt sealed pass both used **2026-01+** — design-level family contamination for vol_gate residual shape.
- Sole prior survivor `vol_gate_sparse` (`hard_pass`, n=20 knife-edge, develop PF 1.36 < holdout PF 2.12) is a **research freeze**, not virgin confirmation.
- Develop KEEP_OPTIMIZING fires (donchian ablate, atr_trail trade-count, htf_fib widen) stayed develop-only; they correctly **did not** re-mine 2026-01+.

**Verdict §1:** True unused bars exist only as a 2-bar stub after last peek; **no calendar day after 2026-08-06**; virgin window **not available** for sealed evaluation.

---

## 2. If skipped: confirm correct skip, no fake promote

### 2.1 Eval artifact (`xau_virgin_holdout_eval.json`)

```json
{
  "skipped": true,
  "reason": "insufficient bars after last_peeked_end",
  "n_evaluated": 0,
  "catalog_n_entries": 8,
  "safety": "offline only; no retune; virgin not evaluated",
  "frontier": { "n_virgin_bars": 2, "virgin_available": false, ... }
}
```

### 2.2 Skip correctness checklist

| Check | Result |
|-------|--------|
| `virgin_available == false` matches measured n=2 < 24 | **PASS** |
| Skip reason explicit and accurate | **PASS** |
| `n_evaluated == 0` | **PASS** |
| No fabricated per-config virgin metrics | **PASS** |
| No `xau_virgin_survivors.json` inventing hard_pass | **PASS** (absent) |
| Catalog not re-ranked by “virgin” outcomes | **PASS** (no outcomes) |
| `xau_candidate_params.json` not rewritten from virgin best-NP | **PASS** (no virgin ranking) |
| Offline only / no `--live` | **PASS** |
| No paper/live GO asserted by eval | **PASS** |

### 2.3 What must **not** be claimed from this fire

- Not: “virgin holdout confirmed edge”
- Not: “vol_gate survived virgin”
- Not: “catalog of 8 passed sealed future data”
- Not: LIVE_GO / PAPER_GO from this pass

**Verdict §2:** Skip is **correct and complete**. No fake promote path.

---

## 3. If evaluated: look-ahead, sample size, multiple testing

**N/A — evaluation did not run** (`n_evaluated=0`).

Pre-registered standards for when data arrives (do not relax later):

| Gate / concern | Standard |
|----------------|----------|
| Hard gates (virgin) | PF > 1.5, WR > 55, DD < 10, **n ≥ 20** |
| Underpowered | n < 20 → **not** hard_pass; never soft-promote |
| Look-ahead | Fib via shared `htf_fib_core` (`active = c + right`); no future bar leakage in simulators |
| Window | **Only** `time > last_peeked_end` (not re-use 2026-01+) |
| Catalog multiplicity | **8** frozen configs (`catalog_n_entries=8`) — multiplicity penalty applies; one hard_pass among 8 is weaker than one among 1 |
| Multiple testing | Prior ~2.9k develop evals + refine packs already selected these 8; virgin is **confirmation**, not another free search |
| Retune after virgin metrics | **Forbidden** for any promote claim |
| `real=true` | Only `hard_pass` + true virgin window + not underpowered |

### Catalog under test (frozen; for future single sealed pass)

| id | lane | role |
|----|------|------|
| `baseline_vol_gate_sparse` | vol_gate_sparse | baseline_champion (prior contaminated hard_pass) |
| `baseline_donchian_turtle` | donchian_turtle | baseline_champion |
| `baseline_atr_trail_breakout` | atr_trail_breakout | baseline_champion |
| `baseline_htf_fib_xau` | htf_fib_xau | baseline_champion |
| `baseline_htf_pullback_new` | htf_pullback_new | baseline_champion |
| `refined_donchian_exit_N8_gate_pass` | donchian_turtle | refined_develop |
| `refined_atr_pack_entry20_no_atr_floor` | atr_trail_breakout | refined_develop |
| `refined_htf_fib_best_gate_pass` | htf_fib_xau | refined_develop |

Safety on catalog: *“offline frozen catalog only; not a live promote.”* Params from develop artifacts only; holdout not used for selection of refined packs.

---

## 4. Survive `real=true` only with hard gates + true virgin

| Requirement | This fire |
|-------------|-----------|
| True virgin window available | **FAIL** (n=2, available=false) |
| Single sealed virgin eval | **not run** (correct) |
| Hard gates PF/WR/DD/n | **not applied** (no trades) |
| `real=true` survivors | **0** |
| Prior `vol_gate_sparse` hard_pass on 2026-01+ | **does not count** as virgin `real` survivor |

**Survive count (virgin, real):** **0**

Hostile reminder on the parked prior survivor (not virgin):

- Holdout n exactly at floor (20)
- Design-contaminated window
- Develop PF below holdout hard PF threshold (OOS > IS fragility)
- ~600+ lane trials → multiplicity lottery risk

---

## 5. Disposition

### Decision matrix (applied)

| Condition | Required for LIVE_GO | This fire |
|-----------|----------------------|-----------|
| Virgin hard_pass | yes | no eval |
| `real=true` | yes | 0 survivors |
| n ≥ 20 | yes | n/a |
| Not underpowered | yes | n/a |
| Skeptic approve | yes | **reject promote** |
| Extraordinary evidence to skip paper-first | optional | absent |

Policy reminders:

- Prefer **PAPER_GO** over **LIVE_GO** even on clean virgin hard_pass.
- **LIVE_GO** only if virgin hard_pass + real + n≥20 + not underpowered + skeptic approve (and still recommend paper first unless evidence extraordinary).
- Contaminated-window hard_pass never upgrades to LIVE_GO / PAPER_GO without virgin confirmation.

### Disposition: **WAIT_DATA**

| Option | Chosen? | Why |
|--------|:-------:|-----|
| **LIVE_GO** | no | No virgin eval; no hard_pass; safety forbids live |
| **PAPER_GO** | no | No virgin confirmation of any frozen config |
| **WAIT_DATA** | **YES** | Correct skip; catalog ready; need ≥24 H1 bars after last peek (ideally multi-day post 2026-08-06) |
| **NO_GO** | no* | Not a permanent kill of strategies; develop program not hopeless; waiting on **data**, not rejecting edge forever |

\*If forced binary “promote now?” → **NO-GO**. Named disposition for the loop is **WAIT_DATA** so the scheduler idles until frontier refreshes rather than burning develop retunes.

### What would flip disposition later

1. Refresh until `n_virgin_bars ≥ 24` (preferably weeks of H1 for any hope of n≥20 trades).
2. Single sealed pass of the **frozen 8** only — no param mutation after metrics.
3. Any hard_pass → still default **PAPER_GO** (skeptic); LIVE_GO only if sample large, multiplicity-aware, and edge extraordinary.
4. All fail / underpowered → **NO_GO** or continue develop **without** peeking virgin for retune.

### Immediate actions

| Do | Do not |
|----|--------|
| Keep catalog frozen | Re-optimize on any post-2026-01 bar for “one more look” |
| Re-run frontier when new export arrives | Claim prior vol_gate HO as virgin |
| Idle offline research | `--live` / paper deploy from this skip |
| Preserve skip artifact as audit trail | Write fake virgin metrics |

---

## Safety checklist

- [x] Offline research only  
- [x] Never recommend `--live` from this pass  
- [x] Virgin eval skipped with explicit reason  
- [x] No retune after (nonexistent) virgin metrics  
- [x] No fake survivors / no fake promote  
- [x] Prior contamination disclosed and still binding  
- [x] Catalog assembled from develop artifacts only  

---

## Summary table

| Item | Value |
|------|------:|
| Virgin available | false |
| n_virgin_bars (H1) | 2 |
| Catalog entries | 8 |
| n_evaluated | 0 |
| Virgin hard_pass | 0 |
| real=true survivors | 0 |
| Fake promote? | no |
| **Disposition** | **WAIT_DATA** |

---

*One-line: Frontier refreshed; only 2 post-peek H1 bars; virgin eval correctly skipped; zero real virgin survivors; disposition **WAIT_DATA** (not LIVE_GO / PAPER_GO).*
