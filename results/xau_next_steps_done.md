# Next steps done — charter B, draft PR, Exness bridge

**Date:** 2026-08-08  
**Commit:** `777f40e2d9170b5aad9f5d806438c5f4daed98ea`  
**Message:** `docs: adopt dual-layer charter B; draft PR + Exness bridge deploy notes`  
**Branch:** `research/algo-trading-btc-gold-forex` (ordinary push to origin; no force-push, no merge)

---

## 1. Charter Option B (adopted)

**Decision:** dual-layer charter **Option B** is adopted.

| Doc | Role |
|-----|------|
| [`docs/CHARTER-RESEARCH-LAYER.md`](../docs/CHARTER-RESEARCH-LAYER.md) | Full dual-layer charter |
| [`AGENTS.md`](../AGENTS.md) | Operating rules (authoritative where it overlaps CLAUDE.md) |
| [`results/xau_charter_adopted.md`](xau_charter_adopted.md) | One-pager adoption record |

**Layers (hard boundaries):**

| Layer | Paths (examples) | Role |
|-------|------------------|------|
| Platform | `src/mt5_arch/`, `scripts/NN-*.sh`, `mql5/Mt5ArchBridge.mq5` | Wine MT5 + file/RPyC bridge + thin CLI |
| Offline research | `backtest.py`, `fetch_data.py`, `live_trader.py`, `scripts/xau_*`, `scripts/htf_fib_*`, research indicators, `results/` | Falsifiable offline strategy work only |

**Non-negotiable:**

1. **`src/mt5_arch` ↛ research** — platform must never import research modules / `results/`.
2. **No live without consent** — `live_trader.py` dry by default; no `--live` from automation without a direct human yes.
3. **Merge ≠ promote** — landing dual-layer code on `main` does **not** authorize paper/live trading or flipping `promote` / `live_go` / `PAPER_GO`.

**Strategy disposition (unchanged by charter):**

| Field | Value |
|-------|--------|
| **next_step** | **RESEARCH_IDLE** |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | **no** |

Null kills still apply: `KILL_BB_RSI_LINE`, `KILL_DONCHIAN_LINE`. See [`results/xau_loop_status.md`](xau_loop_status.md).

---

## 2. Draft PR

| Field | Value |
|-------|--------|
| **PR** | [#1](https://github.com/Trujillofa/mt5-arch-integration/pull/1) |
| **URL** | https://github.com/Trujillofa/mt5-arch-integration/pull/1 |
| **isDraft** | true |
| **Base** | `main` |
| **Head** | `research/algo-trading-btc-gold-forex` |
| **Record** | [`results/xau_pr_opened.md`](xau_pr_opened.md) (body draft earlier: [`xau_pr_draft.md`](xau_pr_draft.md)) |

**Safety:** draft only — human review before any merge. No force-push. No live-order claims in the PR.

---

## 3. Exness bridge deploy (Mt5ArchBridge v1.22)

Full notes: [`results/xau_bridge_deploy_exness.md`](xau_bridge_deploy_exness.md).

| Check | Result |
|-------|--------|
| Source → Exness Experts | **yes** (`ResolveSymbol`, `#property version "1.22"`) |
| Compile Exness | **0 errors, 0 warnings** |
| Compile Vantage (optional) | **0 errors, 0 warnings** |
| Terminals killed | **no** |
| Live orders | **no** |

Primary tree: `~/.mt5-exness` → `…/MetaTrader 5 EXNESS/MQL5/Experts/Mt5ArchBridge.{mq5,ex5}`.

---

## 4. Remaining **human** ops

These are intentionally not automated:

### A. Re-attach / reload Mt5ArchBridge v1.22 (Exness)

MT5 does **not** hot-reload a replaced `.ex5` while the EA is already on a chart. A live Exness terminal was left running during deploy.

1. Detach **Mt5ArchBridge** from the chart, then re-attach from Navigator → Expert Advisors (Algo Trading green), **or** restart the Exness terminal when convenient.
2. Confirm Experts log / tab shows something like `Mt5ArchBridge WRITER v1.22 ON …`.
3. Bridge dir:  
   `~/.mt5-exness/drive_c/Program Files/MetaTrader 5 EXNESS/MQL5/Files/mt5_arch/`  
   Heartbeat must stay fresh (`MT5_BRIDGE_MAX_AGE`, default 15s).  
   Note: post-deploy `symbols.json` was empty `[]` until the EA fully refreshes / exercises the symbol list path.

Same re-attach rule on Vantage if that EA is already charted.

### B. CSV history (process hygiene / virgin data)

- Holdout remains sealed: `holdout_start = 2026-01-01` (`results/xau_holdout_lock.json`) — never for selection.
- Multi-year / virgin coverage still limited by available `xauusd_data.csv` depth; extend history via approved export path (`fetch_data.py` / Wine export / broker history) when ready.
- Disposition stays **RESEARCH_IDLE** / promote=no until sealed virgin hard_pass exists (and even then merge ≠ promote).

See also: `results/xau_csv_history_plan.md`, `results/xau_history_coverage.json`.

### C. Commission / slippage (still unmeasured)

- Sims currently use **measured spread** where wired; **commission_per_lot** and **slippage_points** still default **0** unless set from a real broker figure.
- Need an explicit human-sourced commission (and optional slippage) from Exness/Vantage contract specs or executed deals — not inventable from OHLC history.
- Replay any future fit with the `costs` block stored in `strategy_params.json`.

---

## Shipped in this commit

| Path | Change |
|------|--------|
| `docs/CHARTER-RESEARCH-LAYER.md` | Charter B dual-layer text |
| `AGENTS.md` | Dual-layer + Option B adoption pointer |
| `results/xau_loop_status.md` | Charter adoption status block |
| `results/xau_charter_adopted.md` | Adoption one-pager |
| `results/xau_pr_opened.md` | Draft PR #1 record |
| `results/xau_bridge_deploy_exness.md` | Exness/Vantage v1.22 deploy + human re-attach |
| `.grok/workflows/xau-charter-pr-bridge.rhai` | Workflow for charter/PR/bridge run |

**Not committed (by design):** `.omo/`, Wine `.ex5` binaries.

---

## Summary line

**ok=true** — `777f40e` pushed; PR https://github.com/Trujillofa/mt5-arch-integration/pull/1 (draft); charter B adopted; Exness bridge v1.22 compiled; human still needs EA re-attach, CSV history extension, and measured commission/slippage.
