# XAU Pre-Registered Holdout — Summary

**Symbol / TF:** XAUUSD H1  
**Artifacts:** `xau_preregistered_registry.json`, `xau_holdout_lock.json`, `xau_preregistered_holdout_eval.json`, `xau_preregistered_survivors.json`, `xau_preregistered_skeptic.md`  
**Phase flags:** PREREG · IMPL · EVAL · SKEPTIC → **final: NO-GO**

| Phase | Status | One-line |
|---|---|---|
| PREREG | true | `vol_gate_sparse=6`, `donchian_turtle=6`, `htf_fib_xau=6`, `atr_trail_breakout=6` (total **24**); `holdout_start=2026-01-01T00:00:00+00:00` |
| IMPL | true | 24 configs scored: `hard_pass=0`, `underpowered=15`, `fail=9` |
| EVAL | true | **NONE** (survivors empty; no hard-gate passers) |
| SKEPTIC | true | `survive=0`; `promote=NO` |

---

## Safety

- **Research only.** Offline backtests; never recommend or run `--live`.
- Skeptic **real survivors = 0** → **no paper, no dry-run, no strategy_params write, no live**.
- Underpowered_positive flags (5 cells) are **flag-only, not promotion** — do not treat as dry/paper candidates.
- Holdout is mechanically sealed for the 24-config single pass; design-level prior OOS contamination still blocks any soft “almost validated” narrative.
- Fib simulator has confirmed pivot-confirmation look-ahead; fib metrics are not trustable for any future claim until fixed.

---

## Protocol

| Item | Value |
|---|---|
| Holdout start (lock) | `2026-01-01T00:00:00+00:00` |
| Develop end | `2025-12-31T23:59:59+00:00` |
| Holdout rule | NEVER used for selection; single evaluation after all configs frozen |
| Max configs / family | 6 |
| Families | 4 × 6 = **24** frozen configs |
| Registry sha256 (lock) | `eb9ec45fc4f6a0c7d71d6f6117f297459fa9c0c4f80b9f1f384fe1640c999b16` |
| Data CSV | `xauusd_data.csv` |
| H1 range (eval) | develop `2024-08-16 19:00` → `2025-12-31 23:00` (**8114** bars); holdout `2026-01-02 01:00` → `2026-08-06 18:00` (**3523** bars) |
| Hard gates (holdout promote) | PF **> 1.5**, WR **> 55%**, max DD **< 10%**, n_trades **≥ 20** |
| Soft note | holdout n_trades < 20 → **UNDERPOWERED** (not pass) |
| Selection policy | single-pass pre-registered only; no grid; no holdout re-pick |
| Underpowered_positive rule | PF>1.2 AND NP>0 AND n∈[8,19] AND DD<10 — **flag only, not promote** |
| Verification | `n_registered=n_evaluated=24`, `ids_match=true`, `no_extra_trials=true`, `holdout_start_matches_lock=true` |
| `candidate_params_written` | **false** |

### Families (pre-registered)

| Family | Mode | Side | n | Thesis (registry) |
|---|---|---|---:|---|
| `vol_gate_sparse` | `vol_gate_bb` | long_only | 6 | Sparse calm-regime BB reclaim MR; fixed SL/TP 1.5/2.5, bb_lo15+ema200 |
| `donchian_turtle` | `donchian_turtle` | long_only | 6 | Classic turtle S1/S2 channel TF; ATR stop; optional EMA200 / vol gate |
| `htf_fib_xau` | `htf_fib` | both_flat_only | 6 | H4 Fib 61.8–78.6 golden zone on XAU H1; EMA200 bias; flat_only |
| `atr_trail_breakout` | `atr_trail_breakout` | long_only | 6 | Donch breakout under elevated atr_pctile; ATR trail, no fixed TP |

---

## Configs evaluated (develop vs holdout)

Hard gates applied on **holdout only**. Develop is diagnostic.  
\* PF=99.0 = zero-loss artifact (`metrics_from_pnls`).  
† Flagged `underpowered_positive` in survivors (not promoted).

| id | family | status | dev n | dev PF | dev WR% | dev DD% | dev NP | ho n | ho PF | ho WR% | ho DD% | ho NP |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vol_gate_sparse_a035_r30 | vol_gate | underpowered | 3 | 0.974 | 66.7 | 1.49 | −2.6 | 1 | 99.0* | 100 | 0.23 | +105.5 |
| vol_gate_sparse_a035_r35 | vol_gate | underpowered† | 26 | 1.457 | 69.2 | 2.86 | +353.6 | 17 | 1.537 | 64.7 | 1.96 | +247.8 |
| vol_gate_sparse_a040_r30 | vol_gate | underpowered | 4 | 3.410 | 75.0 | 1.85 | +239.6 | 2 | 99.0* | 100 | 0.23 | +106.4 |
| vol_gate_sparse_a040_r35 | vol_gate | underpowered† | 28 | 1.793 | 71.4 | 2.45 | +605.9 | 17 | 1.342 | 64.7 | 2.61 | +180.8 |
| vol_gate_sparse_a050_r30 | vol_gate | underpowered | 7 | 1.266 | 57.1 | 3.11 | +74.3 | 2 | 99.0* | 100 | 0.23 | +106.4 |
| vol_gate_sparse_a050_r35 | vol_gate | underpowered† | 35 | 1.400 | 65.7 | 6.47 | +453.2 | 17 | 1.244 | 64.7 | 2.86 | +134.9 |
| donch_turtle_s1_sl20 | turtle | fail | 125 | 2.043 | 44.8 | 8.32 | +8573.2 | 45 | 1.368 | 40.0 | 9.31 | +714.0 |
| donch_turtle_s1_sl25_ema | turtle | fail | 107 | 2.229 | 47.7 | 8.08 | +6068.7 | 34 | 1.483 | 44.1 | 6.35 | +515.0 |
| donch_turtle_s2_sl20 | turtle | fail | 64 | 3.165 | 54.7 | 6.75 | +7215.0 | 21 | 1.804 | 33.3 | 13.09 | +816.8 |
| donch_turtle_s2_sl25_ema | turtle | underpowered† | 62 | 2.655 | 56.5 | 4.97 | +4664.6 | 19 | 1.237 | 31.6 | 9.34 | +203.1 |
| donch_turtle_s1_sl20_ema_vol | turtle | fail | 73 | 2.164 | 43.8 | 6.84 | +4561.4 | 24 | 0.947 | 29.2 | 10.43 | −55.2 |
| donch_turtle_s2_sl20_ema_vol | turtle | underpowered | 45 | 3.338 | 53.3 | 7.16 | +5035.3 | 15 | 1.878 | 26.7 | 12.38 | +749.0 |
| htf_fib_xau_filt_on_sl15_tp20 | fib | underpowered | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| htf_fib_xau_filt_on_sl15_tp30 | fib | underpowered | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| htf_fib_xau_filt_on_sl20_tp30 | fib | underpowered | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| htf_fib_xau_filt_off_sl15_tp20 | fib | underpowered | 14 | 0.786 | 35.7 | 5.33 | −172.3 | 3 | 2.607 | 66.7 | 1.10 | +116.5 |
| htf_fib_xau_filt_off_sl15_tp30 | fib | underpowered | 14 | 0.824 | 28.6 | 7.41 | −160.6 | 3 | 0 | 0 | 3.03 | −214.2 |
| htf_fib_xau_filt_off_sl20_tp30 | fib | underpowered | 13 | 1.346 | 46.2 | 5.02 | +219.2 | 3 | 0.698 | 33.3 | 2.20 | −50.7 |
| atr_trail_n20_v055_t25 | trail | fail | 88 | 1.268 | 39.8 | 9.96 | +1100.9 | 30 | 0.770 | 36.7 | 12.95 | −344.3 |
| atr_trail_n20_v055_t30 | trail | fail | 74 | 1.822 | 47.3 | 5.93 | +3217.0 | 26 | 0.860 | 30.8 | 14.43 | −236.5 |
| atr_trail_n20_v065_t25 | trail | fail | 77 | 1.170 | 41.6 | 9.51 | +634.8 | 26 | 0.823 | 34.6 | 10.81 | −218.6 |
| atr_trail_n24_v055_t25 | trail | fail | 80 | 1.421 | 41.3 | 7.19 | +1541.9 | 27 | 0.858 | 40.7 | 11.41 | −189.2 |
| atr_trail_n24_v055_t30 | trail | fail | 67 | 1.920 | 47.8 | 6.32 | +3304.3 | 23 | 0.984 | 34.8 | 12.43 | −24.1 |
| atr_trail_n24_v065_t30 | trail | underpowered† | 60 | 1.829 | 46.7 | 6.47 | +2590.2 | 19 | 1.344 | 36.8 | 9.66 | +388.7 |

### Gate summary

| Bucket | Count |
|---|---:|
| hard_pass | **0** |
| underpowered (n&lt;20) | **15** |
| fail (n≥20, gates miss) | **9** |
| underpowered_positive (soft flag) | **5** |
| **real survivors** | **0** |

### Closest non-survivors (why not hard_pass)

| id | Holdout highlight | Blocker |
|---|---|---|
| `vol_gate_sparse_a035_r35` | PF 1.537, WR 64.7, DD 1.96 | **n=17 &lt; 20** |
| `donch_turtle_s2_sl20` | PF 1.804, n=21, NP +817 | **WR 33.3; DD 13.1** |
| `donch_turtle_s1_sl25_ema` | n=34, DD 6.35, NP +515 | **WR 44.1; PF 1.483 &lt; 1.5** |
| `donch_turtle_s1_sl20` | n=45, DD 9.31, NP +714 | **WR 40.0; PF 1.368** |

---

## Survivors

| Field | Value |
|---|---|
| `n_survivors` | **0** |
| `survivors` | `[]` |
| hard_pass | 0 |
| underpowered | 15 |
| fail | 9 |
| underpowered_positive | 5 (flag only) |

### Underpowered_positive (not promoted)

Rule: holdout PF>1.2 AND NP>0 AND n∈[8,19] AND DD&lt;10.

| id | family | ho n | ho PF | ho WR% | ho DD% | ho NP |
|---|---|---:|---:|---:|---:|---:|
| vol_gate_sparse_a035_r35 | vol_gate_sparse | 17 | 1.537 | 64.7 | 1.96 | +247.8 |
| atr_trail_n24_v065_t30 | atr_trail_breakout | 19 | 1.344 | 36.8 | 9.66 | +388.7 |
| vol_gate_sparse_a040_r35 | vol_gate_sparse | 17 | 1.342 | 64.7 | 2.61 | +180.8 |
| vol_gate_sparse_a050_r35 | vol_gate_sparse | 17 | 1.244 | 64.7 | 2.86 | +134.9 |
| donch_turtle_s2_sl25_ema | donchian_turtle | 19 | 1.237 | 31.6 | 9.34 | +203.1 |

**Reason (survivors):** No config passed hard holdout gates (PF≥1.5, WR≥55.0, DD&lt;10.0, n_trades≥20). Of 24 pre-registered configs: 0 hard_pass, 15 underpowered, 9 fail. 5 underpowered_positive flagged — not promoted.

---

## Skeptic

**Source:** `results/xau_preregistered_skeptic.md`  
**Stance:** Fail closed. Soft / underpowered / contaminated ≠ survive.

| Question | Verdict |
|---|---|
| Holdout sealed for 24-config single pass? | **YES (mechanical)** — lock fingerprint matches; eval after freeze; no re-pick |
| Holdout virgin for family / thesis selection? | **NO** — same ~2026-01+ window already used as prior shortlist OOS |
| Re-tuning after this holdout eval? | **NONE found** |
| Config count ≤6/family; hidden search this run? | **6×4=24 exact; no in-script grid** |
| Look-ahead | **Fib: CRITICAL confirmation lag** (stamp at pivot center, not `c+right`); Donch OK; trail same-bar path ambiguity |
| Hard-gate survivors (`real=true`)? | **0** |
| Promote? | **DO NOT PROMOTE** |

**Survive count (`real=true`): 0**  
Even arithmetic hard_pass would still be unverified for promotion given (a) prior-OOS design contamination and (b) fib confirmation bug (fib did not pass anyway).

```text
SURVIVE=0  PROMOTE=NO  FAIL_CLOSED=true
```

---

## Winner or NO-GO

# **NO-GO**

- **Winner id:** none  
- **Promote:** **NO**  
- **Paper / dry / live:** **none** (no skeptic real survivors)  
- **Do not write** promotion params or claim holdout-confirmed edge  
- Turtle PF&gt;1 on some cells is **not** promotion (WR/DD gates fail by design)  
- Sparse MR shape (WR~65, low DD) remains **underpowered** (max n=17 on holdout)

---

## Next steps

1. **Do not promote** any of the 24 configs; keep lock + registry immutable as audit of this failed attempt.
2. **Fix Fib pivot stamp** to confirmation index `c+right` (and after H4 bar close) before any future fib registration; do not trust current fib metrics.
3. If a **new virgin holdout** is defined (data never used in shortlist OOS / redesign — e.g. bars after `2026-08-06`), re-register **before** evaluation; do not recycle these 24 as a first look.
4. Trend-family gate redesign (e.g. expectancy instead of WR&gt;55 for turtles) only on **develop**, pre-registered — never by peeking this holdout ranking.
5. Treat underpowered_positive cells as **research notes only**, not dry-run candidates.
6. Continue offline research only; **never `--live`**.

---

## Sources

| Path | Role |
|---|---|
| `results/xau_preregistered_registry.json` | Frozen 24 configs |
| `results/xau_holdout_lock.json` | Pre-registration lock + fingerprint |
| `results/xau_preregistered_holdout_eval.json` | Develop + holdout metrics |
| `results/xau_preregistered_survivors.json` | Gate application / ranking |
| `results/xau_preregistered_skeptic.md` | Hostile quant review |
