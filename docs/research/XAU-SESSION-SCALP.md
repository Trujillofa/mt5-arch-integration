# GoldSessionScalp — design memo

| Field | Value |
|-------|--------|
| Date | 2026-09-09 |
| **Disposition** | **CLOSED** · **observe-only** · **promote=no** · **live_go=false** |
| Indicator | `GoldSessionScalp` v1.10 — chart overlay / research artifact. **Not a live entry host.** |
| Family | `xau_london_defined_r_be_flat_v1` (terminal; do not retune) |
| Supersedes | `xau_london_orb_overlap_vwap_ema_flat` |
| Status file | `results/xau_session_scalp/STATUS.md` |
| Kill inventory | `results/xau_session_scalp/KILLED.md` |
| Vs index overlay | `results/indicator_compare_gold_vs_index.md` |
| Holdout | **2026-01-01** — never for selection |

M5 London/NY session-OR scalp is **structurally cost-killed** on the FP M5
tape + gold cost book (point 0.01, contract 100, slip 10/side, spread cap 40).
The 80% WR + PF≥1 goal is **closed on this event class**.

Do **not** retune the frozen 16-cell defined-R grid, add cells, peek holdout
to salvage PF, swap this overlay onto indices, or chase 80% WR on sub-15m XAU.
Do **not** write `strategy_params.json` or edit `results/xau_loop_status.md`
from this track (loop stays `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`).

## Honest result (terminal; do not recompute)

Primary `tpr1_be0_ts6` (lock-before-metrics): select n=230 WR 47.8% PF 0.83.
0/16 cells eligible. Tight 0.35R printed WR 69.6% / PF 0.60 (trap, not 80%).
See `NOTE.md`, `defined_r_v1_pareto.json`, `80wr_next_steps.md`.

## User questions (answered; track closed)

**Best current gold indicator?** Only gold-*scalp* overlay in-repo.
`ForexHtfPivotsFib` is the other gold-capable indicator (H1/M15 swing fib).
"Only" ≠ edge.

**Can it be tuned?** Not on this family. A new `family_id` would need a
new horizon/structure, not more M5 knobs.

**80% WR + PF≥1 after costs?** No. Incompatible on this tape + cost model.

## Frozen combo (historical; v1.10)

Clock: London 30m OR, London VWAP, EMA 9/21, London + NY-metals boxes.
Risk: 1.0 ATR SL, 1.0R TP, 6-bar time-stop, no BE, OR-width [0.35, 2.5].
Select `≤ 2025-10-31`. Confirm Nov–Dec 2025. Holdout evaluate-once.

## Costs

`(spread_pts + 20) * 0.01 * 100` USD / lot. Frictionless books refused.

## If XAU research continues

See `docs/research/MATH-MODELS-ROADMAP.md`. This overlay is **not** a host
for GARCH or exogenous-β. Those were not started from this close-out.
