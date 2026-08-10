# XAU family research protocol v2.1

**Date:** 2026-08-10  
**Status:** active for new families  
**PR #1 note:** Protocol work is on the same branch as draft PR #1 — scope **did expand**; do not claim separation.

## Why

Prior null harnesses mixed module-local soft gates with hard-coded report strings, used n_null=40 (coarse under add-one smoothing), defaulted to global return shuffle (invalid for pure session claims), and overwrote a single “next charter” path.

### v2.1 correction (post review)

* **`day_block_shuffle` is PROTOCOL_NULL_INVALID** for server-hour rules (variable-length absolute-price paste).
* Session null = **`within_day_return_rotate`** (rebase within day; preserve bar counts; break hour↔path association).
* Clock: server hours as stored; **no London–NY claim** without external offset proof.
* Strict charter/runtime equality; blocking fixtures; slip sensitivity in report.
* `tod_london_ny_flat` v1 = `PROTOCOL_NULL_INVALID` / `SCREEN_FAIL`; r1 not burned.

## Rules

1. **Immutable charters** under `results/xau_charters/YYYY-MM-DD_<family>_vN.json`. Refuse overwrite.
2. **Gates from charter only** when `--charter` is passed; report strings derived from the same structure.
3. **n_null ≥ 199** (prefer **999** for 0–1 knobs). Freeze before execution.
4. **Null method preregistered** (`global_return_shuffle` | `day_block_shuffle` | `circular_day_shift`) with invariants tested.
5. **Costs wording:** account-matched spread + commission only; slippage unmeasured (0); swap unmodeled → require **intraday flat** or explicit swap handling. Frozen slip sensitivity is report-only (no rescue tuning).
6. **Sealed cycle:** synthetic fixtures → one command real grid+null → attempt ledger. No mid-run retune.
7. **Multiple testing:** every sealed run appends `results/xau_family_attempts.jsonl`.

## Candidates (2026-08-10)

| Candidate | Decision |
|-----------|----------|
| Multi-instrument fixed rule | **Deferred** — data/harness single-symbol |
| Fixed EMA20 + H4 bias | **Removed** — overlaps dead htf_pullback |
| Zero-knob time-of-day + day-block null | **Selected** — `tod_london_ny_flat` |

## Next command (when ready to burn a sealed attempt)

```bash
python3 scripts/xau_sealed_family_cycle.py \
  --charter results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json \
  --family tod_london_ny_flat \
  --run-id r1
```

Expect ~999 null trials × 1 config — wall time depends on workers.
