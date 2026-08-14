# Multi-instrument exogenous-predictor protocol v1

**Date:** 2026-08-14
**Status:** **SPECIFICATION ONLY** — not implemented · not enforced · not freeze-ready for thesis
**Branch:** `research/exogenous-predictor-protocol-v1` from `main@a492f2c`
**Parent:** extends family protocol 2.2 (`docs/research/XAU-FAMILY-PROTOCOL-V2.md`) without replacing it for single-frame / joint-cosign families
**Revision:** Phase A amend 2 (executable null algorithm, pre-entry events, identity, accounting boundary)

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
- a **canonical, executable** conditional null (`conditional_fixed_signal_events_fixed_trades_v1`) that Phase B can implement without open-ended “charter algorithm text”;
- finite-catalog Bonferroni multiplicity with corrected historical baseline and **provisional PASS** while the catalog remains open.

### 0.2 Non-goals (explicit)

| Out of scope for this spec PR | Why |
|-------------------------------|-----|
| Thesis charter / memo / family module | Phase C after Phase B merges |
| Implementation of validators or null engine | Phase B |
| Develop package load, screen, null, holdout | Forbidden until freeze+fixtures authorized |
| Reshaping EUR/GBP into a derived XAU indicator | Evades exogenous structure; **forbidden** |
| Changing single-frame or `multi_instrument_joint_v1` contracts | Leave 2.2 joint-cosign path intact |
| Multiple traded books | **Deferred to protocol v2** |
| Alternate null algorithms (with-replacement, strata, recompute signals, etc.) | **Not in v1** — charter may only pin parameters listed in §5.8 |

### 0.3 Relationship to existing kinds

| `harness.kind` | Role |
|----------------|------|
| (single-frame default) | One symbol, `xau_family_null_maxstat` / sealed cycle |
| `multi_instrument_joint_v1` | All listed symbols co-traded; joint soft primary; shared-k OHLC null |
| **`multi_instrument_exogenous_predictor_v1`** | Non-empty predictors; **exactly one traded book**; canonical fixed-event fixed-trade null |

All-traded families **must not** select this kind. Predictor theses **must not** use joint_v1.

---

## 1. Instrument roles: traded vs predictor

### 1.1 Required charter blocks

```text
instrument.symbols                  # ordered list; all package members used
instrument.traded_symbols           # EXACTLY one symbol
instrument.predictor_symbols        # non-empty; no overlap with traded
instrument.multi_symbol_in_scope    # true
```

Signal formation always uses the full `symbols` list on the intersection calendar.
Field `require_all_symbols_for_signal` is **not** part of v1.

### 1.2 Invariants (validator — fail closed)

1. `len(traded_symbols) == 1`.
2. `len(predictor_symbols) ≥ 1`.
3. `traded_symbols[0] ∈ symbols`.
4. Every predictor ∈ `symbols`.
5. Disjoint roles; union equals `symbols`; traded is a **proper subset**.
6. Every symbol has `per_symbol_meta` (point_size, contract_size, digits).
7. Package pin complete (Phase-0 multi-instrument data).

**Phase B regression cases:** zero predictors; multiple traded; overlap; missing roles; predictor fills.

### 1.3 Semantic rules

| Role | Orders | Soft/classic gates | MTM equity | Null path |
|------|--------|--------------------|------------|-----------|
| **traded** (exactly one) | Yes | Sole primary book | Yes | Outcome paths only |
| **predictor** (≥1) | **No** | **No** | **No** | Real-path signal formation only; events frozen on null |

### 1.4 Gates scope (v1)

- Primary `n_passers` ∈ {0,1} on the single traded book’s soft gate only.
- `gates.primary_n_passers = "soft"`.
- No summed multi-traded passers (matches fail-closed parser `real.n_passers == 1` for positive screen).
- Classic report-only unless a later protocol freezes otherwise.

---

## 2. Harness kind and dispatch

### 2.1 Kind

```text
harness.kind = "multi_instrument_exogenous_predictor_v1"
```

### 2.2 Dispatch (Phase B)

| Caller | Behavior |
|--------|----------|
| `xau_family_null_maxstat.py` | **Refuse** |
| `xau_sealed_family_cycle.py` | **Refuse** (unless later extended under this kind) |
| `xau_multi_instrument_joint_screen.py` | **Refuse** |
| Dedicated exogenous harness | Only screen/null path |

### 2.3 Freeze-time vs run-time

Phase C may freeze `module_expected` before the file exists **only after** Phase B recognizes this kind in validators/accounting.
Dispositional clean-tree must include `scripts/xau_multi_instrument_*.py` and conditional-null core.

---

## 3. Analysis calendar

```text
analysis_calendar.mode = "intersection_only"
```

Mandatory for signals, ATR, entries, exits, MTM, real, and null on set **I** (timestamps in every `symbols` member).
Clock: naive server clock; hour/day_id derived from time; unique strictly increasing timestamps.
Empty **I** → `EMPTY_JOINT_INTERSECTION` (hard error).

---

## 4. MTM equity and drawdown (traded book only)

For traded symbol **S** and each \(t \in I\):

\[
\text{equity}_S(t) = B_S(t) + \text{open\_pnl}_S(t)
\]

with mark = close on **I** by default; DD uses full equity series including floating open P&L.
**Ban:** realized-only step equity for gate DD.
Multiple traded books: **not in v1**.

---

## 5. Conditional null — canonical algorithm (Phase B must implement exactly this)

### 5.1 Implementation id

```text
null.method = conditional_fixed_signal_events_fixed_trades_v1
null.implementation_id = conditional_fixed_signal_events_fixed_trades_v1
null.estimand = fixed_real_preentry_events_fixed_trade_count
```

**Unsupported alternatives are protocol errors** if a charter names them under this kind:
with-replacement sampling, within-trial donor overlap, strata sampling, OHLC-rotate signal recompute,
outcome-dependent donors, unfilled events, free-form “algorithm text” overrides of §5.5–§5.7.

Phase C freezes only **parameters** listed in §5.8 (H, risk, lot bounds, N, seed, package pins, signal predicate) — not alternate engines.

### 5.2 Holding constants (canonical)

| Constant | v1 value |
|----------|----------|
| H | **3** (holding bars including entry bar) |
| Entry | open of **next** joint bar after signal bar \(t^\*\) on **I** |
| Same-day | \(t^\*\), entry, and all H hold bars share one `day_id` |
| Exit priority per bar after entry | SL then TP then time-flat at end of hold window (close of bar \(t_{\text{entry}}+H-1\)) |
| Mark for MTM | close |

### 5.3 Real path — event set E (pre-entry only)

**Step R1 — raw signal candidates.**
On each \(t \in I\) (after warmup as frozen by thesis), evaluate the **charter signal predicate** using only data allowed by the freeze (predictors + traded history through \(t\), features from \(t-L..t-1\) when applicable). Produce candidate \(c = (t^\*=t, \text{side} \in \{+1,-1\})\).

**Step R2 — pre-entry eligibility predicate \(P_{\text{entry}}(c)\).**
Admit \(c\) into \(E\) **iff all** hold (no post-entry information):

1. Next bar \(t_e = \text{index}(t^\*)+1\) exists on **I**.
2. `day_id(t_e) == day_id(t^\*)`.
3. Bars \(t_e, t_e+1, \ldots, t_e+H-1\) all exist on **I** and share `day_id(t_e)`.
4. ATR at freeze source bar (canonical: **atr at \(t^\*\)** on traded series on **I**, Wilder 14 unless thesis freezes another **before Phase C** — default Wilder 14) is finite and \(> 0\).
5. Lots from canonical sizing (§5.6) using balance at decision time and that ATR satisfy lots ≥ lot_min after floor-to-step and ≤ lot_max.
6. Spread at \(t_e\) on traded symbol is finite and ≥ 0.
7. side is ±1.

Candidates failing \(P_{\text{entry}}\) are **rejected** and **never** enter \(E\).

**Step R3 — event list.**
\(E = (e_1,\ldots,e_M)\) is the ordered list of admitted candidates. Each event stores at least:
`event_id` (0..M-1), `t_star`, `t_entry`, `side`, `atr_tstar`, `lots` (as computed at real admission), `spread_entry` (real traded spread at \(t_e\)).

**Step R4 — post-entry execution (must complete).**
For each \(e_m \in E\), enter at open(\(t_{\text{entry}}\)) with stored side/lots; apply SL/TP/time on the H bars using real traded OHLC on **I**.
**Every** \(e_m\) **must** produce exactly one closed trade (exit by SL, TP, or time-flat at last hold bar).

If any admitted event cannot complete (missing bar that passed eligibility — should be impossible —, non-finite mark mid-hold, engine bug, etc.):
→ **run invalid**: disposition `FAILED_RUN_UNKNOWN` (if dispositional STARTED already written) with r1 burned; **do not** drop the event from \(M\) or silently skip the trade.

Therefore on every **valid** real run: **\(T_{\text{real}} = M\)**.

### 5.4 Donor segment definition

A **donor** is a contiguous traded-path segment on **I** identified by a stable **`donor_id`**.

**Canonical donor_id:** integer index of the **entry bar** \(t_e\) on the joint calendar **I** (0-based position in the aligned traded frame).

Donor \(d\) at entry index \(i = \text{donor_id}\) is **eligible** iff \(P_{\text{donor}}(i)\):

1. Bars \(i, i+1, \ldots, i+H-1\) exist on **I**, same `day_id`.
2. OHLC finite on those bars; spread at \(i\) finite and ≥ 0.
3. (No outcome filter: eligibility **must not** depend on future P&L, win/loss, or gate metrics.)

**Eligible donor pool \(\mathcal{D}\):** sorted list of all eligible `donor_id` values on develop **I**.

**Real identity donor** for event \(e_m\): `donor_id = index(e_m.t_entry)` (must be in \(\mathcal{D}\) on a valid real run).

### 5.5 Canonical pairing algorithm (counted null trials)

**RNG:** for trial index \(j \in \{0,1,\ldots,N-1\}\):

```text
rng_j = numpy.random.Generator(numpy.random.PCG64(base_seed + j))
```

**Assignment (without replacement, no overlap within trial):**

1. Require \(|\mathcal{D}| ≥ M\). If not → **donor preflight failure** (§8.3).
2. Draw a random permutation of \(\mathcal{D}\) via `rng_j.permutation(len(D))` applied to sorted \(\mathcal{D}\).
3. Take the first \(M\) donor_ids in that permutation as \((d_0,\ldots,d_{M-1})\) assigned to events \(e_0,\ldots,e_{M-1}\) in order.
4. **Complete-identity rejection:** let \(d_m^{\text{id}} = \text{index}(e_m.t_entry)\). If \((d_0,\ldots,d_{M-1}) = (d_0^{\text{id}},\ldots,d_{M-1}^{\text{id}})\), **discard** and redraw from the **same** `rng_j` (continue consuming RNG state) until the assignment is **not** the full identity vector, or until `MAX_IDENTITY_REDRAWS = 1000` failures → **trial invalid** / run UNKNOWN (should be astronomically rare when \(|\mathcal{D}| > M\); if \(|\mathcal{D}| = M\) the only permutation may be identity — then protocol refuse at preflight: require \(|\mathcal{D}| ≥ M+1\) **or** \(|\mathcal{D}| ≥ M\) and \(M ≥ 1\) with at least one non-identity permutation available; **v1 pin: require \(|\mathcal{D}| ≥ max(M+1, M)\) and if the only possible assignments are identity, preflight fails**).

**v1 pin on pool size:** \(|\mathcal{D}| ≥ M + 1\) when \(M ≥ 1\), guaranteeing at least one non-identity injection-style assignment under without-replacement of M distinct donors (when M=1, need ≥2 donors).

**Per-event self-pairing:** **allowed** (an event may draw its own real donor_id) **provided** the full M-vector is not the complete identity assignment. No ban on partial self-hits.

**Forbidden in v1:** with-replacement; overlapping donors within a trial; strata; free charter overrides of this pairing.

### 5.6 Path transplant, sizing, costs (canonical)

For event \(e_m\) paired with donor_id \(i\):

1. **Entry fill price** = open of traded bar \(i\).
2. **Side** = \(e_m.\text{side}\) (frozen from real event).
3. **Lots** = \(e_m.\text{lots}\) frozen from real admission (**lot_source = frozen_from_real_event**).
4. **SL/TP distances** from \(e_m.\text{atr_tstar}\) and freeze SL/TP ATR multiples (**atr_source = frozen_from_real_event**).
5. **Spread cost** at entry = donor spread at bar \(i\) × point_size_traded × contract × lots (+ commission/slippage from cost pin) (**spread_source = donor_at_entry**).
6. Simulate H bars of donor OHLC from \(i\); exit SL→TP→time-flat; deduct costs at exit booking.
7. Must produce exactly one closed trade; failure → trial/run invalid (§8.3), not drop event.

**Normalization:** absolute donor price path (no residual rebase). Entry is donor open; SL/TP absolute prices = entry ± sl_atr×atr_tstar / tp_atr×atr_tstar.

### 5.7 Identity diagnostic (not a counted trial)

1. Build assignment \(d_m = d_m^{\text{id}}\) for all m (full identity).
2. Run §5.6; metrics must match real path within float tolerance (fixture).
3. **Excluded from N, hits, and p.** Not stored as `trials[j]` for j in 0..N-1.
4. Phase B **forced-identity RNG regression:** construct an RNG stream that first yields the identity assignment; implementation must redraw and **must not** count that draw as a successful null trial outcome; assert final stored trial assignment ≠ identity and `len(trials)==N`.

### 5.8 Charter parameters only (Phase C may set)

Charter under this kind may set: signal predicate, L, SL/TP ATR multiples, risk_pct, lot_min/step/max, start_balance, N (≥999), base_seed, package pins, soft thresholds, multiplicity block.
Charter **must** set `null.implementation_id = conditional_fixed_signal_events_fixed_trades_v1` and must **not** set alternate sampling enums.

### 5.9 Invariants (summary)

| Invariant | Rule |
|-----------|------|
| Event definition | Pre-entry \(P_{\text{entry}}\) only |
| Real T | \(T = M\) or run invalid |
| Null T | every counted trial \(T = M\) |
| Predictors on null | not re-simulated for signals |
| Identity | diagnostic only; full identity assignment rejected in counted trials |
| Attrition | forbidden |

### 5.10 Screen vs null

- `n_passers == 0` → SCREEN_FAIL, null not run, r1 unburned.
- `n_passers == 1` → pending null / sealed null under §8.
- else → implementation error for v1 binary families.

---

## 6. Signal / entry / exit freeze obligations (thesis text)

Lookbacks: prior bars \(t-L..t-1\) on **I**; strict inequalities; per-symbol stats; zero/non-finite reject.
Hold: H=3 same-day as §5.2 (thesis may not relax H without a new protocol version).
Weekend: next bar same `day_id` or reject (not in E).
Sign mapping: explicit long/short toy examples required at freeze.
Gate provenance: formulas on traded book; PF 0/99 house convention.

---

## 7. Multiplicity — finite-catalog Bonferroni + provisional PASS

### 7.1 Rule (chosen)

1. \(K_{\text{prior}}\) = audited unique scored families (§7.2–7.3).
2. New family freezes with \(K = K_{\text{prior}}+1\).
3. \(\alpha_0 = 0.05\), \(\alpha_{\text{adj}}(K) = \alpha_0 / K\).
4. **Catalog remains open:** there is **no** finite \(K_{\max}\) in v1.
5. **PASS is provisional** while the catalog is open:
   - A family that beats \(\alpha_{\text{adj}}(K_{\text{at_test}})\) may be labeled `PASS_KEEP_RESEARCHING` / research-keep only.
   - **Paper and live are forbidden** until either (a) a later protocol freezes a closed catalog \(K_{\max}\) and the family still passes \(\alpha_0/K_{\max}\), or (b) an explicit human program-close decision freezes K and revalidates.
   - When K increases, every provisional PASS must be re-checked against the new \(\alpha_{\text{adj}}\) before any promotion step; failure demotes research status (no silent grandfather).
6. Identity diagnostics do not increment K.

### 7.2 Scored-family definition

Unique family_id with committed develop score or null evaluation (registry SCREEN_FAIL / KILL_* / PASS_* / WEAK_FAIL / PROTOCOL_NULL_INVALID develop-facing, and/or committed null artifacts), excluding pure SUPERSEDED never-scored freezes.

### 7.3 Baseline audit (2026-08-14)

**Eight prior scored families:**

1. `tod_london_ny_flat`
2. `server_hour_window_flat`
3. `early_server_range_break_flat`
4. `day_open_reclaim_flat`
5. `joint_london_open_cosign_fade_flat`
6. `bb_rsi`
7. `Donchian`
8. `prior_day_high_break`

| Quantity | Value |
|----------|-------|
| \(K_{\text{prior}}\) | **8** |
| Next family \(K\) | **9** |
| \(\alpha_{\text{adj}}\) | **0.05/9 ≈ 0.005556** |
| N | **≥ 999** |

### 7.4 Freeze multiplicity block

```text
multiplicity.method = finite_catalog_bonferroni_open_catalog
multiplicity.alpha_uncorrected = 0.05
multiplicity.K_prior = 8   # re-audit at freeze; update if needed
multiplicity.K = 9
multiplicity.alpha_adjusted = 0.05 / K
multiplicity.prior_scored_family_ids = [ ... eight ids ... ]
multiplicity.pass_status = provisional_while_catalog_open
multiplicity.paper_live_while_open = false
multiplicity.revalidation_on_K_increase = true
multiplicity.identity_excluded_from_null_trials = true
```

---

## 8. STARTED / terminal accounting and failure boundary

### 8.1 Dispositional screen / null launch order

1. Validate charter + kind + clean tree + sealed path + cost match.
2. **Non-dispositional donor preflight (optional but recommended):** build \(\mathcal{D}\) and check \(|\mathcal{D}| ≥ M+1\) (after real E is known). If this preflight is run **before** STARTED, failure → exit non-zero, **no** registry row, **r1 not burned** (attempt never dispositionally opened).
3. Create fresh out-dir; write **STARTED** (dispositional attempt open).
4. Package load / score / null as applicable.
5. Write terminal report; append terminal ledger row.

### 8.2 Success terminals

| Outcome | exit | r1_burned | notes |
|---------|------|-----------|-------|
| SCREEN_FAIL (n_passers=0) | 0 | false | empty trials |
| SCREEN_PASS_PENDING_NULL_REVIEW (n_passers=1) | 0 | false | skipped_reason=SCREEN_ONLY |
| Full null success | 0 | true | N trials, each T=M, no full-identity assignment stored |

### 8.3 Failure after STARTED (canonical burned path)

Once STARTED exists for a dispositional run, **any** of the following produces **one** terminal report with:

- `disposition = FAILED_RUN_UNKNOWN`
- `execution_state = UNKNOWN`
- `r1_burned = true`
- `sealed_null_attempt = true` (conservative consume)
- `n_null_executed = null` (JSON null; never substitute planned)

**Triggers:**

- Donor pool empty or \(|\mathcal{D}| < M+1\) discovered after STARTED.
- Assignment failure (including MAX_IDENTITY_REDRAWS exceeded).
- Any counted trial with \(T ≠ M\).
- Post-entry completion failure on real or null for an admitted event.
- Missing/malformed report blocks; nonzero harness crash; trade-count mismatch.

**Do not** invent a second disposition string for “protocol invalid” after STARTED — use FAILED_RUN_UNKNOWN so fail-closed parsers burn the attempt uniformly.

### 8.4 Failure before STARTED

Validator errors, clean-tree dirty, cost mismatch, sealed-path failure, or **optional non-dispositional preflight** failure: no STARTED, no registry terminal SCREEN/KILL, r1 not burned.

### 8.5 Synthetic

Non-dispositional; cannot write registry against real charter SHA.

---

## 9. Validator checklist (Phase B)

1. Kind recognized; refuse joint/single-frame runners.
2. Exactly one traded + ≥1 predictors; partition tests.
3. Intersection-only calendar.
4. Null implementation_id exactly `conditional_fixed_signal_events_fixed_trades_v1`; reject alternate sampling enums.
5. Binary soft primary on traded only.
6. MTM DD on traded equity series.
7. H=3 same-day + next-bar day_id in entry eligibility.
8. Sign examples at freeze (Phase C).
9. Multiplicity block with K_prior audit + provisional PASS + paper/live false while open.
10. Cost identity + finite sim keys; no global point_size on FX.
11. Package pin.
12. Prefer n_free_knobs=0, search_cardinality=1.
13. Synthetic tests: trade count T=M all trials; forced-identity redraw; zero predictors; multi-traded; predictor fill ban; donor preflight refuse.

---

## 10. Phased delivery

| Phase | Deliverable | Stop |
|-------|-------------|------|
| **A (this doc)** | Spec only | Protocol review → merge doc-only PR |
| **B** | Validator + **canonical** null engine + accounting + synthetic tests | Fresh branch post-merge; no thesis signals |
| **C** | Immutable charter + memo | Freeze review; fixtures; screen |

---

## 11. Explicit bans

- Zero predictors / multi-traded under this kind.
- Event membership decided by post-entry success.
- Null unfilled events or T≠M as success.
- Full identity assignment as a counted null trial.
- With-replacement, strata, charter-defined alternate pairings in v1.
- Outcome-dependent donors.
- Fail-open multiplicity (K_prior=5) or birth-only α without revalidation.
- Promoting to paper/live while catalog open / PASS only provisional.
- Collapsing predictors into an XAU-only indicator to evade this protocol.

---

## 12. Document control

| Item | Value |
|------|--------|
| Spec version | multi_instrument_exogenous_predictor_protocol_v1 |
| Implementation status | **not started** |
| Phase B | **not authorized** until this amend passes and doc-only PR merges |
| Next gate | **AWAIT_ADVERSARIAL_PROTOCOL_REVIEW** |

**End of Phase A specification (amend 2).**
