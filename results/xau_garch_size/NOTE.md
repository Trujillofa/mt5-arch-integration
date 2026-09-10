# XAU H1 GARCH size overlay — kill

| Field | Value |
|-------|--------|
| Date | 2026-09-09 |
| Overlay | `xau_h1_bb_rsi_garch11_invvol_size_v1` (**size overlay**, not a new search family) |
| Host | shipped `strategy_params.json` `bb_rsi` via `slice_to_window` (25 582 H1 bars → 2025-12-31) |
| Lock | `lock.json` — **frozen before** metrics |
| **Verdict** | **kill** — GARCH did not beat ATR-lot on develop after costs |
| promote / live_go | **no / false** |
| n | **42 develop trades is thin** |

`bb_rsi` was later null-killed as a **search** family. This probe does not revive it.
Signal (+1/−1, hours, SL/TP) stayed frozen. Overlay changed **lots only**.
Do not write `strategy_params.json`. Do not edit `results/xau_loop_status.md`.

## Pre-registered spec

- GARCH(1,1), variance targeting. EGARCH **not** searched.
- Expanding window, min 500 bars, refit every 120 H1 bars.
- Forecast at bar i uses log-returns **strictly before** i.
- Warmup fallback: ATR-lot until GARCH is ready.
- Size: `lot = 1% equity / (σ̂_ret × close × sl_atr × 100)`, cap 0.50 / floor 0.01.
- Sideline if σ̂_ret > expanding 95th percentile of **past** forecasts (5 develop trades).
- Constant-lot baseline frozen at **0.10**.
- Score (develop only): max PF, tie-break net. GARCH wins iff PF > ATR PF (or PF equal and NP higher).

## Costs

Official book: `results/xau_research_costs.json` — spread column, point 0.01,
commission 0 (Standard STP), **slippage_points=0 UNMEASURED**. Not a claim of
zero slip. Frictionless (no spread column) was not used. No assumed-slip
sensitivity was used to pick.

## Develop (selection; `utc < 2026-01-01` fit window)

| Book | n | WR | PF | Net | Max DD |
|------|--:|---:|---:|----:|-------:|
| constant 0.10 lot | 42 | 59.5% | 1.48 | +693 | 3.13% |
| **ATR-lot (host)** | **42** | **59.5%** | **1.67** | **+1 188** | **3.84%** |
| GARCH(1,1) inv-vol | 37 | 56.8% | 1.42 | +1 080 | 5.85% |

Winner by locked score: **atr_lot_host**. GARCH sidelined 5 high-σ trades and
lost on both PF and net. ATR-lot net **exactly** matches `strategy_params.json`
(+1 188.27, PF 1.671) — host replay is intact.

## Holdout (evaluate once; not used to pick)

| Book | n | WR | PF | Net | Max DD |
|------|--:|---:|---:|----:|-------:|
| constant 0.10 | 3 | 33% | 0.16 | −920 | 10.8% |
| ATR-lot | 3 | 33% | 0.60 | −71 | 1.76% |
| GARCH | 2 | 50% | 1.14 | +28 | 1.99% |

Holdout n=3 is not evidence. Do not retune from it.

## Kill vs continue

**Kill.** Inverse-vol GARCH did not beat the host ATR-lot after the official
cost book on the pre-registered develop window. Thin n, one overlay, no knob hunt.

GoldSessionScalp / the M5 defined-R grid were not reopened. Exogenous β was
not built.
