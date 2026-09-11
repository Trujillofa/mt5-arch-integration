# GoldSessionScalp vs UsIndexSessionScalp — observe deploy + performance

| Field | Value |
|-------|--------|
| **Date** | 2026-09-11 |
| **Role** | Chart-overlay deploy (not a promote) + apples-to-apples book compare |
| **Gold disposition** | **CLOSED** · **observe-only** · **promote=no** · **live_go=false** |
| **Index disposition** | observe-only · **promote=no** · **live_go=false** (1%/20% goal archived) |
| **Gold family** | `xau_london_defined_r_be_flat_v1` primary `tpr1_be0_ts6` (do not retune) |
| **Index family** | frozen `ny_cash_orb_vwap_ema_flat` (do not retune v1–v8) |
| **No live gold orders** | No `--live`, no `OrderSend`, no Seven Desk gold-scalp fanout, Algo Trading not enabled for this overlay |

This file does **not** reopen the 16-cell gold grid, GARCH, or β families.
It does **not** rewrite `results/xau_research_costs.json`. Official gold
metrics stay in `results/xau_session_scalp/defined_r_v1_*.json`. Index scan
metrics stay in the sibling worktree
`/home/yderf/Projects/trading/.worktrees/mt5-arch-integration/index-session-scan/results/index_session_scan/`.

---

## What was installed / compiled

Full `scripts/18-install-forex-indicator.sh` was **not** run: it would have
overwritten live `Mt5ArchBridge.mq5` on Vantage/FP (installed hash ≠ this
worktree). Overlay-only copy + headless MetaEditor `/compile` instead.

| Prefix | Gold `.ex5` | Index `.ex5` | Logger `.set` | Bridge EA |
|--------|-------------|--------------|---------------|-----------|
| `~/.mt5-vantage` (live XAUUSD + DJ30.r) | 0 errors / 0 warnings | 0 / 0 | both presets | **untouched** |
| `~/.mt5-fpmarkets` (research XAUUSD.r + US30/US100) | 0 / 0 | 0 / 0 | both presets | **untouched** |
| `~/.mt5-wsf` (live; no gold/index chart in use) | 0 / 0 | 0 / 0 | both presets | **untouched** |
| `~/.mt5-exness`, `~/.mt5` | sources + presets copied | sources copied | both presets | not compiled (no live gold/index test) |

Headers after copy still say **CLOSED / observe-only / Never OrderSend**.
`GoldSessionScalp` v1.10 has no `OrderSend`. Logger presets are on disk only;
`ForexSignalLogger` was **not** attached (that path wants Algo Trading green).

### Live readonly probe (2026-09-11)

| Prefix | `mt5-arch ping` | Heartbeat | Open chart | Overlay on chart |
|--------|-----------------|-----------|------------|------------------|
| Vantage | OK (file bridge) | fresh; writer EURUSD | **XAUUSD M1** in GUI; saved profile also DJ30.r / NAS100.r | **UsIndexSessionScalp is on the XAUUSD chart (wrong event).** UsIndex is correctly on DJ30.r M15. Gold overlay compiled, **not** auto-attached. |
| WSF | OK | fresh; writer EURUSDc | EURUSDc H1 | neither overlay attached |
| FP Markets | fail closed | stale ~45.6 h | terminal/EA not writing | saved profile: UsIndex on US30 + US100; XAUUSD.r has no Gold overlay |

Official MT5 MCP (`user-mt5-official`) is down, so this session could not
`ChartIndicatorAdd`. Live `.chr` files were **not** rewritten while terminals
were open.

**Attach (human, observe-only):** Vantage Navigator → drop `GoldSessionScalp`
on **XAUUSD M5** (switch off M1). Remove `UsIndexSessionScalp` from that gold
chart — NY cash 09:30 OR is the wrong clock for metals. Leave UsIndex on
`DJ30.r` / FP `US30`/`US100`. Never use buffer 8 as an entry host.

Human-attached (2026-09-11): Vantage `Config/terminal.ini` now lists `GoldSessionScalp 1.10 (XAUUSD,M1)` after the user drop. Saved Default `chart01.chr` still shows UsIndex on XAUUSD (profile not flushed; Wine charts are not git).

---

## Honesty first

Gold M5 session-OR scalp **lost after costs**. The index overlay was built for
the **NY cash 09:30** print. “Most suitable to trade” comes from the index
scan, not from deploying gold. Deploying gold is so the two overlays can be
**seen** side by side — not so gold is traded.

Do **not** read gold PF ≈ 1 from unmodified index rules held to 15:45 ET as a
scalp win. That book is hours-long drift (median MAE ~15 vs scalp ~2).

---

## A. Each on its intended market (primary ranking)

n / WR / PF / net are the **selection** slice used by that book (gold official
pick = select ≤ 2025-10-31; index scan = develop, ET date < 2026-06-01).
Holdout is evaluation-only and did **not** pick a winner.

| symbol | family | n | WR | PF | net | costs | window | session fit | verdict |
|--------|--------|--:|---:|---:|----:|-------|--------|-------------|----------|
| XAUUSD.r (FP M5) | `xau_london_defined_r_be_flat_v1` `tpr1_be0_ts6` | 230 | 47.8% | **0.83** | −$5,886 | slip 10 UNMEAS + spr cap 40 + $0 comm; XAU contract 100; 1 lot | select 2025-04-03→2025-10-31 (tape→2026-09-01) | London 08:00 + NY **metals** 08:00 — **not** cash 09:30 | **killed** |
| XAUUSD.r (FP M5) | `xau_london_orb_overlap_vwap_ema_flat` (adjusted overlay) | 381 | 43.0% | **0.82** | −$13,157 | same gold book | develop →2025-12-31 | London 30m OR + NY metals | **killed** |
| US30 (Dukascopy M5) | `ny_cash_orb_vwap_ema_flat` | 334 | 53.6% | **1.27** | +$8,225 | slip 10 UNMEAS + **assumed 60** + $0 comm; idx contract 1 | develop <2026-06-01 (tape 2025-01-01→2026-09-09) | NY cash 09:30 | **tradeable observe** (scan pick; holdout PF **0.43**) |
| US30 (FP M5) | `ny_cash_orb_vwap_ema_flat` | 150 | 50.0% | **1.20** | +$2,539 | slip 10 UNMEAS + **tape spr med 140** + $0 comm | develop <2026-06-01 (tape 2025-10-12→2026-09-08) | NY cash 09:30 | **tradeable observe** (cost-honest twin; holdout PF **0.50**) |
| US30m (Exness M5) | `ny_cash_orb_vwap_ema_flat` | 141 | 53.2% | 1.18 | +$2,412 | slip 10 UNMEAS + tape spr med 21 | develop <2026-06-01 | NY cash 09:30 | tradeable observe (same holdout fail, PF 0.48) |
| US500 (Dukascopy M5) | `ny_cash_orb_vwap_ema_flat` | 358 | 53.6% | 1.15 | +$735 | slip 10 UNMEAS + assumed 60 | develop <2026-06-01 | NY cash 09:30 | tradeable observe — **eval note only** (holdout PF 1.36; not the pick) |
| US100 (Dukascopy M5) | `ny_cash_orb_vwap_ema_flat` | 349 | 55.6% | 1.08 | +$1,754 | slip 10 UNMEAS + assumed 60 | develop <2026-06-01 | NY cash 09:30 | tradeable observe (holdout PF 0.88) |
| US2000 (Dukascopy M5) | `ny_cash_orb_vwap_ema_flat` | 267 | 52.8% | 1.01 | +$13 | slip 10 UNMEAS + assumed 60 | develop <2026-06-01 | NY cash 09:30 | tradeable observe (flat after costs) |
| US100 (FP M5) | `ny_cash_orb_vwap_ema_flat` | 149 | 43.0% | **0.72** | −$3,098 | slip 10 UNMEAS + tape spr med 60 | develop <2026-06-01 (archived flatten twin) | NY cash 09:30 | **killed** on this broker tape |
| ESP35 (Dukascopy M5) | `ny_cash_orb_vwap_ema_flat` | 261 | 56.3% | **1.38** | +$2,707 | slip 10 UNMEAS + assumed 60 | develop <2026-06-01 | Madrid 09:00 | **wrong event** (highest PF; coincidental overlap) |

Gold official extras (not used to pick; holdout sealed 2026-01-01): confirm
n=40 WR 45.0% PF 0.72 net −$2,351; develop n=270 WR 47.4% PF 0.81 net −$8,237;
holdout n=226 WR 44.2% PF 0.78 net −$14,126. 0/16 defined-R cells eligible.

Vantage `DJ30.r` M5 (100,006 bars, tape spr med **310**) is a **poor broker
fit**, not a model retune: develop n=1 because spread exceeds the locked 200-pt
research cap. WSF `DJ30.c` had no usable M5 cache in the scan.

### Most suitable to trade (if you trade anything)

**US30** — only name that is both the right event (NY cash 09:30) and the
highest locked develop PF among US-cash tapes (`dukascopy_US30` PF 1.27;
cost-honest `fpmarkets_US30` PF 1.20).

**Do not trade it as a live-go.** Holdout dies the same way the 2026-08-18
archived flatten said (Dukas 0.43 / FP 0.50). `promote=no`. Gold is not in
this ranking.

---

## B. Same-tape control (already known; restated)

Unmodified **index** rules on **gold** vs the gold-adjusted overlay. Both
already run. Same FP XAUUSD.r M5 tape + gold cost book unless noted.

| symbol | family | n | WR | PF | net | costs | window | session fit | verdict |
|--------|--------|--:|---:|---:|----:|-------|--------|-------------|----------|
| XAUUSD.r (FP M5) | `ny_cash_orb_vwap_ema_flat` flatten **15:45 ET** | 191 | 52.4% | **1.01** | +$2,302 | gold book (slip 10 + cap 40) | develop →2025-12-31 | US **cash** 09:30 on metals | **wrong event** — not a scalp |
| XAUUSD.r (FP M5) | same, holdout (eval) | 168 | 47.0% | 1.23 | +$62,057 | same | ≥2026-01-01 | US cash 09:30 on metals | eval-only melt-up; still not a scalp |
| XAUUSD.r (FP M5) | `xau_london_orb_overlap_vwap_ema_flat` | 381 | 43.0% | 0.82 | −$13,157 | same | develop →2025-12-31 | London + NY metals | **killed** (true scalp hold, med MAE ~2.6) |
| XAUUSD (Vantage M15) | `ny_cash_orb_vwap_ema_flat` flatten 15:45 | 770 | 50.0% | **1.11** | +$48,332 | gold book | develop (tape 2022-06-06→2026-08-28) | US cash 09:30 on metals | **wrong event** — M15 trend hold, not this overlay |
| XAUUSD (Vantage M15) | `xau_london_orb_overlap_vwap_ema_flat` | 1684 | 45.5% | 0.83 | −$49,284 | gold book | develop | London + NY metals | **killed** |

The 15:45 flatten PF≈1 (M5) / 1.11 (M15) is a **multi-hour gold drift ride**
(median MAE ~15 on FP M5, ~8 on Vantage M15). Gold does not print US cash
09:30. Relabeling that as `GoldSessionScalp` would be a lie.

---

## Sources (frozen; not recomputed)

- Gold official: `results/xau_session_scalp/defined_r_v1_primary.json` + `STATUS.md` + `KILLED.md`
- Gold same-tape: `results/xau_session_scalp/{baseline,adjusted}.json` and `vantage_m15_transfer/`
- Index archived flatten: `results/us_index_session_scalp_backtest.md` (US100 PF 0.72 / US30 develop 1.20 holdout 0.50)
- Index universe: sibling `results/index_session_scan/{ANALYSIS.md,ranking.json}` (2026-09-10)

---

## Files written / touched this pass

- This file (gold worktree).
- Pointer: sibling `results/indicator_compare_gold_vs_index.md`.
- HOWTO / docs index one-liners on this worktree.
- Wine prefix overlay sources + `.ex5` + logger presets (not git).
- **Not** committed. **Not** `xau_research_costs.json`. **Not** `strategy_params.json`. **Not** `xau_loop_status.md`.
