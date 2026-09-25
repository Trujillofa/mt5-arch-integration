# Grid Scalper MA MT5 — official `.ex5` ruin run (2026 YTD)

Not a `family_id`. `promote=no`. Lock: `results/grid_scalper_ma_ruin_2026_lock.md`.

Machine: `results/grid_scalper_ma_ruin_2026_ex5.json`.
Same scaled inputs as March: `results/grid_scalper_ma_2digit.set`. **No retune.**

## What actually ran

- Expert `Market\Grid Scalper MA MT5 EA` (Market 133466, licensed on Vantage, Community `FredyA`)
- Venue **Vantage `XAUUSD` M15** via the official Strategy Tester. FP still cannot load this EA (license 538 / no Market tab).
- Window **2026.01.01 → 2026.09.11** (YTD; year not closed). Tester end is exclusive: last simulated trades are **2026.09.10**.
- 16 396 bars, 107 138 029 generated ticks. Test wall time 0:05:35.
- Deposit **$10 000** / leverage **1:100** / optimize **off**
- Model **every tick generating** (journal: no `real ticks` line). History synchronized 2023.01.03–2026.09.11.
- Inputs: **same binary defaults**, point fields **÷ 10**. Confirmed `inpTp_Points=1100`.

MCP `tester_run_backtest` timed out (`-32001`) so there is no `run_id`. The tester **kept running and finished**. Numbers below come from the official Tester `.tst` cache (same byte layout as the March JSON, which matched `tester_get_report`) plus the Core 01 journal (`final balance 11965.78`, bars/ticks, no stop-out).

## Allowed reading

| Metric | Value |
|---|---|
| Stop-out | **No** (no stop-out / margin-call / “not enough money” line) |
| Final balance | **$11 965.78** (net **+$1 965.78**) |
| Equity floor / max equity DD | **$7 672** / **$3 771 (33.0%)** |
| Balance floor / max balance DD | **$9 970** / **$1 473 (12.9%)** |
| Trades / deals | 901 / 1 802 (779–122) |
| Tightest reported margin level | **167.3%** |
| Max ladder lot that filled | **0.38** (Basket 1 BUY, 2026-06-11 02:15) |
| Next add | **not taken** — price bounced to basket TP 11 minutes later. No `blocked` line in this window. |

Deepest stretch was a **BUY grid into the 10–11 June dump**, ~9.5 hours open (17:00 Jun 10 → 02:26 Jun 11). Adds: 0.01 → 0.02 → 0.02 → 0.03 → 0.05 → 0.08 → 0.11 → 0.17 → 0.26 → **0.38**. Flatten printed the run’s max balance loss (**−$1 473** mid-close) and max single win (**+$1 050** on the 0.38). Overlapping SELL baskets were open on the way down.

Second-deepest printed ladder: **SELL** into the 11 August bounce, peaked at **0.26**, closed 07:55 the same morning.

## What this is not

Do not read +$1 966 or PF 1.48 as an edge. 2026 YTD is a **milder** window than March 2024 (33% equity DD vs 64%; 0.38 lots vs 0.58 and a blocked 0.86; margin 167% vs 97%). It survived $10k / 0.01 because the June dump reversed before the next 1.5× add, not because the idea is safe.

A larger start lot, real ticks, the rest of 2026, or a cleaner one-way stretch is a **new lock**, not a retune of this one.
