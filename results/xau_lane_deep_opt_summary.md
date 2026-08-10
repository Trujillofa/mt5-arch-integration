# XAU lane deep optimization

**Date:** 2026-08-06  
**Pipeline:** develop-only deep opt → freeze 1 champion/lane → single sealed holdout → skeptic disposition  
**Artifacts:** `xau_lane_opt_charter.json`, `xau_lane_deep_opt.json`, `xau_lane_champions.json`, `xau_lane_holdout_eval.json`, `xau_lane_survivors.json`, `xau_lane_deep_opt_skeptic.md`, `xau_xcom_research_notes.md`

---

## Safety

| Rule | Status |
|------|--------|
| Offline research only | **YES** — all meta labels: *offline research only; never --live* |
| Never recommend `--live` | **YES** — live promote **NO-GO** |
| Optimize on develop only (`time < 2026-01-01`) | **YES** — `holdout_used: false` during search |
| Holdout sealed until champions frozen | **YES** — `champions_mutated: false`; single eval pass |
| No early lane discard | **YES** — all 5 lanes `exhausted=true`; doctrine satisfied |
| Fib look-ahead fixed before fib claims | **YES** — shared `htf_fib_core` (`active = c + right`) |
| Virgin holdout for promotion claims | **NO** — 2026-01+ window previously peeked (disclosed contamination) |

**Bottom line:** Mechanical protocol for param choice is clean. Evidence is **not** sufficient for live. Do not re-tune on this holdout.

---

## X.com ideas incorporated

Source: `xau_xcom_research_notes.md` + charter `xcom_ideas[]`. Coded as optional grid axes in `scripts/xau_lane_deep_opt.py` (not cargo-cult slogans alone).

| Idea | Coded? | In winning champions? |
|------|--------|------------------------|
| HTF direction first (H4 bias) | YES | atr_trail + pullback only |
| Pullback-not-chase (new `htf_pullback` lane) | YES (partial; no post-breakout retest) | Pullback champ: ema20 + h4_up |
| `be_at_r=1.0` | YES | **All off** (`null`) |
| `max_entries_per_day` (1–2) | YES | **All = 2** |
| Risk ~1% / ATR sizing | YES | All `risk_pct: 0.01` |
| ATR pctile / regime / failed-breakout fade | YES | Mostly baseline; fade **off** on champs |
| Channel extremes (`mid_channel_k`) | YES | Champions **null** |
| Session London/NY | YES | Champions **hours: null** |
| Ignore discrete call levels | N/A (correctly not encoded) | — |
| Fib golden zone 618–786 | YES | Fib champ `fib_lo/hi = 0.618/0.786` |

**Takeaway:** X.com informed the **search menu**. Selected systems are mostly classic baselines + `max_entries_per_day=2` (and occasional H4 bias). Do not claim “X.com-enhanced systems passed holdout.”

### Fib infrastructure (prerequisite)

HTF Fib pivot look-ahead fixed: events/fib activate at `c+right` via shared `htf_fib_core`; self-check + 4 unit tests pass. Residual caveat: H4 left-label resample can be slightly optimistic inside the 4h bucket.

---

## Per-lane develop opt (budget, best metrics)

**Doctrine:** never discard until develop budget exhausted. Total planned budget **2500** evals; realized **~2931** (stage-2 refine overspend).

| Lane | Budget | n_evals | Exhausted | Develop PF | WR% | DD% | n | NP | Develop status |
|------|-------:|--------:|:---------:|----------:|----:|----:|--:|---:|----------------|
| `vol_gate_sparse` | 500 | 617 | yes | **1.355** | 71.4 | 7.28 | **42** | +398 | viable |
| `donchian_turtle` | 600 | 612 | yes | **2.271** | 43.4 | 9.22 | **129** | +15180 | viable |
| `atr_trail_breakout` | 500 | 609 | yes | **2.480** | 52.6 | 9.24 | **38** | +4877 | viable |
| `htf_fib_xau` | 400 | 472 | yes | **3.584** | 58.8 | 3.75 | **17** | +1795 | viable |
| `htf_pullback_new` | 500 | 621 | yes | **1.335** | 51.6 | 8.34 | **225** | +3915 | viable |

**Champion sketch (develop-selected params):**

- **vol_gate_sparse:** `vol_gate_bb`, atr_max_pct=0.55, rsi_buy=35, tp_atr=3.0, bb_lo15, exit_on_vol_spike, max_entries/day=2  
- **donchian_turtle:** entry_N=20 / exit_N=10, atr_sl=1.5, long_only, no H4 bias / no BE  
- **atr_trail_breakout:** entry_N=24, trail_atr=3.5, **h4_bias=true**, atr_min_pct=0.55  
- **htf_fib_xau:** pivot 5/3, fib 0.618–0.786, flat_only, long_only, sl_atr=1.2 / tp_atr=3.0  
- **htf_pullback_new:** ema20 pull, stack_mode=h4_up, rsi 45–60, h4_bias  

Develop soft floors: met for all five (fib n=17 barely ≥15). Kill candidates: **0**.

---

## Sealed holdout table

**Protocol:** single sealed pass; hard gates PF>1.5, WR>55, DD<10, n≥20. Holdout start 2026-01-01. No retune.

| Lane | HO PF | HO WR% | HO DD% | HO n | HO NP | Status | Hard pass? |
|------|------:|-------:|-------:|-----:|------:|--------|:----------:|
| `vol_gate_sparse` | 2.125 | 80.0 | 1.43 | **20** | **+413.8** | hard_pass | **YES** |
| `donchian_turtle` | 1.721 | 39.6 | 8.15 | 48 | +1762 | fail (WR) | no |
| `atr_trail_breakout` | 5.126 | 75.0 | 2.78 | **4** | +572 | underpowered | no |
| `htf_fib_xau` | 2.406 | 50.0 | 2.20 | **14** | +928 | underpowered | no |
| `htf_pullback_new` | 0.800 | 38.7 | 7.60 | 31 | **−288** | fail | no |

**Summary:** hard_pass=**1**; underpowered=2; fail=2. Best holdout lane by NP among hard_pass: **vol_gate_sparse (NP=413.8)**.

---

## Skeptic keep/park/kill

Policy: **KILL** only if budget exhausted **and** develop **and** holdout both hopeless. Prefer **KEEP_OPTIMIZING** when evidence mixed. **PARK** = freeze / deprioritize; no kill; no further tuning on *this* holdout.

| Lane | Disposition | Rationale |
|------|-------------|-----------|
| `vol_gate_sparse` | **PARK** | Only real hard_pass (n=20 on the floor). Freeze survivor; do **not** re-optimize after seeing holdout. Fragile + contaminated window asterisk. Not KILL. |
| `donchian_turtle` | **KEEP_OPTIMIZING** | Strong develop expectancy; holdout fails WR only while PF 1.72 n=48 NP+. WR>55 gate is known turtle mismatch. |
| `atr_trail_breakout` | **KEEP_OPTIMIZING** | Strong develop; holdout n=4 underpowered but positive shape — sample death, not negative proof. |
| `htf_fib_xau` | **KEEP_OPTIMIZING** | Bug fix landed; first honest sparse sample (dev n=17 PF 3.58; HO n=14 PF 2.4). Not enough n for kill or promote. |
| `htf_pullback_new` | **PARK** | Develop soft floor barely held; holdout transfer failed (PF 0.80 NP−). Not KILL (develop not hopeless); reopen only with structural redesign on develop. |

**KILL count: 0.** Live: **NO-GO**.

---

## Survivors or none

| Metric | Value |
|--------|------:|
| Real survivors (`hard_pass` + `real=true`) | **1** |
| Survivor lane | `vol_gate_sparse` (`mode=vol_gate_bb`) |
| Holdout NP | 413.8 |
| Holdout PF / WR / DD / n | 2.12 / 80% / 1.43% / 20 |
| Offline candidate freeze | OK (`xau_candidate_params.json`) with contamination asterisk |
| Live promote | **NO-GO** |

Hostile discounts on the sole survivor: holdout n exactly at gate floor; prior peek of same window; develop PF 1.36 &lt; holdout hard PF 1.5 (OOS better than IS → fragile). Treat as **research survivor**, not edge proof.

---

## Next steps (continue optimizing which lanes)

1. **KEEP_OPTIMIZING (priority order)**  
   - **`donchian_turtle`** — Pre-register expectancy-centric promote gates (WR secondary); BE/trail/partial ablations on **develop only**; no holdout-guided search.  
   - **`atr_trail_breakout`** — Raise trade count on develop (entry_N / risk path); re-eval later on **virgin** sealed data only.  
   - **`htf_fib_xau`** — Widen entry/cooldown carefully post-fix; residual H4 close semantics optional; need n≥20 path before another sealed look.

2. **PARK**  
   - **`vol_gate_sparse`** — Frozen hard_pass; do not re-tune on this holdout. Next confirmation requires **virgin** holdout (bars never used in shortlist OOS / this eval) or walk-forward + deflated metrics.  
   - **`htf_pullback_new`** — Holdout failed; only reopen with pre-registered structural redesign on develop.

3. **Do not**  
   - Recommend or run `--live`.  
   - Re-tune champions after holdout for promote claims.  
   - Claim X.com-enhanced edge from this pass.  
   - Kill any lane (KILL=0).

4. **Evidence standard for any future promote**  
   Virgin holdout **or** walk-forward + multiplicity-aware metrics with pre-registered gates.

---

*One-line: Budgets exhausted without early discard; fib stamp fixed; 1 fragile hard_pass (`vol_gate_sparse`); live NO-GO; keep optimizing donchian / atr_trail / htf_fib.*
