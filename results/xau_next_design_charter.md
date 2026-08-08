# XAU next design charter — FROZEN research program

**Status:** FROZEN · pre-register only · 2026-08-08  
**Context:** `KILL_BB_RSI_LINE` and `KILL_DONCHIAN_LINE` closed. Standing disposition RESEARCH_ONLY / promote=no / live_go=false.  
**Machine-readable twin:** [`results/xau_next_design_charter.json`](xau_next_design_charter.json)

This document freezes **one** next family before any code or search runs. No mine on holdout. No refine loops after kill gates.

---

## 1. Family (thesis A — structural, low knob)

| Field | Value |
|-------|--------|
| **family_id** | `prior_day_high_break` |
| **display_name** | Prior-day high breakout (fixed geometry) |
| **thesis_class** | session_or_breakout_fixed → **breakout_fixed** |
| **instrument** | **XAUUSD H1** first; multi-symbol only after this family survives null + costed WF on gold (not in scope of this freeze) |
| **direction** | **long_only** |
| **risk_pct** | **0.01** (fixed) |

### Hypothesis (one sentence — who pays you)

Long H1 closes through the **prior calendar day's high** extract continuation from short-covering and mean-reversion inventory that underprices range expansion after a confirmed break of yesterday's auction high.

### Economic intuition (not free knobs)

- Prior day high is a widely watched reference; breaks force inventory rebalancing.
- Fixed ATR stops/targets and fixed session hours prevent inventing a new strategy under a new name.
- Low search volume keeps null max-stat interpretable (gates measure market, not grid size).

---

## 2. Concrete entry / exit rule (implementable in one session)

### Entry (causal)

1. Define **prior day high** on broker/server calendar day `D-1`:  
   `prior_day_high = max(high of all H1 bars with date == D-1)`.
2. On bar `i` of day `D` (closed H1 only):  
   **long entry signal** iff  
   - `close[i] > prior_day_high`  
   - **and** `close[i-1] <= prior_day_high` (first close through, not re-entries every bar)  
   - **and** server hour of bar `i` ∈ **fixed hours** (below)  
   - **and** no open position (one position at a time).
3. Fill model: same as existing offline sims — enter at next-bar open or at signal bar close if that is the house convention in the lane simulator used; **document once in the implement script and do not switch mid-family**.

### Exit (fixed geometry)

| Item | Fixed value |
|------|-------------|
| SL | `sl_atr × ATR(14)` at entry (ATR causal, closed bars) |
| TP | `tp_rr × SL` distance (symmetric R-multiple from entry) |
| Other exits | none (no trail, no time stop, no signal flip exit) |
| Cooldown | 0 after flat (re-arm next session/day naturally via first-through rule) |

### Session hours (fixed)

- **Server hours allowed:** `{8, 9, 10, 11, 12, 13, 14, 15, 16}` (inclusive), matching typical liquid London→early NY window on broker server clock.  
- **Not free.** Do not grid hours in this family.

### Sizing / policy (fixed)

| Item | Value |
|------|--------|
| risk_pct | 0.01 |
| long_only | true |
| max_lots | 0.5 (house cap if present; not a search knob) |
| short entries | forbidden |

---

## 3. Free knobs (≤ 3 — this family uses **1**)

Everything not listed here is **fixed** for the life of the family.

| Axis | Allowed values | Notes |
|------|----------------|-------|
| **`sl_atr`** | `{1.0, 1.5, 2.0}` | only free axis |

**Derived / fixed with the free knob:**

| Axis | Value |
|------|--------|
| `tp_rr` | **2.0** always → TP distance = `2.0 * sl_atr * ATR` |
| hours | fixed set above |
| atr_period | 14 |
| risk_pct | 0.01 |
| long_only | true |
| entry rule | prior-day high first-close-through only |

**Search cardinality:** 3 configs. No early exit of the grid. Full enumerate for null max-stat.

---

## 4. Costs (mandatory — never frictionless)

Load and charge **exactly** from [`results/xau_research_costs.json`](xau_research_costs.json):

| Field | Value |
|-------|--------|
| spread | `spread_col=spread`, `point_size=0.01` (measured H1 spread points) |
| commission | **RAW ECN floor** `commission_per_lot=3.0` **per side** per lot (RT = `2 * 3.0 * lots`) |
| slippage | `slippage_points=0.0` until demo fills measured |
| formula | same as `backtest.simulate` trade_cost at entry; subtract on every close |

**Forbidden:** any develop/WF/null report with commission 0 and no spread debit while claiming this family passed.

---

## 5. Windows & holdout discipline

| Window | Rule |
|--------|------|
| **Develop / selection** | `time < holdout_start` only. Holdout from [`results/xau_holdout_lock.json`](xau_holdout_lock.json): **`holdout_start = 2026-01-01T00:00:00+00:00`**. |
| **Holdout** | **NEVER used for selection**, knob choice, early-stop, or “just peeking at PF”. |
| **Eval on holdout** | Allowed **once**, only if family survives null + costed walk-forward; params frozen first. |
| **Virgin / peek** | Same seals as existing research loop; do not re-label IS years as OOS. |

Walk-forward (costed): expanding or fixed folds **entirely inside develop** (`time < holdout_start`). Fold design frozen at implement time; no retune of fold edges after seeing results.

---

## 6. Success gates (all required)

A family **PASS_KEEP_FROZEN** (still promote=no until separate promotion decision) only if **all** hold:

1. **Null max-stat (develop, costed, full 3-config grid, no early exit)**  
   - `p_max_pf <= 0.05`  
   - `p_n_passers <= 0.05`  
   - Protocol mirror: real max PF / n_passers vs return-shuffled null paths (same grid, same costs, same develop window). Trial count ≥ 40 unless compute forces a pre-registered lower N written into the run artifact **before** seeing p-values.
2. **Costed walk-forward not negative**  
   - Aggregate WF net profit **> 0** under RAW $3/side + measured spread  
   - Document fold-level PF/NP; soft diagnostics allowed but **sum NP ≤ 0 or mean PF < 1 with negative sum → fail**.

No other success path (no “interesting IS PF”, no multi-year frictionless rescue).

---

## 7. Kill rules (no refine loops)

| Outcome | Disposition |
|---------|-------------|
| Fail null max-stat (`p_max_pf > 0.05` **or** `p_n_passers > 0.05`) | **KILL_PRIOR_DAY_HIGH_BREAK** |
| Pass null but costed WF not positive | **KILL_PRIOR_DAY_HIGH_BREAK** |
| Pass both | freeze the **single** best develop config (or the sole grid survivor under pre-registered passer definition); holdout eval once later; **promote remains no** until explicit human decision |

**After KILL:** stop. Do **not**:

- widen `sl_atr` grid  
- free `tp_rr`, hours, ATR period, cooldown, or trend filters  
- add RSI/BB/Donchian overlays  
- re-run with frictionless costs  
- “one more try” on a sibling rule under the same family_id  

A **new** family requires a **new** charter freeze (new id), not a patch to this one.

---

## 8. Explicitly forbidden (this program)

- Re-grid or revive **bb_rsi** / **rsi_cross** / **Donchian/turtle** lines  
- Early-exit search (must score full 3-config grid on real and each null path)  
- Frictionless eval (missing spread and/or commission while claiming pass)  
- Holdout mining or any selection using `time >= holdout_start`  
- Live orders / `--live` / paper promotion from this charter alone  
- Expanding knobs past the table in §3 without a new frozen charter  
- Labeling develop folds as OOS holdout

---

## 9. Passer definition (for null `n_passers`)

Pre-registered soft passer on develop (costed), used only for null counting — not for promotion:

| Gate | Threshold |
|------|-----------|
| n_trades | ≥ 20 |
| profit_factor | ≥ 1.2 |
| net_profit | > 0 |

Classic hard passer (optional diagnostic only): PF > 1.5, WR > 55%, DD% < 10%, n ≥ 20 — **not** required for family kill/pass; soft definition above is what `p_n_passers` uses.

---

## 10. Implementation checklist (one session)

1. Load `xauusd_data.csv` H1; slice `time < holdout_start`.  
2. Compute prior calendar-day high (causal; no future day).  
3. Simulate 3 configs (`sl_atr` ∈ {1.0, 1.5, 2.0}), costs from `xau_research_costs.json`.  
4. Costed walk-forward on develop; record aggregate NP/PF.  
5. Null max-stat: shuffle returns, rebuild OHLC path or bar returns per existing null scripts, re-run **full** grid; emit `p_max_pf`, `p_n_passers`.  
6. Write results artifact + skeptic note; update loop status: PASS_KEEP_FROZEN or KILL.  
7. **Do not** touch holdout unless both gates pass and params are frozen in writing.

---

## 11. Summary freeze line

```
family=prior_day_high_break
knobs=1 (sl_atr ∈ {1.0,1.5,2.0}); tp_rr=2.0 fixed; hours={8..16} fixed
risk_pct=0.01 long_only costs=RAW_$3/side+spread
develop_only selection; holdout sealed
success: p_max_pf≤0.05 ∧ p_n_passers≤0.05 ∧ costed_WF_NP>0
fail → KILL; no refine; no bb_rsi/Donchian revival
```
