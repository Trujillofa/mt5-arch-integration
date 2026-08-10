# PR draft — research branch → main (do not auto-open)

**Safety:** Draft only. Do **not** open with `gh` until the owner confirms
charter option and branch is intentionally ready. Do **not** merge. Do **not**
force-push.

**Branch:** `research/algo-trading-btc-gold-forex`  
**Base:** `main`  
**Disposition at draft time:** `RESEARCH_IDLE` · `promote=no` · `live_go=false`  
**Charter:** see [`docs/CHARTER-RESEARCH-LAYER.md`](../docs/CHARTER-RESEARCH-LAYER.md) — **recommended Option B**

---

## Suggested title

```
research: offline XAU pipeline with measured costs; null-kill bb_rsi + Donchian (RESEARCH_IDLE, promote=no)
```

Alternate (shorter):

```
research: costed XAU null kills (bb_rsi, Donchian) — dual-layer, no promote
```

---

## Suggested body

```markdown
## Summary

Offline research layer on top of the Wine MT5 / file-bridge platform. This PR
**does not claim a tradable edge**. Standing disposition from
`results/xau_loop_status.md`:

| Field | Value |
|-------|--------|
| next_step | **RESEARCH_IDLE** |
| promote | **no** |
| live_go | **false** |
| PAPER_GO | **no** |

Charter proposal (product decision): **Option B** — explicit dual-layer repo
(platform + offline research) with hard boundaries. Options A/C documented in
`docs/CHARTER-RESEARCH-LAYER.md`. Do not merge if you want pure platform-only
`main` (Option A) without a deliberate choice.

## What landed (process wins, not edge claims)

### Platform-adjacent (safe, reusable)

- **Bridge spread dump** — `Mt5ArchBridge.mq5` v1.21: per-bar `spread` in candle
  snapshots + one-shot deep history dump (OHLC + spread). Still **no OrderSend**.
- **Fetch path** — `fetch_data.py` prefers bridge dump; carries `spread` column;
  reports zero-spread bars (old history backfill).
- **Cost model** — `backtest.simulate()` charges optional round-trip
  spread / commission / slippage; defaults remain zero so old metrics reproduce.
  Measured H1 spread used in later evals; **commission and slippage still
  unmeasured** (explicit zeros).

### Research falsification

- **bb_rsi / vol-gate family** — `KILL_BB_RSI_LINE` via develop-only null /
  max-stat (`scripts/xau_null_maxstat.py`). Real max PF / passer counts are not
  above return-shuffled nulls (`p_max_pf≈0.85`, `p_n_passers≈0.71`).
- **Costs on frozen multi-year** — lane sims wired to same cost formula; 8×9
  matrix re-scored. Under spread, only Donchian remained multi-year sign-stable;
  other lanes died or thinned.
- **Donchian / turtle family** — `KILL_DONCHIAN_LINE` via matching null protocol
  (`scripts/xau_donchian_null_maxstat.py`): `p_max_pf=0.195`,
  `p_n_passers=0.293` (not distinguishable from null at conventional thresholds).
- **RESEARCH_IDLE** — no remaining interesting strategy lane from the frozen
  catalog for further edge research. Virgin-data `WAIT_DATA` is process hygiene
  only, not permission to re-mine killed families.

### Research hygiene already in tree

- Pre-registered holdout (`results/xau_holdout_lock.json`, start `2026-01-01`);
  selection must stay pre-holdout.
- Fit-window stamping on `strategy_params.json`; `backtest.py --save` is the only
  mutator of tracked params.
- Causality: HTF fractal pivots stamped at confirmation bar
  (`scripts/htf_fib_core.py`).
- `live_trader.py` dry by default; requires explicit `--live` + user consent.

### Docs / agent rules (include in commit list)

- Expanded **`AGENTS.md`** dual-layer story aligned with `CLAUDE.md` (platform vs
  offline research; research invariants; file-bridge defaults; multi-broker
  gotchas).
- **`docs/CHARTER-RESEARCH-LAYER.md`** — options A/B/C + recommended B.
- This draft: `results/xau_pr_draft.md`.

## What this PR does **NOT** claim

- **No promote** — no champion for paper or live.
- **No live trading** — no orders, no `--live` enablement, no agent automation
  to place trades.
- **No “edge found”** — null tests say develop gate-passers measured the
  *search*, not the market, for both bb_rsi and Donchian.
- **No commission-complete cost model** — spread is measured; commission and
  slippage remain assumption zeros unless separately measured.
- **No charter ratification by merge alone** — owner still picks A/B/C if
  dual-layer on `main` is contested.

## Open items (post-merge or blocking, owner call)

| Item | Notes |
|------|--------|
| **CSV history** | `xauusd_data.csv` is large; fresh clones need `python3 fetch_data.py`. Broker history may zero-fill old spreads. Longer virgin windows still `WAIT_DATA`. |
| **Charter choice** | Recommend **B** (dual-layer merge-with-boundaries). **A** = never merge research; **C** = split repo later. |
| **Commission still unmeasured** | Need broker-true commission (and optional slippage) before any future costed claim is complete. |
| **Uncommitted / dirty worktree** | Confirm ruff/housekeeping and any local edits are intentional before open. |
| **Research tests** | `tests/test_xau_pipeline.py` expects CSV ≥300 days — document or gate for CI. |

## Boundaries (merge gates)

- [x] `src/mt5_arch` does not import research modules
- [x] Research remains offline / research-flagged
- [x] No live path without explicit consent
- [x] Status files say RESEARCH_IDLE / promote=no
- [ ] Owner accepts charter **B** (or explicitly chooses A/C)
- [ ] Branch pushed and draft reviewed by human

## Test plan

```bash
uv sync --all-extras
uv run pytest                          # platform + offline unit (CSV may be required for xau tests)
uv run ruff check src tests
# research scripts use host python3 + numpy/pandas (not uv):
python3 -c "import backtest; print('backtest import ok')"
# optional live platform only — not research:
# ./scripts/healthcheck.sh --ping
```

## Planned commit list (conceptual; squash/split as preferred)

1. Platform: bridge spread dump + fetch/cost plumbing (`Mt5ArchBridge`, `fetch_data.py`, `backtest.py` costs)
2. Research: XAU quant pipeline, HTF Fib tools, frozen multi-year catalog
3. Research: fit-window / reproducibility fixes; holdout lock
4. Research: charge measured spread; costed frozen multi-year after bb_rsi kill
5. Research: null max-stat → KILL_BB_RSI_LINE
6. Research: Donchian null max-stat → KILL_DONCHIAN_LINE / RESEARCH_IDLE
7. Docs: **AGENTS.md dual-layer expansion** (matches CLAUDE.md) + `docs/CHARTER-RESEARCH-LAYER.md` + this PR draft under `results/`

## Checklist for the human opener

- [ ] Read `results/xau_loop_status.md` (top section)
- [ ] Read `docs/CHARTER-RESEARCH-LAYER.md` and pick A/B/C
- [ ] Confirm no secrets (`.env`, passwords) in diff
- [ ] Prefer draft PR over auto-merge; do not force-push
- [ ] If charter A: **do not open** this PR — leave research on branch only
```

---

## Notes for the opener

- Prefer pasting the body above into a **draft** PR after push.
- If charter stays **A**, archive this file as “not for main” and keep working on
  the research branch only.
- If **C** is chosen later, this PR history is still useful as the extract
  source; do not rewrite kills away.
```