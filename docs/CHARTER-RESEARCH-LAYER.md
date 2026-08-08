# Charter: research layer vs platform

**Status:** `adopted — Option B (dual-layer)` · 2026-08-08  
**Date:** 2026-08-08  
**Context branch:** `research/algo-trading-btc-gold-forex`  
**Current XAU disposition:** `RESEARCH_IDLE` · `promote=no` · `live_go=false`  
**Related:** [`AGENTS.md`](../AGENTS.md), [`CLAUDE.md`](../CLAUDE.md), [`results/xau_loop_status.md`](../results/xau_loop_status.md), [`results/xau_charter_adopted.md`](../results/xau_charter_adopted.md)

This note is the **adopted** dual-layer charter for how offline strategy research
relates to the `mt5-arch-integration` platform. Options A and C remain below as
historical alternatives. Adoption does **not** authorize live trading, parameter
promotion, or imply that merge equals promote.

---

## Reality check (why this is not abstract)

| Fact | Implication |
|------|-------------|
| Branch already carries ~10 commits / ~160+ files over `main` (XAU pipeline, HTF Fib tools, Phase 0 observe pack, `results/*`, large CSV) | Research is not a “small sidecar” anymore |
| `AGENTS.md` / `CLAUDE.md` on the branch already describe **two layers in one repo** | Operating rules have drifted toward dual-layer before a formal charter |
| Standing disposition is **RESEARCH_IDLE** / **promote=no** / **live_go=false** | No strategy is ready for paper or live; null kills closed bb_rsi and Donchian |
| Platform scope on `main` remains: Wine MT5 + file/RPyC bridge + thin CLI | Strategies, risk managers, bots stay out of `src/mt5_arch` |

Hard rules that apply under **any** option (and under adopted B):

1. **`src/mt5_arch` must not import research.** No imports from repo-root
   `backtest.py`, `fetch_data.py`, `live_trader.py`, `scripts/xau_*`,
   `scripts/htf_fib_*`, or `results/`.
2. **No live orders from research without explicit user consent.**
   `live_trader.py` stays dry by default; never pass `--live` from tests,
   smokes, or agent automation without a direct human yes.
3. **Status truth.** Read `results/xau_loop_status.md` before touching the
   pipeline. Current next_step is **RESEARCH_IDLE** (strategy-edge research
   idle; virgin-data `WAIT_DATA` is process hygiene only, not permission to
   re-mine killed families).

---

## Option A — Keep research offline-only on this branch; never merge to main

*(Historical alternative — not adopted.)*

**Idea:** Treat `research/algo-trading-btc-gold-forex` as a permanent research
fork. Platform `main` / default `AGENTS.md` stay **platform-pure** (no strategy
engines, no research invariants, no `results/` state machine). Research work
continues only on the branch (or long-lived forks of it).

| Pros | Cons |
|------|------|
| `main` charter stays simple and agent-safe | Research already large; never-merge means forever dual maintenance |
| No risk of platform consumers tripping over `numpy`/`pandas` research deps | AGENTS/CLAUDE dual-layer text on the branch conflicts with “main is pure” |
| Easy story for public repo: “this is Wine MT5 + bridge only” | PRs that improve shared MQL5/bridge for research still need careful cherry-picks |
| Matches **promote=no** psychologically (research never “lands”) | History, null-kill evidence, and cost plumbing stay hard to share |

**When A is right:** You want a clean public platform story and accept that
research lives only as a long-lived branch artifact.

---

## Option B — Explicit dual-layer charter; allow merge with clear boundaries

### **ADOPTED** (2026-08-08)

**Idea:** Adopt what the branch already documents: one repo, **two layers**,
hard boundaries. Merge to `main` is allowed when:

- Platform code and research code stay separable by path.
- `src/mt5_arch` never depends on research.
- Research stays offline/research-flagged; no live without consent.
- Docs (`AGENTS.md`, this charter) state the dual layer so agents do not
  “helpfully” grow bots into the platform package.
- Disposition files (`results/xau_loop_status.md`) remain authoritative for
  research GO/NO-GO; merge ≠ promote.

| Pros | Cons |
|------|------|
| Matches **current branch reality** (research already large; dual-layer AGENTS already written) | `main` is no longer “platform only” in the strict old sense |
| Shared bridge improvements (e.g. per-bar spread dump) land once | Reviewers must police imports and scope creep |
| Null-kill evidence and cost models stay with the data that produced them | Fresh clones may fail research tests until CSV fetch (document that) |
| RESEARCH_IDLE / promote=no can live *on* main without implying live readiness | Slightly larger mental load for contributors |

**Boundary checklist (merge gates under B):**

| Layer | In tree | Must not |
|-------|---------|----------|
| Platform | `src/mt5_arch/`, `scripts/NN-*.sh`, core `mql5/Mt5ArchBridge.mq5`, platform docs | Import research; run strategy optimizers; place orders |
| Offline research | `backtest.py`, `fetch_data.py`, `live_trader.py`, `scripts/xau_*`, `scripts/htf_fib_*`, research `mql5/Indicators/*`, `results/`, `docs/research/` | Be imported by `src/mt5_arch`; default to live; relabel holdout as develop |

**When B is right:** You want one place for platform + falsifiable offline
research, with merge as “archive and share process,” not “promote edge.”

---

## Option C — Split research into a separate repo later; strip research from main forever

*(Historical alternative — not adopted now; valid follow-on if dual-layer noise becomes painful.)*

**Idea:** Eventually extract offline research into e.g.
`mt5-arch-research` / `xau-research`. Platform repo stays pure forever; research
depends on the platform package (or git submodule / path dep) but not vice
versa. Current branch is transitional.

| Pros | Cons |
|------|------|
| Cleanest long-term product boundary | **Later** — high move cost while RESEARCH_IDLE |
| Platform public surface stays minimal | Duplicates MQL5 deploy stories unless carefully factored |
| Research can declare `numpy`/`pandas` deps honestly | Premature split freezes coupling decisions before the next research cycle |
| Matches original “platform only” AGENTS spirit | Two remotes, two release cadences, two agent contexts |

**When C is right:** After a deliberate extract (not now as a blocking decision).
Treat C as a **follow-on** if dual-layer noise on main becomes painful.

---

## Recommendation (pre-adoption; now historical)

### **Recommend Option B** (explicit dual-layer charter; merge allowed with boundaries)

**Why not A:** Research is already large on this branch; AGENTS/CLAUDE already
tell a two-layer story. “Never merge” forces perpetual cherry-picks of useful
platform-adjacent work (bridge spread dump, deploy scripts) and strands the
null-kill paper trail off main.

**Why not C (now):** Split is valid later, but RESEARCH_IDLE + promote=no means
there is no product urgency to extract. Splitting mid-idle costs churn without
buying safety that B’s import and live rules do not already provide.

**Why B fits the facts:**

1. Dual-layer is already how the branch operates.
2. Hard rules (`src/mt5_arch` ↛ research; no live without consent; RESEARCH_IDLE
   as status) keep merge from meaning promote.
3. Costed null kills (bb_rsi, Donchian) are process assets worth keeping next to
   the bridge that produced the spread series.

### If you prefer maximal platform purity

Pick **A** as a temporary hold: leave research on the branch, do not open a merge
PR, and revisit B/C when the next research cycle starts. Do **not** silently
merge under A.

### Adopted defaults (Option B)

| Rule | Default |
|------|---------|
| Charter | **B — adopted** |
| `src/mt5_arch` → research imports | **Forbidden** |
| Live / `--live` from research | **Forbidden** without direct user consent |
| promote / live_go / PAPER_GO | **no / false / no** (see `results/xau_loop_status.md`) |
| Strategy-edge next_step | **RESEARCH_IDLE** |
| Merge to main | Allowed under B boundaries; **merge ≠ promote** |
| Auto-open merge PR | **No** — human opens when ready |

---

## Decision log

| Date | Decision | By |
|------|----------|----|
| 2026-08-08 | Draft options A/B/C; recommend B | Agent draft (awaiting owner) |
| 2026-08-08 | **Official adoption — Option B (dual-layer)** | owner via agent workflow (Option B) |
