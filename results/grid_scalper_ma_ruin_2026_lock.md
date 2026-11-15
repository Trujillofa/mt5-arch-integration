# Grid Scalper MA MT5 — 2026 YTD ruin lock (frozen before tester)

Not a `family_id`. Not a develop screen. Not an edge hunt.
`promote=no`. `live_go=false`. No OrderSend. Same binary defaults as the March 2024 `.ex5` run — **no retune**.

| Field | Frozen value |
|---|---|
| Product | Market 133466 Grid Scalper MA MT5 EA v11.48 |
| Venue | Vantage `XAUUSD` (2-digit) via official Strategy Tester |
| Why not FP | license 538 / no Market tab |
| Window | **2026.01.01 → 2026.09.11** (YTD; year not closed) |
| Deposit / leverage | $10 000 / 1:100 |
| Model | `every tick` generated (real `.tkc` only exists for 2026.08–09) |
| Period | M15 |
| Inputs | `results/grid_scalper_ma_2digit.set` (binary defaults, points ÷ 10) |
| Optimize | **No** |
| Allowed reading | stop-out / max DD / max lots / time underwater |
| Forbidden reading | PF as edge; retune after look |
