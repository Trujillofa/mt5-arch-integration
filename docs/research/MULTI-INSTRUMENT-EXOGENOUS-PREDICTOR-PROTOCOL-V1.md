# Multi-instrument exogenous-predictor protocol v1

**Date:** 2026-08-14  
**Status:** **SPECIFICATION ONLY** — not implemented · not enforced · not freeze-ready for thesis  
**Branch:** `research/exogenous-predictor-protocol-v1` from `main@a492f2c`  
**Parent:** extends family protocol 2.2 (`docs/research/XAU-FAMILY-PROTOCOL-V2.md`) without replacing it for single-frame / joint-cosign families  

## Standing loop disposition (unchanged)

**`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`** · promote=no · live_go=false  

Closed: `joint_london_open_cosign_fade_flat` v4 **SCREEN_FAIL**. Do not retune that family.  
This document does **not** freeze a new thesis, access develop metrics, or authorize scoring.

---

## 0. Purpose and non-goals

### 0.1 Purpose

Define a **protocol extension** so a multi-instrument thesis may use some symbols as **predictors only** (no orders, no gate on their P&L) and one or more symbols as the **traded book**, with:

- validator vocabulary the current protocol lacks;
- a dedicated harness kind and accounting path;
- a **conditional null** estimand that freezes real signal events and re-associates them with subsequent traded-path outcomes;
- program-level multiplicity rules that do not assume a phantom attempt index.

### 0.2 Non-goals (explicit)

| Out of scope for this spec PR | Why |
|-------------------------------|-----|
| Thesis charter / memo / family module | Phase C after Phase B merges |
| Implementation of validators or null engine | Phase B |
| Develop package load, screen, null, holdout | Forbidden until freeze+fixtures authorized |
| Reshaping EUR/GBP into a derived XAU indicator | Evades exogenous structure; **forbidden as a protocol workaround** |
| Changing single-frame or `multi_instrument_joint_v1` contracts | Leave 2.2 joint-cosign path intact |

### 0.3 Relationship to existing kinds

| `harness.kind` | Role |
|----------------|------|
| (single-frame default) | One symbol, `xau_family_null_maxstat` / sealed cycle |
| `multi_instrument_joint_v1` | All listed symbols co-traded; joint soft primary; shared-k OHLC null on intersection |
| **`multi_instrument_exogenous_predictor_v1`** (this extension) | Predictors generate signals; **gates and P&L only on traded books**; conditional null on fixed signal events |

A charter that claims predictors but uses `multi_instrument_joint_v1` **must fail validation**.  
A charter that requires this kind **must not** be runnable on the joint-cosign harness.

---

## 1. Instrument roles: traded vs predictor

### 1.1 Required charter blocks

```text
instrument.symbols                  # ordered list, all package members used
instrument.traded_symbols           # non-empty subset; books that may hold positions
instrument.predictor_symbols        # may be empty only if all symbols are traded
instrument.multi_symbol_in_scope    # true
instrument.require_all_symbols_for_signal  # boolean; see signal contract
```

**Invariants (validator):**

1. `traded_symbols ⊆ symbols` and `predictor_symbols ⊆ symbols`.
2. `traded_symbols ∪ predictor_symbols = symbols` (every listed symbol has a role).
3. `traded_symbols ∩ predictor_symbols = ∅`.
4. `len(traded_symbols) ≥ 1`.
5. Every symbol in `symbols` has `per_symbol_meta` (point_size, contract_size, digits).
6. Package pin (package_id, per-file sha256, holdout, develop derivation) as under Phase-0 multi-instrument data protocol.

### 1.2 Semantic rules

| Role | May enter orders | Contributes to soft/classic gates | In MTM gate equity | In null path |
|------|------------------|-----------------------------------|--------------------|--------------|
| **traded** | Yes | Yes (per traded book + aggregate if defined) | Yes | Outcome paths (see §5) |
| **predictor** | **No** | **No** | **No** (not as a P&L book) | May enter **signal formation only** under frozen estimand |

**Fail closed:** any `OrderSend`-equivalent or simulated fill on a predictor symbol is a protocol violation (fixture + implementation must assert zero predictor trades).

### 1.3 Gates scope

Under `multi_instrument_exogenous_predictor_v1`:

- **Primary n_passers** is defined **only** on the traded book(s).
- Default (freeze must restate):  
  - single traded symbol (e.g. XAU only): primary = that book’s soft gate;  
  - multiple traded symbols: charter must freeze either (a) binary joint over **traded** soft only, or (b) sum of per-traded soft passers — **not** a mix that counts predictor soft.
- Predictor books **must not** appear in `gates.multi_instrument.per_symbol_soft` as required passers.
- Classic remains report-only unless charter freezes otherwise (same as 2.2).

---

## 2. Harness kind and dispatch

### 2.1 Kind string

```text
harness.kind = "multi_instrument_exogenous_predictor_v1"
```

### 2.2 Dispatch rules (implementation obligation in Phase B)

| Caller | Required behavior |
|--------|-------------------|
| `xau_family_null_maxstat.py` | **Refuse** (existing multi-instrument refuse, extended to this kind) |
| `xau_sealed_family_cycle.py` | **Refuse** (single-frame sealed path) |
| `xau_multi_instrument_joint_screen.py` | **Refuse** (joint-cosign / all-traded family hardcode) |
| New dedicated harness (Phase B name TBD, e.g. `xau_multi_instrument_exogenous_screen.py`) | Only path for develop screen + later null |

### 2.3 Freeze-time vs run-time

| Stage | Harness module file | Required |
|-------|---------------------|----------|
| **Charter freeze (Phase C)** | May be absent on disk | Charter must name `harness.kind`, `harness.module_expected`, and `prohibited_runners` |
| **Fixtures PR** | Synthetic only | Module implements signal/entry/exit + fixtures; no develop peek |
| **Screen / null** | Present and sealed | Dispositional clean-tree includes module + protocol |

Freezing a charter that names an unimplemented module is **allowed only after** Phase B has landed validator vocabulary and accounting hooks that **recognize** this kind (so freeze validation does not fail open as “unknown multi-instrument”).

### 2.4 Clean-tree protection (Phase B)

Extend `DISPOSITIONAL_PATH_GLOBS` to cover:

- `scripts/xau_multi_instrument_*.py` (already includes joint screen; keep for exogenous harnesses)
- any new null core module for conditional multi-frame nulls

---

## 3. Analysis calendar

### 3.1 Mode

```text
analysis_calendar.mode = "intersection_only"
```

**Mandatory** for all of: signal formation, ATR (if used), entries, exits, MTM equity, real path, null path.

### 3.2 Construction

1. Restrict each symbol’s develop series to `server_time < holdout_start` (package-derived develop).
2. Build ordered set **I** of timestamps present in **every** symbol in `instrument.symbols` (traded **and** predictors).
3. Drop any bar not in **I** before any rule logic.
4. **Forbidden:** real path on full per-symbol calendars while null uses intersection (or the reverse).

### 3.3 Clock fields

Same as multi-instrument joint v3/v4 integrity:

- timezone-naive `server_clock_as_stored`;
- `hour == time.dt.hour`, `day_id == time.dt.strftime("%Y-%m-%d")`;
- timestamps unique and strictly increasing on **I**.

Empty joint intersection → hard error (`EMPTY_JOINT_INTERSECTION`), never a zero-trade “valid” screen.

---

## 4. MTM equity and drawdown (traded books)

### 4.1 Contract (mandatory for gate DD)

For each traded symbol **S** and each bar \(t \in I\):

\[
\text{equity}_S(t) = B_S(t) + \text{open\_pnl}_S(t)
\]

where:

- \(B_S(t)\) = realized balance after all closed trades with exit bar \(\le t\) (costs already deducted at exit booking);
- \(\text{open\_pnl}_S(t) = 0\) if flat;
- if open long/short:  
  \(\text{open\_pnl}_S(t) = (\text{mark}_t - \text{entry}) \cdot \text{contract}_S \cdot \text{lots} \cdot \text{side}\)  
  with \(\text{mark}_t\) = mid/close of bar \(t\) on **I** (freeze must pin mark = close unless otherwise frozen).

**Peak / drawdown** for soft/classic DD on a traded book use the **equity_S series on I**, not a flat realized-only step function that ignores open floating loss.

### 4.2 Aggregate if multiple traded symbols

If more than one traded symbol, freeze either:

- **sum MTM:** \(\text{equity}_{\text{joint}}(t) = \sum_{S \in \text{traded}} \text{equity}_S(t)\), DD on that series; or  
- **per-book only** (no joint DD gate).

Predictors **never** enter the sum as P&L books.

### 4.3 Explicit ban

Do **not** reuse a “realized balance path only” DD implementation that would pass a fixture where open floating DD is large but no trade has closed yet.

---

## 5. Conditional null estimand

### 5.1 Why joint OHLC rotate is wrong here

Shared-k within-day OHLC rotate preserves cross-symbol dependence under **co-trading / cosign** theses. For **exogenous predictors**, the scientific claim is typically:

> Given the **observed** set of signal events formed from predictors (and possibly traded history), is the traded-book P&L of the rule extreme under re-association of those events with subsequent traded paths?

Re-simulating predictors under OHLC rotate **recomputes** signal counts and times → different estimand, and attrition/threshold effects are not controlled by a hand-waved ±30% band.

### 5.2 Frozen estimand (default for this protocol)

**Name (implementation id):** `conditional_fixed_signal_events_v1`

**Real path:**

1. On intersection calendar **I**, run the frozen signal predicate → ordered list of signal events  
   \(E = (e_1,\ldots,e_M)\), each \(e_m = (t_m^\*, \text{side}_m, \ldots)\) with \(t_m^\* \in I\).
2. For each event, apply frozen entry/exit on **traded** symbols only → metrics.

**Null path (trial \(j = 0..N-1\)):**

1. **Freeze** \(E\) from the real path: same \(M\), same \(t_m^\*\), same \(\text{side}_m\) (and any other event fields the rule uses that are not traded-path outcomes).
2. Draw a null association that re-pairs each event with a **subsequent traded path segment** under invariants below (seed = `base_seed + j`).
3. Re-run **entry/exit and costs only** on traded books for those re-paired paths; **do not** re-run predictor signal formation.
4. Score the same gates on the null metrics.

**Identity trial:** one explicit construction with identity pairing (document in freeze) must reproduce real metrics within float tolerance.

### 5.3 What must be frozen in the charter for null

| Field | Requirement |
|-------|-------------|
| `null.method` / `implementation_id` | `conditional_fixed_signal_events_v1` (or a named successor with full algorithm) |
| `null.estimand` | `fixed_real_signal_events` (not `recompute_signals_under_ohlc_rotate`) |
| `null.n_trials` | ≥ 999 for α≈0.05 program-adjusted (see §7); freeze exact N |
| `null.base_seed` | non-negative int |
| `null.pairing_algorithm` | full PRNG steps; day/order keys; what is held fixed vs redrawn |
| `null.invariants` | list (see §5.4) |
| `null.forbidden_methods` | at least: independent per-symbol k; OHLC rotate that recomputes signals; day_block_shuffle of predictors only; global return shuffle of predictors |

### 5.4 Invariants (minimum)

1. **Fixed event count:** null trial has exactly \(M\) events (same as real).  
2. **Fixed event timestamps and sides:** \(t_m^\*\) and \(\text{side}_m\) unchanged.  
3. **Intersection calendar I** for all traded-path construction.  
4. **Causal entry:** entry remains on a bar strictly after \(t_m^\*\) under the freeze’s entry rule (e.g. T\*+1 open), and still obeys same-day / holding-bar existence rules.  
5. **If a re-paired path cannot complete a legal trade** under the freeze (missing bars, invalid ATR, lot floor), the event contributes **no trade** (not a fabricated fill); report `n_null_events_unfilled` diagnostic — but **M is not reduced** by dropping events from the event list (attrition is outcome, not redefinition of M).  
6. **Costs** use the same contract as real (spread column, commission, slippage; per-symbol point/contract on traded).  
7. **No lookahead:** pairing may only use information allowed by the freeze (default: within-develop permutation of eligible path segments that start at or after a legal entry bar for that event’s day structure — exact algorithm Phase B + freeze).

### 5.5 Estimand alternatives (not default)

A freeze may instead choose `recompute_signals_under_joint_ohlc_rotate_v1` **only** if the thesis claims joint dependence of predictors+traded under shared k. That is a **different** family of claims and must not be labeled exogenous-predictor conditional null.

### 5.6 Screen vs null

Same as protocol 2.2 screen-fail rule for primary passers:

- real primary passers = 0 → **SCREEN_FAIL**, null not run, r1 unburned;  
- real primary passers ≥ 1 → screen-only stop or sealed null under dispositional accounting (see §8).

---

## 6. Signal / entry / exit predicates (freeze obligations)

These are **charter-level** requirements for Phase C. The protocol only defines what must be unambiguous.

### 6.1 Lookback returns (template)

When a freeze uses lagged returns for ranking or thresholds:

1. On bar \(t \in I\), the feature window is **prior** bars \(t-L,\ldots,t-1\) on **I** (not wall-clock holes).  
2. **Exclude** the signal bar’s own return from the feature that decides the signal at \(t\) (no using \(r_t\) to decide a signal labeled at \(t\) if entry is at \(t\) or \(t+1\) without a frozen causal story).  
3. Comparisons are **strict** `>` / `<` unless the freeze explicitly chooses `≥` and defends ties.  
4. Per-symbol statistics (e.g. median log-return) are computed **per symbol** on that symbol’s series on **I**.  
5. Zero or non-finite returns: freeze must state **reject signal** (default) vs impute (discouraged).  
6. Only intersection bars participate.

### 6.2 Holding period (preferred default for this protocol)

**Prefer a fixed H-bar holding period** (default recommendation **H = 3**), not “flat at last bar of day” alone.

Rules:

1. Entry at bar \(t_{\text{entry}}\) (e.g. open of first joint bar after signal).  
2. Exit evaluation on bars \(t_{\text{entry}}, t_{\text{entry}}+1, \ldots, t_{\text{entry}}+H-1\) under freeze’s SL/TP/time priority.  
3. **Entry is allowed only if** all \(H\) holding bars exist on **I** and share the **same `day_id`** as \(t_{\text{entry}}\) (no overnight / no cross-day hold under this default).  
4. If any of the H bars is missing on I or `day_id` differs → **consume/reject** the signal (no entry).

“Last bar of day” remains available only as an emergency flat if H bars exist but a freeze adds intraday session end — must not replace the H-bar existence gate.

### 6.3 Same calendar day as signal / weekend gap

If entry is “next bar after signal”:

- that next bar must exist on **I** and must share **`day_id`** with the signal bar (or with \(t_{\text{entry}}\) per freeze);  
- otherwise **consume/reject** the signal (no Monday open fill for Friday signal under default).

### 6.4 Sign mapping

Freeze must include **explicit long/short examples**, e.g.:

| Condition (illustrative) | Side on traded XAU |
|--------------------------|--------------------|
| Predictor feature \(f > 0\) under frozen definition | long (+1) |
| Predictor feature \(f < 0\) | short (−1) |
| \(f = 0\) or non-finite | no signal |

No ambiguous “follow/fade” without a worked numeric toy bar.

### 6.5 Gate provenance

Freeze must state for each gate metric: formula, book (which traded symbols), cost timing, and PF zero-denominator house convention (0 / 99). Documentation requirement; incomplete freeze fails validator in Phase B/C.

---

## 7. Program-level hypothesis counting and multiplicity

### 7.1 Ledger sources

| Ledger | Role |
|--------|------|
| `results/xau_charter_disposition_registry.jsonl` | Terminal charter dispositions (SCREEN_FAIL, KILL_*, SUPERSEDED, …) |
| `results/xau_family_attempts.jsonl` | Sealed single-frame STARTED/terminal attempts (when present) |
| Multi-instrument screen reports under `results/xau_runs/` | Must feed the same attempt/accounting model once Phase B wires multi-instrument screens into STARTED/terminal rows |

**Note:** On current main, `xau_family_attempts.jsonl` may be absent locally while registry rows exist. Multiplicity **must not** invent “index 9” without an audit.

### 7.2 Counting rule (normative for Phase B+)

Define **program attempt index \(K\)** for a new exogenous-predictor family freeze as:

1. Count **unique `family_id`** values that have at least one **scored develop attempt** recorded as:
   - registry `DETERMINISTIC_SCREEN` / `SCREEN_FAIL` / `SCREEN_PASS_PENDING_NULL_REVIEW`, or  
   - sealed `SEALED_NULL` / `KILL_*` / `PASS_*` / `WEAK_FAIL`, or  
   - `PROTOCOL_NULL_INVALID` if a develop-facing null protocol burn was recorded,  
   **excluding** pure `SUPERSEDED` freezes that never scored develop.
2. Add 1 for the **new** family about to be frozen.  
3. Freeze must publish:  
   - `multiplicity.prior_scored_family_ids` (explicit list from audit date),  
   - `multiplicity.K`,  
   - `multiplicity.alpha_uncorrected` (default 0.05),  
   - `multiplicity.alpha_adjusted = alpha_uncorrected / K` (Bonferroni default),  
   - `multiplicity.method` (default `bonferroni_unique_scored_family_id`).

### 7.3 Provisional audit snapshot (2026-08-14, registry on main@a492f2c)

Terminal scored-like **unique families** observed in `xau_charter_disposition_registry.jsonl` (method §7.2 step 1):

| family_id (from path/id) | disposition |
|--------------------------|-------------|
| `tod_london_ny_flat` | PROTOCOL_NULL_INVALID |
| `server_hour_window_flat` | SCREEN_FAIL |
| `early_server_range_break_flat` | SCREEN_FAIL |
| `day_open_reclaim_flat` | SCREEN_FAIL |
| `joint_london_open_cosign_fade_flat` | SCREEN_FAIL |

**Provisional \(K_{\text{prior}} = 5\)** → next new family \(K = 6\) → \(\alpha_{\text{adj}} \approx 0.05/6 \approx 0.00833\) under Bonferroni.

This is **not** a freeze of K=6 forever. Phase C must **re-audit** ledgers at freeze time. If historical sealed KILL rows (e.g. older Donchian/bb_rsi/prior_day) are restored into program counting policy, K increases.

### 7.4 Null trial resolution

For one-sided p = (hits+1)/(N+1) ≤ α_adj with hits=0: need \(N+1 ≥ 1/\alpha_{\text{adj}}\).  
For α_adj ≈ 0.00556 (K=9), N ≥ 179 is mathematically enough for a zero-hit threshold; **protocol still requires N ≥ 999** for continuity with 2.2 reporting resolution unless a freeze explicitly justifies a larger N for smaller α_adj.

---

## 8. STARTED / terminal accounting (screens and nulls)

### 8.1 Principles (align with fail-closed v3–v6)

1. Dispositional multi-instrument exogenous screen **always**:
   - sealed charter path under `results/xau_charters/`;
   - clean dispositional tree;
   - cost match (identity + sim keys; no global XAU point_size abuse on FX);
   - fresh out-dir; **STARTED** marker **before** package load/score;
   - canonical report blocks for parser (`verdict`, `null`, `screen`, `real`, `attempt_accounting`).
2. Synthetic frames are **non-dispositional**: cannot `--write-registry` or close a real charter SHA.
3. **SCREEN_FAIL** (zero primary passers): exit 0, r1_burned=false, null trials empty, counts paired.  
4. **SCREEN_PASS_PENDING_NULL_REVIEW** (exactly one binary passer under cardinality-1 families, or freeze-defined n_passers): exit 0, r1_burned=false, skipped_reason=SCREEN_ONLY.  
5. Full null success: exit 0, trials id set `== range(N)`, r1_burned=true.  
6. Any incomplete path: FAILED_RUN_UNKNOWN, r1_burned=true, n_null_executed=null.

### 8.2 Attempt ledger for multi-instrument

Phase B must either:

- append STARTED/terminal rows to `results/xau_family_attempts.jsonl` for exogenous screens/nulls (preferred, shared with sealed cycle), or  
- maintain a dedicated `results/xau_multi_instrument_attempts.jsonl` with the same attempt_id semantics,

and **include those rows** in §7 multiplicity audits.

### 8.3 Registry

Terminal dispositions append to `results/xau_charter_disposition_registry.jsonl` only from dispositional reports; monotonic terminal rules unchanged.

---

## 9. Validator checklist (Phase B acceptance criteria)

A charter with `harness.kind=multi_instrument_exogenous_predictor_v1` **fails closed** unless all hold:

1. Protocol version ≥ extension minimum (freeze `protocol_version` field once Phase B pins it, e.g. 2.3 or 3.0).  
2. Traded/predictor partition valid (§1).  
3. Intersection-only calendar (§3).  
4. Null block names conditional estimand + full pairing algorithm or explicit forbidden recompute (§5).  
5. Gates only on traded books; primary_n_passers consistent (§1.3).  
6. MTM DD definition present for traded books (§4).  
7. Entry/hold predicates include H-bar same-day existence and next-bar same-day rules if used (§6).  
8. Sign mapping examples present (§6.4).  
9. Multiplicity block with audited K and α_adj (§7).  
10. Costs: identity + finite sim keys; per-symbol point/contract for traded.  
11. Package pin complete.  
12. `n_free_knobs` / search_cardinality frozen (prefer 0 / 1).  
13. Harness kind refuse list includes single-frame and joint_v1 runners.

---

## 10. Phased delivery

| Phase | Deliverable | Stop condition |
|-------|-------------|----------------|
| **A (this doc)** | Spec only on clean branch | Adversarial review of protocol |
| **B** | Generic validator + conditional-null machinery + accounting + synthetic tests | PR merge; no thesis signals |
| **C** | Immutable charter + memo for a concrete exogenous thesis | Freeze review; then fixtures PR; then screen PR |

---

## 11. Explicit bans (summary)

- Predictor fills / predictor soft as primary passers.  
- Joint-cosign harness reuse for predictor theses.  
- Empty intersection as zero-trade success.  
- Realized-only DD for open positions when gate uses max_drawdown.  
- Recomputing signals under OHLC rotate while claiming conditional fixed-event null.  
- ±30% trade-count bands as a substitute for a fixed-event estimand.  
- Declaring multiplicity index without ledger audit.  
- Collapsing EUR/GBP into an XAU-only indicator to avoid this protocol.

---

## 12. Document control

| Item | Value |
|------|--------|
| Spec version | multi_instrument_exogenous_predictor_protocol_v1 |
| Implementation status | **not started** |
| Thesis freeze | **not authorized** |
| Next gate | **AWAIT_ADVERSARIAL_PROTOCOL_REVIEW** |

**End of Phase A specification.**
