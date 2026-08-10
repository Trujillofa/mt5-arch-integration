# XAU Lane Deep Opt — Hostile Quant Skeptic Review

**Date:** 2026-08-06  
**Stance:** Fail closed. Real survivors only under hard gates + clean protocol. Soft / underpowered / contaminated ≠ live promote.  
**Doctrine under review:** *never discard lane until develop opt budget exhausted* (`xau_lane_opt_charter.json`).

**Artifacts reviewed:**

| Path | Role |
|---|---|
| `results/xau_lane_opt_charter.json` | Doctrine, budgets, X.com ideas, soft floors, discard policy |
| `results/xau_lane_deep_opt.json` | Develop-only search results (5 lanes) |
| `results/xau_lane_champions.json` | Frozen 1 champion / lane (no holdout numbers) |
| `results/xau_lane_holdout_eval.json` | Single sealed holdout pass on frozen champions |
| `results/xau_lane_survivors.json` | Gate application / survivor list |
| `results/xau_candidate_params.json` | Best hard_pass params (offline candidate only) |
| `results/xau_fib_fix_note.md` | Pivot confirmation look-ahead fix |
| `results/xau_xcom_research_notes.md` | External idea source |
| `scripts/xau_lane_deep_opt.py` | Optimizer + enhanced simulators |
| `scripts/htf_fib_core.py` | Causal pivot stamp (`active = c + right`) |
| (context) `results/xau_preregistered_skeptic.md` | Prior contamination of same 2026-01+ window |

---

## Executive summary

| Question | Verdict |
|---|---|
| Every lane exhaust develop budget? Early discard? | **YES exhausted / NO early discard** (all `exhausted=true`; `n_evals ≥ budget_target`) |
| Holdout leakage into **param choice**? | **NO mechanical leakage** in deep opt; **YES design-level contamination** of the same holdout window from prior OOS |
| Fib confirmation fixed? | **YES** (shared `htf_fib_core`; residual H4 left-label caveat remains) |
| X.com ideas coded vs cargo-cult? | **Partially coded** as optional grid axes; **winning champions mostly turn them OFF** |
| Multiple testing / overfit risk? | **HIGH** (~2.9k develop evals → 5 champs → 1 knife-edge hard_pass) |
| Real survivors under hard gates + clean protocol? | **1 hard_pass cell, protocol mechanically clean for this pass; holdout not virgin for thesis** |
| Live promote? | **NO-GO** without a **virgin** holdout (or explicit contamination-discounted claim) |

**Survive count (`real=true` hard_pass):** **1** (`vol_gate_sparse` only)  
**Recommendation:** offline research only; never `--live`. Freeze survivor; do not re-tune on this holdout.

---

## 1. Did every lane exhaust develop budget? Any early discard?

### Verdict: **PASS on doctrine (exhausted); no early kill**

| Lane | budget_target | n_evals | designed_grid | exhausted | kill_candidate | develop status |
|---|---:|---:|---:|---|---|---|
| `vol_gate_sparse` | 500 | 617 | 976 | true | false | viable |
| `donchian_turtle` | 600 | 612 | 2656 | true | false | viable |
| `atr_trail_breakout` | 500 | 609 | 2176 | true | false | viable |
| `htf_fib_xau` | 400 | 472 | 3040 | true | false | viable |
| `htf_pullback_new` | 500 | 621 | 2712 | true | false | viable |

Evidence from `scripts/xau_lane_deep_opt.py`:

- Docstring: *“full budget, no early discard.”*
- `optimize_lane` always runs stage-1 grid (subsampled to budget if larger) **then** stage-2 neighborhood refine; `exhausted` is hard-coded `True` after completion.
- `soft_floor_fail` only sets `kill_candidate` / `struggling`; it does **not** abort the search.
- `main` processes all 5 lanes unconditionally; exit requires `all_exhausted`.

**Caveats (hostile, not fatal to doctrine):**

1. **Designed grids ≫ budget.** Stage-1 uses stratified `grid[::step][:budget]`. Structure variants were **sampled**, not exhaustively Cartesian-searched (e.g. donchian designed 2656 → ~600 evals). “Budget exhausted” ≠ “every structure variant fully explored.”
2. **`n_evals > budget_target`** is expected (stage-2 refine additive, up to ~120). This is *over*-spend, not early stop.
3. Total wall time ~106s for ~2.9k H1 sims is fine for offline research; it is not evidence of a thorough walk-forward / multi-seed study.

**Early discard:** **None observed.** Doctrine satisfied at the lane level.

---

## 2. Holdout leakage into param choice?

### 2.1 Mechanical seal for deep opt + champion freeze — **PASS**

| Check | Evidence |
|---|---|
| Opt window | `develop = times < 2026-01-01` only |
| Holdout in ranking | `holdout_used: false`; champions meta: `holdout_numbers: "NONE — sealed until promote pass"` |
| Pseudo-val | Last **20% of develop** only (`pseudo_val_frac=0.2`); 15% score blend when `n≥3` — **not** post-2026-01 |
| Champions mutated after holdout? | `champions_mutated: false`; holdout eval recomputes develop metrics and matches frozen |
| Selection policy | 1 champion / lane by **develop_score** before holdout pass |

Deep opt **does not** read holdout metrics to choose params. Timestamps consistent with freeze-then-eval: deep_opt/champions ~11:42, holdout_eval/survivors/candidate ~11:43.

### 2.2 Design / family contamination of the *same* holdout window — **FAIL (for virgin claims)**

Charter itself admits:

> `prior_contamination_note`: *“2026-01+ window already used in prior shortlist OOS; any future promote claim needs virgin holdout or explicit contamination disclosure.”*

Prior skeptic (`xau_preregistered_skeptic.md`) already established:

- Same calendar holdout used in `xau_oos_holdout.json` / new-design OOS.
- Family shortlist (esp. vol_gate_bb residual OOS shape) was **informed by a prior peek**.

Deep-opt **does not clean** that contamination. A single sealed pass of *new* champions on a *previously peeked* window is still **design-level leakage** for any “holdout-confirmed edge” marketing claim.

### 2.3 Post-holdout candidate write — **narrow OK**

`xau_candidate_params.json` selects “best hard_pass by holdout net_profit.” With **n_hard_pass = 1**, there is no multi-survivor holdout argmax abuse. Still: that file is **not** a second independent confirmation.

### 2.4 Intra-develop leakage (secondary)

Champion ranking blends 15% pseudo-val score from the last 20% of develop. That slightly favors params that fit the late-develop regime (same bars already in full develop metrics). Not holdout leakage; still inflates in-sample confidence.

**Skeptic bottom line:** Param choice was develop-only (**good**). Promotion claims on this holdout remain contaminated (**bad**).

---

## 3. Fib confirmation fixed?

### Verdict: **YES — critical multi-bar look-ahead removed; residual single-bucket caveat**

| Item | Status |
|---|---|
| Shared helper | `scripts/htf_fib_core.py`: `active = c + right` |
| Deep opt import | `from htf_fib_core import confirmed_pivots, expand_fib_states, walk_swing_and_fibs` |
| Consumers | offline backtest + preregistered holdout + deep opt wired to core |
| Self-check / tests | `self_check_pivot_confirmation()`; `tests/test_htf_fib_pivot_confirmation.py` |
| Pre-fix metrics | **Invalidated** per fix note (prior n≈0–3 underpowered anyway) |

Fix note residual (honest, still true):

- H4 from `resample("4h")` is **left-labeled**; activation at confirmation bar’s left edge is slightly optimistic vs “strictly after H4 close” inside that 4h bucket.
- MQL5 chart labels still draw at pivot center (live path already requires right bars present).

### Post-fix fib champion (develop-selected)

| Metric | Develop | Holdout |
|---|---:|---:|
| n_trades | 17 | 14 |
| PF | 3.58 | 2.41 |
| WR | 58.8% | 50.0% |
| DD% | 3.75 | 2.20 |
| NP | +1795 | +928 |

Develop soft floor from charter (`n≥15`, `PF>1.2`): **met** (barely on n). Holdout: **underpowered** (`n=14 < 20`), WR gate fail, **not** hard_pass. Pseudo-val n=2 / PF=99 is worthless noise — scoring correctly caps PF but the cell remains fragile.

**Skeptic:** Fix is real and necessary. Fib lane is **not** a survivor. Sparse positive shape after fix is **interesting, not proven**.

---

## 4. X.com ideas actually coded vs cargo-cult?

Source: `xau_xcom_research_notes.md` + charter `xcom_ideas[]`. Implementation: enhanced sims + multi-block grids in `xau_lane_deep_opt.py`.

### 4.1 Implementation audit

| Idea id | Coded in sims/grids? | In **winning** champion params? | Notes |
|---|---|---|---|
| `htf_direction_first` (H4 bias) | **YES** (`h4_bull` causal shift+ffill; `h4_bias` flag) | Only **atr_trail** + **pullback** (`true`); vol/turtle/fib **false** | No Daily bias; H4 only |
| `pullback_not_chase` | **Partial** — new `htf_pullback` lane; vol_gate still BB reclaim | Pullback champion is ema20 + h4_up | **Missing** charter variant `post_breakout_retest_entry` (zero code hits) |
| `be_at_r=1.0` | **YES** (`_apply_be`) | **ALL champions `be_at_r: null`** | Grid searched; optimizer rejected BE on develop score |
| `max_entries_per_day` | **YES** (`day_id` calendar) | **All = 2** | Portable risk rule that stuck |
| `risk_1pct` | **YES** (`risk_pct: 0.01` fixed) | All champions | Turtle N-style ATR stop distance + fixed fraction |
| `atr_pctile_regime` | **YES** (atr max/min / pctile bands; failed-breakout fade) | Mostly baseline gates; fade **false** on champs | Present as options |
| `channel_extremes` (`mid_channel_k`) | **YES** (donch + atr_trail) | Champions **null** | Searched, not selected |
| `session_london_ny` | **YES** (`HOURS_LONDON_NY`, late variant) | **ALL champions `hours: null`** | Searched, not selected |
| `ignore_call_levels` | N/A (correctly not encoded) | — | Good discipline |
| Fib golden zone 618–786 | **YES** | Fib champ `fib_lo/hi = 0.618/0.786` | Aligned with structure variant |
| `require_ema_stack` / stack modes | **YES** (trail + pullback) | Trail: false; pullback: `stack_mode=h4_up` | Partial |
| FVG proxy | **YES** (`use_fvg_proxy`) | Pullback champ **false** | Token feature |

### 4.2 Cargo-cult assessment

**Not pure cargo-cult:** Ideas were turned into real optional parameters and given search mass across lanes. HTF pullback lane is a genuine new sibling, not a slogan.

**Still cargo-cult-adjacent:**

1. Headline X risk filters (**BE**, **session**, **mid-channel extremes**, **failed-breakout fade**) are **absent from every frozen champion**. The narrative “we added X.com risk rules” is true of the *search space*, false of the *selected systems*.
2. `post_breakout_retest_entry` appears in the charter structure list for vol_gate and is **not implemented**.
3. No evidence of systematic ablation (“with H4 bias vs without”) published beyond latent grid competition under a composite score — winners can be pure in-sample noise magnets.
4. Scoring objectives differ by lane (n-seeking for MR/pullback vs expectancy√n for trend). That is good, but it also means X filters that reduce n get penalized hard on vol_gate/pullback scores even if they improve true edge quality.

**Skeptic line:** X.com informed the **menu**. Develop search ordered **mostly classic baselines** with `max_entries_per_day=2` and occasional H4 bias. Do not claim “X.com-enhanced systems passed holdout.”

---

## 5. Multiple testing / overfit risk

### Verdict: **HIGH — one knife-edge survivor after industrial search**

| Factor | Magnitude |
|---|---|
| Charter total budget | 2500 planned |
| Realized develop evals | 617+612+609+472+621 = **2931** |
| Champions evaluated on holdout | **5** (1 per lane) |
| Hard gates | PF>1.5, WR>55, DD<10, n≥20 |
| Hard passes | **1** |
| Survivor holdout n | **20 exactly** (minimum gate) |
| Deflated Sharpe / SPA / Bonferroni | **None** |
| Walk-forward on deep-opt champs | **None in this pipeline** |
| Virgin holdout for family design | **No** (prior OOS contamination) |

**Specific overfit red flags:**

1. **Vol_gate survivor:** develop PF 1.36 (soft) → holdout PF 2.12 WR 80% n=20. Shape improvement OOS after ~600 develop trials is classic multiple-testing lottery behavior *unless* pre-registered and virgin — neither fully true here (family already peeked).
2. **Nearby prior cells:** preregistered grid already explored atr_max ∈ {0.35,0.40} × rsi_buy ∈ {30,35} bb_lo15. Deep-opt champ is `atr_max_pct=0.55`, `rsi_buy=35`, `tp_atr=3.0`, `exit_on_vol_spike=true`, `max_entries_per_day=2` — a **neighborhood extension**, not a new thesis. Good for continuity; bad for “independent discovery.”
3. **Donchian:** develop NP ~15k / PF 2.27 / n=129 vs holdout WR 39.6% (fails WR gate) but PF 1.72 n=48. Expectancy thesis partially OOS-stable; **WR hard gate is mismatched** for turtles (known from charter). Selecting on expectancy then grading on WR invites false “fail” *and* hides that the gate was never the scientific claim.
4. **ATR trail holdout n=4** with PF~5.1: **statistically meaningless** for promotion; “underpowered positive” is correct labeling.
5. **Fib pseudo-val WR 100% n=2:** score blend can still nudge ranks; capped PF helps but does not create sample size.
6. **Pullback:** develop n=225 PF 1.33 → holdout PF 0.80 NP negative n=31. Classic in-sample overfit of a high-frequency lane. Budget exhausted; edge **did not transfer**.

**No correction for the look-elsewhere effect across 5 lanes × ~500–600 cells.** One hard_pass at the n-floor is the expected false-discovery rate ballpark for noisy H1 gold strategies under these gates.

---

## 6. Real survivors only — hard gates + clean protocol

### Protocol checklist

| Gate / rule | Result |
|---|---|
| Optimize develop only | **PASS** |
| Freeze champions before holdout | **PASS** |
| Single holdout pass, no retune | **PASS** (`champions_mutated=false`) |
| Hard gates on holdout only | **PASS** (develop diagnostic) |
| Underpowered ≠ pass | **PASS** (atr_trail n=4, fib n=14) |
| Survivors = hard_pass only | **PASS** (`n_survivors=1`, `real=true`) |
| Virgin holdout for thesis selection | **FAIL** (disclosed contamination) |
| Multiple-testing control | **FAIL** (absent) |
| Fib look-ahead fixed before fib claim | **PASS** (post-fix develop opt) |

### Holdout scoreboard (frozen champions)

| Lane | HO PF | HO WR | HO DD% | HO n | Status | Hard pass? |
|---|---:|---:|---:|---:|---|---|
| `vol_gate_sparse` | 2.12 | 80.0 | 1.43 | **20** | hard_pass | **YES** |
| `donchian_turtle` | 1.72 | 39.6 | 8.15 | 48 | fail (WR) | no |
| `atr_trail_breakout` | 5.13 | 75.0 | 2.78 | **4** | underpowered | no |
| `htf_fib_xau` | 2.41 | 50.0 | 2.20 | **14** | underpowered | no |
| `htf_pullback_new` | 0.80 | 38.7 | 7.60 | 31 | fail | no |

### Real survivor judgment

**Mechanical real survivor count: 1** — `vol_gate_sparse` (`mode=vol_gate_bb`).

Hostile discount:

- Holdout **n = 20 on the nose** — zero buffer; one trade flips underpowered.
- Prior peek of same window + ~600 vol_gate develop evals + family pre-selection → **not a clean confirmatory test**.
- Develop PF only 1.36 (below holdout hard PF 1.5) — OOS looks *better* than IS, which is either regime luck or selection artifact; treat as **fragile**.
- `xau_candidate_params.json` is correctly labeled offline / not live until separate promote.

**Promote to live? NO.**  
**Offline “real survivor” label for research tracking? YES (1), with contamination asterisk.**

---

## 7. Per-lane disposition: KEEP_OPTIMIZING vs PARK vs KILL

Policy from user + charter:

- **KILL** only if budget exhausted **AND** develop **and** holdout both hopeless.
- **PARK** = freeze / deprioritize; no kill; no further tuning on *this* holdout.
- **KEEP_OPTIMIZING** = residual thesis hope under develop soft floors or underpowered-but-positive holdout; next work on **develop** or **virgin** OOS only.

| Lane | Budget exhausted? | Develop soft floor | Holdout | Disposition | Justification |
|---|---|---|---|---|---|
| `vol_gate_sparse` | YES (617≥500) | Met (PF1.35 WR71 DD7.3 n42) | **hard_pass** n=20 | **PARK** (frozen survivor) | Only real hard_pass. Do **not** re-optimize after seeing holdout. Claim needs virgin window or explicit contamination discount. Not KILL. |
| `donchian_turtle` | YES (612≥600) | Strong (PF2.27 DD9.2 n129; WR secondary by design) | Fail WR only; PF1.72 n48 NP+ | **KEEP_OPTIMIZING** | Not hopeless. Thesis is expectancy/trend-following; WR>55 gate is known mismatch. Next: pre-register expectancy-centric promote gates + BE/trail ablations on develop; **no** holdout-guided param search. |
| `atr_trail_breakout` | YES (609≥500) | Strong develop (PF2.48 n38) | Underpowered n=4 but PF/WR/DD pretty | **KEEP_OPTIMIZING** | Sample death on holdout, not negative expectancy proof. HTF bias already on champ; BE/session still off. Need more trades (looser entry_N / risk path) on develop before re-eval on **new** sealed data. |
| `htf_fib_xau` | YES (472≥400) | Soft floor met post-fix (n17 PF3.58) | Underpowered n14; PF2.4 WR50 | **KEEP_OPTIMIZING** | Bugfix landed; first honest sparse sample. Not enough n for kill *or* promote. Widen entry/cooldown carefully on develop; residual H4 close semantics optional. |
| `htf_pullback_new` | YES (621≥500) | Soft floor barely (PF1.33 WR51.6 DD8.3) | **Fail hard** PF0.80 NP− n31 | **PARK** | Develop not hopeless → **not KILL**. Holdout transfer failure after full budget is serious. Park lane; only reopen with structural redesign pre-registered on develop, never by mining this holdout ranking. |

### Explicit non-kills

No lane meets **KILL** criteria:

- All budgets exhausted (**yes**).
- None have **both** develop and holdout hopeless:
  - Pullback holdout is bad, develop is not.
  - Trend lanes have develop strength and/or underpowered-positive holdout.
  - Vol_gate survived.

---

## 8. Cross-checks the pipeline got right

1. **Doctrine of no early discard** was implemented and run.
2. **Holdout not used for tuning** in deep opt (mechanical).
3. **Fib look-ahead** fixed in shared core before fib deep opt.
4. **Survivors file** correctly excludes underpowered / fail; only hard_pass gets `real=true`.
5. **Safety labeling** (“offline research only; never --live”) consistent across artifacts.
6. **Donchian holdout** still shows material PF/NP — gate redesign is a scientific issue, not data fraud.

---

## 9. What the pipeline got wrong / left open

1. **Contaminated holdout** used again for “confirmation” after prior OOS peeks — disclosed but not remediated.
2. **~3k unrestricted develop trials** without multiplicity control; 1/5 hard_pass at n=20 is weak evidence.
3. **X.com story oversold** relative to champion params (BE/session/extremes off).
4. **Missing structure variant** `post_breakout_retest_entry` despite charter listing.
5. **No walk-forward / deflated metrics** on frozen champions.
6. **WR hard gate** remains hostile to the best expectancy lane (turtle) by construction.
7. **Pseudo-val 15% blend** is mild data leakage inside develop ranking.
8. Grid **subsampling** means “budget exhausted” is weaker than full structure coverage.

---

## 10. Final recommendation

| Item | Decision |
|---|---|
| Survive count (real hard_pass) | **1** (`vol_gate_sparse`) |
| Live promote | **NO-GO** |
| Offline candidate freeze | **OK** (`xau_candidate_params.json`) with contamination asterisk |
| Re-tune after this holdout | **FORBIDDEN** for promote claims |
| Next evidence standard | **Virgin holdout** (bars never used in shortlist OOS / this eval — e.g. strictly after last bar of this dataset) **or** walk-forward + deflated Sharpe on develop with pre-registered gates |
| Lane program | vol_gate **PARK**; pullback **PARK**; turtle / atr_trail / fib **KEEP_OPTIMIZING** on develop only; **KILL none** |

**One-line summary:** Budgets exhausted without early discard; fib stamp fixed; X.com ideas mostly optional and largely not selected; protocol seal for param choice is clean but holdout is not virgin; **1 fragile hard_pass survivor**; **no live promote**.

---

*Skeptic stance: fail closed. Soft shapes and underpowered PF fireworks are not edge.*
