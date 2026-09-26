# Grid Scalper MA MT5 — ruin study lock (frozen before tester)

Not a `family_id`. Not a develop screen. Not an edge hunt.
`promote=no`. `live_go=false`. No OrderSend. Live Vantage left running.

| Field | Frozen value |
|---|---|
| Product | Market 133466 Grid Scalper MA MT5 EA v11.48 |
| Venue | `~/.mt5-fpmarkets` / `XAUUSD.r` (2-digit, point 0.01) — idle prefix |
| Why not Vantage | Live book open; tester would kill `terminal64` |
| Window | **2024.03.01 → 2024.03.31** (named first: March 2024 gold breakout) |
| Deposit / leverage | $10 000 / 1:100 |
| Model | `4` every tick based on real ticks; fallback `0` generated ticks if no `.tkc` |
| Period | M15 |
| Inputs | Published defaults, **point fields ÷ 10** for 2-digit gold |
| Optimize | **No** |
| Allowed reading | stop-out / max DD / max lots / time underwater |
| Forbidden reading | PF as edge; retune after look; the 2024-03 JSON as evidence (same-bar high after low adds understated ruin) |

Point scale (author: 3-digit defaults → divide by ten on 2-digit):

- Take profit / grid size / SL: `11000` → `1100` ($11)
- Extra profit / min trail activate: `100` → `10`
- Trailing / breakeven: `30`/`50` → `3`/`5`
