# Oil session scalp develop screen (`oil_session_scalp_develop_v1`)

| Field | Value |
|-------|-------|
| **Search** | `oil_session_scalp_develop_v1` |
| **Disposition** | **SCREEN_FAIL** |
| **Overlay default** | `oil_london_orb_vwap_ema_flat` |
| **Configs** | 96 (eligible 0) |
| **Holdout** | `2026-04-01` unused for selection |
| **promote / live_go** | no / false |

Machine JSON: `results/oil_session_scalp_autoresearch.json`.

## Best develop

No develop-eligible config (`trades>=40` and `net_pnl>0`). SCREEN_FAIL.

## Transfers (never ranked)

- `index_transfer` develop n=232 PF=0.7748960988266627 net=-19607.00
- `gold_transfer` develop n=352 PF=0.575346523934596 net=-13115.82
- `btc_transfer` develop n=248 PF=0.47519635046087366 net=-11613.23
- `eurusd_mr_transfer` develop n=247 PF=0.4476976780978926 net=-13059.13

## Null (a-priori London OR cell)

frac_null_ge_real = 1.00 over 10 seeds.

Do not promote. Do not reopen closed theses. Do not edit `results/xau_loop_status.md`.

## Signal-edge diagnostic (before the exit grid)

`python3 scripts/signal_edge_diagnostic.py --lane oil` on the stamped Vantage book
(develop `< 2026-04-01`, friction = 36.0 pts = p50 30 + 2×3.0 slip):

| Family | n | best mean pts | t | verdict |
|--------|--:|--------------:|--:|---------|
| oil_london_orb_vwap_ema_flat | 146 | +113.5 (H100) | 1.07 | DEAD |
| oil_ny_inventory_drive | 0 | — | — | EMPTY |
| oil_prior_day_reclaim | 158 | +39.8 (H20) | 1.09 | DEAD |

No family CLEARS-FRICTION. NY drive produced 0 fills. London / reclaim means above friction fail the t-gate. Frozen 96-cell grid still ran; 0/96 eligible (`trades>=40` and `net_pnl>0`). Best-of-family develop: reclaim PF 0.73 / net −$4139 (n=158); London PF 0.64 / net −$7019 (n=146). Holdout unused for selection.

## Book

Vantage `CL-OIL` M5 via Mt5ArchBridge `dump_history.request` (not Dukascopy, not USOUSD M15, not CL=F, not cTrader H1). 100,000 bars, 440 ET dates, server 2025-04-15 10:55 → 2026-09-11 23:55. Clock lag-0 vs cTrader XTIUSD H1 corr 0.946 (n=4745); constant-10800 rejected (0.004). SymbolInfo: digits 3, point 0.001, contract 1000, tick_value 1. Spread p50/p95 = 30/90; slip 3.0; typical RT $36.00. `sha256=7e55dab7b8b5fab3f4478cf2a420a4be771122858ecc4f211d6bc644c16dbbf2`.
