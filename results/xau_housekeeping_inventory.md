# XAU / platform housekeeping inventory

**Date:** 2026-08-08  
**Branch:** `research/algo-trading-btc-gold-forex`  
**Research disposition:** `RESEARCH_IDLE` — bb_rsi and Donchian null-killed; `live_go=false`, `promote=no`, `PAPER_GO=no`  
**Source of truth for loop state:** `results/xau_loop_status.md` (top: KILL_DONCHIAN_LINE → RESEARCH_IDLE)

This note inventories open housekeeping items only. It does **not** authorize strategy re-mining, live trading, force-push, or history rewrite.

---

## Standing context (read first)

| Layer | Charter / reality |
|-------|-------------------|
| **Platform** (`AGENTS.md` / `CLAUDE.md`) | Wine MT5 + file bridge (default) or RPyC + thin Python CLI. Explicitly: no strategy engines, no risk managers, no bots in scope. |
| **Research** (this branch, repo root) | Full offline XAU/FX/BTC layer: `backtest.py`, `live_trader.py`, `fetch_data.py`, `scripts/xau_*`, `scripts/htf_*`, `mql5/Indicators/*`, `results/`. Must stay offline/research-flagged; `src/mt5_arch` must not import from it. |
| **Tension** | Platform-only charter now hosts a full research layer on this branch — open item #1 below. |

---

## Findings snapshot

### 1. Charter mismatch (docs vs tree)

- `AGENTS.md` + `CLAUDE.md` correctly document **two layers** and research invariants (holdout, costs, causality, no `--live`).
- Repo charter still reads “platform-only”; research is large, active, and at root (not a submodule/package).
- **Unstaged local expansion:** `AGENTS.md` is modified vs `HEAD` (`cb7709c`): **+63 / −16** lines — local expansion of research rules / multi-broker / invariants. Decide keep vs commit (do not drop research-safety text without replacement).

### 2. `xauusd_data.csv` in public git history

| Metric | Value |
|--------|--------|
| Working tree size | **9.4M** (`du -h`) |
| Tracked? | **Yes** (`git ls-files` lists it; not gitignored) |
| Commits touching file | `e65d71c` (initial ~9.0M / 129152 lines) → `9a67561` (spread column; ~9.4M / still ~129k lines; full-file rewrite in diff) |
| Blob sizes (approx) | ~9.0MB then ~9.4MB |

**Risks:** clones pull multi-MB binary-ish CSV; history retains both blobs forever without filter rewrite (out of scope this phase — no history rewrite). Tests (`test_xau_pipeline.py`) require CSV ≥300 days.

**Safe forward options (no rewrite):** gitignore + document fetch path; optional Git LFS for future; leave history alone until an explicit rewrite phase.

### 3. Ruff on research Python

```text
uv run ruff check backtest.py fetch_data.py live_trader.py scripts/xau_*.py scripts/htf_*.py
→ Found 101 errors
→ 43 fixable with --fix (+36 with --unsafe-fixes)
```

| Rule | Count | Notes |
|------|------:|-------|
| F541 | 17 | f-string missing placeholders (auto-fix) |
| C408 | 11 | unnecessary collection call |
| I001 | 11 | unsorted imports (auto-fix) |
| F841 | 10 | unused variable |
| SIM102 | 8 | collapsible if |
| E741 / N803 | 6+6 | ambiguous / invalid arg names |
| UP017 | 6 | `datetime.timezone.utc` (auto-fix) |
| B905 | 5 | zip without `strict=` |
| F401 | 4 | unused import (auto-fix) |
| other | ~17 | SIM*, UP035, N806/N813, C401, … |

Prior note said ~83; **current count is 101** (grid/null scripts added). Platform lint target remains `uv run ruff check src tests` — research files are extra debt.

### 4. Exness bridge empty `symbols.json` (m-suffix)

**`mql5/Mt5ArchBridge.mq5` defaults (v1.21):**

```text
InpSymbols = "EURUSD,GBPUSD,USDJPY,XAUUSD,XAUUSD.r,BTCUSD"
```

**SymbolSelect loop** (`WriteSymbols` / `WriteCandles`): split on `,`, trim, **`if(!SymbolSelect(sym, true)) continue;`** — failed symbols are **silently skipped**. If every default fails (Exness often uses `EURUSDm`, `XAUUSDm`, etc.), `symbols.json` becomes `[]` and candle dumps are empty. Same silent skip in `DumpHistory` with a Print only on history path.

Docs already list alias candidates (`XAUUSDm`, `GOLD`, …) in research notes; **defaults still lack m-suffix**.

### 5. `config/brokers/` — Exness missing

| Present | Missing |
|---------|---------|
| `fpmarkets.env`, `vantage.env`, `wsf.env` | **`exness.env`** |

Docs (`CLAUDE.md` / `AGENTS.md` / README) advertise `~/.mt5-exness` and multi-broker switch via `config/brokers/<name>.env` + `./scripts/16-use-broker.sh`, but **no Exness env file** is in tree. Hardcoded brand paths elsewhere (tester script, `fetch_data.py`, `file_bridge` default) also need Exness when/if that prefix is used.

---

## Prioritized actions

### P0 — Decide / safety (do soon, low code risk)

| # | Action | Risk if deferred | Notes |
|---|--------|------------------|-------|
| **A1** | **Decide AGENTS.md keep/commit** | Local research invariants diverge from remote; agents read wrong charter | Diff is expansion (+research rules). Prefer **commit as docs-only** on this branch, or fold into a charter PR. No force-push. |
| **A2** | **Exness symbols: extend InpSymbols + document** | Empty `symbols.json` / false “bridge dead” when Algo Trading is fine | Add Exness m-suffix names to defaults **or** per-broker input preset; log SymbolSelect failures (count + names) so silent `[]` is diagnosable. Redeploy/compile EA into Exness prefix. |
| **A3** | **Add `config/brokers/exness.env` skeleton** | `16-use-broker.sh exness` / docs lie | Mirror vantage pattern: `WINEPREFIX`, `MT5_BACKEND=file`, server/login placeholders, **no password in git**. |

### P1 — Repo hygiene (medium; no strategy work)

| # | Action | Risk if deferred | Notes |
|---|--------|------------------|-------|
| **A4** | **Charter resolution** | Scope creep; platform PRs mixed with research | Options: (1) document dual-layer as permanent on this branch, (2) split research to separate repo later, (3) quarantine research under `research/` package boundary. Prefer **docs clarity now**; mechanical split later. |
| **A5** | **Stop growing CSV in git** | Clone bloat; accidental larger commits | `.gitignore` `xauusd_data.csv`; document `python3 fetch_data.py` / Wine export; keep tests skip-or-require-data message. **Do not** filter-history this phase (SAFETY). Blobs remain until later rewrite. |
| **A6** | **Ruff research cleanup** | Noise in CI if scope expands; harder reviews | Phase 1: `ruff check --fix` on listed files (~43). Phase 2: unused vars / naming / zip strict. Keep platform `src tests` green; optional separate ruff path for research. |

### P2 — Platform polish (when touching Exness / multi-broker)

| # | Action | Risk if deferred | Notes |
|---|--------|------------------|-------|
| **A7** | Symbol alias map (Python or EA) | Per-broker manual InpSymbols forever | e.g. try `XAUUSD` then `XAUUSDm` / `.r` / `.a` once and cache. |
| **A8** | Broker path matrix audit | Broken headless tester / fetch on new brand | Update `scripts/19-run-htf-fib-backtest.sh`, `fetch_data.py`, `file_bridge.default_bridge_dir` when adding Exness. |
| **A9** | Align HTF Fib buffer index docs | Wrong `CopyBuffer` wiring | `mql5/README.md` vs `docs/HOWTO-HTF-FIB.md` disagree — fix when next touching indicators. |

### Explicit non-actions (this phase)

- No `--live`, no order placement, no promote from RESEARCH_IDLE.
- No Donchian/bb_rsi re-tune or cross-instrument mining.
- No force-push / `git filter-repo` / history rewrite.
- No wipe of Wine prefixes unless user asks.

---

## Top 3 actions (executive)

1. **Commit or intentionally discard unstaged `AGENTS.md` expansion** — keep research-safety text; align agents with tree.  
2. **Fix Exness empty symbols path** — m-suffix (or aliases) in `InpSymbols` + visible SymbolSelect failures; add `config/brokers/exness.env`.  
3. **Decouple data bloat** — gitignore / stop tracking growth of `xauusd_data.csv` going forward; leave history rewrite for a later explicit phase.

---

## Evidence log (commands)

```bash
du -h xauusd_data.csv
# 9.4M

git log --oneline -- xauusd_data.csv | head -15
# 9a67561 feat: charge measured broker spread in the XAU backtest
# e65d71c feat: XAU quant pipeline, HTF Fib tools, and frozen multi-year research

uv run ruff check backtest.py fetch_data.py live_trader.py scripts/xau_*.py scripts/htf_*.py
# Found 101 errors (43 auto-fixable)

ls config/brokers/
# fpmarkets.env  vantage.env  wsf.env   # NO exness.env

# Mt5ArchBridge.mq5:20
# input string InpSymbols = "EURUSD,GBPUSD,USDJPY,XAUUSD,XAUUSD.r,BTCUSD";
# WriteSymbols/WriteCandles: SymbolSelect fail → continue (silent skip)
```

---

## Disposition linkage

| Item | Links to research state |
|------|-------------------------|
| Strategy edge | **Closed** for frozen catalog (null kills). Housekeeping only. |
| Virgin / process hygiene | `WAIT_DATA` for process hygiene only — not permission to mine Donchian. |
| Inventory artifact | This file: `results/xau_housekeeping_inventory.md` |
