# XAU Frozen Multi-Year Eval — Hostile Quant Skeptic Review

**Date:** 2026-08-06  
**Stance:** Fail closed. Calendar slices on develop-selected frozen params are **diagnostics**, not a promote unlock. In-sample years do not become OOS by re-labeling. Contaminated holdout-era does not become virgin by re-scoring.

**Pipeline phase:** Offline multi-year matrix of 8 frozen catalog configs (no retune, no `--live`).

**Artifacts reviewed:**

| Path | Role |
|------|------|
| `results/xau_frozen_multi_year_eval.json` | Full cell metrics + hard/soft gates |
| `results/xau_frozen_multi_year_matrix.csv` | Compact PF/WR/DD/n/NP matrix |
| `results/xau_frozen_champions_catalog.json` | 8 frozen configs (baseline + refined_develop) |
| `results/xau_history_coverage.json` | H1 span, bars/year, `has_2023` |
| `results/xau_holdout_lock.json` | develop_end / holdout_start doctrine |
| `results/xau_lane_deep_opt_skeptic.md` | Prior: develop-only selection; 2026-01+ contaminated |
| `results/xau_virgin_holdout_skeptic.md` | Virgin frontier still empty for promote |

**Script:** `scripts/xau_frozen_multi_year_eval.py` — params only from catalog; same simulators as deep-opt / preregistered lineage.

---

## Executive summary

| Question | Verdict |
|----------|---------|
| Multi-year depth available? | **YES** — 2023 present (5894 H1 bars); not missing |
| Are 2024–2025 independent proof? | **NO** — largely **in-sample** for develop-selected champs |
| Is `year_2026_to_peek` confirmatory? | **NO** — already-peeked holdout era; **diagnostic only** |
| Any lane stable sign(PF/NP) across 2023–2025(+peek)? | **Donchian** (baseline + refined) — only clear multi-year +NP / PF>1 sign-stability |
| Classic hard_pass cells (all windows) | **3** total (not a promote argument) |
| Soft_pass_expectancy cells | **13** (mostly donchian / IS halves) |
| Unlocks PAPER_GO / LIVE_GO? | **NO** |
| Disposition | **RESEARCH_ONLY — promote=no** |

**One-line:** Donchian keeps +NP/PF>1 across calendar years including pre-sample 2023; atr_trail collapses in 2023; 2024–25 are IS and 2026 is peeked — **no PAPER_GO / LIVE_GO**.

---

## 1. Protocol & contamination map

### 1.1 Catalog roles (selection context)

From `xau_frozen_champions_catalog.json`:

| Role | Meaning |
|------|---------|
| `baseline_champion` | Per-lane champ from `xau_lane_champions.json` — **develop selection** |
| `refined_develop` | Develop-only ablate/refine gate-pass (donchian exit_N=8, atr pack, fib widen) |

Selection doctrine (deep-opt / lock):

- `develop = time < 2026-01-01`
- Holdout start: `2026-01-01`
- Holdout rule: never used for selection
- Original develop H1 available at selection time started ~**2024-08-16** (see older `xau_holdout_lock.json` `data_h1_min_time`); deep history re-export came later

### 1.2 Window independence labels

| Window | Bars | Independence label | Skeptic use |
|--------|------|--------------------|-------------|
| `year_2023` | 5894 | **Pre-sample / never used for param selection** (deep export post-dates champ freeze; original develop path lacked full 2023) | Best historical stress on frozen params without refit |
| `year_2024` | 5935 | **Mostly contaminated as “independent”** — H2 and especially post-2024-08 overlap develop selection path | Not independent proof |
| `year_2025` | 5911 | **In-sample** (fully inside develop selection era) | Not independent proof |
| `h2_2024`, `h1_2025`, `h2_2025` | ~3k each | **In-sample / develop-adjacent** | Diagnostics only |
| `develop_like` | 25626 | **In-sample aggregate** (`time < 2026-01-01`) | Ranking echo, not OOS |
| `year_2026_to_peek` | 3523 | **Already-contaminated holdout-era** (shortlist OOS, preregistered HO, deep-opt HO peeks through ~2026-08-06 18:00) | **Diagnostic only** — never promote on this alone |
| `full_available` | 29151 | Mix of pre-sample + IS + peeked | Narrative only |

**User-required point 1:** 2024–2025 windows are **largely in-sample** for develop-selected champions. Re-running frozen params on those years is **not** independent multi-year confirmation.

**User-required point 2:** `year_2026_to_peek` is the known peeked holdout era — **diagnostic only**. Same contamination doctrine as virgin skeptic / deep-opt skeptic.

---

## 2. History coverage — 2023 is present

From `results/xau_history_coverage.json`:

| Field | Value |
|-------|--------|
| H1 span | 2021-09-01 → 2026-08-06 |
| `n_h1` | 29151 |
| `bars_per_year.2023` | **5894** |
| `has_2023` | **true** |
| Source | Wine Vantage export `InpMonths=60` (not invented bars) |

Eval `years_available`: `year_2023`, `year_2024`, `year_2025`, `year_2026_to_peek`.  
`windows_skipped_empty`: **[]**.

**User-required point 3:** 2023 is **not** missing. Multi-year depth **can** be claimed in the narrow sense “frozen params evaluated on full calendar 2023 + 2024 + 2025 + partial 2026.”  
Caveat: depth ≠ independence. Only 2023 is cleanly pre-selection; 2024–25 are largely IS; 2026 is peeked.

---

## 3. Aggregate gate counts (do not over-read)

From eval `summary`:

| Stat | Value |
|------|-------|
| Cells | 72 (8 configs × 9 windows) |
| `n_hard_pass_classic` | **3** |
| `n_soft_pass_expectancy` | **13** |

Hard-pass classic cells (PF>1.5, WR>55, DD<10, n≥20):

| Config | Window | Note |
|--------|--------|------|
| `baseline_vol_gate_sparse` | `year_2023` | Pre-sample — interesting, not promote |
| `baseline_vol_gate_sparse` | `year_2026_to_peek` | Contaminated HO-era — knife-edge n=20 already known |
| `baseline_htf_pullback_new` | `h2_2025` | In-sample half-year only |

Soft-pass expectancy (intended for turtle-like lanes) clusters on **donchian** in 2025 / halves / peek and **refined donchian** on 2024–2025 windows — i.e. mostly IS-friendly gold trend path, not a sealed OOS package.

---

## 4. Stability by lane — sign of PF / NP across years

Focus calendar years: **2023, 2024, 2025**, plus **2026_to_peek** as contaminated diagnostic.

Convention: **stable** = PF>1 **and** NP>0 on every calendar year 2023–2025 (and preferably still + on peek). **Collapse** = PF<1 or NP≤0 in at least one full year.

### 4.1 Year matrix (PF / NP / n)

| Config | 2023 PF / NP / n | 2024 PF / NP / n | 2025 PF / NP / n | 2026_peek PF / NP / n | Stability call |
|--------|------------------|------------------|------------------|----------------------|----------------|
| `baseline_vol_gate_sparse` | 1.51 / +518 / 37 | 1.40 / +332 / 26 | 1.26 / +234 / 34 | 2.12 / +414 / 20 | **Sign-stable** 2023–25 (all +NP, PF>1); PF **decays** IS years; `develop_like` PF **1.03** (edge washes over full develop path) |
| `baseline_donchian_turtle` | 1.42 / +2630 / 96 | 1.38 / +2221 / 107 | 2.16 / +9213 / 100 | 1.64 / +1576 / 48 | **Most stable** +NP/PF>1 all years; DD heavy in 2023 (19.8%) / develop (27.7%) |
| `baseline_atr_trail_breakout` | **0.71 / −361 / 16** | **0.99 / −19 / 28** | 2.46 / +3605 / 29 | 5.13 / +572 / **4** | **Collapses 2023–24**; 2025 hero; peek underpowered |
| `baseline_htf_fib_xau` | 1.45 / +445 / 16 | 1.09 / +74 / 13 | 5.70 / +1360 / 10 | 2.41 / +928 / 14 | Sign-stable NP but **n too small** for year claims |
| `baseline_htf_pullback_new` | 1.01 / +43 / 110 | 1.29 / +2401 / 158 | 1.33 / +2735 / 173 | **0.80 / −288 / 31** | Mild + on develop years; **collapses peeked 2026** (matches prior PARK) |
| `refined_donchian_exit_N8` | 1.42 / +2602 / 102 | 1.56 / +3308 / 108 | 2.20 / +9610 / 104 | 1.44 / +1055 / 53 | **Sign-stable** like baseline turtle; 2023 DD 21%; soft-pass cluster on IS windows |
| `refined_atr_pack_entry20…` | **0.90 / −365 / 45** | 1.42 / +2242 / 62 | 2.45 / +9897 / 67 | 1.21 / +354 / 17 | **Collapses 2023**; 2025-centric soft story; peek weak n/DD |
| `refined_htf_fib_best…` | 1.26 / +1454 / 87 | 1.16 / +961 / 88 | 1.45 / +2096 / 79 | **1.00 / −9 / 51** | Mild + IS years; **flat/collapse on peeked 2026** |

### 4.2 Stable vs collapse (user point 4)

**Sign-stable across years (PF>1 and NP>0 on 2023–2025):**

1. **`donchian_turtle` baseline** — strongest multi-year profit-sign continuity; also + on contaminated peek (PF 1.64). Soft expectancy passes on 2025 / halves / peek; classic WR>55 gate remains a known mismatch for turtles.
2. **`refined_donchian_exit_N8_gate_pass`** — same family behavior; more soft-pass hits on 2024–2025 (IS). Not cleaner than baseline for independence.
3. **`baseline_vol_gate_sparse`** — year signs hold, but magnitude **decays** into 2025 and nearly vanishes on full `develop_like` (PF≈1.03, DD 11%). Only multi-window classic hard_pass config — and one of those windows is contaminated 2026.

**Collapse (or near-collapse) in at least one year:**

| Config | Collapse year(s) | Read |
|--------|------------------|------|
| `baseline_atr_trail_breakout` | **2023, 2024** | Path-dependent long-breakout; dies outside 2025 bull impulse |
| `refined_atr_pack_entry20_no_atr_floor` | **2023** | Same lane; develop refine did not buy pre-sample robustness |
| `baseline_htf_pullback_new` | **2026_to_peek** | Transfer fail already documented; hard_pass only on IS `h2_2025` |
| `refined_htf_fib_best_gate_pass` | **2026_to_peek** (~flat) | IS-mild; peek not confirmatory |
| `baseline_htf_fib_xau` | (no full-year sign flip) | **Underpowered** every year (n≈10–16) — stability of sign is noise-adjacent |

**Bottom line stability:** Only **Donchian** (both baseline and refined) looks multi-year **sign-stable**. ATR trail is a **2025-regime** story that **fails pre-sample 2023**. Vol-gate is the only classic hard_pass multi-cell lane but is **soft on long develop aggregate** and one hard_pass is peeked. Pullback / refined fib do not survive the contaminated peek with positive edge.

---

## 5. Explicit promote ruling (user point 5)

### This run does **NOT** unlock PAPER_GO or LIVE_GO by itself

Reasons (any one would suffice; all apply):

1. **2024–2025 are not independent** of develop selection for these frozen champs.
2. **2026_to_peek is already contaminated** — scoring it again cannot mint a virgin hard_pass.
3. **No sealed virgin window** with adequate bars after last peek (`last_peeked_end` ≈ 2026-08-06 18:00; frontier still stub — see `xau_virgin_holdout_skeptic.md`).
4. Gate hits are sparse (3 classic hard_pass cells total) and/or on IS/peeked windows; turtle soft-passes are mostly IS halves + contaminated peek.
5. Multiplicity: champs already survived ~3k develop evals + refine + prior peeks; multi-year re-score of the **same 8** is not a new confirmatory experiment.
6. Catalog meta: `"safety": "offline frozen catalog only; not a live promote"`.

| Gate | Status |
|------|--------|
| **PAPER_GO** | **no** |
| **LIVE_GO** | **no** |
| **promote** | **no** |
| Disposition | **RESEARCH_ONLY** / continue WAIT_DATA for virgin |

---

## 6. What would count as stronger evidence (user point 6)

Ranked, fail-closed:

### A. Virgin post-peek holdout (primary promote path)

- Bars **strictly after** last peeked end (currently ≥24 H1 minimum; practically enough for n≥20 closed trades under frozen params).
- **Single** sealed pass of **frozen catalog only** — no retune, no grid, no champion rewrite from the virgin slice.
- Prefer pre-registered gates per lane family (classic for high-WR; expectancy-centric for turtle-like) with multiplicity disclosure.
- Even then: default **PAPER_GO ≫ LIVE_GO**; LIVE_GO only with extraordinary sample + skeptic LIVE_GO.

### B. True pre-sample 2023 without refit (already partially obtained)

- **Already run:** frozen params on `year_2023` without re-optimization after deep export.
- **Value:** honest historical stress — e.g. atr_trail **fails** 2023; donchian **keeps** +NP; vol_gate hard_pass on 2023 is a research note.
- **Not sufficient alone for PAPER_GO/LIVE_GO:**
  - Selection multiplicity still high on later develop path.
  - Gold regime 2023 ≠ future regime.
  - Single pre-sample year ≠ sealed out-of-time confirm after freeze protocol.
  - Promote doctrine still requires virgin post-peek (or equivalently clean never-peeked forward window).

### C. What does **not** count

| Non-evidence | Why |
|--------------|-----|
| Re-labeling 2025 as “OOS” | Inside develop selection |
| Another pass on `year_2026_to_peek` | Contaminated |
| Soft_pass on h1/h2 2025 halves | IS path slicing |
| `full_available` PF stories | Mixes IS + peek + pre-sample |
| Underpowered year cells (n<20, especially fib/atr peek) | Cannot support hard gates |

### D. Optional intermediate (still not auto-promote)

- Walk-forward / deflated metrics on develop **with** pre-registered gates and no holdout mining.
- Structural redesign only on develop; re-freeze; then virgin eval — never tune on peek/virgin.

---

## 7. Lane-level research notes (not promote)

| Lane / config | Multi-year read | Next research (offline) |
|---------------|-----------------|-------------------------|
| Donchian baseline + refined | Only clear multi-year **sign** stability; DD can be severe on long paths | Keep frozen; expectancy gates; **no** IS re-pick; wait virgin |
| Vol gate sparse | Pre-sample 2023 hard_pass interesting; IS decay + weak develop_like PF | Research freeze; do not promote on peeked 2026 hard_pass |
| ATR trail baseline + refined | **2023 collapse** — reject “robust multi-year breakout” claim | Regime-conditional thesis only; no promote from 2025 soft |
| HTF fib baseline | Tiny n; high PF noise | Need more trades or stay diagnostic |
| Refined fib | Mild IS +; peek flat | Do not promote |
| HTF pullback | Develop years soft +; **peek collapse** | Stay PARK per prior skeptic |

---

## 8. Checklist vs user requirements

| # | Requirement | Status in this note |
|---|-------------|---------------------|
| 1 | 2024–2025 largely IS for develop-selected champs | **Stated §1.2, §5** |
| 2 | 2026_to_peek contaminated / diagnostic only | **Stated §1.2, §5** |
| 3 | If 2023 missing, say so | **2023 present** (`has_2023=true`); multi-year depth claimable with independence caveats §2 |
| 4 | Stable vs collapse lanes | **§4** — Donchian stable; atr_trail collapses 2023; pullback/refined-fib fail peek |
| 5 | Does not unlock PAPER_GO/LIVE_GO | **Explicit §5 — promote=no** |
| 6 | Stronger evidence | **§6** virgin post-peek primary; pre-sample 2023 without refit already diagnostic, not sufficient alone |

---

## 9. Disposition

| Field | Value |
|-------|--------|
| **ok (artifact written)** | true |
| **promote** | **no** |
| **PAPER_GO** | no |
| **LIVE_GO** | no |
| **summary** | Donchian sign-stable across years incl. pre-sample 2023; atr_trail collapses 2023; 2024–25 IS + 2026 peeked — promote=no |

*Hostile one-liner: Multi-year matrix is useful autopsy (donchian survives 2023; atr dies there); it is not a sealed multi-year proof and **does not** unlock paper or live.*
