# Plan: `xauusd_data.csv` and git history

**Date:** 2026-08-08  
**Branch:** `research/algo-trading-btc-gold-forex` (public on `origin`)  
**Safety:** no history rewrite, no force-push, no BFG/filter-repo in this phase.  
**Related:** `results/xau_housekeeping_inventory.md` §2 / action A5; `fetch_data.py`; `tests/test_xau_pipeline.py`.

---

## 1. Status quo cost (clone size)

| Metric | Value |
|--------|------:|
| Working-tree file | **9.4 MB** (`du -h`; ~129 134 lines; ASCII CSV) |
| Tracked? | **Yes** (`git ls-files`); **not** on `main` |
| Commits touching file | **2** — `e65d71c` (introduce ~9.0 MB) → `9a67561` (spread column rewrite ~9.4 MB) |
| Loose zlib objects | **~3.3 MB each** × 2 ≈ **6.6 MB** under `.git/objects/` |
| Whole `.git` (this clone) | **~8.9 MB** — CSV blobs ≈ **~74%** of object store |
| Research branch tip | `origin/research/algo-trading-btc-gold-forex` |
| Remote | `https://github.com/Trujillofa/mt5-arch-integration.git` |

**What a fresh clone of the research branch pays today**

1. **Transfer:** both historical blobs (≈6.6 MB compressed as loose zlib; similar once packed) plus the rest of the branch (~0.3 MB of other objects in this clone’s pack).  
2. **Checkout:** another **~9.4 MB** for the tip working tree.  
3. **Disk peak:** order of **~15–20 MB** attributable to this one path (history + working copy), dwarfing platform code.

**Growth risk if left tracked:** each full re-export is a near-full new blob (~3 MB compressed). The file is rewritten as a whole (not line-oriented edits), so history cost scales with “number of CSV-touching commits,” not with bar growth alone.

**CI / tests:** `tests/test_xau_pipeline.py::test_csv_exists_and_covers_year` requires the file and H1 span ≥300 days. Documented in `AGENTS.md` / `CLAUDE.md`: fails on a fresh clone until `python3 fetch_data.py` (once untracked) or until the tracked blob is present.

**`main`:** does **not** contain `xauusd_data.csv`. Cost is research-branch / research-merge only.

---

## 2. Options (ranked)

### (a) Leave it — keep tracking in git

| | |
|--|--|
| **What** | Status quo. CSV stays in tree and in future commits. |
| **Pros** | Zero process change; clone always has data for offline tests; bit-for-bit shared research CSV without MT5. |
| **Cons** | Every clone of this branch keeps ~6.6 MB+ history forever; each update adds ~3 MB; public GitHub history grows; platform-only consumers of a merged branch pay for research market data. |
| **Force-push?** | No |
| **Rank** | Acceptable short-term if CSV is frozen and rarely rewritten. **Weak** if anyone keeps re-fetching and committing it. |

### (b) Git LFS going forward

| | |
|--|--|
| **What** | `git lfs track "xauusd_data.csv"`; migrate **future** commits only (or full LFS migrate — see (d)). |
| **Pros** | Pointer files stay tiny in git; large payloads live in LFS store; familiar for binary-ish assets. |
| **Cons** | Does **not** shrink existing non-LFS history without a rewrite/migrate; every clone needs `git lfs install` + LFS quota/bandwidth; GitHub free LFS bandwidth is limited; overkill for a regenerable research CSV that `fetch_data.py` already builds. |
| **Force-push?** | Not for “track going forward” alone; full history migrate to LFS **does** rewrite and needs force-push. |
| **Rank** | Reasonable if the team wants the **exact** broker CSV pinned in the repo without regenerating. **Not** recommended as default: data is regenerable and research-only. |

### (c) gitignore + `fetch_data.py` required + stop tracking on **future** commits only  ✅ recommended

| | |
|--|--|
| **What** | Add `xauusd_data.csv` to `.gitignore`; `git rm --cached xauusd_data.csv`; commit; document `python3 fetch_data.py` (and Wine export path). **Do not** rewrite past commits. |
| **Pros** | No force-push; no collaborator history breakage; stops **further** bloat; aligns with regenerable data model; `main` unaffected; history blobs remain but new commits stay lean. |
| **Cons** | Old blobs stay in history until an explicit rewrite (d); fresh clones of old commits still download historical blobs; research tests need a local fetch (or optional skip — §5); exact tip CSV is no longer identical for every clone (sha256 / fit window discipline already lives in `strategy_params.json` + holdout lock). |
| **Force-push?** | **No** |
| **Rank** | **Best default now.** Matches SAFETY constraints and A5 in housekeeping inventory. |

**Human steps for (c)** (when ready to commit):

```bash
# 1. Ensure ignore rule exists (may already be present)
grep -q 'xauusd_data.csv' .gitignore || echo 'xauusd_data.csv' >> .gitignore

# 2. Stop tracking; keep local file
git rm --cached xauusd_data.csv

# 3. Commit on the research branch (normal push, not force)
git add .gitignore
git status   # should show "deleted" xauusd_data.csv in index only
git commit -m "chore: stop tracking xauusd_data.csv (regenerate via fetch_data.py)"

# 4. Push normally
git push origin research/algo-trading-btc-gold-forex

# 5. On any machine after pull:
python3 fetch_data.py    # needs numpy/pandas (host/venv), not uv run
# optional preferred path when Wine MT5 is logged in:
#   ./scripts/export-xau-from-wine-mt5.sh   # then fetch_data prefers export
```

**Verify after (c):**

```bash
test -f xauusd_data.csv && du -h xauusd_data.csv
git check-ignore -v xauusd_data.csv
git ls-files xauusd_data.csv   # must be empty
uv run pytest tests/test_xau_pipeline.py -q
```

### (d) Full history rewrite — **BLOCKED**

| | |
|--|--|
| **What** | `git filter-repo` / BFG / `git lfs migrate import --everything` to purge `xauusd_data.csv` (or move all versions to LFS) from **all** commits; force-push all affected branches; every collaborator re-clones or hard-resets. |
| **Pros** | Actually removes ~6.6 MB from clone transfer forever; clean public history. |
| **Cons** | Rewrites SHAs; breaks open PRs and local clones; needs coordinated force-push of **public** branch; easy to get wrong; violates standing SAFETY without explicit human approval. |
| **Force-push?** | **Yes — mandatory** |
| **Status** | **BLOCKED** until explicit human approval of: (1) rewrite tool + scope, (2) force-push of listed refs, (3) collaborator re-clone plan. Document-only commands in §4. |

---

## 3. Recommended path (no force-push)

**Do (c) when next convenient docs/hygiene commit is made:**

1. Keep `xauusd_data.csv` in `.gitignore` (prep may land before the untrack commit).  
2. Human runs `git rm --cached xauusd_data.csv` + normal commit + normal push.  
3. Treat `python3 fetch_data.py` as the source of working-tree data (Wine export preferred when available; offline Dukascopy/yfinance fallback exists in `fetch_data.py`).  
4. Leave historical blobs alone until/unless (d) is unblocked.  
5. Do **not** adopt LFS unless someone needs a shared **immutable** multi-GB archive later.  
6. Do **not** merge the research branch to `main` with the CSV still tracked (if merge ever happens, untrack first or the cost lands on `main` clones).

**Why not (a):** two full versions already dominate `.git`; a third spread/refetch commit would be pure waste.  
**Why not (b) alone:** LFS without rewrite leaves old blobs; LFS ops cost for regenerable data.  
**Why not (d) now:** public history + SAFETY + no approved force-push.

---

## 4. Rewrite commands (document only — **do not run** without approval)

Only after a human explicitly approves force-push of every listed ref.

### Prerequisites

- [ ] Backup: full bare clone of `origin` kept offline.  
- [ ] List refs that contain the file: at least  
  `research/algo-trading-btc-gold-forex` (+ any forks/PRs).  
- [ ] Confirm no open PR depends on old SHAs without a re-push plan.  
- [ ] Written approval: “rewrite history of `<refs>` and force-push.”

### Option D1 — purge path with `git filter-repo` (preferred tool)

```bash
# WARNING: rewrites all commits that ever touched the path. DO NOT RUN casually.
# Install: pacman -S git-filter-repo  OR  pipx install git-filter-repo

cd /path/to/mt5-arch-integration
git fetch origin
git checkout research/algo-trading-btc-gold-forex

# Dry analysis
git rev-list --objects --all | grep xauusd_data.csv

# Rewrite (destructive to local history graph)
git filter-repo --path xauusd_data.csv --invert-paths --force

# Ensure ignore is present post-rewrite
grep -q 'xauusd_data.csv' .gitignore || echo 'xauusd_data.csv' >> .gitignore
# restore local data if needed
python3 fetch_data.py

# Force-push ONLY after approval — example (adjust refs):
# git push --force-with-lease origin research/algo-trading-btc-gold-forex
```

Collaborators after rewrite:

```bash
# safest
rm -rf mt5-arch-integration
git clone https://github.com/Trujillofa/mt5-arch-integration.git
git checkout research/algo-trading-btc-gold-forex
python3 fetch_data.py
```

### Option D2 — BFG (alternative)

```bash
# DO NOT RUN without approval
java -jar bfg.jar --delete-files xauusd_data.csv
git reflog expire --expire=now --all
git gc --prune=now --aggressive
# git push --force-with-lease origin research/algo-trading-btc-gold-forex
```

### Option D3 — LFS migrate entire history

```bash
# DO NOT RUN without approval; also rewrites history
git lfs install
git lfs track "xauusd_data.csv"
git lfs migrate import --include="xauusd_data.csv" --everything
# git push --force-with-lease origin --all
# git push --force-with-lease origin --tags
```

**Not recommended** over D1 for this repo: regenerable data should leave git entirely, not move to LFS.

---

## 5. Should `test_xau_pipeline` skip if CSV is missing?

### Pros of `pytest.skip` when missing

- Platform-oriented `uv run pytest` stays green on clones that never run research.  
- Matches optional-data patterns for integration tests.  
- After (c), avoids a hard fail that is really an environment setup step.

### Cons

- Hides “I forgot to fetch data” when someone intends a full research verification.  
- Fit-window / sha256 reproduction tests only fire when data is present — easy to think the pipeline is tested when it was skipped.  
- `AGENTS.md` already documents the hard requirement; silent skip weakens that contract.  
- Risk of CI “always skip” if nobody provisions the CSV in the job.

### Decision (this phase)

**Do not switch to skip-if-missing yet** — not clearly better while the file is still tracked (clones always have it).  

**After (c) lands**, prefer one of:

| Approach | When |
|----------|------|
| **A. Keep hard fail + clear message** | Default for research authenticity; document in README / AGENTS. |
| **B. Skip only if env `XAU_PIPELINE_DATA=0` or marker** | Explicit opt-out for platform-only CI. |
| **C. `pytest.importorskip` / skip-if-missing** | Only if research tests are split into `tests/research/` and CI runs them in a job that fetches data. |

**Tiny non-destructive improvement now:** assert message points at `python3 fetch_data.py` and this plan (implemented in `tests/test_xau_pipeline.py`). No behavior change when the file exists.

---

## 6. Small prep done alongside this plan (no history rewrite)

| Change | Purpose |
|--------|---------|
| `results/xau_csv_history_plan.md` | This document |
| `.gitignore` → `xauusd_data.csv` | Prep for (c); no effect on already-tracked files until `git rm --cached` |
| `README.md` research data note | Fetch path for future clones |
| `tests/test_xau_pipeline.py` message | Clearer failure → `fetch_data.py` |

**Not done:** `git rm --cached`, history rewrite, LFS, force-push.

---

## 7. Decision summary

| Choice | Status |
|--------|--------|
| **Recommended now** | **(c)** stop tracking going forward; regenerate via `fetch_data.py` |
| **Acceptable stall** | **(a)** if CSV is frozen and no one commits updates |
| **Optional later** | **(b)** only if exact shared CSV must stay in-repo without regenerating |
| **Blocked** | **(d)** full purge / LFS migrate of history — needs explicit human + force-push approval |

**Next human action for (c):** run the §2(c) command block, review `git status`, normal push.
