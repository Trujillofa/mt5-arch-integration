# Donchian turtle — expectancy-centric develop ablations

**Timestamp (UTC):** 2026-08-06T17:03:48Z
**Window:** develop only (`time < 2026-01-01 00:00:00+00:00`); holdout sealed / unused
**Safety:** offline research only; never --live; develop only; holdout unused
**n_ablations:** 47 | **secondary_refine_evals:** 120

## Pre-registered promote gates (before ranking)

### Develop diagnostic (expectancy thesis)
```json
{
  "profit_factor": 1.5,
  "expectancy": 20.0,
  "expectancy_sqrt_n": 150.0,
  "max_drawdown_pct": 12.0,
  "n_trades": 40,
  "win_rate_floor_diagnostic_only": 35.0,
  "note": "WR>55 classic hard gate is MISMATCHED for turtles; not used for pass/fail here"
}
```

### Future virgin holdout (not run this fire)
```json
{
  "profit_factor": 1.4,
  "expectancy": 15.0,
  "expectancy_sqrt_n": 80.0,
  "max_drawdown_pct": 12.0,
  "n_trades": 20,
  "win_rate": null,
  "win_rate_note": "WR not a hard gate for turtle promote claims; report only",
  "require_virgin_bars": true,
  "forbid_retune_on_holdout": true
}
```

## Baseline champion (frozen from deep opt)

- Params: `{"atr_min_pct": null, "atr_sl": 1.5, "be_at_r": null, "cooldown": 2, "entry_N": 20, "exit_N": 10, "exit_on_exit_channel": true, "failed_breakout_fade": false, "h4_bias": false, "hours": null, "long_only": true, "max_entries_per_day": 2, "mid_channel_k": null, "partial_tp": false, "risk_pct": 0.01}`
- PF=2.271 WR=43.4% DD=9.22% n=129 NP=15180.0
- expectancy=117.67 exp√n=1336.5 score=1560.3
- Pre-reg develop hard_pass_expectancy: **True**

## Ablation ranking (develop score_expectancy_sqrt)

| Rank | Tag | PF | WR% | DD% | n | NP | exp | exp√n | score | vs base Δscore |
|-----:|-----|---:|----:|----:|--:|---:|----:|------:|------:|---------------:|
| 1 | `exit_channel_off_be_1.0` | 64.261 | 4.3 | 21.47 | 23 | 17784 | 773.2 | 3708.1 | 3910.7 | +2350.4 |
| 2 | `atr_sl=1.0` | 2.253 | 35.3 | 13.03 | 150 | 23239 | 154.9 | 1897.5 | 2211.4 | +651.1 |
| 3 | `exit_N=8` | 2.409 | 44.4 | 7.92 | 133 | 17252 | 129.7 | 1496.0 | 1747.8 | +187.4 |
| 4 | `exit_N=20` | 2.470 | 37.1 | 12.15 | 105 | 14768 | 140.6 | 1441.2 | 1661.4 | +101.1 |
| 5 | `baseline_champion` | 2.271 | 43.4 | 9.22 | 129 | 15180 | 117.7 | 1336.5 | 1560.3 | +0.0 |
| 6 | `max_entries_per_day=3` | 2.271 | 43.4 | 9.22 | 129 | 15180 | 117.7 | 1336.5 | 1560.3 | +0.0 |
| 7 | `mid_channel_k=0.5` | 2.271 | 43.4 | 9.22 | 129 | 15180 | 117.7 | 1336.5 | 1560.3 | +0.0 |
| 8 | `mid_channel_k=1.0` | 2.271 | 43.4 | 9.22 | 129 | 15180 | 117.7 | 1336.5 | 1560.3 | +0.0 |
| 9 | `failed_breakout_fade=True` | 2.271 | 43.4 | 9.22 | 129 | 15180 | 117.7 | 1336.5 | 1560.3 | +0.0 |
| 10 | `cooldown=0` | 2.271 | 43.4 | 9.22 | 129 | 15180 | 117.7 | 1336.5 | 1560.3 | +0.0 |
| 11 | `cooldown=1` | 2.271 | 43.4 | 9.22 | 129 | 15180 | 117.7 | 1336.5 | 1560.3 | +0.0 |
| 12 | `cooldown=4` | 2.277 | 44.1 | 9.29 | 127 | 14950 | 117.7 | 1326.6 | 1547.6 | -12.7 |

## Key one-factor effects (delta score vs baseline)

- `exit_channel_off_be_1.0`: Δscore=+2350.4
- `exit_channel_off`: Δscore=-2056.3
- `be_at_r=0.5`: Δscore=-1721.5
- `pack_h4_be_max1`: Δscore=-1535.4
- `be_1.0_plus_partial_1.5`: Δscore=-1356.7
- `pack_be_partial_exit12`: Δscore=-1313.7
- `h4_bias=True_be_1.0`: Δscore=-1308.5
- `partial_tp_r=1.0_frac=0.5`: Δscore=-1274.6
- `be_1.0_plus_partial_1.0`: Δscore=-1274.6
- `be_at_r=1.0`: Δscore=-1187.1
- `pack_partial_exit8_atr2`: Δscore=-1052.8
- `atr_sl=3.0`: Δscore=-997.1
- `partial_tp_r=1.5_frac=0.67`: Δscore=-988.6
- `partial_tp_r=1.5_frac=0.5`: Δscore=-896.1
- `atr_sl=2.5`: Δscore=-887.1

## Secondary refine top (Cartesian neighborhood, develop only)

| Rank | PF | WR% | DD% | n | NP | exp√n | score | highlight params |
|-----:|---:|----:|----:|--:|---:|------:|------:|------------------|
| 1 | 2.278 | 43.2 | 9.43 | 132 | 15235 | 1326.1 | 1550.7 | `{"atr_sl": 1.5, "be_at_r": null, "entry_N": 20, "exit_N": 8, "h4_bias": false, "max_entries_per_day": 1, "partial_tp": false}` |
| 2 | 2.598 | 43.8 | 8.88 | 96 | 12682 | 1294.3 | 1491.8 | `{"atr_sl": 1.5, "be_at_r": null, "entry_N": 30, "exit_N": 15, "h4_bias": false, "max_entries_per_day": 1, "partial_tp": false}` |
| 3 | 2.278 | 40.4 | 13.13 | 114 | 13708 | 1283.9 | 1478.0 | `{"atr_sl": 1.5, "be_at_r": null, "entry_N": 20, "exit_N": 15, "h4_bias": false, "max_entries_per_day": 1, "partial_tp": false}` |
| 4 | 2.224 | 43.0 | 10.52 | 128 | 14083 | 1244.8 | 1454.2 | `{"atr_sl": 1.5, "be_at_r": null, "entry_N": 20, "exit_N": 10, "h4_bias": false, "max_entries_per_day": 1, "partial_tp": false}` |
| 5 | 2.364 | 40.0 | 10.18 | 105 | 12480 | 1217.9 | 1409.4 | `{"atr_sl": 1.5, "be_at_r": null, "entry_N": 24, "exit_N": 15, "h4_bias": false, "max_entries_per_day": 1, "partial_tp": false}` |
| 6 | 2.142 | 41.0 | 11.46 | 122 | 13021 | 1178.9 | 1373.8 | `{"atr_sl": 1.5, "be_at_r": null, "entry_N": 20, "exit_N": 12, "h4_bias": false, "max_entries_per_day": 1, "partial_tp": false}` |
| 7 | 2.330 | 42.5 | 8.76 | 113 | 12325 | 1159.4 | 1348.4 | `{"atr_sl": 1.5, "be_at_r": null, "entry_N": 30, "exit_N": 8, "h4_bias": false, "max_entries_per_day": 1, "partial_tp": false}` |
| 8 | 2.221 | 41.5 | 9.55 | 123 | 12508 | 1127.8 | 1317.5 | `{"atr_sl": 1.5, "be_at_r": null, "entry_N": 24, "exit_N": 8, "h4_bias": false, "max_entries_per_day": 1, "partial_tp": false}` |

## Best develop candidate (ablation ∪ refine; NOT holdout-confirmed)

- Source: **ablation** / tag=`exit_channel_off_be_1.0`
- PF=64.261 WR=4.3% DD=21.47% n=23 NP=17783.5 exp√n=3708.1
- Pre-reg develop hard_pass_expectancy: **False**
- Params: `{"atr_min_pct": null, "atr_sl": 1.5, "be_at_r": 1.0, "cooldown": 2, "entry_N": 20, "exit_N": 10, "exit_on_exit_channel": false, "failed_breakout_fade": false, "h4_bias": false, "hours": null, "long_only": true, "max_entries_per_day": 2, "mid_channel_k": null, "partial_tp": false, "risk_pct": 0.01}`

## Disposition

- Lane remains **KEEP_OPTIMIZING** (not KILL).
- Baseline already meets pre-reg develop expectancy gates: **True**.
- Classic WR>55 gate still fails on turtle shapes by design — do not kill on WR.
- **No holdout re-eval this fire** (contaminated window; virgin bars not available past last peek).
- Live promote: **NO-GO**. Next: optional atr_trail trade-count work, or virgin holdout when data > last peeked end.

*Offline research only; never --live.*
