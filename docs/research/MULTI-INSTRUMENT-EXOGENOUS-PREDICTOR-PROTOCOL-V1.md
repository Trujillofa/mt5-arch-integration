# Multi-instrument exogenous-predictor protocol v1

**Date:** 2026-08-14
**Status:** **SPECIFICATION ONLY** — not implemented · not enforced · not freeze-ready for thesis
**Branch:** `research/exogenous-predictor-protocol-v1` from `main@a492f2c`
**Parent:** extends family protocol 2.2 (`docs/research/XAU-FAMILY-PROTOCOL-V2.md`) without replacing it for single-frame / joint-cosign families
**Revision:** Phase A amend (review CHANGES REQUIRED) — same document, no v2 bump

## Standing loop disposition (unchanged)

**`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`** · promote=no · live_go=false

Closed: `joint_london_open_cosign_fade_flat` v4 **SCREEN_FAIL**. Do not retune that family.
This document does **not** freeze a new thesis, access develop metrics, or authorize scoring.

---

## 0. Purpose and non-goals

### 0.1 Purpose

Define a **protocol extension** so a multi-instrument thesis may use some symbols as **predictors only** (no orders, no gate on their P&L) and **exactly one** symbol as the **traded book**, with:

- validator vocabulary the current protocol lacks;
- a dedicated harness kind and accounting path;
- a **conditional null** estimand that freezes real signal events **and** executes exactly the real trade count on every trial;
- a **finite-catalog Bonferroni** multiplicity rule with a corrected historical baseline.

### 0.2 Non-goals (explicit)

| Out of scope for this spec PR | Why |
|-------------------------------|-----|
| Thesis charter / memo / family module | Phase C after Phase B merges |
| Implementation of validators or null engine | Phase B |
| Develop package load, screen, null, holdout | Forbidden until freeze+fixtures authorized |
| Reshaping EUR/GBP into a derived XAU indicator | Evades exogenous structure; **forbidden as a protocol workaround** |
| Changing single-frame or `multi_instrument_joint_v1` contracts | Leave 2.2 joint-cosign path intact |
| Multiple traded books | **Deferred to protocol v2** |

### 0.3 Relationship to existing kinds

| `harness.kind` | Role |
|----------------|------|
| (single-frame default) | One symbol, `xau_family_null_maxstat` / sealed cycle |
| `multi_instrument_joint_v1` | All listed symbols co-traded; joint soft primary; shared-k OHLC null on intersection |
| **`multi_instrument_exogenous_predictor_v1`** (this extension) | Non-empty predictors form signals; **exactly one traded book** is gated; conditional fixed-event **and fixed-trade** null |

A charter that claims predictors but uses `multi_instrument_joint_v1` **must fail validation**.
A charter that requires this kind **must not** be runnable on the joint-cosign harness.
An all-traded family **must not** select this kind (use joint v1 or single-frame).

---

## 1. Instrument roles: traded vs predictor

### 1.1 Required charter blocks

```text
instrument.symbols                  # ordered list; all package members used in the thesis
instrument.traded_symbols           # EXACTLY one symbol
instrument.predictor_symbols        # non-empty list; no overlap with traded
instrument.multi_symbol_in_scope    # true
```

**Removed from v1:** `instrument.require_all_symbols_for_signal` as an optional undefined boolean.
Signal formation **always** uses the full `symbols` list on the intersection calendar (all predictors + the traded symbol contribute to the feature world as frozen). There is no “drop a predictor and still fire” mode in v1.

### 1.2 Invariants (validator — fail closed)

1. `len(traded_symbols) == 1`.
2. `len(predictor_symbols) ≥ 1`.
3. `traded_symbols[0] ∈ symbols`.
4. Every `p ∈ predictor_symbols` satisfies `p ∈ symbols`.
5. `set(traded_symbols) ∩ set(predictor_symbols) = ∅`.
6. `set(traded_symbols) ∪ set(predictor_symbols) = set(symbols)`.
7. `traded_symbols` is a **proper subset** of `symbols` (equivalently: at least one predictor).
8. Every symbol in `symbols` has `per_symbol_meta` (point_size, contract_size, digits).
9. Package pin (package_id, per-file sha256, holdout, develop derivation) as under Phase-0 multi-instrument data protocol.

**Required regression cases (Phase B tests):**

| Case | Expected |
|------|----------|
| `predictor_symbols = []` | validation error |
| `len(traded_symbols) ≠ 1` | validation error |
| Overlap traded ∩ predictor | validation error |
| Missing traded or predictor block | validation error |
| Union ≠ symbols / proper-subset fail | validation error |
| Simulated fill on a predictor | fixture hard-fail / protocol violation |

### 1.3 Semantic rules

| Role | May enter orders | Soft/classic gates | MTM gate equity | Null path |
|------|------------------|--------------------|-----------------|-----------|
| **traded** (exactly one) | Yes | Yes — **sole** primary book | Yes | Outcome paths only (§5) |
| **predictor** (≥1) | **No** | **No** | **No** | Signal formation on **real path only**; frozen events on null |

**Fail closed:** any simulated fill on a predictor is a protocol violation.

### 1.4 Gates scope (v1)

- **Primary n_passers** is **binary** on the single traded book’s soft gate: `0` or `1`.
- `gates.primary_n_passers` must be `"soft"`.
- Soft keys apply to the **traded** book only (n_trades, PF, NP, max_drawdown_pct with MTM contract §4).
- **No** summed multi-traded passers; **no** joint three-book primary (that is joint_v1).
- Classic remains report-only unless a future protocol freezes otherwise.
- Predictor books must not appear under required soft passers.

This matches fail-closed accounting that accepts positive screens when `real.n_passers == 1` (cardinality-1 binary family).

---

## 2. Harness kind and dispatch

### 2.1 Kind string

```text
harness.kind = "multi_instrument_exogenous_predictor_v1"
```

### 2.2 Dispatch rules (implementation obligation in Phase B)

| Caller | Required behavior |
|--------|-------------------|
| `xau_family_null_maxstat.py` | **Refuse** |
| `xau_sealed_family_cycle.py` | **Refuse** (until/unless a dedicated multi-frame sealed path is added under this kind) |
| `xau_multi_instrument_joint_screen.py` | **Refuse** |
| Dedicated exogenous harness (Phase B name TBD) | Only path for develop screen + later null |

### 2.3 Freeze-time vs run-time

| Stage | Harness module file | Required |
|-------|---------------------|----------|
| **Charter freeze (Phase C)** | May be absent on disk | Must name `harness.kind`, `harness.module_expected`, `prohibited_runners` |
| **Fixtures PR** | Synthetic only | Module implements signal/entry/exit + fixtures; no develop peek |
| **Screen / null** | Present and sealed | Dispositional clean-tree includes module + protocol |

Freezing a charter that names an unimplemented module is allowed **only after** Phase B lands validator vocabulary that **recognizes** this kind (freeze validation must not fail open as “unknown multi-instrument”).

### 2.4 Clean-tree protection (Phase B)

Keep/extend `DISPOSITIONAL_PATH_GLOBS` for `scripts/xau_multi_instrument_*.py` and any new conditional-null core module.

---

## 3. Analysis calendar

### 3.1 Mode

```text
analysis_calendar.mode = "intersection_only"
```

**Mandatory** for: signal formation, ATR (if used), entries, exits, MTM equity, real path, null path.

### 3.2 Construction

1. Restrict each symbol’s develop series to `server_time < holdout_start`.
2. Build ordered set **I** of timestamps present in **every** symbol in `instrument.symbols`.
3. Drop any bar not in **I** before any rule logic.
4. **Forbidden:** unequal calendars between real and null, or full-path ATR/exits off **I**.

### 3.3 Clock fields

- timezone-naive `server_clock_as_stored`;
- `hour == time.dt.hour`, `day_id == time.dt.strftime("%Y-%m-%d")`;
- timestamps unique and strictly increasing on **I**.

Empty joint intersection → hard error (`EMPTY_JOINT_INTERSECTION`), never a zero-trade valid screen.

---

## 4. MTM equity and drawdown (traded book only)

### 4.1 Contract (mandatory for soft DD)

For the single traded symbol **S** and each bar \(t \in I\):

\[
\text{equity}_S(t) = B_S(t) + \text{open\_pnl}_S(t)
\]

- \(B_S(t)\): realized balance after all closed trades with exit bar \(\le t\) (costs deducted at exit booking).
- \(\text{open\_pnl}_S(t) = 0\) if flat; else mark-to-close (default mark = close on **I**) × contract × lots × side.

**Peak / max_drawdown_pct** use the full `equity_S` series on **I**, including open floating loss.

### 4.2 Explicit ban

Do **not** use realized-only step equity that ignores open floating DD.

### 4.3 Multiple traded books

**Not in v1.** Protocol v2 only.

---

## 5. Conditional null estimand (fixed events **and** fixed trades)

### 5.1 Why attrition is forbidden

Allowing re-paired events to produce “no trade” reintroduces null trade-count attrition and breaks the estimand “same signals, different subsequent traded paths under legal completion.”

### 5.2 Frozen estimand

**Name:** `conditional_fixed_signal_events_fixed_trades_v1`

**Real path:**

1. On **I**, run frozen signal predicate → ordered events \(E = (e_1,\ldots,e_M)\) with \(e_m = (t_m^\*, \text{side}_m, \ldots)\).
2. Apply frozen entry/exit on the **single traded** symbol → **exactly** \(T\) executed trades (each event that is allowed to enter under the freeze must produce one completed trade under real data; freeze design must make illegal incomplete holds impossible on real by construction, or document that only events that complete are in \(E\) — **v1 requires: \(T = M\)** after applying the same legal-entry filter that defines \(E\)).
3. **v1 event set definition:** \(E\) is the list of signals that **successfully complete** a full legal trade under the freeze on the real path (so \(M = T_{\text{real}}\)). Signals rejected for missing H-bars / day_id / lots are **not** members of \(E\).

**Null path (trial \(j = 0..N-1\)):**

1. Freeze \(E\) completely: same \(M\), times, sides, and event payload used for entry sizing flags that are not path outcomes.
2. For each \(e_m\), sample a **donor traded path segment** from a pre-built **eligible donor pool** (§5.4) using RNG seed `base_seed + j` and frozen sampling rules.
3. Execute entry/exit/costs on that donor segment for every event.
4. **Every null trial must end with exactly \(T = M\) executed trades.** If construction cannot supply a legal donor for every event, the **trial is invalid** (protocol/run failure), not a partial-trade success.

### 5.3 Identity construction

- One **identity** pairing (real event → real subsequent path) is an **invariant fixture**.
- Identity is **excluded from N, hits, and p-value**.
- Identity must reproduce real metrics within documented float tolerance.
- Identity may live as a synthetic/real-path unit fixture; it is not null trial index 0 unless a freeze explicitly marks trial 0 as non-counting diagnostic (discouraged — prefer separate fixture).

### 5.4 Eligible donor pool (must be fully frozen before Phase B)

Before any trial draw, build pool \(\mathcal{D}\) of donor segments on the traded symbol only, each segment already satisfying:

1. Schema/cost eligibility (finite nonnegative spreads on required bars; OHLC finite; clock invariants).
2. **H-bar same-day existence** from a candidate entry bar (default H=3): bars \(t_{\text{entry}},\ldots,t_{\text{entry}}+H-1\) all on **I**, same `day_id`.
3. ATR/lot sizing inputs at the freeze-defined source bar are finite and produce lots ≥ lot_min after floor (or freeze pins lots from real event payload — see §5.5).
4. Entry day / weekend rule: next-bar-after-signal style constraints are encoded as eligibility of the segment start.

**Donor construction failure** (empty pool, insufficient donors for sampling policy) → **protocol invalid / run refuse**, not zero trades.

### 5.5 Sampling policy (charter must pin all of these)

| Pin | v1 requirement |
|-----|----------------|
| RNG | `numpy.random.Generator(PCG64(base_seed + trial_index))` unless freeze names another Generator |
| With/without replacement | Freeze must choose **one**; default recommendation: **without replacement within a trial** across the M events when \(\|\mathcal{D}\| ≥ M\); if \(\|\mathcal{D}\| < M\), protocol refuse (do not silent-replace) |
| Overlap of donors | Freeze: `forbid_overlap_within_trial` (default **true**) or allow with explicit justification |
| Strata | Optional; if used, define strata key (e.g. entry hour) and sample within strata; underfull stratum → refuse trial/protocol |
| Normalization | How donor OHLC is applied to the event (e.g. splice continuous path from entry open; absolute price path transplant) — full algorithm text required |
| ATR source | Freeze: `atr_from_donor_at_entry` **or** `atr_frozen_from_real_event` (no silent mix) |
| Lot source | Freeze: recompute from ATR/balance rule **or** freeze lots from real event; must still pass lot_min/max |
| Spread/cost source | Freeze: donor bar spreads at entry **or** real event spread snapshot; commission/slippage from cost pin |
| Outcome independence | Donor selection uses **only** eligibility geometry and RNG — **never** realized P&L, future closes beyond eligibility window definition, or gate metrics |

### 5.6 Invariants (minimum)

1. Null trial event count \(M\) equals real \(M\).
2. Null trial **executed trade count** \(T\) equals real \(T\) equals \(M\).
3. Event timestamps and sides unchanged.
4. Intersection calendar **I** only.
5. Causal entry after signal under freeze; H-bar same-day hold rules enforced via donor eligibility.
6. Predictor series not re-simulated for signal formation on null.
7. Invalid donor/ assignment → **invalid trial/run**, not a zero-trade null success.
8. Identity fixture excluded from p-value accounting.

### 5.7 Charter null block (required fields)

```text
null.method / implementation_id = conditional_fixed_signal_events_fixed_trades_v1
null.estimand = fixed_real_completed_events_fixed_trade_count
null.n_trials = N  # default ≥ 999; see multiplicity §7
null.base_seed = <non-negative int>
null.identity_excluded_from_n = true
null.donor_pool = { eligibility, strata, ... }
null.sampling = { with_replacement, overlap, rng, ... }
null.atr_source / lot_source / spread_source = pinned enums
null.invariants = [ ... ]
null.forbidden_methods = [
  recompute_signals_under_ohlc_rotate,
  allow_unfilled_events_in_trial,
  independent_k_per_symbol,
  day_block_shuffle_predictors,
  global_return_shuffle_predictors,
  outcome_dependent_donor_pick
]
```

### 5.8 Screen vs null

Same screen-fail rule as protocol 2.2 for binary primary:

- real `n_passers == 0` → **SCREEN_FAIL**, null not run, r1 unburned;
- real `n_passers == 1` → screen-only pending null or sealed null under accounting §8;
- real `n_passers ∉ {0,1}` → protocol/implementation error for v1 cardinality-1 binary families.

---

## 6. Signal / entry / exit predicates (freeze obligations)

### 6.1 Lookback returns (template)

When using lagged returns:

1. Feature window on **I**: bars \(t-L,\ldots,t-1\) (exclude signal return at \(t\) when deciding a signal stamped at \(t\)).
2. Strict `>` / `<` unless freeze defends `≥`.
3. Per-symbol statistics (e.g. median log-return) per symbol on **I**.
4. Zero / non-finite → **reject** (default).
5. Intersection bars only.

### 6.2 Holding period (v1 default)

**Fixed H-bar hold, default H = 3:**

1. Entry at \(t_{\text{entry}}\) (e.g. open of next joint bar after signal).
2. Exit evaluation on \(t_{\text{entry}},\ldots,t_{\text{entry}}+H-1\) under SL/TP priority frozen.
3. Entry allowed **only if** all H bars exist on **I** and share the same `day_id` as \(t_{\text{entry}}\).
4. Otherwise reject/consume signal (and such a signal is **not** in \(E\) on the real path).

### 6.3 Same calendar day / weekend

Next bar after signal must exist on **I** and share `day_id` with the signal bar (or with \(t_{\text{entry}}\) as frozen); else reject (no Friday→Monday fill under default).

### 6.4 Sign mapping

Freeze must include explicit long/short examples (numeric toy bars), e.g.:

| Condition (illustrative) | Side on traded symbol |
|--------------------------|----------------------|
| Frozen feature \(f > 0\) | long (+1) |
| Frozen feature \(f < 0\) | short (−1) |
| \(f = 0\) or non-finite | no signal |

### 6.5 Gate provenance

Freeze must state formula, book (= sole traded symbol), cost timing, PF zero-denominator house convention (0 / 99).

---

## 7. Program-level hypothesis counting and multiplicity

### 7.1 Chosen rule: finite-catalog Bonferroni (open catalog growth)

**Choice for this protocol:** **finite-catalog Bonferroni with growing catalog size**, not one-shot α-spending at birth only.

Normative consequences:

1. Let \(K_{\text{prior}}\) = number of distinct scored program families already in the catalog (§7.2).
2. The next new family freezes with \(K = K_{\text{prior}} + 1\).
3. Uncorrected α₀ = 0.05 (unless a future protocol freezes another α₀).
4. **Adjusted threshold for any family in the catalog at a given time:**
   \(\alpha_{\text{adj}}(K) = \alpha_0 / K\).
5. **When a new family is added, K increases for the whole program.** Any earlier family still under consideration for promotion or “PASS” status **must be re-evaluated** against the **new** \(\alpha_{\text{adj}}(K)\) before promotion. A past p-value that beat 0.05/K_old but fails 0.05/K_new does **not** promote.
6. Identity diagnostics and synthetic non-dispositional runs **never** increment K and never enter null hit counts.

**Rejected alternative (not used unless a later protocol freezes it):** alpha-spending sequences (O’Brien–Fleming, etc.). v1 does **not** implement spending; it uses catalog Bonferroni only.

### 7.2 What counts as a prior scored family

Count **unique `family_id`** (or equivalent thesis line) that has a committed **scored** attempt:

- registry `SCREEN_FAIL` / `DETERMINISTIC_SCREEN` / sealed `KILL_*` / `PASS_*` / `WEAK_FAIL` / `PROTOCOL_NULL_INVALID` when develop-facing, and/or
- committed null/screen artifacts that record a completed develop grid or null evaluation for that family,

**excluding** pure `SUPERSEDED` freezes that never scored develop.

### 7.3 Corrected baseline audit (2026-08-14)

**Registry terminal families (5):**

1. `tod_london_ny_flat`
2. `server_hour_window_flat`
3. `early_server_range_break_flat`
4. `day_open_reclaim_flat`
5. `joint_london_open_cosign_fade_flat`

**Additional committed scored lines omitted from the provisional K_prior=5 list (3):**

6. `bb_rsi`
7. `Donchian`
8. `prior_day_high_break`

(Confirmed by committed research/null artifacts and program history on main; not optional.)

**Therefore:**

| Quantity | Value |
|----------|-------|
| \(K_{\text{prior}}\) | **8** |
| Next new family \(K\) | **9** |
| \(\alpha_{\text{adj}}\) at K=9 | **0.05/9 ≈ 0.005556** |
| Null trials N | **≥ 999** (keep 2.2 resolution; adequate for zero-hit threshold at this α_adj) |

Phase C freeze must **re-list** `multiplicity.prior_scored_family_ids` explicitly. If audit finds more scored families, K increases before freeze.

### 7.4 Freeze multiplicity block (required)

```text
multiplicity.method = finite_catalog_bonferroni
multiplicity.alpha_uncorrected = 0.05
multiplicity.K_prior = <audited int>
multiplicity.K = K_prior + 1
multiplicity.alpha_adjusted = alpha_uncorrected / K
multiplicity.prior_scored_family_ids = [ ... explicit ... ]
multiplicity.revalidation_rule =
  "any earlier PASS/promotion candidate must meet alpha_adjusted at current catalog K"
multiplicity.identity_excluded_from_null_trials = true
```

### 7.5 Ledgers

| Ledger | Role |
|--------|------|
| `results/xau_charter_disposition_registry.jsonl` | Terminal charter dispositions |
| `results/xau_family_attempts.jsonl` | Sealed single-frame STARTED/terminal (when present) |
| Multi-instrument run dirs | Must feed STARTED/terminal accounting once Phase B wires exogenous screens |

---

## 8. STARTED / terminal accounting (screens and nulls)

### 8.1 Principles

1. Dispositional exogenous screen: sealed charter path; clean dispositional tree; cost identity + finite sim keys (no global XAU point_size forced onto FX); fresh out-dir; **STARTED before package load/score**; canonical report blocks.
2. Synthetic = non-dispositional: never registry-close a real charter SHA.
3. **SCREEN_FAIL** (n_passers=0): exit 0, r1_burned=false, empty trials.
4. **SCREEN_PASS_PENDING_NULL_REVIEW** (n_passers=1): exit 0, r1_burned=false, skipped_reason=SCREEN_ONLY.
5. Full null success: exit 0, trials id set `== range(N)`, every trial \(T=M\), r1_burned=true.
6. Incomplete / trade-count mismatch on any null trial: FAILED_RUN_UNKNOWN, r1_burned=true, n_null_executed=null.

### 8.2 Attempt ledger

Phase B must append STARTED/terminal rows for exogenous screens/nulls into the program attempt ledger (shared or dedicated) and include them in §7 audits.

---

## 9. Validator checklist (Phase B acceptance)

Charter with `harness.kind=multi_instrument_exogenous_predictor_v1` fails closed unless:

1. Extension vocabulary recognized (protocol field pinned in Phase B).
2. Exactly one traded + ≥1 predictor; partition invariants (§1.2).
3. Intersection-only calendar (§3).
4. Null block = fixed events **and** fixed trades; full donor/sampling pins (§5).
5. Binary soft primary on traded book only (§1.4).
6. MTM DD definition for traded book (§4).
7. H-bar same-day + next-bar day_id rules if used (§6).
8. Explicit sign examples (§6.4).
9. Multiplicity block with K_prior audit and finite-catalog Bonferroni (§7).
10. Costs: identity + finite sim keys; per-symbol point/contract on traded.
11. Package pin complete.
12. Prefer `n_free_knobs=0`, `search_cardinality=1`.
13. Prohibited runners include single-frame and joint_v1.

---

## 10. Phased delivery

| Phase | Deliverable | Stop condition |
|-------|-------------|----------------|
| **A (this doc)** | Spec only | Adversarial protocol review |
| **B** | Generic validator + fixed-trade conditional-null machinery + accounting + synthetic tests (zero predictors, multi-traded reject, trade-count identity across trials, dirty harness, etc.) | PR merge; **no** thesis signals |
| **C** | Immutable charter + memo | Freeze review; then fixtures; then screen |

---

## 11. Explicit bans (summary)

- Zero predictors / all-traded under this kind.
- Multiple traded symbols in v1.
- Predictor fills or predictor soft as primary.
- Joint-cosign harness reuse.
- Empty intersection as zero-trade success.
- Realized-only DD for open positions.
- Null trials with unfilled events or \(T ≠ M\).
- Outcome-dependent donor selection.
- Counting identity construction inside N/hits/p.
- Multiplicity fail-open (K_prior=5) or birth-only α without revalidation.
- Collapsing EUR/GBP into an XAU-only indicator to evade this protocol.

---

## 12. Document control

| Item | Value |
|------|--------|
| Spec version | multi_instrument_exogenous_predictor_protocol_v1 |
| Implementation status | **not started** |
| Thesis freeze | **not authorized** |
| Phase B | **not authorized** until this amend passes review |
| Next gate | **AWAIT_ADVERSARIAL_PROTOCOL_REVIEW** |

**End of Phase A specification (amended).**
