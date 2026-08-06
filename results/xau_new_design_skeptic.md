# XAU New-Design Skeptic Review (Hostile Quant)

**Date:** 2026-08-06  
**Artifacts reviewed:**
- `results/xau_new_design_search.json`
- `results/xau_new_design_walkforward.json`
- `results/xau_new_design_candidates.json`
- `scripts/xau_new_design_search.py`
- `scripts/xau_new_design_walkforward.py`
- `backtest.py` (`indicators`, `passes`, `metrics_from_pnls`)

**Verdict stance:** Fail closed. Unverified if evidence missing. Claims of edge require *independent* OOS that was not used for selection, adequate trade counts, and hard gates — not soft folds or arithmetic mean of PFs.

---

## Executive summary

| Claim surface | Result |
|---|---|
| Train-only grid + frozen shortlist OOS protocol (search) | **Partially sound** |
| Walk-forward as independent confirmation | **Contaminated** (folds 1–2 fully inside search train) |
| `candidates.json` (2 designs: vol_gate_bb, ema_pullback) | **Does not survive scrutiny** |
| Survive count (`real=true` with evidence) | **0** |
| Recommendation | **NO-GO** — do not promote, do not paper-trade as validated, do not touch live |

---

## 1. Look-ahead / leakage risks

### 1.1 `atr_pctile` (rolling rank) — **no future leak found**

```python
# scripts/xau_new_design_search.py — extend_indicators
d["atr_pctile"] = atr.rolling(100, min_periods=30).apply(_rank_last, raw=True)
# _rank_last: rank of last value within the window only
```

- Window is causal (ends at bar `i`).
- Meta correctly labels: `"atr_pctile": "rolling_100_rank_0_1"`.
- **Status:** verified causal. Not a look-ahead vector.

### 1.2 Donchian breakout — **same-bar high avoided correctly**

Breakout modules use prior bar channel:

```text
long_sig = close[i] > donch_hi[i - 1]   # atr_breakout / dual_regime bo
```

`donch_hi_n = high.rolling(n).max()` *includes* bar `i` high if indexed at `i`, but the signal correctly shifts to `i-1`.  
**Status:** no classic Donchian same-bar leak.

### 1.3 Mean-reversion / pullback signals — **bar-close entry (standard, not future)**

- `vol_gate_bb` / dual MR: `low[i] <= bb_lo[i]` and `close[i] > bb_lo[i]` → entry at `close[i]`.
- `ema_pullback`: touch on `low[i]` vs EMA + close recovery same bar.

This is bar-close logic, not peeking at bar `i+1`. Mild **execution optimism** (fill at close after seeing full OHLC of the signal bar) is present in *all* families — common in H1 research, not automatic invalidation, but **live expectancy should be marked lower** (spread, gap, partial fill). Status: **not pure look-ahead; unverified as tradable fill quality**.

### 1.4 Full-series indicator compute then split — **OK for causal features**

```python
d = extend_indicators(raw)
train = d.loc[times < split_ts]
oos = d.loc[times >= split_ts]
```

EMAs, ATR, BB, rolling ranks are causal → train-bar values match a train-only recompute.  
**Status:** no train/OOS indicator contamination from this pattern.

### 1.5 Exit / entry bar mechanics — **minor optimism bugs**

| Issue | Evidence | Impact |
|---|---|---|
| No SL/TP on entry bar | Entry sets `pos` after exit block; first risk check next bar | Mild positive bias (misses same-bar stop-outs) |
| `cooldown=1` same-bar re-entry | Exit sets `cool=cooldown`, then same iteration `cool -= 1`; if `cooldown==1`, cool→0 and entry allowed same bar | `vol_gate_bb` shortlist uses `cooldown: 1` — can re-enter after exit on same bar |
| Zero-loss PF = 99.0 | `metrics_from_pnls`: `pf = 99.0 if gw > 0 else 0` when no losses | Inflates train metrics (e.g. WF fold1 train: 6 wins, PF 99) |

None of these alone invent the full train edge, but they **bug-inflate** some train scores and slightly overstate OOS for low-cooldown configs.

### 1.6 **CRITICAL: walk-forward OOS is not independent of parameter selection**

Search split (from holdout / meta):

```text
split = 2026-01-02 18:18:00+00:00
train_bars = 8132  (times < split)
oos_bars   = 3505  (times >= split)
```

WF folds (`xau_new_design_walkforward.json`):

| Fold | OOS window | Relation to **search train** (`< 2026-01-02`) |
|---|---|---|
| 1 | 2025-01-02 → 2025-05-27 | **Fully inside search train** |
| 2 | 2025-05-27 → 2025-10-17 | **Fully inside search train** |
| 3 | 2025-10-17 → 2026-03-13 | **Partial** (pre-split in-sample; post-split true OOS) |
| 4 | 2026-03-13 → 2026-08-06 | **True post-selection OOS** (also inside frozen shortlist OOS region) |

**Implication:** fixed-param WF aggregates for shortlisted designs are **heavily contaminated**. Folds 1–2 (and much of 3) are not “OOS” relative to grid selection — they are **in-sample replay** of the period used to pick family bests.  
Any “mean PF,” “soft_pass_rate,” or “sum NP” that leans on folds 1–3 is **not confirmatory evidence**.

True independent checks available in artifacts:

1. **Frozen shortlist OOS** once after train-only selection (protocol-correct in search script).
2. **WF fold 4** only (and the post-2026-01-02 slice of fold 3) — still small-N.

### 1.7 Selection on train only — **search script OK**

`xau_new_design_search.py` selects best per family on `train` only, then evaluates shortlist OOS once. Meta note is honest.  
**Leak path is not in the train loop; it is in treating contaminated WF as qualification evidence in `qualifies_candidate`.**

### 1.8 Candidate gate bypass — **logical contamination**

```python
# walkforward qualifies_candidate:
# if shortlist OOS PF/n fail, accept if fixed WF mean_PF > 1.2 and n >= 8
```

This **re-admits designs that failed the only clean OOS** by using a WF metric that reuses search-train bars. That is selection bias / metric shopping, not validation.

---

## 2. Multiple testing / overfit risk

| Quantity | Value |
|---|---|
| Total train evals | **3798** |
| Train passers (`passes`: n≥20, PF>1.5, WR>55, DD<10) | **78** |
| Families | 4 |
| Shortlist size | 4 (one family best each) |
| Frozen OOS evals | 4 (once each) |
| Candidate soft criteria | further OR-gates on contaminated WF |

**Interpretation (hostile):**

- ~3.8k correlated trials on the same H1 XAU path ⇒ high family-wise error rate. 78 train passers is **expected under mild path noise + long-only bull bias in gold 2024–2025**, not proof of 78 edges.
- Selection maximises train NP among passers (`is_better` → `net_profit` primary). That **explicitly overfits** the train path.
- `ema_pullback` alone: 2722 evals, 77 passers — almost all train passers come from one family. Classic **multiple-testing soup**.
- No deflated Sharpe, no SPA/White reality check, no holdout locked *before* family design, no Bonferroni/FDR.
- Neighbor **refit** adds another ~24 trials per fold (optional path) — secondary overfit risk; primary fixed path already fails scrutiny.

**Status:** overfit risk **severe**. Train edges are **not** credible as real until independent OOS holds with adequate N and hard gates.

---

## 3. Sample size adequacy on OOS

Hard gate requires `n_trades >= 20`. Soft fold gate allows `n < 20` with PF>1.2, WR>50, DD<12.

### 3.1 Frozen shortlist OOS (only clean single-split OOS)

| Design | n | PF | WR | NP | oos_gates | Adequacy |
|---|---|---|---|---|---|---|
| vol_gate_bb | **16** | 1.19 | 62.5 | +103 | **false** | **Inadequate** (n&lt;20; PF&lt;1.5) |
| atr_breakout | 23 | 0.94 | 34.8 | −57 | false | n OK; edge **negative** |
| ema_pullback | 28 | **0.71** | 32.1 | **−449** | false | n OK; **clear fail** |
| dual_regime | 35 | 1.10 | 37.1 | +136 | false | n OK; PF/WR fail hard gates |

### 3.2 Walk-forward trade counts (contaminated + small per fold)

| Design | total WF n | per-fold n | hard_pass_rate | soft_pass_rate |
|---|---|---|---|---|
| vol_gate_bb | 41 | 7, 7, 14, 13 | **0.0** | 0.75 |
| atr_breakout | 73 | 19–23 | 0.0 | 0.0 |
| ema_pullback | 100 | 19–31 | 0.5 | 0.5 |
| dual_regime | 113 | 24–32 | 0.0 | 0.0 |

**vol_gate_bb:** every fold has **n &lt; 20**. Soft passes on 7-trade folds (e.g. fold2 PF=5.11, 6W/1L) are **noise**, not stability.  
**ema_pullback:** aggregate N looks fine, but **hard passes only on folds 2–3 (search-train-contaminated)**; fold4 true-ish OOS: n=19, PF=0.42, WR=21%, NP=−657.

### 3.3 Mean PF aggregation bug (metric inflation)

`aggregate_folds` uses **arithmetic mean of per-fold PFs**, not trade-weighted combined PF:

```text
vol_gate_bb fold PFs: 0.36, 5.11, 1.55, 1.27  → mean_PF ≈ 2.07
```

One 7-trade miracle fold dominates the headline. **Combined / trade-weighted PF would be far lower.** Treat `mean_profit_factor` as **misleading** unless recomputed from pooled PnLs (not present in artifacts).

### 3.4 Sample-size verdict

- No design has **hard** OOS evidence with adequate, independent trades.
- vol_gate is **structurally undersampled** (rare vol-gated MR).
- ema_pullback has enough shortlist OOS trades to **reject**, not to promote.

---

## 4. Which candidate claims survive scrutiny?

`candidates.json` claims **n_candidates = 2** under soft criteria. Hostile re-grade below.

### 4.1 Survival criteria used here (`real=true` only if all hold)

1. Clean protocol: selected without the OOS window used for claim.
2. Frozen shortlist OOS **passes hard gates** *or* true post-selection folds (fold4 + post-split) do, with n≥20.
3. No catastrophic late-period collapse that contradicts early “wins.”
4. Not qualified solely via contaminated WF / soft n&lt;20 / mean-of-PFs.

### 4.2 Per-design

#### `vol_gate_bb` — **real=false** (candidate claim **rejected**)

| Check | Result |
|---|---|
| train_gates | true (n=28, PF=1.81, WR=71, DD=2.5) — **in-sample only** |
| shortlist OOS hard gates | **FAIL** (n=16, PF=1.19) |
| WF hard_pass_rate | **0.0** |
| WF independence | folds 1–2 in search train |
| Sample size | 7–16 trades typical — **inadequate** |
| mean_PF ≈ 2.07 | **inflated** by 7-trade PF=5.11 fold |
| qualify_reason | `soft_pass_rate=0.75` — **soft/noise** |

Evidence for a real edge: **missing**. Residual small positive shortlist NP (+103 on 16 trades) is **unverified noise**, not a pass.

#### `ema_pullback` — **real=false** (candidate claim **rejected hard**)

| Check | Result |
|---|---|
| train_gates | true (n=98, PF=1.91, NP=+4284) — **most overfit-looking family** |
| shortlist OOS | **FAIL catastrophically**: PF **0.71**, WR **32%**, NP **−449**, n=28 |
| WF folds 1–3 | Strong NP — but **inside / largely inside search train** |
| WF fold 4 | PF **0.42**, WR **21%**, NP **−657** — true late OOS **dies** |
| qualify_reason | `soft_pass_rate=0.50` **despite** shortlist OOS failure |

This is textbook **train/WF contamination + OOS death**. Promoting it as a candidate is a **criteria bug**, not a research result.  
**real=false** with strong evidence *against* out-of-sample edge.

#### `atr_breakout` — **real=false** (already rejected in candidates)

- train_gates=false; shortlist OOS PF 0.94 NP −57.
- Early WF folds profitable (in-sample-ish vs search train), fold4 PF 0.36 collapse.
- Correctly rejected for train_gates; would fail OOS scrutiny anyway.

#### `dual_regime` — **real=false** (already rejected)

- train_gates=false; shortlist OOS PF 1.10 fails hard gates.
- fold4 negative; soft_pass_rate 0.

### 4.3 Survive table

| Design | candidates.json | Skeptic `real` | Evidence |
|---|---|---|---|
| vol_gate_bb | listed | **false** | OOS gates fail; n too small; WF contaminated; hard_pass 0 |
| ema_pullback | listed | **false** | Clean OOS deeply negative; fold4 collapse |
| atr_breakout | rejected | **false** | OOS loss; train fail |
| dual_regime | rejected | **false** | OOS fail hard gates; train fail |

**Survive count: 0**

---

## 5. Explicit NO-GO

### NO-GO — nothing survives scrutiny

**Do not:**

- Promote either “candidate” to paper or live.
- Write strategy params / EA inputs from this shortlist.
- Cite WF mean PF or soft_pass_rate as confirmation.
- Claim “OOS validated” for vol_gate_bb (small-N soft wins) or ema_pullback (failed frozen OOS).

**If research continues (optional; not an approval):**

1. **Lock a true holdout** (e.g. last 20–25% of bars or calendar 2026H1+) *before* any further grid; never touch it until one pre-registered design is chosen.
2. Re-run WF **only on OOS region after search split**, or re-select params *inside each fold train* without ever seeing global shortlist fitted on overlapping bars.
3. Require **hard** gates on independent OOS: n≥20 (preferably ≥40), PF>1.5, WR>55, DD&lt;10 — no soft n&lt;20 for promotion.
4. Report **pooled** OOS PF (sum wins / sum |losses|), not mean of fold PFs.
5. Multiple-testing: pre-limit family grids; report how many trials; consider deflated metrics.
6. Fix cooldown semantics (no same-bar re-entry); stress fills with spread/slippage model.
7. Until then, label all train-beating configs: **`UNVERIFIED / RESEARCH ONLY`**.

### Honest residual signals (not approvals)

- Search protocol (train select → freeze OOS once) is the right *shape*; OOS results simply **did not pass**.
- Long-only gold 2024–mid-2025 can make many trend/pullback grids look good **in sample**; fold4 / post-2026-01 failures are consistent with regime/path dependency, not robust alpha.
- vol_gate_bb has low DD and sparse trades — even if eventually real, **current N cannot prove it**. Fail closed.

---

## Appendix A — Key numbers (source of truth)

**Search meta:** 3798 evals; split 2026-01-02; train 8132 / oos 3505 bars; 78 train passers.

**Shortlist OOS (frozen):**

```text
vol_gate_bb   PF=1.194  n=16  NP=+102.7   oos_gates=false
atr_breakout  PF=0.937  n=23  NP= -56.8   oos_gates=false
ema_pullback  PF=0.708  n=28  NP=-449.4   oos_gates=false
dual_regime   PF=1.098  n=35  NP=+136.5   oos_gates=false
```

**Candidates qualify reasons (insufficient under this review):**

```text
vol_gate_bb:  soft_pass_rate=0.75>=0.5   → contaminated + soft n
ema_pullback: soft_pass_rate=0.50>=0.5   → ignores shortlist OOS failure
```

---

## Appendix B — Script audit checklist

| Check | Finding |
|---|---|
| Look-ahead atr_pctile | Clean (rolling rank) |
| Donchian same-bar | Avoided via `i-1` |
| Train contamination in search loop | Not found |
| OOS used in selection (search) | Not found |
| WF OOS vs search train overlap | **Found — critical** |
| Candidate OR-gate on contaminated WF | **Found — critical** |
| Soft pass n&lt;20 promotion | **Found — weak** |
| mean_PF arithmetic | **Found — inflates** |
| PF=99 zero-loss | **Found — train only** |
| cooldown=1 same-bar re-entry | **Found — mild** |
| Bug inventing large OOS profits | Not found; OOS mostly fails honestly |

---

**Final line:** **Survive = 0. Hard recommendation = NO-GO.**
