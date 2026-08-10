# XAU new design search

**Symbol / TF:** XAUUSD H1  
**Search split:** 2026-01-02 18:18:00+00:00 (train 8132 bars / OOS 3505 bars)  
**WF data range:** 2024-08-16 → 2026-08-06 (11637 bars), 4 expanding folds  
**Artifacts:** `xau_new_design_specs.json`, `xau_new_design_search.json`, `xau_new_design_walkforward.json`, `xau_new_design_candidates.json`, `xau_new_design_skeptic.md`  
**Phase flags:** DESIGN_OK · BUILD_OK · VALIDATE_OK · SKEPTIC_OK → **final: NO-GO**

---

## Safety

- **Research only.** Offline backtests; never recommend or run `--live`.
- Skeptic survive count = **0** → **no paper, no dry-run promotion, no strategy_params write, no live**.
- Candidates that soft-passed WF gates still lack independent OOS evidence (WF folds 1–2 fully inside search train). Soft-pass is not approval.
- Baseline regime context (specs): ATR mean OOS/train **2.44×**, ret std **1.85×**, BB width **1.76×**; frac close > EMA200 train **0.687** → OOS **0.482**. Prior bb_rsi OOS PF **0.59** (collapsed).

---

## Designs evaluated

### Spec families (6)

| Spec id | Name | Built / gridded? |
|---|---|---|
| `vol_gate_meanrev` | Volatility-gated BB/RSI mean reversion | Yes → mode `vol_gate_bb` |
| `atr_breakout_trend` | ATR-aware N-bar breakout + EMA trend | Yes → mode `atr_breakout` |
| `ema_pullback_trend` | EMA pullback continuation | Yes → mode `ema_pullback` |
| `dual_regime_switch` | HIGH vol breakout else mean-rev | Yes → mode `dual_regime` |
| `htf_fib_proxy` | HTF Fib golden-zone (H4 pivots on H1) | **Not in search shortlist** |
| `donchian_channel` | Donchian trend-follow + ATR stops | **Not in search shortlist** |

### Search meta

| Metric | Value |
|---|---|
| Total train evals | **3798** |
| Train passers (`passes` hard gates) | **78** |
| Search wall time | 105.45 s |
| atr_pctile | rolling_100_rank_0_1 (causal) |
| Selection | train-only per family → freeze shortlist OOS once |

### Train hard gates (specs / search)

- profit_factor > 1.5, win_rate > 55%, max_drawdown_pct < 10%, n_trades ≥ 20

### Family grid outcomes (search)

| Family (search id) | n_evals | n_passers | train_gates | train PF | train NP | train n |
|---|---:|---:|---|---:|---:|---:|
| vol_gate_bb | 226 | 1 | **true** | 1.814 | +622.5 | 28 |
| atr_breakout | 510 | 0 | **false** | 2.457 | +3827.5 | 71 |
| ema_pullback | 2722 | 77 | **true** | 1.911 | +4284.2 | 98 |
| dual_regime | 340 | 0 | **false** | 1.794 | +4017.9 | 102 |

`atr_breakout` / `dual_regime` fail train gates mainly on **win_rate** (47.9% / 45.1%) despite high PF and NP.

---

## Train / OOS table (all shortlist)

Frozen params after train-only selection; OOS evaluated **once**. **All four: `oos_gates=false`.**

| Rank* | Design | train PF | train WR% | train DD% | train n | train NP | oos PF | oos WR% | oos DD% | oos n | oos NP | train_gates | oos_gates |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 2 | **vol_gate_bb** | 1.814 | 71.4 | 2.46 | 28 | +622.5 | **1.194** | 62.5 | 2.63 | 16 | **+102.7** | true | false |
| — | atr_breakout | 2.457 | 47.9 | 3.91 | 71 | +3827.5 | **0.937** | 34.8 | 6.52 | 23 | **−56.8** | false | false |
| 1 | **ema_pullback** | 1.911 | 56.1 | 5.99 | 98 | +4284.2 | **0.708** | 32.1 | 10.46 | 28 | **−449.4** | true | false |
| 3 | dual_regime | 1.794 | 45.1 | 4.42 | 102 | +4017.9 | **1.098** | 37.1 | 7.24 | 35 | **+136.5** | false | false |

\*global_rank from search shortlist (train-side ordering among passers/family bests).

**Shortlist headline:** only `vol_gate_bb` is modestly positive on clean OOS NP with PF slightly above 1.0 — but n=16 &lt; 20 and PF 1.194 &lt; 1.5 → hard OOS fail. `ema_pullback` is the strongest train book and the **worst** frozen OOS (PF 0.71, −449).

### Best frozen params (reference only — not for promotion)

**vol_gate_bb:** atr_max_pct=0.4, rsi_buy=35, rsi_sell=50, sl_atr=1.5, tp_atr=2.5, bb_lo15, ema200 uptrend, cooldown=1, exit_on_vol_spike=true  

**ema_pullback:** ema20 pull, stack ema20&gt;ema50&gt;ema100, atr_buffer=0.5, rsi 40–55 / sell 70, atr_pctile 0–0.75, sl=2.0, tp=3.0, cooldown=2  

**atr_breakout:** donch_n=24, atr_min_pct=0.55, ema100, rsi_max=75, sl=2.0, tp=4.0, cooldown=3  

**dual_regime:** switch_pct=0.6, donch_n=20, rsi_buy=30, rsi_sell=50, bo sl/tp 1.8/4.0, mr sl/tp 1.5/2.5  

---

## Walk-forward ranking

**Method:** expanding train, equal-bar OOS (~2358–2359 bars/fold), fixed shortlist params (primary); light neighbor refit optional.  
**Soft pass (n&lt;20):** PF&gt;1.2, WR&gt;50, DD&lt;12 · **Hard:** PF&gt;1.5, WR&gt;55, DD&lt;10, n≥20.

### Fixed-param aggregate OOS (rank by soft_pass_rate, then sum NP)

| Rank | Design | soft_pass | hard_pass | sum NP | total n | mean PF† | mean WR% | fold soft | fold hard | max OOS DD% |
|---:|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| 1 | vol_gate_bb | **0.75** | **0.00** | +492.7 | 41 | 2.075 | 63.4 | F T T T | F F F F | 2.63 |
| 2 | ema_pullback | **0.50** | **0.50** | +2226.2 | 100 | 1.500 | 49.0 | F T T F | F T T F | 8.78 |
| 3 | atr_breakout | 0.00 | 0.00 | +2125.1 | 73 | 1.997 | 43.8 | F F F F | F F F F | 6.05 |
| 4 | dual_regime | 0.00 | 0.00 | +1809.4 | 113 | 1.352 | — | 0 soft | 0 hard | — |

†**Arithmetic mean of per-fold PFs** — skeptic flags this as inflated (e.g. vol_gate fold2 PF 5.11 on 7 trades). Prefer pooled PF when available.

### Per-fold fixed OOS (key)

**vol_gate_bb** — n always &lt;20; hard_pass never:

| Fold | OOS window | n | PF | WR% | NP | soft |
|---:|---|---:|---:|---:|---:|---|
| 1 | 2025-01-02 → 2025-05-27 | 7 | 0.364 | 42.9 | −237.9 | false |
| 2 | 2025-05-27 → 2025-10-17 | 7 | 5.113 | 85.7 | +376.4 | true |
| 3 | 2025-10-17 → 2026-03-13 | 14 | 1.551 | 64.3 | +237.2 | true |
| 4 | 2026-03-13 → 2026-08-06 | 13 | 1.272 | 61.5 | +116.9 | true |

**ema_pullback** — hard passes only folds 2–3; fold 4 collapses:

| Fold | n | PF | WR% | NP | hard | soft |
|---:|---:|---:|---:|---:|---|---|
| 1 | 31 | 1.764 | 54.8 | +1041.8 | false | false |
| 2 | 23 | 1.950 | 56.5 | +915.5 | true | true |
| 3 | 27 | 1.863 | 55.6 | +925.9 | true | true |
| 4 | 19 | **0.421** | **21.1** | **−657.0** | false | false |

### Candidates gate (VALIDATE)

Criteria: train_gates AND (shortlist OOS PF&gt;1.2 & n≥8 **OR** fixed WF meanPF&gt;1.2 & n≥8) AND (WF soft_pass≥0.5 OR sum_NP&gt;0 with mean_PF&gt;1.2).

| Outcome | Designs |
|---|---|
| **Survived soft criteria (2)** | `vol_gate_bb` (soft_pass 0.75, NP +493), `ema_pullback` (soft_pass 0.50, NP +2226) |
| **Rejected** | `atr_breakout` (train_gates=false), `dual_regime` (train_gates=false) |

---

## Skeptic verdict

**Survive count: 0. Hard recommendation: NO-GO.**

| Claim | Result |
|---|---|
| Train-only grid + frozen shortlist OOS protocol | Partially sound (search loop OK) |
| WF as independent confirmation | **Contaminated** |
| candidates.json (2 designs) | **Does not survive scrutiny** |
| Promote / paper / live | **Do not** |

### Critical failures

1. **WF contamination:** folds 1–2 OOS windows are **fully inside search train** (&lt; 2026-01-02). Fold 3 is partial. Only fold 4 (and post-split slice of fold 3) is true post-selection OOS. Soft_pass_rate and mean PF therefore **overstate** independence.
2. **Candidate OR-gate** re-admits designs that failed clean shortlist OOS by using contaminated WF aggregates (esp. `ema_pullback`: frozen OOS PF 0.71 / −449, still listed via soft_pass 0.50).
3. **Sample size:** `vol_gate_bb` never reaches n≥20 on any WF fold or shortlist OOS (n=16). Soft passes on 7-trade folds are noise.
4. **Multiple testing:** 3798 train evals, 78 passers; `ema_pullback` alone 2722 evals / 77 passers. No deflated metrics / holdout locked before design.
5. **Metric inflation:** mean of fold PFs (e.g. vol_gate 0.36, 5.11, 1.55, 1.27 → mean ~2.07); zero-loss PF=99 on tiny train folds; cooldown=1 same-bar re-entry mild optimism.
6. **True late OOS:** `ema_pullback` fold4 PF **0.42**, WR **21%**, NP **−657**. `atr_breakout` fold4 PF **0.36**. No design hard-passes independent OOS with adequate n.

### Skeptic re-grade

| Design | candidates.json | Skeptic `real` |
|---|---|---|
| vol_gate_bb | listed | **false** (OOS gates fail; n inadequate; WF contaminated; hard_pass 0) |
| ema_pullback | listed | **false** (clean OOS deeply negative; fold4 dies) |
| atr_breakout | rejected | **false** |
| dual_regime | rejected | **false** |

Look-ahead audit: atr_pctile causal; Donchian uses prior bar; no train loop OOS peek. Failures are **evidence / contamination / soft gates**, not invented PnL from future leak.

---

## Winner(s) or none

### **None. NO-GO.**

Do **not**:

- Write `results/xau_candidate_params.json` from this shortlist  
- Start paper or dry-run as “validated”  
- Promote to EA / live / `--live`  
- Cite WF mean PF or soft_pass_rate as confirmation  

Honest residuals (not approvals): search *shape* (train select → freeze OOS once) is correct; OOS simply failed. `vol_gate_bb` has low DD and small positive shortlist NP (+103 / 16 trades) — **unverified noise**. Long-only gold 2024–mid-2025 makes many trend/pullback grids look good in-sample; post-2026-01 / fold4 failures match regime path dependence, not robust alpha.

---

## Recommended next steps

**Do not run more random grids on the same 3798-trial soup.** Redesign process and families with locked independence.

### A. Protocol (required before any new claim of edge)

1. **Lock a true holdout first** (e.g. last 20–25% of bars or calendar 2026H1+) and never touch it until one pre-registered design is chosen.
2. **Re-define WF** so every fold’s OOS is after that design’s train-only selection window — or re-select params *inside each fold train only* with no global shortlist fitted on overlapping bars.
3. Promotion bar: **hard** gates only on independent OOS — n≥20 (prefer ≥40), PF&gt;1.5, WR&gt;55, DD&lt;10. Drop soft n&lt;20 for promotion.
4. Report **pooled** OOS PF (Σ wins / Σ|losses|), not arithmetic mean of fold PFs.
5. Cap family grids; log trial counts; consider deflated Sharpe / simple Bonferroni on family bests.
6. Fix cooldown semantics (no same-bar re-entry); add spread/slippage stress on fills.

### B. Concrete redesign directions (thesis-driven, not grid spam)

| Direction | Why | What to build |
|---|---|---|
| **1. Sparse MR with pre-registered vol gate** | Only residual non-negative clean OOS was vol_gate; n too small to prove | Single pre-registered rule (e.g. atr_pctile&lt;0.4 + bb reclaim + ema200); no 226-cell search — only validate on locked holdout. If n stays &lt;20 over multi-year OOS, abandon MR for XAU H1. |
| **2. High-vol trend with train WR gate redesign** | Breakout PF high but WR &lt;55 blocked train_gates; OOS still failed late | Fewer params: fixed N + ATR expansion only; trail instead of wide fixed TP; require **pooled** OOS and fold4-like windows, not early-2025 bull replay. |
| **3. Regime label as state, not switch of two broken modules** | dual_regime = max of two failing modules → train WR fail, OOS mediocre | Explicit stand-down deadband when atr_pctile mid-conflict; modules must each pass train gates **alone** before switch is allowed. |
| **4. Unused families with structure** | `htf_fib_proxy`, `donchian_channel` never gridded | Implement once with **tiny** pre-registered param sets (≤6 configs each), evaluate on locked holdout only. Fib: flat-only, require_bias, wider XAU ATR exits. Donchian: entry_N/exit_N turtle + ATR SL, optional atr_pctile≥0.5. |
| **5. Multi-timeframe / session filter** | 2026 expansion + weaker EMA200 stickiness | Session or H4 trend filter as hard structure, not another RSI grid; measure trade count impact before claiming edge. |
| **6. Path dependency check** | ema_pullback folds 1–3 strong, fold4 death | Any new design must report **last-fold / post-split** metrics as primary, early folds as diagnostics only. |

### C. Explicit non-goals

- No `--live`.  
- No paper/dry until a design clears **skeptic-grade independent OOS** (survive ≥1 with hard gates).  
- No blending families until a single family passes.  
- No writing promotion params from soft_pass 0.75 / 0.50 candidates.

---

**Final line:** **Survive = 0. Winner = none. Recommendation = NO-GO** (research redesign only; never `--live`).
