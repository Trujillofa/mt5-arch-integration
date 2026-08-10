# XAU housekeeping summary

**Date:** 2026-08-08  
**Branch:** `research/algo-trading-btc-gold-forex`  
**Commit:** `668070a56e41ae55c0fce3ea605ef3b4686a0e1e`  
**Push:** ordinary `git push origin HEAD` → `origin/research/algo-trading-btc-gold-forex` (`7119b76..668070a`)  
**Tests:** `uv run pytest tests/test_cli_unit.py tests/test_xau_pipeline.py -q` → **15 passed**

---

## What shipped (this commit)

| Area | Change |
|------|--------|
| **Mt5ArchBridge v1.22** | `ResolveSymbol()` tries bare name then `m` / `.r` / `.m` / `#` / `pro` so Exness raw etc. no longer skip every default and leave empty `symbols.json`. Defaults are bare (`EURUSD,…,XAUUSD,BTCUSD`). Documented in `mql5/README.md`. |
| **AGENTS.md** | Expanded dual-layer operating rules (platform vs offline research), file-bridge notes, multi-broker paths, research invariants, safety. Coherent with branch reality. |
| **README** | Note that research tests need `xauusd_data.csv` + link to CSV history plan. |
| **`.gitignore`** | Future `xauusd_data.csv` ignore (file **still tracked** in history; no `git rm` / rewrite). |
| **Ruff-safe Python** | Import order (I001), `UTC` (UP017), `collections.abc` (UP035), unused imports (F401), f-string placeholders (F541), equivalent if/elif collapses on research scripts + clearer CSV missing assert. No intentional strategy/behavior change. |
| **Charter draft** | `docs/CHARTER-RESEARCH-LAYER.md` — Options A/B/C; recommended **B**. |
| **PR draft** | `results/xau_pr_draft.md` — do not auto-open until owner confirms charter. |
| **CSV plan** | `results/xau_csv_history_plan.md` — size facts, options; **no history rewrite applied**. |
| **Inventory / ruff notes** | `results/xau_housekeeping_inventory.md`, `results/xau_housekeeping_ruff.md`. |
| **Workflow** | `.grok/workflows/xau-housekeeping.rhai` (shared workflow path). |

**Not committed:** `.omo/` (left untracked by design).

---

## BLOCKED (explicitly not done)

| Item | Why blocked |
|------|-------------|
| **Git history rewrite** for `xauusd_data.csv` (~9.4 MB working tree; ~2 historical blobs ≈6.6 MB compressed) | Requires force-push / filter-repo / BFG and owner approval. Safety rules for this phase: **no force-push, no history rewrite**. |
| **`git rm --cached xauusd_data.csv`** | Would stop tracking tip only; old blobs remain until rewrite. Plan documents this as a separate decision; ignore entry is forward-looking only. |
| **Open / merge PR to `main`** | Draft only (`results/xau_pr_draft.md`). Needs charter choice + human gate. |
| **Adopt charter formally** | `docs/CHARTER-RESEARCH-LAYER.md` is a product decision draft, not adopted. |
| **Live promote / `--live`** | Standing disposition unchanged: **RESEARCH_IDLE / promote=no / live_go=false**. |
| **Compile + redeploy bridge EA into Wine prefix** | Repo source updated; MT5 still needs `./scripts/18-install-forex-indicator.sh` (or equivalent) + MetaEditor compile for the running terminal. |
| **Full ruff clean of research tree** | Safe subset applied; remaining debt documented in `results/xau_housekeeping_ruff.md` (platform target remains `uv run ruff check src tests`). |

---

## Charter recommendation

**Option B — Explicit dual-layer charter; allow merge with clear boundaries** (see `docs/CHARTER-RESEARCH-LAYER.md`).

- Platform: Wine MT5 + file/RPyC bridge + thin CLI in `src/mt5_arch`.
- Research: offline-only at repo root / `scripts/xau_*` / `results/`; **never** imported by `src/mt5_arch`.
- Matches what this branch already documents in `AGENTS.md` / `CLAUDE.md`.

Alternatives (still valid human choices): **A** never-merge research branch; **C** extract research to a separate repo.

---

## Next human decisions

1. **Charter:** Adopt A, B, or C (or edit the draft). Until chosen, do not open the PR to `main` as a merge intent.
2. **CSV history:** Accept the ~9 MB blob on the research branch, or schedule an approved rewrite/filter (owner-only, force-push aware) per `results/xau_csv_history_plan.md`. Optionally `git rm --cached` + fetch_data on clone **without** rewrite as a tip-only mitigation.
3. **PR:** If B: open draft PR from `results/xau_pr_draft.md` when ready; **do not merge** until review and promote policy stay `promote=no`.
4. **Bridge ops:** After pulling, deploy/compile `Mt5ArchBridge.mq5` v1.22 on Exness (and other m-suffix brokers); confirm non-empty `symbols.json` / candles.
5. **Research disposition:** Remain **RESEARCH_IDLE** — do not re-mine null-killed families (bb_rsi, Donchian); virgin-data hygiene only unless a new pre-registered design is approved.

---

## Commit hash(es)

```
668070a56e41ae55c0fce3ea605ef3b4686a0e1e  Housekeep research branch after RESEARCH_IDLE: Exness ResolveSymbol, ruff, charter drafts.
```

**Blocked items (short):** history rewrite of `xauusd_data.csv`; force-push; auto PR open/merge; formal charter adoption; live promote; full research ruff zero; EA install into live Wine prefix (ops).
