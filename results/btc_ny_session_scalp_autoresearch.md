# BTC NY-desk overlap develop screen (`btc_ny_session_scalp_develop_v1`)

| Field | Value |
|-------|-------|
| **Search** | `btc_ny_session_scalp_develop_v1` |
| **Disposition** | **SCREEN_FAIL** |
| **Overlay default** | `btc_ny_overlap_vwap_ema_flat` |
| **Configs** | 96 (eligible 0) |
| **Holdout** | `2026-03-01` unused for selection |
| **promote / live_go** | no / false |

Machine JSON: `results/btc_ny_session_scalp_autoresearch.json`.

## Best develop

No develop-eligible config (`trades>=40` and `net_pnl>0`). SCREEN_FAIL.

## Transfers (never ranked)

- `index_transfer` develop n=208 PF=1.0794512985129736 net=8752.68
- `gold_transfer` develop n=326 PF=0.72107267255589 net=-8736.86

## Null (a-priori VWAP+EMA cell)

frac_null_ge_real = 1.00 over 10 seeds.

Do not promote. Do not reopen closed theses. Do not edit `results/xau_loop_status.md`.

## Best-of-family (develop, not eligible)

| Family | n | WR | PF | Net |
|--------|--:|---:|---:|----:|
| `btc_ny_overlap_vwap_ema_flat` | 217 | 37.8% | 0.7023226395665297 | -6056.80 |
| `btc_ny_overlap_atr_drive` | 0 | 0.0% | 0.0 | 0.00 |
| `btc_ny_overlap_htf_pullback` | 188 | 43.1% | 0.747015083851638 | -5673.73 |

Index transfer develop PF ~1.08 is the 15:45 flatten **drift ride**, not a scalp (holdout PF 0.88). Do not promote it.

