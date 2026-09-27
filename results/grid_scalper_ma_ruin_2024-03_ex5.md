# Grid Scalper MA MT5 — official `.ex5` ruin run

Not a `family_id`. `promote=no`. Lock: `results/grid_scalper_ma_ruin_lock.md`.

Machine: `results/grid_scalper_ma_ruin_2024-03_ex5.json`.
Scaled inputs: `results/grid_scalper_ma_2digit.set`.

## What actually ran

- Expert `Market\Grid Scalper MA MT5 EA` (Market 133466, licensed on Vantage, Community `FredyA`)
- Venue **Vantage `XAUUSD` M15** via the official Strategy Tester (in-process MCP). FP copy still dies with license 538; FP has no Market tab.
- Window **2024.03.01 → 2024.03.31** (1 840 bars, 2 288 847 generated ticks)
- Deposit **$10 000** / leverage **1:100** / optimize **off**
- Model **every tick generating** (no March 2024 `.tkc`; lock fallback from model 4)
- Inputs: **binary defaults**, point fields **÷ 10**. Not a retune.

Binary defaults that differ from the product page (logged, not changed):

| Input | Page | Binary dump | 2-digit used |
|---|---|---|---|
| `signalStrategy` | Price vs MA | **1 = BOS** | 1 |
| `inpTp_Points` / `inpGridSize` / `inpSl_Points` | 11000 | 11000 | **1100** |
| `inpBreakevenPts` | 50 | 50 | **5** |
| `inpRecoveryExtraPts` | 100 | 100 | **10** |
| `trailingStopPoints` | 30 | **300** | **30** |
| `minProfitPoints` | 100 | **1000** | **100** |
| `inpRecoveryPercent` / `inpGeomRangePct` | 30 / 50 | 30 / 50 | left as percents |

`slMode=0`, `basketTradeCap=0`, `basketsCap=0`, `dailyDrawdownMode=0`, start lot **0.01**, multiplier **1.5**.

## Allowed reading

| Metric | Value |
|---|---|
| Stop-out | **No** (no stop-out / margin-call line in the tester journal) |
| Final balance | **$10 305.97** (net **+$305.97**) |
| Equity floor / max equity DD | **$3 567** / **$6 437 (64.3%)** |
| Balance floor / max balance DD | **$8 447** / **$1 595 (15.9%)** |
| Trades / deals | 90 / 180 (68–22) |
| Tightest reported margin level | **96.7%** |
| Max ladder lot that filled | **0.58** (Basket 1 SELL, 2024-03-08) |
| Next add | **0.86 blocked** — “pre-trade checks”, ladder held at 0.58 |

Basket 1 was a **SELL grid into the March gold rally**. Adds: 0.01 → 0.02 → 0.02 → 0.03 → 0.05 → 0.08 → 0.11 → 0.17 → 0.26 → 0.38 → 0.58. Overlapping long baskets kept opening on BOS buys at the same time.

## What this is not

Do not read +$306 or PF 1.18 as an edge. The reconstruction on M15 OHLC / Price-vs-MA (`+$56`, 2.4% DD) was the advertisement shape. The compiled EA default is **BOS**, every-tick, no SL, no basket cap. March 2024 put it **64% underwater** and one refused add from a ~1 lot SELL stack. It survived $10k / 0.01 because the ladder was blocked, not because the idea is safe.

A larger start lot, real ticks, or a cleaner one-way stretch is a **new lock**, not a retune of this one.
