# Multi-instrument exogenous-predictor protocol v1

**Date:** 2026-08-14
**Status:** **SPECIFICATION ONLY** — not implemented · not enforced · not freeze-ready for thesis
**Branch:** `research/exogenous-predictor-protocol-v1` from `main@a492f2c`
**Parent:** extends family protocol 2.2 (`docs/research/XAU-FAMILY-PROTOCOL-V2.md`) without replacing it for single-frame / joint-cosign families
**Revision:** Phase A amend 3 (HEAD) — segment non-overlap pairing; dual SCREEN/NULL STARTED; concurrent books

### Reviewer map (re-review this HEAD only)

| Finding | Status | Where |
|---------|--------|-------|
| Prior four gaps (executable null, pre-entry E, identity, accounting) | **Closed** (amend 2/2b) | §5, §8 |
| Distinct donor_ids still allow H-bar segment overlap | **Closed this amend** | §5.4–§5.5 interval packing |
| Develop score before any STARTED | **Closed this amend** | §8.1 dual-phase SCREEN_STARTED / NULL_STARTED |
| Concurrent events undefined | **Closed this amend** | §5.3 R4 / §4.1 concurrent MTM |
| Open-catalog promotion | **Closed** | §7.1 provisional PASS; paper/live forbidden while open |

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

### 4.1 Concurrent positions (canonical)

Concurrent open positions on the single traded symbol **S** are **allowed**.

- Admission does **not** require a flat book and does **not** apply an H-window occupancy filter (§5.3 R2).
- Signals fewer than H bars apart may both enter; early exit of one does not cancel the other.
- Each admitted event is an independent lot-sized trade with its own SL/TP/time-flat clock from its own entry bar.

### 4.2 Same-bar order processing and balance

Process each bar \(t \in I\) in this **fixed** order:

1. **Exits first:** evaluate SL → TP → time-flat for every open position whose exit rules fire on \(t\), ordered by ascending `event_id`. Book realized P&L into the cash balance after each exit.
2. **Entries second:** open any events with \(t_{\text{entry}} = t\), ordered by ascending `event_id`. Lot sizing for a new entry uses the **realized cash balance after all exits on this bar and before any new entries on this bar** (same balance for all same-bar entries; no intra-bar compounding across concurrent opens).
3. **Mark last:** mark all still-open positions at close(\(t\)).

### 4.3 Equity series

For traded symbol **S** and each \(t \in I\):

\[
\text{equity}_S(t) = B_S(t) + \sum_{p \in \text{open}(t)} \text{floating\_pnl}_p(t)
\]

where \(B_S(t)\) is realized cash after the exit step on \(t\), and floating P&L is the **sum** over all still-open positions marked at close(\(t\)).

- Soft DD gates use this full equity series (realized + summed floating).
- **Ban:** realized-only step equity for gate DD.
- Multiple traded books: **not in v1**.

**Phase B regression:** two consecutive admitted signals; first hits SL early before second entry; assert both trades booked, intervening bars have concurrent floating sum when both open, final \(T=2\).

---

## 5. Conditional null — canonical algorithm (Phase B must implement exactly this)

### 5.1 Implementation id

```text
null.method = conditional_fixed_signal_events_fixed_trades_v1
null.implementation_id = conditional_fixed_signal_events_fixed_trades_v1
null.estimand = fixed_real_preentry_events_fixed_trade_count
```

**Unsupported alternatives are protocol errors** if a charter names them under this kind:
with-replacement sampling, within-trial **segment-overlapping** donors (distinct ids alone do not satisfy non-overlap), strata sampling, OHLC-rotate signal recompute,
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
Admit \(c\) into \(E\) **iff all** hold (no post-entry information; **no flat-book / occupancy filter** — concurrency allowed):

1. Next bar \(t_e = \text{index}(t^\*)+1\) exists on **I**.
2. `day_id(t_e) == day_id(t^\*)`.
3. Bars \(t_e, t_e+1, \ldots, t_e+H-1\) all exist on **I** and share `day_id(t_e)`.
4. ATR at \(t^\*\) on the traded series on **I** using **Wilder period 14** only (`TR.ewm(alpha=1/14, adjust=False).mean()`); must be finite and \(> 0\).
5. Lots from §5.6 sizing using **realized balance before any same-bar new entries** (see §4.2) and that ATR: `risk_cash = risk_pct * balance`; `raw = risk_cash / (sl_atr * atr_tstar * contract_size)`; floor to `lot_step`; cap `lot_max`; require ≥ `lot_min` (never force min).
6. Spread at \(t_e\) on traded symbol is finite and ≥ 0.
7. side is ±1.

Candidates failing \(P_{\text{entry}}\) are **rejected** and **never** enter \(E\).
Signals fewer than H bars apart **may both be admitted** (concurrent positions).

**Step R3 — event list.**
\(E = (e_1,\ldots,e_M)\) is the ordered list of admitted candidates. Each event stores at least:
`event_id` (0..M-1), `t_star`, `t_entry`, `side`, `atr_tstar`, `lots` (as computed at real admission), `spread_entry` (real traded spread at \(t_e\)).

**Step R4 — post-entry execution (must complete; concurrency allowed).**
Process the develop calendar bar-by-bar with §4.2 ordering. Each \(e_m \in E\) enters at open(\(t_{\text{entry}}\)) and **must** produce exactly one closed trade by SL, TP, or time-flat at \(t_{\text{entry}}+H-1\).

If any admitted event cannot complete:
→ **run invalid**: if **SCREEN_STARTED** or **NULL_STARTED** already written, terminal `FAILED_RUN_UNKNOWN` with burn rules in §8; **do not** drop the event from \(M\).

On every **valid** real run: **\(T_{\text{real}} = M\)**.

**Phase B regression:** two consecutive admitted signals with first exiting early (SL) before second entry; assert both trades exist, concurrent floating sum on intervening bars, and final \(T=2\).

### 5.4 Donor segment definition (interval geometry)

A **donor** is a contiguous traded-path segment on **I** identified by a stable **`donor_id`**.

**Canonical donor_id:** integer index of the **entry bar** \(i\) on joint calendar **I** (0-based).

**Occupied bar interval** of donor_id \(i\):

\[
I(i) = \{i, i+1, \ldots, i+H-1\}
\]

Two donors \(i,j\) **segment-overlap** iff \(I(i) \cap I(j) \neq \emptyset\) (equivalently: not (\(i+H-1 < j\) or \(j+H-1 < i\))).

**Distinct donor_ids are not sufficient for non-overlap.** Example: \(H=3\), \(\mathcal{D}=\{0,1,2\}\): every pair segment-overlaps; a “pick M distinct ids” rule is **not** a non-overlap rule.

Donor \(i\) is **eligible** iff \(P_{\text{donor}}(i)\):

1. Bars in \(I(i)\) exist on **I**, same `day_id`.
2. OHLC finite on those bars; spread at \(i\) finite and ≥ 0.
3. No outcome filter (eligibility independent of P&L / gates).

**Eligible donor pool \(\mathcal{D}\):** sorted ascending list of all eligible `donor_id` values on develop **I**.

**Real identity donor** for event \(e_m\): `donor_id = index(e_m.t_entry)` (must ∈ \(\mathcal{D}\) on a valid real run).

**Packing capacity** `pack_capacity(D)`: size of a maximum set of pairwise non-segment-overlapping donors from \(\mathcal{D}\). Canonical computation (deterministic):

1. Sort eligible ids ascending: \(i_1 < i_2 < \ldots\).
2. Greedy earliest-start: accept next id if it does not segment-overlap any already accepted; else skip.
3. `pack_capacity =` number accepted.

(This greedy is optimal for interval scheduling by start time with fixed length H.)

### 5.5 Canonical pairing algorithm (counted null trials)

**RNG:** for trial index \(j \in \{0,1,\ldots,N-1\}\):

```text
rng_j = numpy.random.Generator(numpy.random.PCG64(base_seed + j))
```

**Preflight (mandatory before NULL_STARTED when \(M ≥ 1\)):**

1. Build \(\mathcal{D}\).
2. Require `pack_capacity(D) ≥ M` (pairwise non-segment-overlapping capacity, not mere \(|\mathcal{D}|\)).
3. Identity is **not** preflight-gated by a second capacity test; §5.5 assignment **rejects** the full identity vector at draw time (up to 1000 redraws). If every feasible size-M packing is only the identity, counted trials fail after NULL_STARTED → §8.3.

**Refuse preflight** when `pack_capacity(D) < M`. Canonical adjacent-id regression: \(\mathcal{D}=\{0,1,2\}\), \(H=3\), \(M=2\) → every pair segment-overlaps → `pack_capacity=1` → preflight refuse (no NULL_STARTED, r1 unburned).

**Do not** treat \(|\mathcal{D}| ≥ M\) or \(|\mathcal{D}| ≥ M+1\) alone as sufficient — those admit overlapping H-bar segments.

**Assignment — Phase B implements exactly this (segment non-overlap + no full identity):**

1. If \(M = 0\): no null trials.
2. `D_sorted = sorted(D)`.
3. `redraws = 0`.
4. Loop:
   a. `perm = rng_j.permutation(len(D_sorted))`; `order = [D_sorted[k] for k in perm]`.
   b. **Greedy pack from `order`:** walk `order` left to right; accept donor if it does **not segment-overlap** any already accepted donor in this trial; stop when M accepted or order exhausted.
   c. If fewer than M accepted: `redraws += 1`; if `redraws ≥ 1000` → trial/run invalid; else continue loop.
   d. Let assignment map event_id `m` → `accepted[m]` (order of acceptance is event_id order 0..M-1).
   e. If assignment equals full identity vector \((d_0^{\text{id}},\ldots)\): `redraws += 1`; if `redraws ≥ 1000` → invalid; else continue loop.
   f. Else: accept assignment; break.
5. Execute §5.6 for every event with its donor_id.

**Per-event self-pairing:** allowed iff the full assignment is not complete identity **and** all pairs are non-segment-overlapping (self-pair is a single interval; always “non-overlapping” with itself as one donor).

**Forbidden in v1:** with-replacement; **segment-overlapping** donors within a trial (not merely distinct ids); strata; charter-supplied pairing; OHLC-rotate signal recompute; unfilled events.

**Phase B regression (adjacent donors):** \(\mathcal{D}=\{0,1,2\}\), \(H=3\), \(M=2\) → preflight fail (`pack_capacity=1`). Separate case: non-overlapping pool e.g. `{0,3,6}` with \(H=3\), \(M=2\) → assignments must never include `(0,1)`-style overlap; assert every stored trial has pairwise disjoint intervals.

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
| Donor non-overlap | pairwise non-segment-overlapping intervals \(I(d)\); not distinct-id-only |
| Concurrency | concurrent traded positions allowed; equity = realized + sum floating |

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

### 8.0 Two dispositional arming phases (mandatory)

| Phase marker | File (canonical name) | When written | Purpose |
|--------------|----------------------|--------------|---------|
| **SCREEN_STARTED** | `SCREEN_STARTED.json` | **Before** package load and **before** real develop score | Makes a scored develop attempt visible if the process crashes mid-screen |
| **NULL_STARTED** | `NULL_STARTED.json` (or `STARTED.json` only for null-only tools) | **After** positive screen **and** successful donor preflight, **before** any counted null trial | Arms sealed null; failures after this burn r1 |

Screen and null may share one out-dir tree with both markers, or separate out-dirs; markers must exist before the work they protect.

### 8.1 Screen phase (dispositional develop score)

1. Validate charter + kind + clean tree + sealed path + cost match.
2. Fresh screen out-dir (refuse overwrite).
3. Write **SCREEN_STARTED** (`execution_state=SCREEN_STARTED`, `r1_burned=false`, family/charter/package pins).
4. Package load + real path (build \(E\), execute trades, gates).
5. Terminal screen report:
   - **SCREEN_FAIL** (\(n_{\text{passers}}=0\)): exit 0, r1_burned=false, null not armed; registry optional per program policy.
   - **SCREEN_PASS_PENDING_NULL_REVIEW** (\(n_{\text{passers}}=1\)): exit 0, r1_burned=false; may proceed to null preflight.
6. **Crash / failure after SCREEN_STARTED but before successful screen terminal:**
   - Write terminal `FAILED_RUN_UNKNOWN` if possible;
   - `execution_state=UNKNOWN`;
   - **`r1_burned=false`** (screen-phase failures do **not** burn sealed-null r1);
   - `sealed_null_attempt=false`;
   - attempt remains visible via SCREEN_STARTED + terminal row.

**Phase B tests:** kill/raise before package load after SCREEN_STARTED; raise mid-score; assert marker present and r1_burned=false on terminal accounting.

### 8.2 Null phase (only if n_passers=1)

1. **Donor preflight (before NULL_STARTED):** build \(\mathcal{D}\); require `pack_capacity(D) ≥ M` (§5.5). Failure → exit non-zero, **no** NULL_STARTED, **r1_burned=false** (null never armed); screen PASS remains pending human decision.
2. Fresh null out-dir (or subdir); write **NULL_STARTED** (`execution_state=NULL_STARTED`, arms burn).
3. Run N counted trials (§5.5–§5.6).
4. Success terminal: full null report, r1_burned=true, trials id set `== range(N)`, each \(T=M\).
5. **Any failure after NULL_STARTED** → §8.3 burned UNKNOWN.

**Phase B tests:** raise after preflight success before first trial; raise mid-trial; assert NULL_STARTED present and r1_burned=true.

### 8.3 Failure after NULL_STARTED (canonical burned path)

Produces **one** terminal report:

- `disposition = FAILED_RUN_UNKNOWN`
- `execution_state = UNKNOWN`
- `r1_burned = true`
- `sealed_null_attempt = true`
- `n_null_executed = null` (JSON null)

**Triggers:** assignment failure (incl. 1000 redraws); any trial \(T ≠ M\); post-entry completion failure; pack/assignment bugs discovered after arming; crash; malformed report.

### 8.4 Failure before any STARTED

Validator / clean-tree / cost / sealed-path errors: no SCREEN_STARTED, no registry burn.

### 8.5 Failure after SCREEN_STARTED, before NULL_STARTED

Includes: score crash; SCREEN_FAIL path; donor preflight fail after PASS.
→ visible attempt; **r1_burned=false**; null not armed.

### 8.6 Synthetic

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
13. Synthetic tests: trade count T=M all trials; forced-identity redraw; segment-overlap rejection (adjacent donor ids); concurrent early-exit pair; SCREEN_STARTED before load; NULL_STARTED burn boundary; zero predictors; multi-traded; predictor fill ban; pack_capacity preflight refuse.

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
- Treating distinct donor_ids as “no overlap” without segment-interval checks.
- Outcome-dependent donors.
- Flat-book-only admission or undefined concurrent MTM (v1 allows concurrency under §4).
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

**End of Phase A specification (amend 3).**
