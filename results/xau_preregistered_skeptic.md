# XAU Pre-Registered Holdout — Hostile Quant Skeptic Review

**Date:** 2026-08-06  
**Stance:** Fail closed. Promote only if hard gates + clean protocol + adequate n. Soft / underpowered / contaminated ≠ survive.

**Artifacts reviewed:**
| Path | Role |
|---|---|
| `results/xau_holdout_lock.json` | Pre-registration lock + registry fingerprint |
| `results/xau_preregistered_registry.json` | Frozen 24 configs (4 families × ≤6) |
| `results/xau_preregistered_holdout_eval.json` | Single-pass develop + holdout metrics |
| `results/xau_preregistered_survivors.json` | Gate application / ranking |
| `scripts/xau_preregistered_holdout.py` | Evaluator (Donchian, ATR trail, HTF Fib, vol_gate dispatch) |
| (context) `scripts/htf_fib_offline_backtest.py` `confirmed_pivots` | Pivot confirmation semantics |
| (context) `results/xau_new_design_search.json`, `xau_new_design_summary.md` | Prior OOS peek that informed family choice |

---

## Executive summary

| Question | Verdict |
|---|---|
| Holdout sealed for the 24-config single pass? | **YES (mechanical)** — lock fingerprint matches; eval after freeze; no re-pick |
| Holdout virgin for family / thesis selection? | **NO** — same ~2026-01+ window already used as prior shortlist OOS |
| Evidence of iterative re-tuning *after* this holdout eval? | **NONE found** |
| Config count ≤6/family; hidden search in this run? | **6×4=24 exact; no in-script grid** |
| Look-ahead (Fib / Donch / trails)? | **Fib: CRITICAL confirmation lag bug; Donch: OK; trail: same-bar path ambiguity** |
| Hard-gate survivors (`real=true`)? | **0** |
| Promote? | **DO NOT PROMOTE** |

**Survive count (real=true):** **0**  
**Recommendation:** **NO-GO** — offline research only; never `--live`; do not write promotion params.

---

## 1. Was holdout sealed? Re-tuning after seeing holdout?

### 1.1 Mechanical seal for this protocol — **PASS**

Lock (`xau_holdout_lock.json`):

```text
holdout_start     = 2026-01-01T00:00:00+00:00
develop_end       = 2025-12-31T23:59:59+00:00
registry_sha256   = eb9ec45fc4f6a0c7d71d6f6117f297459fa9c0c4f80b9f1f384fe1640c999b16
n_families        = 4
n_configs_total   = 24
configs_per_family= 6 each
holdout_rule      = NEVER used for selection; single evaluation after all configs frozen
```

Independent recompute on disk:

```text
sha256(results/xau_preregistered_registry.json) == lock.registry_fingerprint.sha256
bytes = 19801  (matches lock)
```

Timestamps (local, 2026-08-06):

| Artifact | mtime |
|---|---|
| `xau_preregistered_registry.json` | 11:07:38 |
| `xau_holdout_lock.json` | 11:07:38 (same second) |
| `xau_preregistered_holdout_eval.json` | 11:10:20 (~2.5 min later) |
| `xau_preregistered_survivors.json` | 11:11:33 |

Eval script (`main`) loads **only** registry configs, runs each once on develop and holdout, writes eval JSON — no grid expansion, no argmax over holdout, no second-pass re-registration.

Survivors artifact:

```text
n_registered = n_evaluated = 24
ids_match = true
no_extra_trials = true
holdout_start_matches_lock = true
n_survivors = 0
candidate_params_written = false
```

**No evidence** of registry edits, re-runs with expanded configs, or promotion file writes after holdout was observed. Failures were accepted (0 hard_pass).

### 1.2 Virgin holdout for design / family selection — **FAIL (contamination)**

Prior research already evaluated OOS on essentially the same calendar window:

| Source | Split / OOS |
|---|---|
| `xau_oos_holdout.json` | `2026-01-02 18:18:00+00:00` |
| `xau_new_design_search.json` meta | same split; train 8132 / oos 3505 bars |
| This protocol | `holdout_start=2026-01-01`; holdout bars 3523 (2026-01-02 → 2026-08-06) |

Registry thesis text **explicitly** cites prior OOS residual:

> vol_gate_sparse: *"Only residual non-negative clean OOS shape was vol_gate_bb…"*

`xau_new_design_summary.md` redesign table (post shortlist OOS) pre-specified the four families now frozen (sparse MR, turtle/Donch, HTF Fib, trail breakout). Prior shortlist OOS for `vol_gate_bb` used params nearly identical to registered cells (`atr_max_pct=0.4`, `rsi_buy=35`, sl/tp 1.5/2.5, bb_lo15, ema200).

**Skeptic conclusion:** The **24-config evaluation pass** was sealed and single-shot. The **choice of families and several anchor params** was informed by a prior peek at the same post-2026-01 region. That is **design-level contamination**, not post-lock re-tuning. For promotion standards that require a virgin holdout for thesis selection, this holdout is **not clean**. For the narrow claim “we did not re-tune the frozen 24 after this eval,” the claim holds.

**Re-tuning after *this* holdout?** No artifact evidence. Fail closed still applies because nothing passed gates and the holdout is not virgin for family choice.

---

## 2. Config count vs max 6/family — hidden search?

| Family | Registered | Cap |
|---|---|---|
| `vol_gate_sparse` | 6 | 6 |
| `donchian_turtle` | 6 | 6 |
| `htf_fib_xau` | 6 | 6 |
| `atr_trail_breakout` | 6 | 6 |
| **Total** | **24** | **24** |

- Protocol `max_configs_per_family: 6` enforced in lock fingerprint `configs_per_family`.
- `xau_preregistered_holdout.py` iterates `reg["families"] → configs` only — **no** itertools product, no random search, no train-side selection.
- Verification: `n_evaluated=24`, `no_extra_trials=true`.

**Hidden search inside this run:** not found.

**Caveat (prior multiplicity):** Historical `xau_new_design_search` ran **3798** train evals before this protocol. That multiplicity does not expand *this* holdout trial count, but it did shape which families/params were “pre-registered.” Multiplicity is therefore **upstream of registration**, not hidden inside the holdout script. Bonferroni/deflation over 3798+24 is not applied anywhere — correctly, survivors did not claim deflated significance.

**Config structure:** small literature-style factorials (MR: 3 atr_max × 2 rsi; turtle: S1/S2 × SL/filter variants; fib: filter on/off × 3 exit geometries; trail: 2 N × vol/trail neighbors). Looks hand-chosen, not a stealth full grid.

---

## 3. Look-ahead / leakage

### 3.1 HTF Fib pivots — **CRITICAL: missing confirmation delay**

`confirmed_pivots(high, low, left, right)` (and local copy in holdout script) requires bars `[c-left, c+right]` to label bar `c` as a pivot, but **stamps the event at index `c`**, not at confirmation index `c+right`.

```python
# scripts/htf_fib_offline_backtest.py
for c in range(left, n - right):
    is_h = all(high[i] < h for i in range(c - left, c + right + 1) if i != c)
    ...
    events.append((c, float(h), 1))  # stamped at center, not c+right
```

`simulate_htf_fib` maps H4 pivot **label timestamp** → H1 index and activates fib state when `states[state_i][0] <= i`:

```python
pos = h1_index.searchsorted(ts, side="right") - 1  # ts = H4 left edge of pivot bar
...
while state_i < len(states) and states[state_i][0] <= i:
    _, cur_dir, cur_a, cur_b = states[state_i]
```

Empirical lag on this CSV (`pivot_right=5` H4):

```text
pivot stamped ~19 H1 bars before true confirmation bar (c+right)
≈ 5 H4 bars × 4h = 20h of future information
```

Additional issues:

1. **H4 bar completeness:** event uses H4 bar `c` OHLC at its left-edge label; bar `c` itself is not complete until +4h.
2. **Causal fix:** stamp pivots at `c + right` (and only after H4 bar close), then map that confirmation timestamp to H1.
3. **Impact on this holdout:** fib family produced **n=0** (filter on) or **n=3** (filter off) — underpowered either way. Look-ahead did **not** manufacture a false hard_pass here, but the simulator is **not safe for any future claim** until confirmation lag is fixed.

**Status:** look-ahead bug confirmed. Family fails gates; do not trust fib metrics even if they later “pass.”

### 3.2 Donchian turtle — **no classic same-bar channel leak**

Entry:

```python
long_sig = close[i] > donch_hi[i - 1]
```

Exit channel:

```python
close[i] < donch_lo[i - 1]
```

Rolling max/min at `i` includes bar `i` high/low, but signals use **prior bar** channel — correct Turtle-style.

**Status:** verified causal for channel. Residual: bar-close fill after full OHLC of signal bar (standard H1 optimism, not unique to this family).

### 3.3 ATR trail breakout — **same-bar path ambiguity; not pure future leak**

```python
# trail first from close[i], then test low[i] vs updated sl
if pos > 0 and px > entry:
    trail_sl = px - atr[i] * trail_mult
    if trail_sl > sl:
        sl = trail_sl
if low[i] <= sl:
    exit_px = sl
```

Within one H1 bar, order of high/low/close is unknown. Raising the trail from **close** then stopping out on **low of the same bar** can invent stops that never existed in real time (if low printed before the close that justified the tighter trail). This is **path-dependent simulation error**, usually modest, direction ambiguous without tick data.

Also: no SL check on the entry bar (exit block runs only when already in position at start of iteration; entry is after). Mild positive bias (misses same-bar stop-outs).

Donch entry uses `donch_hi[i-1]` — OK.

Initial risk sizing uses `sl_atr` while initial stop uses `trail_atr` when trail > 0 — intentional but **inconsistent risk geometry** (lots sized on 2.0 ATR, stop placed at 2.5–3.0 ATR). Not look-ahead; can understate risk / oversize.

### 3.4 Indicators / split

- `atr_pctile`: rolling-100 rank of last value only — causal (same as prior skeptic).
- Non-fib modes: `extend_indicators` on full series then time-split — OK for causal features.
- Fib: rebuilds H4 + pivots **per window** (develop vs holdout separately) — good isolation; still broken confirmation lag *inside* each window.
- `hard_pass` uses **strict** `PF > 1.5` and `WR > 55` (not `>=`); survivors prose sometimes says `>=`. No config sits on the boundary in a way that flips the outcome.

### 3.5 PF=99.0 zero-loss inflation

`metrics_from_pnls` sets PF=99 when there are wins and zero losses. Holdout shows PF=99 for several vol_gate cells with n=1–2. Correctly labeled underpowered; must never be read as “PF 99 edge.”

---

## 4. Sample size on holdout (all configs; no survivors)

Holdout window: **2026-01-02 01:00 → 2026-08-06 18:00 UTC**, **3523 H1 bars** (~7 months). Hard gate: `n_trades >= 20`.

### 4.1 Full holdout n / PF / WR / DD

| id | family | n | PF | WR% | DD% | NP | status |
|---|---|---:|---:|---:|---:|---:|---|
| vol_gate_sparse_a035_r30 | vol_gate | 1 | 99.0* | 100 | 0.23 | 106 | underpowered |
| vol_gate_sparse_a035_r35 | vol_gate | 17 | 1.537 | 64.7 | 1.96 | 248 | underpowered† |
| vol_gate_sparse_a040_r30 | vol_gate | 2 | 99.0* | 100 | 0.23 | 106 | underpowered |
| vol_gate_sparse_a040_r35 | vol_gate | 17 | 1.342 | 64.7 | 2.61 | 181 | underpowered† |
| vol_gate_sparse_a050_r30 | vol_gate | 2 | 99.0* | 100 | 0.23 | 106 | underpowered |
| vol_gate_sparse_a050_r35 | vol_gate | 17 | 1.244 | 64.7 | 2.86 | 135 | underpowered† |
| donch_turtle_s1_sl20 | turtle | 45 | 1.368 | 40.0 | 9.31 | 714 | fail (WR) |
| donch_turtle_s1_sl25_ema | turtle | 34 | 1.483 | 44.1 | 6.35 | 515 | fail (WR, PF) |
| donch_turtle_s2_sl20 | turtle | 21 | 1.804 | 33.3 | 13.1 | 817 | fail (WR, DD) |
| donch_turtle_s2_sl25_ema | turtle | 19 | 1.237 | 31.6 | 9.34 | 203 | underpowered† |
| donch_turtle_s1_sl20_ema_vol | turtle | 24 | 0.947 | 29.2 | 10.4 | −55 | fail |
| donch_turtle_s2_sl20_ema_vol | turtle | 15 | 1.878 | 26.7 | 12.4 | 749 | underpowered |
| htf_fib_xau_filt_on_* (×3) | fib | 0 | 0 | 0 | 0 | 0 | underpowered |
| htf_fib_xau_filt_off_* (×3) | fib | 3 | mixed | mixed | ≤3 | small | underpowered |
| atr_trail_n20_v055_t25 | trail | 30 | 0.770 | 36.7 | 13.0 | −344 | fail |
| atr_trail_n20_v055_t30 | trail | 26 | 0.860 | 30.8 | 14.4 | −236 | fail |
| atr_trail_n20_v065_t25 | trail | 26 | 0.823 | 34.6 | 10.8 | −219 | fail |
| atr_trail_n24_v055_t25 | trail | 27 | 0.858 | 40.7 | 11.4 | −189 | fail |
| atr_trail_n24_v055_t30 | trail | 23 | 0.984 | 34.8 | 12.4 | −24 | fail |
| atr_trail_n24_v065_t30 | trail | 19 | 1.344 | 36.8 | 9.66 | 389 | underpowered† |

\* PF=99 artifact (zero losses).  
† Flagged `underpowered_positive` (PF>1.2, NP>0, n∈[8,19], DD<10) — **flag only, not promote**.

### 4.2 Sample-size verdict

- **No config** has holdout n≥20 **and** hard PF/WR/DD.
- Sparse MR: best statistical shape (WR~65, low DD) but **n=17** max — systematically underpowered on a 7-month H1 holdout; develop n for tight RSI30 cells was 3–4.
- Turtle S1 raw: n=45 adequate for a WR test; **WR 40% fails gate** (trend systems often live at 35–45% WR — gate is hostile by design; fail closed).
- ATR trail: n=19–30 adequate; **all PF&lt;1 and/or DD&gt;10** except the n=19 underpowered_positive.
- Fib: **n≤3** — unusable.

**Survivors sample size:** N/A — empty set.

---

## 5. Survive count (`real=true` only if hard gates + clean protocol)

### Hard gates (protocol)

```text
profit_factor > 1.5
win_rate      > 55.0
max_drawdown_pct < 10.0
n_trades      >= 20
```

### Gate matrix outcome

| Bucket | Count |
|---|---:|
| hard_pass | **0** |
| underpowered (n&lt;20) | 15 |
| fail (n≥20 but gates miss) | 9 |
| underpowered_positive (soft flag) | 5 |
| **real survivors** | **0** |

Closest non-survivors (why they die):

| id | Why not real |
|---|---|
| `vol_gate_sparse_a035_r35` | PF 1.54 WR 65 DD 2.0 — **n=17 &lt; 20**; prior-OOS-informed family |
| `donch_turtle_s2_sl20` | PF 1.80 n=21 — **WR 33, DD 13** |
| `donch_turtle_s1_sl25_ema` | n=34 DD 6.3 — **WR 44, PF 1.48 &lt; 1.5** |
| `donch_turtle_s1_sl20` | n=45 DD 9.3 — **WR 40, PF 1.37** |

### Protocol cleanliness for `real=true`

| Criterion | Met? |
|---|---|
| Configs frozen before eval (fingerprint) | YES |
| Single pass; no holdout re-pick | YES |
| n_evaluated = n_registered | YES |
| Hard gates only for promote | YES (script + survivors) |
| Holdout virgin for family design | **NO** (prior shortlist OOS) |
| Fib simulator causal | **NO** (confirmation lag) |
| Multiplicity-corrected inference | NO (not claimed) |

**`real=true` survive count = 0.**  
Even if one config had cleared arithmetic gates, skeptic would still mark **unverified** for promotion because (a) family selection saw this window before, and (b) fib path is look-ahead-tainted (fib did not pass anyway).

Underpowered_positive (5) are **explicitly not survivors** per protocol note.

---

## 6. Explicit promote / do-not-promote

### DO NOT PROMOTE

- **Any** of the 24 pre-registered configs to paper, dry, or live.
- **Any** underpowered_positive cell as “almost validated.”
- Writing `strategy_params.json` / live Expert inputs from this holdout.
- Claiming “holdout confirmed edge” for vol_gate residual shape (n&lt;20; non-virgin design).
- Claiming turtle PF&gt;1.5 alone as promotion (WR/DD gates fail; WR gate is intentional).

### Allowed (research only)

- Keep lock + registry immutable as an audit trail of this failed attempt.
- Fix Fib pivot stamp to `c+right` before any future fib registration.
- If a **new** virgin holdout is defined (e.g. data after 2026-08-06, or a period never used in shortlist OOS / redesign notes), re-register **before** any evaluation; do not recycle these 24 as if first look.
- Consider trend-family gate redesign only on **develop**, with WR gate replaced by expectancy/edge metrics *pre-registered* — never by peeking this holdout ranking.

### Promote checklist (all required; currently all fail or N/A)

1. ~~≥1 config hard_pass on sealed holdout~~ **FAIL (0)**  
2. ~~Holdout unused for family/param selection~~ **FAIL (prior OOS contamination)**  
3. ~~Causal simulators (esp. Fib confirmation)~~ **FAIL for Fib**  
4. ~~n≥20 (prefer ≥40) on holdout~~ **no passer**  
5. ~~No post-holdout re-tune~~ **PASS for this eval**  
6. ~~Deflated / multiplicity-aware claim if many trials upstream~~ **not met / not claimed**

---

## Final line

| Metric | Value |
|---|---|
| **Survive count (`real=true`)** | **0** |
| **Promote** | **NO** |
| **Holdout eval seal** | Mechanical YES; design virginity NO |
| **Hidden search this run** | No (24 frozen) |
| **Look-ahead** | Fib confirmation lag **critical**; Donch OK; trail same-bar ambiguity |
| **Action** | **NO-GO** — do not promote; do not `--live` |

```text
SURVIVE=0  PROMOTE=NO  FAIL_CLOSED=true
```
