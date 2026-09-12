# BTC trend-pullback develop screen (`btc_trend_pullback_develop_v1`)

| Field | Value |
|-------|-------|
| **Search** | `btc_trend_pullback_develop_v1` |
| **Disposition** | **SCREEN_PASS_CANDIDATE** |
| **Overlay default** | `btc_h4bias_h1_full_grammar` |
| **Configs** | 192 (eligible 91) |
| **Holdout** | `2026-04-01` unused for selection |
| **promote / live_go** | no / false |

Machine JSON: `results/btc_trend_pullback_autoresearch.json`.

## Best develop

`btc_h4bias_h1_full_grammar|sl_atr1.5|tp_r2.0|time_stop_bars24|min_atr_pct0.01|one_per_day1|long_only1` develop n=44 WR 47.7% PF 1.4180709981248414 net=9709.32.
Holdout (eval only) n=**0** — unevaluable. A sparse cell that barely clears `trades>=40` and then goes silent on the holdout is not a paper candidate.

A-priori cell (shipped-indicator analog: full_grammar, SL 2.0 ATR, TP 2.0 R, ts 48, min_atr 1%, one-per-day, shorts on): develop n=137 WR 34.3% PF **0.94** net=−$6,933. Null `frac_null_ge_real = 0.60` on that PF — consistent with noise.

## Null (a-priori full_grammar cell)

frac_null_ge_real = 0.6 over 10 seeds.

Do not promote. Do not reopen closed theses. Do not edit `results/xau_loop_status.md`.
Do not re-rank by holdout (one eligible cell has holdout n=15 PF 1.60 — that is eval-only and was not the develop pick).

## Best-of-family (develop)

| Family | n | WR | PF | Net | eligible |
|--------|--:|---:|---:|----:|:--------:|
| `btc_h4bias_h1_pullback_reclaim` | 337 | 40.9% | 1.1432880435173856 | 22509.16 | True |
| `btc_h4bias_h1_continuation` | 186 | 43.0% | 1.238104566657109 | 18747.04 | True |
| `btc_h4bias_h1_full_grammar` | 44 | 47.7% | 1.4180709981248414 | 9709.32 | True |
