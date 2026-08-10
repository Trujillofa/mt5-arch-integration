# XAU family research protocol v2.2 (enforcement complete)

**Date:** 2026-08-10  
**Status:** active  
**PR #1:** Draft head includes protocol work — **scope expanded** (v2 / v2.1 / v2.2). Not a clean research-only PR.

## Standing loop disposition

**`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`** · promote=no · live_go=false · r1 unburned

## Freezes (registry)

| Charter | Status |
|---------|--------|
| `…/server_hour_window_flat_v2.json` | **SCREEN_FAIL** ZERO_PRIMARY_PASSERS (SHA `26ff7532…`) — r1 not burned |
| `…/server_hour_window_flat_v1.json` | **SUPERSEDED** (SHA `6b5811ee…`) |
| `…/tod_london_ny_flat_v1.json` | **PROTOCOL_NULL_INVALID** (SHA `e7cd953f…`) |

## Screen-fail rule (deterministic)

> If the real develop grid has **zero primary passers**, terminate as **`SCREEN_FAIL`**
> **without null trials**. Correct p-value logic: every null trial has
> `n_passers ≥ 0 = real`, so `hits = n_null` and
> `p_n_passers = (n_null+1)/(n_null+1) = 1.0`. **`p_max_pf` is not_evaluated**
> (not reported as 1.0). Accounting fields:
> `n_null_planned`, `n_null_executed=0`, `attempt_type=DETERMINISTIC_SCREEN`,
> `family_screen_attempt=true`, `sealed_null_attempt=false`, `r1_burned=false`.

Only a **valid** `DETERMINISTIC_SCREEN` report with full proof fields may set
`r1_burned=false`:

- exit 0; required blocks: `verdict`, `null`, `attempt_accounting`, `screen`, `real`
- `verdict.disposition=SCREEN_FAIL`, `attempt_type=DETERMINISTIC_SCREEN`
- `verdict.screen_status=ZERO_PRIMARY_PASSERS`
- `null.skipped_reason=ZERO_PRIMARY_PASSERS`
- `screen.zero_primary_passers is True`; `real.n_passers==0` (strict int)
- **Exact** booleans: `family_screen_attempt is True`, `sealed_null_attempt is False`
- All count fields present as **strict ints** on **both** `null` and
  `attempt_accounting` (`n_null_planned`, `n_null_executed`, `n_trials` /
  `null_trials_executed`), mutually equal; planned == charter; executed/trials == 0
- Present-but-invalid values (e.g. `"invalid"`) → UNKNOWN (no cross-block fallback)

Missing, malformed, incomplete-screen, partial-null, plan-mismatch, count-conflict,
invalid-present fields, or nonzero-exit reports use `disposition=FAILED_RUN_UNKNOWN`,
`execution_state=UNKNOWN`, and **conservatively consume** the attempt
(`r1_burned=true`, `sealed_null_attempt=true`, `n_null_executed=null`). The
report's own disposition is preserved separately as `reported_disposition`.

Full sealed-null success requires exit 0; blocks `verdict`+`null`+`attempt_accounting`;
strict equal counts with `n_exec == n_null_planned > 0`; exact booleans
`family_screen_attempt is True` / `sealed_null_attempt is True`;
`attempt_type=SEALED_NULL`; known disposition (`PASS_KEEP_RESEARCHING`, `WEAK_FAIL`,
or `KILL_*`); and `null.trials` list of **planned** rows each with an **explicit**
strict-int `trial` such that `{trial ids} == set(range(n_null_planned))` (no
positional fallback; out-of-range IDs fail). Screen path requires
`null.trials == []` (present and empty).
Partial completion (e.g. 1 of 999) is UNKNOWN, not success.

## Attempt ledger (STARTED + unique attempt_id)

Before `subprocess.run`, the sealed wrapper appends a **STARTED** row with a
fresh `attempt_id` (uuid hex). After the harness (or on interrupt / launch
error), a terminal row is appended with the **same** `attempt_id`.
`count_attempts` counts **unique** `attempt_id` values (STARTED+TERMINAL = 1);
legacy rows without `attempt_id` still count as 1 each. Interrupt
(`KeyboardInterrupt`) and launch failure (`OSError`) still leave the attempt
in the ledger (fail-closed). Provenance remains best-effort; the terminal
ledger write does not depend on provenance success.

## Canonical session null

**`within_day_ohlc_increment_rotate_v1`**

1. Per calendar day, `ref_0 = open[0]`, `ref_j = close[j-1]`.  
2. `inc_j = (open,high,low,close)/ref_j`.  
3. Circular rotate by `k ∈ {0,…,m−1}` (**identity included**).  
4. Rebuild continuous path from day open; timestamps/spreads fixed.  

Invariants: open/ref multiset, TR/ref multiset, per-day bar counts, continuity.

**Invalid for session families:** `day_block_shuffle`, `circular_day_shift`, `global_return_shuffle`, and bare `within_day_return_rotate` under protocol ≥2.2 (name without preregistered OHLC algorithm).

## Enforcement

| Guard | Behavior |
|-------|----------|
| Session thesis | Must set `null.method=within_day_ohlc_increment_rotate_v1` (protocol ≥2.2) |
| `null.forbidden_methods` | Method listed there is rejected |
| Registry JSONL | Fail closed on malformed lines; terminal dispositions are **monotonic** |
| Dispositional tree | Sealed / `--strict-charter` refuse dirty tracked protocol/family/cost/charter/registry files — includes frozen charters under `results/xau_charters/` **and** disposition registry `results/xau_charter_disposition_registry.jsonl` (both remain enforced) |
| Provenance | Records `code_commit` + `tree_clean` / `dirty_paths`; top-level `n_null` is **executed** count only (`null` when UNKNOWN — never planned) |
| Failed harness | `disposition=FAILED_RUN_UNKNOWN`, `execution_state=UNKNOWN`; do not claim zero nulls without full screen proof |
| Attempt ledger | STARTED pre-launch + terminal row share `attempt_id`; count by unique id |

## Next family (not server-hour / TOD)

New `family_id` · freeze under `results/xau_charters/` · git-tracked · match HEAD ·  
freeze **before** inspecting real grid · null only if primary passers ≥ 1.

## Sealed path requirements

- Charter under `results/xau_charters/`
- Git-tracked and byte-identical to `HEAD` blob
- Clean dispositional tree (includes frozen charters under `results/xau_charters/` and disposition registry `results/xau_charter_disposition_registry.jsonl`)
- Charter runnable (registry not terminal)
