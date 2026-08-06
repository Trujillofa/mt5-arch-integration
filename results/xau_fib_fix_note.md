# HTF Fib pivot confirmation look-ahead — fix note

**Date:** 2026-08-06  
**Scope:** Offline Python fib path only (no holdout re-eval, no live).  
**Status:** Fix landed + synthetic self-check passing.

---

## Problem (before)

`confirmed_pivots(high, low, left, right)` correctly *detected* a fractal using bars
`[c - left, c + right]`, but **stamped the event at the pivot center index `c`**.

Downstream:

1. H4 event index `c` was mapped to an H1 timestamp via the **center** H4 bar label.
2. `walk_swing_and_fibs` / state expand activated fib direction when `state.idx <= i`.
3. Signals could therefore use a swing/fib that is not knowable until `right` more H4
   bars have closed.

With default `pivot_right=5` on H4 this is ~5 × 4h ≈ **20 hours** of future structure
information on an H1 chart (see `results/xau_preregistered_skeptic.md` §3.1).

**Buggy stamp (removed):**

```python
# BEFORE (look-ahead)
for c in range(left, n - right):
    ...
    if is_h:
        events.append((c, float(h), 1))  # stamped at center
```

Affected call sites:

| Location | Role |
|----------|------|
| `scripts/htf_fib_offline_backtest.py` | Offline research backtest |
| `scripts/xau_preregistered_holdout.py` | `simulate_htf_fib` (+ local duplicate) |

Prior holdout fib metrics were **underpowered** (n≈0–3), so the bug did not mint a
false hard_pass — but metrics were **not safe for any future claim** until fixed.

---

## Fix (after)

### Shared helper

New module: **`scripts/htf_fib_core.py`**

| API | Behavior |
|-----|----------|
| `confirmed_pivots(...)` | Returns `(active_idx, price, ptype)` with **`active_idx = c + right`** |
| `confirmed_pivots_with_centers(...)` | Same + `center_idx` for audits/tests |
| `walk_swing_and_fibs(...)` | Fib state idx inherited from event (already confirmation-stamped); supports custom `fib_lo` / `fib_hi` |
| `expand_fib_states(n, states)` | Per-bar direction / fib levels; live only for `i >= active_idx` |
| `self_check_pivot_confirmation()` | Synthetic series asserts `active == center + right` and signal bar ≥ confirmation |

**Causal stamp (current):**

```python
# AFTER (causal)
active = c + right  # confirmation bar
events.append((active, float(h), 1))
```

Price is still taken at the center bar (the fractal extreme); only the **activation
index** moves to the confirmation bar.

### Consumers wired to shared helper

- `scripts/htf_fib_offline_backtest.py` — imports `confirmed_pivots`, `walk_swing_and_fibs`,
  `expand_fib_states` from `htf_fib_core` (no local reimplementation).
- `scripts/xau_preregistered_holdout.py` — same; **deleted** `_local_confirmed_pivots` /
  `_local_walk_swing_and_fibs` so optimizer/evaluator cannot drift apart.

Future develop-only fib optimizers must import from `htf_fib_core` only (do not
re-copy pivot detection).

### Self-check

```bash
python3 scripts/htf_fib_core.py
# or
python3 -m pytest tests/test_htf_fib_pivot_confirmation.py -v
```

Rule under test: for every pivot, **`signal / fib active time >= pivot_center + right`**.

---

## What this does *not* do

- Does **not** re-run sealed holdout or rewrite preregistered eval JSON.
- Does not change MQL5 `ForexHtfPivotsFib.mq5` chart labels (still draw at pivot center
  time; live scan already requires `c <= n-1-right` so forming bars cannot confirm early).
- Residual research caveat: H4 bars from `resample("4h")` are left-labeled; activation
  at the confirmation bar’s left edge is still slightly optimistic vs “after H4 close”
  within that single 4h bucket. The **critical multi-bar look-ahead** (`right` bars) is
  what this fix removes.

---

## Next steps (out of scope here)

1. Develop-only fib param optimization using `htf_fib_core` + `simulate_htf_fib`.
2. Single sealed holdout pass only after a frozen shortlist (protocol unchanged).
3. Treat all **pre-fix** fib offline / preregistered metrics as **invalidated**.
