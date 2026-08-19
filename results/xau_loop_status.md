# XAU offline loop status

## 2026-08-19 — Develop screen · `asia_box_london_sweep_fade_flat` **SCREEN_FAIL** (deterministic)

| Field | Value |
|-------|--------|
| **next_step** | **`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`** |
| **promote** | **no** |
| **live_go** | **false** |
| **family_id** | `asia_box_london_sweep_fade_flat` |
| **charter v2 (operative)** | `results/xau_charters/2026-08-19_asia_box_london_sweep_fade_flat_v2.json` · SHA `d2f0b7becca0c489aa06275ea37af143e24449d34907c217d6f99877c0d578b4` (v1 `7cf9f46f…` superseded pre-impl by entry_gap_policy amendment; never scored) |
| **screen** | `--strict-charter --screen-only` · develop 25,582 H1 bars · 2021-09-03 → 2025-12-31 · holdout **untouched** |
| **result** | n **670** · PF **0.553** · NP **−8,141.58** · DD **82.12%** · primary passers **0** (classic 0 / soft 0) |
| **disposition** | **SCREEN_FAIL — ZERO_PRIMARY_PASSERS** · terminal · null **skipped** (`p_n_passers=1.0` trivially for any n_null) · `r1_burned=false` (screen-only, nonterminal machinery; deterministic fail) |
| **artifact** | `results/xau_asia_box_london_sweep_fade_flat_null_maxstat.{json,md}` · provenance `tree_clean=true` · main @ `5a1db7c` |
| **falsifier confirmed** | memo falsifier #1 (exact-extreme SL scratches; NP≤0 / PF<1.1) — actual PF 0.553 is decisively past it, incl. every slippage sensitivity (0.553 → 0.290 at 20 pt) |
| **multiplicity** | look consumed · **K_prior=10 for the next family** · dead-lines list gains this family |
| **null / paper / live** | **forbidden** — family closed |
| **do not** | retune hours/SL/TP/occupancy · revive or rename · flip direction on the same events (breakout-continuation of Asia-box sweeps is the `prior_day_high_break`/`early_server_range_break` neighborhood — closed) |

Thesis dead as frozen: Europe fading Asia-box stop-runs has **negative** develop edge after Standard STP costs (PF 0.553, n=670 — not thin-n). The sweep-and-reclaim *event* is real and frequent; the *fade* of it loses. Standing: 10 dead families. Next research needs a genuinely new `family_id` + freeze-before-peek.

---

## 2026-08-19 — Phase E develop screen r1 · `exog_london_fx_cosign_xau_follow_flat` **SCREEN_FAIL**

| Field | Value |
|-------|--------|
| **next_step** | **`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`** |
| **promote** | **no** |
| **live_go** | **false** |
| **family_id** | `exog_london_fx_cosign_xau_follow_flat` |
| **charter v4** | SHA `3dec09efeee0bc11723c93c0e8ed1de683ac6179c176986cd8d4ba53e594edf5` |
| **screen path** | `results/xau_runs/2026-08-18_exog_london_fx_cosign_xau_follow_flat_screen_r1/` · `report.json` SHA `71d762cca55528f2db719baed27ad5853a2d1f375a9e6db1ee8ec8aba5315ad3` |
| **disposition** | **SCREEN_FAIL** · soft_passers **0** · **null_armed=false** · sealed-null **r1_burned=false** (SCREEN_STARTED only; null never armed) |
| **pooled** | n **885** · PF **0.9027** · NP **−2295.10** · DD **26.41%** |
| **xau_cosign_at_tstar** | n **608** · PF **0.8868** · NP **−1842.08** · DD **23.07%** |
| **xau_not_cosign_at_tstar (fresh)** | n **277** · PF **0.9381** · NP **−453.02** · DD **8.49%** — clears n≥20 and DD≤25; fails PF≥1.1 and NP>0 |
| **package** | `4f44b452…-ee2a993fb5b1befd` |
| **runner** | `scripts/xau_exogenous_predictor_screen.py` + synthetic smoke (`tests/test_exogenous_predictor_screen.py`) |
| **null / paper / live** | **forbidden** — null not armed; do not revive this family_id |
| **do not** | retune / lower n_trades_min · sealed null · holdout peek · report pooled-only as passer · reopen this screen r1 |

Standing: stratified gate did its job (fresh n=277). Follow thesis does **not** carry edge on events the closed fade family never covered. Closed freezes stay closed. Next research needs a **genuinely new** `family_id` and freeze-before-peek.

---

## 2026-08-18 — Phase D **merged on main** · module + fixtures green · enforcement live

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_PHASE_E_SCREEN_AUTHORIZATION`** |
| **promote** | **no** |
| **live_go** | **false** |
| **family_id** | `exog_london_fx_cosign_xau_follow_flat` |
| **charter v4 (operative)** | SHA `3dec09efeee0bc11723c93c0e8ed1de683ac6179c176986cd8d4ba53e594edf5` · v1–v3 superseded, never scored, immutable |
| **Phase D** | **MERGED @ `0519e50`** (PR #23): `scripts/xau_family_exog_london_fx_cosign_xau_follow_flat.py` + 36 synthetic fixtures; repointed to v4 (`2a8852e`); thermo-nuclear review → 2 Low findings fixed (`66c799e`, stale DD note + fail-closed spread_col) |
| **Phase B enforcement** | **MERGED @ `615bce5`** (PR #25): validator now structurally enforces `gates.stratified_required`; mandatory when `provenance.derived_from_observed_result` declared; resolver carries the block. 44 tests |
| **suite on main** | 578 passed, 4 skipped · Phase D 36/36 · Phase B 52/52 |
| **r1** | **unburned** — no develop screen run |
| **develop screen / null** | **not executed / not authorized** — Phase E prompt staged, awaiting explicit `AUTHORIZE PHASE E` |
| **paper / live** | **forbidden** |
| **do not** | peek develop / stratum-split metrics before the screen · mutate v1–v4 · lower `n_trades_min` to dodge short fresh stratum · report pooled-only passer · run the sealed null under a Phase E authorization |

Standing: nothing scored. The screen requires the dedicated exogenous runner (does not exist yet — Phase E builds it). Soft thresholds unchanged; K stays 9.

---

## 2026-08-18 — Phase C re-freeze: `exog_london_fx_cosign_xau_follow_flat` **v4** · metric basis

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_PHASE_D_REPOINT_AND_REVIEW`** |
| **promote** | **no** |
| **live_go** | **false** |
| **family_id** | `exog_london_fx_cosign_xau_follow_flat` |
| **charter v4** | `results/xau_charters/2026-08-15_exog_london_fx_cosign_xau_follow_flat_v4.json` · SHA `3dec09efeee0bc11723c93c0e8ed1de683ac6179c176986cd8d4ba53e594edf5` |
| **v3** | SHA `10ab933b…` · **SUPERSEDED** (design only; never scored; immutable) |
| **v2** | SHA `a5661ec3…` · **SUPERSEDED** (design only; never scored; immutable) |
| **v1** | SHA `db7b015a…` · **SUPERSEDED** (design only; never scored; immutable) |
| **amendment** | declaration-only: `gates.stratified_required.metric_basis` (stratum DD = ordered pnl subsequence rebased to start_balance; pooled DD = full MTM; asymmetry + expected bindingness declared; `n_trades_min` applies to fresh stratum own count → SCREEN_FAIL if short) |
| **memo** | `docs/research/MULTI-INSTRUMENT-THESIS-exog_london_fx_cosign_xau_follow_flat_v1.md` (updated to bind v4) |
| **Phase D** | implemented **locally** on `research/exog-london-fx-cosign-xau-follow-module` against **v3** — **must repoint to v4** before opening the Phase D PR |
| **develop screen / null** | **not executed / not authorized** |
| **paper / live** | **forbidden** |
| **do not** | peek develop / stratum-split metrics · mutate v1–v3 · lower `n_trades_min` to dodge short fresh stratum · report pooled-only passer |

Standing: none of v1–v4 scored. K stays 9. `primary_n_passers` stays `"soft"`. Soft thresholds unchanged.

---

## 2026-08-15 — Phase C re-freeze: `exog_london_fx_cosign_xau_follow_flat` **v3** · AWAIT_FREEZE_REVIEW

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_PHASE_C_FREEZE_REVIEW`** |
| **promote** | **no** |
| **live_go** | **false** |
| **family_id** | `exog_london_fx_cosign_xau_follow_flat` |
| **charter v3** | `results/xau_charters/2026-08-15_exog_london_fx_cosign_xau_follow_flat_v3.json` · SHA `10ab933be675af39d3459b75d40792893027188794fa6ded668e73ac4c1cc4eb` |
| **v2** | SHA `a5661ec3…` · **SUPERSEDED** (design only; never scored; immutable) |
| **v1** | SHA `db7b015a…` · **SUPERSEDED** (design only; never scored; immutable) |
| **amendment** | declaration-only: `stratum_definition` (zero→`xau_not_cosign_at_tstar`) · `resolution_order` (pooled AND stratum; stratum fail → SCREEN_FAIL, r1 unburned) · `enforced_by` (family module fail-closed; Phase B cannot express stratified via `primary_n_passers`) |
| **memo** | `docs/research/MULTI-INSTRUMENT-THESIS-exog_london_fx_cosign_xau_follow_flat_v1.md` (updated to bind v3) |
| **harness.kind** | `multi_instrument_exogenous_predictor_v1` |
| **Phase B** | merged PR #11 @ `47ae0e7` (not modified) |
| **develop screen / null / fixtures** | **not executed / not authorized** |
| **paper / live** | **forbidden** (catalog open; provisional PASS only if later AUTHORIZE) |
| **do not** | retune joint cosign · peek develop metrics · sealed null · holdout selection · mutate v1/v2 charter/SHA · **report a pooled-only soft passer** |

Standing: prior `joint_london_open_cosign_fade_flat` v4 **SCREEN_FAIL** remains closed. K stays 9. `primary_n_passers` stays `"soft"`.

---

## 2026-08-15 — Phase C re-freeze: `exog_london_fx_cosign_xau_follow_flat` **v2** · AWAIT_FREEZE_REVIEW

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_PHASE_C_FREEZE_REVIEW`** |
| **promote** | **no** |
| **live_go** | **false** |
| **family_id** | `exog_london_fx_cosign_xau_follow_flat` |
| **charter v2** | `results/xau_charters/2026-08-15_exog_london_fx_cosign_xau_follow_flat_v2.json` · SHA `a5661ec34e457cbb05d999f92251d443fd86c04cf6d9980dcfc31a8c74762174` |
| **v1** | SHA `db7b015a…` · **SUPERSEDED** (design only; never scored; immutable) |
| **amendment** | declaration-only: `provenance` (derived from joint fade v4 SCREEN_FAIL; sign-inversion on overlap) · `gates.stratified_required` (`xau_not_cosign_at_tstar` soft primary) · `rule.atr_reference_bar=T_star` |
| **memo** | `docs/research/MULTI-INSTRUMENT-THESIS-exog_london_fx_cosign_xau_follow_flat_v1.md` (updated to bind v2) |
| **harness.kind** | `multi_instrument_exogenous_predictor_v1` |
| **Phase B** | merged PR #11 @ `47ae0e7` |
| **develop screen / null / fixtures** | **not executed / not authorized** |
| **paper / live** | **forbidden** (catalog open; provisional PASS only if later AUTHORIZE) |
| **do not** | retune joint cosign · peek develop metrics · sealed null · holdout selection · mutate v1 charter/SHA |

Standing: prior `joint_london_open_cosign_fade_flat` v4 **SCREEN_FAIL** remains closed. K stays 9 (reporting stratum ≠ new family).

---

## 2026-08-15 — Phase C freeze: `exog_london_fx_cosign_xau_follow_flat` v1 · AWAIT_FREEZE_REVIEW

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_PHASE_C_FREEZE_REVIEW`** |
| **promote** | **no** |
| **live_go** | **false** |
| **family_id** | `exog_london_fx_cosign_xau_follow_flat` |
| **charter v1** | `results/xau_charters/2026-08-15_exog_london_fx_cosign_xau_follow_flat_v1.json` · SHA `db7b015a…` |
| **memo** | `docs/research/MULTI-INSTRUMENT-THESIS-exog_london_fx_cosign_xau_follow_flat_v1.md` |
| **harness.kind** | `multi_instrument_exogenous_predictor_v1` |
| **Phase B** | merged PR #11 @ `47ae0e7` |
| **develop screen / null / fixtures** | **not executed / not authorized** |
| **paper / live** | **forbidden** (catalog open; provisional PASS only if later AUTHORIZE) |
| **do not** | retune joint cosign · peek develop metrics · sealed null · holdout selection |

Standing: prior `joint_london_open_cosign_fade_flat` v4 **SCREEN_FAIL** remains closed.

---

## 2026-08-14 — `joint_london_open_cosign_fade_flat` v4 **SCREEN_FAIL** · RESEARCH_IDLE

| Field | Value |
|-------|--------|
| **next_step** | **`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`** |
| **promote** | **no** |
| **live_go** | **false** |
| **family_id** | `joint_london_open_cosign_fade_flat` |
| **charter v4** | SHA `e29b2693…` · **SCREEN_FAIL** / `ZERO_PRIMARY_PASSERS` (registry) |
| **screen path** | develop screen-only (multi-instrument joint harness) · artifact `results/xau_runs/2026-08-14_joint_london_open_cosign_fade_flat_screen_r1/` |
| **develop joint** | PF **0.8647** · NP **−10051.47** · n **1821** · DD **42.74%** · WR **42.7%** · primary passers **0** |
| **per-symbol soft** | all fail (n=607 each; PF < 1.1, NP < 0) |
| **null** | planned **999** · executed **0** · `sealed_null_attempt=false` · **r1_burned=false** · p_n_passers implied **1.0** |
| **package** | `4f44b452…-ee2a993fb5b1befd` |
| **code_commit** | `ca8b721…` (screen run) |
| **do not** | retune joint cosign knobs · sealed r1 / null · holdout peek · paper/live · revive this family_id |

Closed freezes remain closed. Next research requires a **genuinely new** `family_id` and freeze-before-peek.

---

## 2026-08-13 — `joint_london_open_cosign_fade_flat` **v4 SCREEN HARNESS** (not executed)

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_SCREEN_HARNESS_RE_REVIEW`** (SCREEN_ONLY parser + early freshness + cost identity) |
| **family_id** | `joint_london_open_cosign_fade_flat` |
| **charter v4** | SHA `e29b2693…` on main |
| **fixtures PR** | #7 merged (`eadd846`) |
| **screen harness** | `scripts/xau_multi_instrument_joint_screen.py` (dry default) |
| **develop screen** | **not executed / not authorized** |
| **null / sealed / paper / live** | **not authorized** |
| **branch** | `research/multi-instrument-joint-london-cosign-flat-v4-screen` |

Dry CLI validates charter + prints plan. `--execute-develop-screen` is gated until harness review AUTHORIZE.

---

## 2026-08-13 — `joint_london_open_cosign_fade_flat` **v4 FIXTURES** · implementation only

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_IMPLEMENTATION_RE_REVIEW`** (empty-joint refuse + clock derivation + true MTM fixture) |
| **family_id** | `joint_london_open_cosign_fade_flat` |
| **charter v4** | SHA `e29b2693…` (immutable; freeze PR #6 merged) |
| **module** | `scripts/xau_family_joint_london_open_cosign_fade_flat.py` |
| **fixtures** | synthetic only (`tests/test_joint_london_open_cosign_fade_flat.py`) |
| **develop screen / null / sealed / paper / live** | **not authorized** |
| **promote / live_go** | **no / false** |
| **branch** | `research/multi-instrument-joint-london-cosign-flat-v4-fixtures` |

Authorized scope: dedicated joint harness + synthetic fixtures. Stop for implementation review.

---

## 2026-08-13 — `joint_london_open_cosign_fade_flat` **v4 FREEZE** · v3 SUPERSEDED · design only

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_CHARTER_REVIEW_V4`** |
| **family_id** | `joint_london_open_cosign_fade_flat` |
| **charter v4** | `results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json` · SHA `e29b2693…` |
| **v3** | SHA `e88161be…` · **SUPERSEDED** (immutable; impossible “approval of v2” rule) |
| **v2 / v1** | SUPERSEDED (immutable) |
| **authorization** | fixtures/implement only after approval of **this** charter version (v4) |
| **gates protocol** | complete joint soft (incl. max DD); joint_soft_is_primary exact true; full per-symbol soft; non-bool PF pins |
| **package** | `4f44b452…-ee2a993fb5b1befd` pinned |
| **free knobs** | **0** |
| **develop metrics** | **not inspected** |
| **fixtures / screen / null / paper / live** | **not authorized** |
| **promote / live_go** | **no / false** |

v4 closes BLOCK findings: impossible v2 auth, residual gate fail-open, memo/note cleanup.

---

## 2026-08-13 — `joint_london_open_cosign_fade_flat` **v3 FREEZE** · v2 SUPERSEDED · design only

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_CHARTER_REVIEW_V3`** |
| **family_id** | `joint_london_open_cosign_fade_flat` |
| **charter v3** | `results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v3.json` · SHA `e88161be…` |
| **v2** | SHA `935534e2…` · **SUPERSEDED** (immutable; registry append only) |
| **v1** | SHA `2d3fda48…` · **SUPERSEDED** (immutable) |
| **package** | `4f44b452…-ee2a993fb5b1befd` pinned |
| **sizing** | USD; raw_lots = risk_cash / (SL_price_dist * contract_size); floor step; cap max; never force min; all-or-none basket |
| **PF zero-denom** | 0 no trades / 99 all winners (house) |
| **runners** | single-frame null_maxstat + sealed cycle **REFUSE** multi_instrument_joint_v1 |
| **calendar** | **intersection_only** (real + null) |
| **harness** | `multi_instrument_joint_v1` (single-frame prohibited) |
| **gates** | complete joint-soft contract enforced in protocol |
| **free knobs** | **0** |
| **develop metrics** | **not inspected** |
| **fixtures / screen / null / paper / live** | **not authorized** |
| **promote / live_go** | **no / false** |

v3 closes BLOCK findings: sizing/all-or-none, runner refuse, multi gate fail-closed, PF zero-denom.

---

## 2026-08-13 — `joint_london_open_cosign_fade_flat` **v2 FREEZE** · v1 SUPERSEDED · design only

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_CHARTER_REVIEW_V2`** |
| **family_id** | `joint_london_open_cosign_fade_flat` |
| **charter v2** | `results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v2.json` · SHA `935534e2…` |
| **v1** | SHA `2d3fda48…` · **SUPERSEDED** (immutable; registry append only) |
| **package** | `4f44b452…-ee2a993fb5b1befd` pinned |
| **calendar** | **intersection_only** (real + null) |
| **harness** | `multi_instrument_joint_v1` (single-frame prohibited) |
| **gates** | top-level joint soft primary; per-symbol soft under multi_instrument |
| **free knobs** | **0** |
| **develop metrics** | **not inspected** |
| **fixtures / screen / null / paper / live** | **not authorized** |
| **promote / live_go** | **no / false** |

v2 closes BLOCK findings: nested gates, unequal calendars, execution/cost pins, joint stats, shared-k.

---

## 2026-08-13 — MULTI-INSTRUMENT thesis freeze **DESIGN ONLY** · `joint_london_open_cosign_fade_flat` v1

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_CHARTER_REVIEW`** — design freeze only; no implementation |
| **family_id** | `joint_london_open_cosign_fade_flat` |
| **charter** | `results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v1.json` · SHA `2d3fda48…` |
| **thesis_memo** | `docs/research/MULTI-INSTRUMENT-THESIS-joint_london_open_cosign_fade_flat_v1.md` |
| **data package** | `4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd` (pinned) |
| **symbols** | XAUUSD + EURUSD + GBPUSD (joint cosign required) |
| **free knobs** | **0** (cardinality 1) |
| **develop metrics** | **not inspected** |
| **fixtures / screen / null / paper / live** | **not authorized** |
| **promote / live_go / PAPER_GO** | **no / false / no** |
| **do not** | implement family · peek develop grid · open sealed r1 · revive dead lines |

Phase 0 data readiness remains closed on main. Next: adversarial charter review only.

---

## 2026-08-11 — day_open_reclaim_flat v2 **SCREEN_FAIL** · RESEARCH_IDLE

| Field | Value |
|-------|--------|
| **next_step** | **`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`** |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | **no** |
| **family_id** | `day_open_reclaim_flat` |
| **charter** | `results/xau_charters/2026-08-11_day_open_reclaim_flat_v2.json` · SHA `961dd3d4…` |
| **disposition** | **SCREEN_FAIL** / `ZERO_PRIMARY_PASSERS` (registry) |
| **screen path** | `--strict-charter --screen-only` · artifact `results/xau_runs/2026-08-11_day_open_reclaim_flat_screen/` |
| **develop best (n≥20)** | PF **1.0348** · NP **+1251.52** · n **835** · DD **31.08%** · WR **47.3%** · primary passers **0** |
| **soft gate miss** | PF 1.0348 < 1.1 (NP>0 and n≥20 hold) |
| **null** | planned **999** · executed **0** · `sealed_null_attempt=false` · **r1_burned=false** |
| **v1** | SHA `8eafe48b…` · **SUPERSEDED** (left immutable) |
| **do not** | retune day_open knobs · sealed r1 · paper/live · revive dead lines |

Closed freezes remain closed. Next research requires a **new** `family_id` and freeze-before-peek.

---

## 2026-08-11 — IMPLEMENT FIXTURES · `day_open_reclaim_flat` v2 (no develop screen)

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_REVIEW_THEN_DEVELOP_SCREEN`** (`--strict-charter --screen-only` only if authorized) |
| **family** | `scripts/xau_family_day_open_reclaim_flat.py` |
| **charter** | v2 SHA `961dd3d4…` · runnable |
| **fixtures** | same_bar reject · prior_bar accept · two-trade sizing · entry/exit equity cost timing |
| **develop metrics** | **not inspected** |
| **null / sealed r1 / paper / live** | **not authorized** |
| **promote / live_go / PAPER_GO** | **no / false / no** |

---

## 2026-08-11 — SHA GRANDFATHER (no frozen_at spoof) · v2 immutable

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_FREEZE_REVIEW`** then implement fixtures only |
| **charter** | v2 SHA `961dd3d4…` **unchanged** (no v3) |
| **protocol** | seed/protocol exemptions only for exact `GRANDFATHERED_NO_SEED_CHARTER_SHA256` file bytes; self-declared `frozen_at` cannot grandfather |
| **grandfather** | known historical file SHAs only (incl. 2026-08-10 freezes + day_open v1); mutations lose exemption |
| **implement / develop / null / live** | **not authorized** |
| **promote / live_go / PAPER_GO** | **no / false / no** |

---

## 2026-08-11 — PROTOCOL SEED CUTOVER FAIL-CLOSED (v2 immutable)

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_FREEZE_REVIEW`** then implement fixtures only |
| **charter** | v2 SHA `961dd3d4…` **unchanged** (no v3) |
| **protocol** | `frozen_at` required+parseable; seed cutover by freeze date only (not protocol_version); post-cutover protocol <2.2 rejected |
| **grandfather** | exact historical charter file SHAs only (not self-declared dates) |
| **implement / develop / null / live** | **not authorized** |
| **promote / live_go / PAPER_GO** | **no / false / no** |

---

## 2026-08-11 — PROTOCOL SEED-PROOF CORRECTION (v2 charter immutable)

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_FREEZE_REVIEW`** (re-review seed-proof) then implement fixtures |
| **charter** | v2 SHA `961dd3d4…` **unchanged** (no v3) |
| **protocol** | freeze-date cutover for `null.base_seed`; strict `type is int` and `>=0`; sealed parser requires exact seed match on OK; never invent seed 0 |
| **develop / implement** | **not authorized** |
| **promote / live_go / PAPER_GO** | **no / false / no** |

---

## 2026-08-11 — FREEZE CORRECTION · `day_open_reclaim_flat` **v2** (v1 SUPERSEDED)

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_FREEZE_REVIEW`** then implement fixtures only |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | **no** |
| **family_id** | `day_open_reclaim_flat` |
| **charter** | `results/xau_charters/2026-08-11_day_open_reclaim_flat_v2.json` · SHA `961dd3d4…` |
| **v1** | SHA `8eafe48b…` · registry **SUPERSEDED** (byte-immutable) |
| **corrections** | undercut_seen_before_i (j<i); capital start_balance=10000 + cost-at-exit-booking; null.base_seed=20260808 |
| **n_free_knobs** | **0** · null `within_day_ohlc_increment_rotate_v1` · planned **999** · seed **20260808** |
| **kill** | `KILL_DAY_OPEN_RECLAIM_FLAT` |
| **primary** | soft |
| **develop metrics** | **not inspected** (freeze-before-peek) |
| **implement / sealed r1** | **not authorized** until freeze review |
| **branch** | `research/xau-day-open-reclaim-flat-v1` from `main` @ `f4e891f` |
| **scope** | charter/protocol/tests only — no family module, no develop screen |

Closed freezes remain closed (early_server_range_break, server_hour, TOD, prior_day, Donchian, bb_rsi).

---

## 2026-08-11 — NEW THESIS FREEZE · `day_open_reclaim_flat` v1 (no implement / no develop peek)

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_FREEZE_REVIEW`** then implement fixtures only |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | **no** |
| **new family_id** | `day_open_reclaim_flat` |
| **thesis memo** | `docs/research/XAU-THESIS-day_open_reclaim_flat_v1.md` |
| **charter** | `results/xau_charters/2026-08-11_day_open_reclaim_flat_v1.json` |
| **n_free_knobs** | **0** · null `within_day_ohlc_increment_rotate_v1` · planned **999** |
| **kill** | `KILL_DAY_OPEN_RECLAIM_FLAT` |
| **primary** | soft |
| **execution_contract** | Wilder ATR14; close entry; next-bar exits; SL≻TP≻flat; 0.01 lot; no overnight |
| **develop metrics** | **not inspected** (freeze-before-peek) |
| **implement / sealed r1** | **not authorized** until freeze review |
| **branch** | `research/xau-day-open-reclaim-flat-v1` from `main` @ `f4e891f` |

Closed freezes remain closed (early_server_range_break, server_hour, TOD, prior_day, Donchian, bb_rsi).

---

## 2026-08-11 — early_server_range_break_flat v2 **SCREEN_FAIL** · RESEARCH_IDLE

| Field | Value |
|-------|--------|
| **next_step** | **`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`** |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | **no** |
| **family_id** | `early_server_range_break_flat` |
| **charter** | `results/xau_charters/2026-08-10_early_server_range_break_flat_v2.json` · SHA `11099b2a…` |
| **disposition** | **SCREEN_FAIL** / `ZERO_PRIMARY_PASSERS` (registry) |
| **screen path** | `--strict-charter --screen-only` · artifact `results/xau_runs/2026-08-11_early_server_range_break_flat_screen/` |
| **develop best (n≥20)** | PF **0.7829** · NP **−4054.46** · n **542** · DD **47.88%** · WR **41.5%** · primary passers **0** |
| **null** | planned **999** · executed **0** · `sealed_null_attempt=false` · **r1_burned=false** |
| **v1** | SHA `fee8611c…` · **SUPERSEDED** (left immutable) |
| **do not** | retune early-range knobs · sealed r1 · paper/live · revive dead lines |

Closed freezes remain closed. Next research requires a **new** `family_id` and freeze-before-peek.

---

## 2026-08-10 — NEW THESIS FREEZE · `early_server_range_break_flat` **v2** (superseded by screen close above)

| Field | Value |
|-------|--------|
| **next_step** | was `IMPLEMENT_FIXTURES_THEN_DEVELOP_SCREEN` — closed SCREEN_FAIL 2026-08-11 |
| **charter** | `…_early_server_range_break_flat_v2.json` · SHA `11099b2a…` |
| **v1** | SHA `fee8611c…` · registry **SUPERSEDED** |
| **branch** | `research/xau-early-server-range-break-v1` from `main` @ PR#1 merge |

Closed freezes remain closed. Do not revive bb_rsi / Donchian / prior_day / TOD / server_hour.

---

## 2026-08-10 — server_hour v2 SCREEN_FAIL · RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS

| Field | Value |
|-------|--------|
| **next_step** | **`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`** (superseded by early_server_range_break freeze above) |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | **no** |
| **v2 charter** | SHA `26ff7532…` · registry **SCREEN_FAIL** / `ZERO_PRIMARY_PASSERS` |
| **real grid (develop)** | PF **0.8511** · NP **−5052.80** · DD **58.54%** · n **1114** · primary passers **0** |
| **p_n_passers_implied** | **1.0** (arithmetic; nulls not needed) |
| **r1_burned** | **false** |
| **protocol rule** | Real primary passers == 0 → **SCREEN_FAIL without null trials** |
| **next family** | New `family_id` only; freeze before grid peek; null only if ≥1 primary passer |

Do not run: r1, walk-forward, holdout eval, retune, paper, live on closed freezes.

---

## 2026-08-10 — protocol v2.2.1 preregistration + enforcement (still no r1)

| Field | Value |
|-------|--------|
| **v1 server_hour charter** | Registry **SUPERSEDED** (SHA `6b5811ee…`) — preregistered close-return algorithm ≠ v2.2 runtime |
| **v2 freeze** | `results/xau_charters/2026-08-10_server_hour_window_flat_v2.json` · method **`within_day_ohlc_increment_rotate_v1`** · full algorithm + k-domain + OHLC invariants |
| **session null policy** | Canonical method required; `forbidden_methods` enforced; noncanonical rejected |
| **registry integrity** | Malformed JSONL → fail closed; terminal dispositions monotonic |
| **dirty tree** | Sealed / strict-charter refuse dirty tracked protocol/family/cost files |
| **r1** | **not burned** |
| **next** | External review of v2 freeze, then optional sealed r1 on **v2 only** |
| **promote / live_go** | no / false |

---

## 2026-08-10 — protocol v2.2 correction (still do not burn r1)

Review of v2.1 found OHLC-inconsistent within-day null and forced non-identity k.

| Field | Value |
|-------|--------|
| **null v2.2** | Rotate **complete normalized OHLC increments**; k∈{0..m−1} **includes identity**; open/prev and TR/ref multisets preserved; develop gap bp no longer inflated |
| **TOD v1 freeze** | Restored **byte-for-byte** (SHA `e7cd953f…`); invalidation **only** in `results/xau_charter_disposition_registry.jsonl` |
| **strict paths** | `--charter` runs `validate_charter` + registry runnable check; costs keys must exist on both sides |
| **r1** | **not burned** |
| **next** | Re-review then optional sealed `server_hour_window_flat` |
| **promote / live_go** | no / false |

---

## 2026-08-10 — protocol v2.1 correction wave (do not burn r1)

Review blocked Phase 0 on four points; correction shipped without running sealed r1.

| Field | Value |
|-------|--------|
| **TOD v1** | `PROTOCOL_NULL_INVALID` / exploratory `SCREEN_FAIL` — see `results/xau_tod_v1_disposition.md`. **r1 not burned.** |
| **Null fix** | New method `within_day_return_rotate` (per-day return rotation + price rebase). `day_block_shuffle` marked session-invalid. |
| **Clock** | No London–NY claim; superseding family is **server-hour labels only**. |
| **Strict charter** | Family id / null method / n_trials / costs equality; sealed cycle blocks fixture skips. Slip sensitivity rows generated in report. |
| **Superseding freeze** | `results/xau_charters/2026-08-10_server_hour_window_flat_v1.json` + `scripts/xau_family_server_hour_window_flat.py` |
| **PR #1 honesty** | Protocol commits landed on the same branch as draft PR #1 head — **scope expanded**; review as such (not a clean research-only PR). |
| **next_step** | Optional sealed run of `server_hour_window_flat` when ready (still not automatic). promote=no / live_go=false. |

---

## 2026-08-10 — protocol v2 Phase 0 (harden + freeze TOD charter)

Owner-required protocol hardening **before** any next sealed thesis run.

| Field | Value |
|-------|--------|
| **charters** | Immutable under `results/xau_charters/YYYY-MM-DD_<family>_vN.json` (refuse overwrite). Legacy `xau_next_design_charter.json` (`prior_day_high_break`) **not** overwritten. |
| **gates** | From frozen charter when `--charter` passed (fixes prior soft-gate provenance mismatch). |
| **n_null floor** | ≥**199** (prefer **999** for 0–1 knobs); charter freezes count. |
| **null methods** | `global_return_shuffle` \| `day_block_shuffle` \| `circular_day_shift` + invariants. |
| **costs wording** | Account-matched spread+commission only; **slip unmeasured**, **swap unmodeled** → intraday-flat required (v2). |
| **sealed cycle** | `scripts/xau_sealed_family_cycle.py` + attempt ledger `results/xau_family_attempts.jsonl` |
| **next frozen family** | **`tod_london_ny_flat`** zero-knob session thesis — charter only, **sealed run not yet executed** |
| **candidates** | Multi-instrument **deferred**; EMA/H4 pullback **removed** (dead htf_pullback overlap) |
| **PR #1** | **Do not expand scope** until current draft is reviewed |
| **next_step** | Run sealed cycle for TOD when ready: `python3 scripts/xau_sealed_family_cycle.py --charter results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json --family tod_london_ny_flat --run-id r1` |
| **promote / live_go** | **no / false** |

Docs: `docs/research/XAU-FAMILY-PROTOCOL-V2.md`.

---

## 2026-08-10 — cost model matched to live Standard STP

Live account confirmed: **MT5 27496181 · Standard STP · 500:1 · VantageMarkets-Live 5**.

| Field | Value |
|-------|--------|
| **commission** | **$0** (Standard STP — no ticket commission) |
| **spread** | measured from this terminal (H1 median 18 pts) |
| **research default** | `results/xau_research_costs.json` → `commission_per_lot=0`, `account_type=STANDARD_STP` |
| **RAW $3 / PRO $1.50** | stress alternatives only (other account types), not this login |
| **correction** | 2026-08-08 resume-edge had defaulted to RAW $3 before account type was known — **over-costed** relative to 27496181 |
| **strategy disposition** | unchanged: dead families stay dead; `RESEARCH_IDLE_PENDING_NEW_THESIS` |
| **promote / live_go** | **no / false** |

Null kills already run under commission 0 or 3 still stand as process outcomes; any *new* family search should use Standard STP costs (spread + commission 0). Re-running old nulls under RAW was a conservative stress, not live-matched.

---

## 2026-08-08 — resume-edge: RAW $3 costs + prior_day_high_break null KILL

Consolidated status after the **xau-resume-edge** fire (Vantage commission bake-in →
next-design charter → family null scaffold → first low-knob family → full null).

| Field | Value |
|-------|--------|
| **cost update** | Vantage research default **RAW ECN $3.00 / side / lot** (`commission_per_lot=3.0`); PRO $1.50 sensitivity only. Source: `results/xau_research_costs.json`. RT commission = `2 * 3.0 * lots` ($0.06 @ 0.01 lot, $6 @ 1.0 lot) + measured H1 spread. Slippage still 0. |
| **next design family** | **`prior_day_high_break`** (charter-frozen; 1 free knob `sl_atr` ∈ {1.0, 1.5, 2.0}; cardinality **3**) |
| **null disposition** | **`KILL_PRIOR_DAY_HIGH_BREAK`** — p_max_pf **0.463** · p_n_passers **1.000** · real max PF (n≥20) **1.077** · soft passers **0** (null can match/beat) |
| **live_go** | **false** |
| **promote** | **no** |
| **PAPER_GO** | **no** |
| **next_step** | **`RESEARCH_IDLE_PENDING_NEW_THESIS`** — null **KILL** (not PASS). Do **not** run costed walk-forward for this family. Do **not** retune knobs / free hours / frictionless rescue. A new family requires a **new charter freeze** (`NEXT_FAMILY` only after that freeze). |

Dead lines (do not revive): `bb_rsi`, `Donchian`/`turtle`, `prior_day_high_break`.

Key artifacts: `results/xau_research_costs.json`, `results/xau_cost_update_vantage.md`,
`results/xau_next_design_charter.{json,md}`, `scripts/xau_null_core.py`,
`scripts/xau_family_null_maxstat.py`, `scripts/xau_family_prior_day_high_break.py`,
`results/xau_prior_day_high_break_null_maxstat.{json,md}`,
`results/xau_prior_day_high_break_null_skeptic.md`,
`.grok/workflows/xau-resume-edge.rhai`.

---

## 2026-08-08 — prior_day_high_break null / max-stat (charter family KILL)

After `KILL_BB_RSI_LINE` and `KILL_DONCHIAN_LINE`, the frozen next-design charter
(`results/xau_next_design_charter.json`) pre-registered `prior_day_high_break`
(3-config grid: `sl_atr` ∈ {1.0, 1.5, 2.0}). Develop grid was scored under RAW
costs; then `scripts/xau_family_null_maxstat.py --family prior_day_high_break`
ran the full null max-stat protocol (no early exit).

| Field | Value |
|-------|--------|
| **window** | develop only, 25582 H1 bars (`time < 2026-01-01`), holdout sealed |
| **costs** | spread_col=spread, point_size=0.01, commission_per_lot=**3.0** (RAW ECN), slippage=0 |
| **grid** | **3** configs (charter search_cardinality; full enumerate) |
| **real max PF (n≥20)** | **1.0773** · n_passers_soft **0** · n_passers_classic **0** |
| **null (40 trials)** | max PF p50 **≈1.05** · null max **1.31** · n_passers_soft p50 **0** (null max soft passers **2**) |
| **p(null ≥ real)** | p_max_pf **0.463** · p_n_passers **1.000** · p_n_passers_classic **1.000** |
| **disposition** | **KILL_PRIOR_DAY_HIGH_BREAK** |
| **live_go** | **false** |
| **promote** | **no** |
| **PAPER_GO** | **no** |
| **next_step** | **RESEARCH_IDLE** — do **not** retune, widen knobs, free hours/tp_rr, or re-run frictionless |

KILL is a valid success of the scientific process under the charter kill rules.
Real best-of-grid (PF≈1.08, zero soft passers under PF≥1.2 / n≥20 / NP>0) sits
inside the return-shuffle null; null paths reach max PF **1.31** and up to **2**
soft passers. Do **not** launder KILL into walk-forward or PASS_KEEP_FROZEN.
A new family requires a **new** charter freeze (new family_id).

Artifacts: `results/xau_prior_day_high_break_null_maxstat.json`,
`results/xau_prior_day_high_break_null_maxstat.md`,
`results/xau_prior_day_high_break_null_skeptic.md`,
`results/xau_prior_day_high_break_develop_grid.json`,
`scripts/xau_family_null_maxstat.py`, `scripts/xau_family_prior_day_high_break.py`,
`results/xau_next_design_charter.json`.

---

## 2026-08-08 — Charter Option B adopted

**Charter:** Option B (explicit dual-layer) adopted — see [`docs/CHARTER-RESEARCH-LAYER.md`](../docs/CHARTER-RESEARCH-LAYER.md) and [`results/xau_charter_adopted.md`](xau_charter_adopted.md).

Strategy disposition is **unchanged** by charter adoption:

| Field | Value |
|-------|--------|
| **next_step** | **RESEARCH_IDLE** |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | **no** |

Merge under dual-layer boundaries ≠ promote. No live orders without explicit consent.

---

## 2026-08-08 — Donchian null / max-stat (decisive for turtle / Donchian family)

After costed multi-year left Donchian as the only sign-stable lane under spread,
`scripts/xau_donchian_null_maxstat.py` scored the full ~1201-config Donchian grid
(no early exit) on develop bars with saved costs, then re-ran the same search on
40 return-shuffled price paths.

| Field | Value |
|-------|--------|
| **window** | develop only, 25582 H1 bars (`time < 2026-01-01`), holdout sealed |
| **costs** | measured spread; commission/slippage still 0 |
| **grid** | 1201 configs (max_n=1200, seed=42, frozen_prepended=2) |
| **real max PF (n≥20)** | 1.9955 · n_passers_soft **19** · n_passers_classic 1 |
| **null (40 trials)** | max PF p50 **≈1.53** · null max **3.19** · n_passers_soft p50 **0** (null can put up to 308) |
| **p(null ≥ real)** | p_max_pf **0.195** · p_n_passers **0.293** · p_n_passers_classic **0.341** |
| **disposition** | **KILL_DONCHIAN_LINE** |
| **live_go** | **false** |
| **promote** | **no** |
| **PAPER_GO** | **no** |
| **next_step** | **RESEARCH_IDLE** (strategy-edge); virgin-only `WAIT_DATA` for process hygiene — not permission to mine Donchian on virgin |

The gates measured the search, not the market. Do **not** retune Donchian/turtle
champions, do not cross-instrument this family, do not promote, do not launder
KILL into PASS_KEEP_FROZEN. bb_rsi already dead; Donchian now dead. No remaining
interesting strategy lane from the frozen catalog for further edge research.

Artifacts: `results/xau_donchian_null_maxstat.json`, `results/xau_donchian_null_maxstat.md`,
`results/xau_donchian_null_skeptic.md`, `scripts/xau_donchian_null_maxstat.py`,
`.grok/workflows/xau-donchian-null-maxstat.rhai`.

---

## 2026-08-08 — costed frozen multi-year after bb_rsi kill

After `KILL_BB_RSI_LINE`, lane sims were wired to charge the same round-trip costs as
`backtest.simulate`, then the frozen 8×9 multi-year matrix was re-scored (no retune).

| Field | Value |
|-------|--------|
| **fire** | costed frozen multi-year (wire costs → EVAL → SKEPTIC) |
| **context** | bb_rsi null-killed; prior multi-year was frictionless / unfalsifiable |
| **costs** | `spread_col=spread`, `point_size=0.01`, `commission_per_lot=0`, `slippage_points=0` (measured H1 median ~18 pts / ~$0.18 RT; commission/slip still unmeasured) |
| **catalog** | 8 frozen configs × 9 windows = 72 cells; params from `xau_frozen_champions_catalog.json` only |
| **hard_pass** | classic **2/72** (was 3/72 frictionless); soft expectancy **13/72** (unchanged count) |
| **lost under costs** | vol_gate 2023 classic hard_pass (PF 1.51→1.384); pullback 2023 **sign flip**; vol_gate `develop_like` **dies** (PF<1 / NP−) |
| **sign-stable 2023–2025 under spread** | **Donchian only** (baseline + refined exit_N8); ATR still collapses 2023; fib thin-n / peek weak |
| **disposition** | **RESEARCH_ONLY** |
| **live_go** | **false** |
| **promote** | **no** |
| **PAPER_GO** | **no** |
| **next_step** | **Donchian null / max-stat** (spread-costed, develop-only, mirror bb_rsi null protocol). Fail → KILL_DONCHIAN_LINE / RESEARCH_IDLE; pass → keep frozen for virgin-only future eval (still promote=no until sealed virgin hard_pass). |

Do **not** revive bb_rsi, re-mine 2026_to_peek, re-label IS years as OOS, or promote from this matrix.
Costs reduced gate hits; they did not create independence.

### Artifacts this fire

| Path | Role |
|------|------|
| `results/xau_post_kill_plan.md` | Wire + re-eval plan |
| `results/xau_frozen_multi_year_eval.json` | Costed cells + meta.costs |
| `results/xau_frozen_multi_year_matrix.csv` | Compact costed matrix |
| `results/xau_frozen_multi_year_costed_skeptic.md` | Hostile skeptic → promote=no; next Donchian null |
| `results/xau_post_kill_summary.md` | Executive summary (kill + costed re-eval + next) |
| `results/xau_loop_status.md` | This note |

Code (left uncommitted for parent): `scripts/xau_lane_deep_opt.py`, `scripts/xau_frozen_multi_year_eval.py` (+ eval json/csv).

---

## 2026-08-08 — null / max-stat test (decisive for bb_rsi family)

After measured costs flipped walk-forward negative, the remaining question was
whether the develop-window gate-passers were market signal or search artifacts.
`scripts/xau_null_maxstat.py` scored the full ~1205-config grid (no early exit)
on develop bars with saved costs, then re-ran the same search on 40
return-shuffled price paths.

| Field | Value |
|-------|--------|
| **window** | develop only, 25582 H1 bars (`time < 2026-01-01`), holdout sealed |
| **costs** | measured spread; commission/slippage still 0 |
| **grid** | 1205 configs (max_n=1200, seed=42 + 5 seeds) |
| **real max PF (n≥20)** | 2.242 · n_passers **19** · early-exit eligible 10 |
| **baseline replay** | PF 1.6713 · n=42 (still clears gates alone) |
| **null (40 trials)** | max PF p50 **≈3.0** · n_passers p50 **≈22** (often *more* passers than real) |
| **p(null ≥ real)** | p_max_pf **0.854** · p_n_passers **0.707** |
| **disposition** | **KILL_BB_RSI_LINE** |
| **live_go** | **false** |
| **promote** | **no** |

The gates measured the search, not the market. Do **not** tune `bb_rsi` further,
do not cross-instrument this family, do not promote. Artifacts:
`results/xau_null_maxstat.json`, `results/xau_null_maxstat.md`.

Commission figure from Vantage is still useful as cost floor for *other* lanes
(e.g. re-costed Donchian), not for rescuing this one.

---

## 2026-08-08 — transaction costs added (out of band, not a research fire)

The backtest was frictionless. `MqlRates.spread` was always available and the old
`Scripts/ExportXauHistory.mq5` discarded it; `Mt5ArchBridge.mq5` v1.21 now dumps it.

| Field | Value |
|-------|--------|
| **source** | Vantage live terminal (27496181), one-shot bridge dump, 129133 rows |
| **spread** | XAUUSD H1 median **18 pts = $0.18** round trip · p90 $0.21 · max $0.50 |
| **zero-spread bars** | H1 4.4% / M15 2.0% — broker backfill gaps, filled with the median (0 would read as free trading) |
| **data** | H1 29133 bars 2021-09-03 → 2026-08-07 (was 29151, re-exported) |
| **baseline** | same params; PF **1.7456 → 1.6713**, net $1299 → $1188, n=42 (develop only) |
| **walk-forward** | retrained OOS **flips negative**: NP +122 → **−282**, meanPF 1.318 → **0.790**, pass_rate 0% |
| **commission/slippage** | **not measured** — MT5 exposes them only on executed deals. Left at 0; see sensitivity |
| **live_go** | **false** (unchanged) |
| **promote** | **no** (unchanged) |

Sensitivity on the develop-window baseline (measured spread already charged):

| Scenario | PF | Net |
|---|---|---|
| frictionless | 1.7456 | $1299 |
| measured spread only | 1.6713 | $1188 |
| + $3/lot | 1.6372 | $1139 |
| + $3/lot + 10pt slip | 1.5548 | $1006 |
| + $5/lot + 20pt slip | **1.4264** | $795 — below gate |

The baseline survives measured spread; it does not survive spread + $5/lot + 20pt.
Commission for this account still needs the broker contract spec.

---

## 2026-08-06 — baseline protocol correction (out of band, not a research fire)

`strategy_params.json` was re-fitted because its recorded metrics no longer reproduced
(claimed PF 1.7256 / 50 trades; replayed PF 1.378 / 124 trades on the shipped CSV — the
params predated a CSV extension and carried no fit window).

| Field | Value |
|-------|--------|
| **cause** | params file recorded no fit window; CSV grew underneath it |
| **first refit** | unbounded (2021-09-01 → 2026-08-06) — **violated** `holdout_rule`, discarded |
| **shipped refit** | selection window `time < 2026-01-01` (25626 H1 bars); holdout sealed |
| **baseline now** | PF 1.7456 · WR 59.52 · DD 3.81 · n=42 (develop only, in-sample) |
| **guard** | `backtest.py` bounds selection at `holdout_start` from `xau_holdout_lock.json`; `--unbounded` warns |
| **downstream** | `xau_regime_analysis` / `xau_walkforward` / `xau_train_only_retrain` re-run against the corrected baseline |
| **live_go** | **false** (unchanged) |
| **promote** | **no** (unchanged) — baseline OOS samples are tiny: 12–13 trades, 3 long signals in 2026 |

2026 was already labeled `2026_to_peek` (peeked, diagnostic only) before this correction, so
the re-runs consume no fresh holdout. The sealed virgin path is unchanged and still WAIT_DATA.

---

| Field | Value |
|-------|--------|
| **timestamp_utc** | 2026-08-06 (multi-year fire) |
| **fire** | frozen multi-year matrix (DATA → EVAL → SKEPTIC → SUMMARY) |
| **action_taken** | Evaluated 8 frozen catalog configs on 9 windows (72 cells); no retune; skeptic **promote=no** |
| **coverage** | 2023:5894 · 2024:5935 · 2025:5911 · 2026:3525 H1 bars (`has_2023=true`) |
| **eval** | years 2023/2024/2025/2026_to_peek + develop_like/full/halves; **hard_pass 3/72** |
| **stability** | Donchian sign-stable (+NP/PF>1) across years incl. pre-sample 2023; atr_trail collapses 2023 |
| **window labels** | 2024–25 largely **IS**; 2026_to_peek **peeked** (diagnostic only); 2023 pre-sample stress |
| **live_go** | **false** |
| **stop_reason** | **RESEARCH_ONLY** — multi-year autopsy complete; promote=no; virgin frontier still WAIT_DATA |
| **next_step** | Idle on virgin: when `n_virgin_bars ≥ 24` after last peek, single sealed virgin eval of frozen 8 only (no retune). Do **not** re-mine 2026_to_peek or re-label IS years as OOS. Never `--live` unless skeptic LIVE_GO. |

## Phase checklist this fire

| Phase | Ran | Note |
|-------|:---:|------|
| DATA | true | 2023:5894 2024:5935 2025:5911 2026:3525 |
| EVAL | true | years available: 2023,2024,2025,2026_to_peek (+ develop_like, full, h2_2024, h1_2025, h2_2025); hard_pass cells: 3/72 |
| SKEPTIC | true | Donchian sign-stable; atr_trail collapses 2023; 2024–25 IS + 2026 peeked — promote=no |
| SUMMARY | true | `results/xau_frozen_multi_year_summary.md` |

## Artifacts written / updated this fire

| Path | Role |
|------|------|
| `results/xau_history_coverage.json` | Bars/year coverage |
| `results/xau_frozen_multi_year_eval.json` | Full cell metrics |
| `results/xau_frozen_multi_year_matrix.csv` | Compact matrix |
| `results/xau_frozen_multi_year_skeptic.md` | Hostile skeptic → promote=no |
| `results/xau_frozen_multi_year_summary.md` | Human summary + per-lane×year tables |
| `results/xau_loop_status.md` | This note |

## Prior context (unchanged)

- Catalog: 8 frozen configs (baseline + refined_develop)
- Virgin frontier still insufficient (`n_virgin_bars=2` at last virgin fire) → WAIT_DATA for sealed promote path
- Develop program priorities exhausted; PARK vol_gate / htf_pullback; KILL=0

## Safety checklist

- No `--live`, no orders
- No paper/live GO from this fire
- Multi-year matrix is diagnostic only — IS and peeked windows not re-labeled as independent OOS
- Prefer PAPER_GO ≫ LIVE_GO on any future virgin hard_pass

## Stop-condition check

1. Live GO virgin hard_pass → **false**
2. Multi-year offline autopsy complete → **true** (this fire)
3. Waiting on virgin future data → **still true** (promote path unchanged)
4. Task expired → false

**Disposition this fire:** **RESEARCH_ONLY / promote=no** (Donchian multi-year sign-stable including 2023; ATR collapses 2023; no PAPER_GO/LIVE_GO; never `--live`)
