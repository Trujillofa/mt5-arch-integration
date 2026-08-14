# Article-intake gate

**Status:** offline schema + verifier · no catalog Expert Advisor is imported  
**Does not place orders.** Does not score a family. Does not authorize live trading.

Community Strategy Tester / MQL5.com catalog profit-factor numbers are **not**
validation. This gate makes that mechanical: a catalog idea cannot become a
scored research family from the article. It needs an independent Python
implementation (or an explicit refuse), stage comparison via the existing
parity / registry / sync / provenance packages where those apply, and a
written charter decision that does **not** use the holdout for selection.

Priority 5 (trade journal) is [TRADE-JOURNAL.md](TRADE-JOURNAL.md).
This is Priority 6.

## What is and is not proven

| Claim | Status |
|-------|--------|
| Schema `mt5-article-intake/v1` loads | Proven (`tests/fixtures/article_intake/valid.json`) |
| Missing required fields refuse | Proven |
| `holdout_used_for_selection: true` refuses | Proven |
| `decision=adopt` without `independent_python` refuses | Proven |
| Secret keys (`password`, …) refuse | Proven |
| Catalog `.mq5` path without a Python path refuses | Proven |
| Catalog PF / blog PF / download count as evidence | **Not evidence.** Never was. |
| A new strategy engine from this package | **Not claimed.** This is a gate, not an implementation. |
| Live terminal / paper / promote | **Not claimed.** |

Holdout start remains `2026-01-01` and is **never** used for selection
([`results/xau_holdout_lock.json`](../results/xau_holdout_lock.json)).
Evaluating on the holdout after a freeze is a later, separate step.

## Required fields

| Field | Allowed | Notes |
|-------|---------|-------|
| `schema` | `mt5-article-intake/v1` | Fail closed on drift |
| `article_url` | non-empty `http(s)` URL | Source of the claim, not of the code |
| `claim_type` | `pf` \| `pattern` \| `math` | What the article is selling |
| `independent_python` | repo-relative `.py` path, or `false` | `false` is an explicit refuse to implement |
| `parity_package` | `none` \| `htf_fib` \| `other` | Which existing stage-comparison package applies |
| `holdout_used_for_selection` | `false` | Must be the JSON boolean `false` |
| `decision` | `adopt` \| `defer` \| `reject` | Charter decision; not a score |
| `reason` | non-empty string | Why; must not treat catalog PF as proof |

`decision=adopt` requires a real `independent_python` path that exists in this
repo and ends in `.py`. `defer` and `reject` may set `independent_python` to
`false`.

A string value that looks like a catalog `.mq5` (path or filename) without a
Python path is refused. Do not import MQL5.com catalog Expert Advisor source
into the tree to “save time.”

## What is not evidence

- Community / blog / Strategy Tester profit factor, win rate, or “monthly %”
- MQL5.com download count, rating, comments, or vendor screenshots
- Copying the catalog `.mq5` into `mql5/` or `scripts/`
- Any metric computed on the holdout (`time >= 2026-01-01`) used to pick or
  keep the idea
- A live terminal dump, paper fill, or journal identifier (those are other
  packages; they do not validate a catalog claim)

`adopt` means “write an independent charter and implement in Python.”
It does **not** mean promote, paper, live, or “score this family from the
article.” Standing disposition stays RESEARCH_ONLY / `promote=no`
([`results/xau_loop_status.md`](../results/xau_loop_status.md)).

## Files

| Path | Role |
|------|------|
| `docs/ARTICLE-INTAKE.md` | This gate |
| `docs/intake/article_intake.example.json` | Copy-me template (reject of a catalog PF) |
| `scripts/verify_article_intake.py` | Research-adjacent verifier (not in `src/mt5_arch`) |
| `tests/fixtures/article_intake/valid.json` | Committed valid reject |
| `tests/test_article_intake.py` | Offline adversarial tests |

The verifier talks about charters and holdout, so it stays in `scripts/` +
`tests/`. `src/mt5_arch` must not import it.

## Commands

```bash
python3 scripts/verify_article_intake.py
python3 scripts/verify_article_intake.py docs/intake/article_intake.example.json
uv run pytest tests/test_article_intake.py
```

## What this does not do

- Import or compile a catalog `.mq5`.
- Add a trading strategy, family module, or optimizer.
- Place orders, attach a terminal, or run the Strategy Tester.
- Relabel holdout as develop, or use holdout to choose `adopt`.
- Replace [CHARTER-RESEARCH-LAYER.md](CHARTER-RESEARCH-LAYER.md) or the
  XAU family protocol — it only blocks the catalog-copy shortcut into that
  loop.
