# HTF Fib XAU — widen entries post-fix (develop only)

**Timestamp (UTC):** 2026-08-06T17:09:41Z
**Window:** develop only (`time < 2026-01-01 00:00:00+00:00`); holdout sealed unused
**Safety:** offline research only; never --live; develop only; holdout unused
**n_ablations:** 50 | **secondary_evals:** 150

## Pre-registered floors
```json
{
  "profit_factor": 1.3,
  "max_drawdown_pct": 10.0,
  "n_trades_min": 20,
  "n_trades_target": 30,
  "win_rate_diagnostic_floor": 50.0,
  "expectancy_min": 15.0
}
```

## Baseline champion (post-fix deep-opt freeze)

- Params: `{"be_at_r": null, "cooldown": 1, "fib_hi": 0.786, "fib_lo": 0.618, "flat_only": true, "h4_bias": false, "hours": null, "long_only": true, "max_entries_per_day": 2, "pivot_left": 5, "pivot_right": 3, "require_ema200_bias": false, "risk_pct": 0.01, "rsi_long_max": 35.0, "rsi_short_min": 60.0, "sl_atr": 1.2, "tp_atr": 3.0, "use_rsi_ma_filter": false}`
- PF=3.584 WR=58.8% DD=3.75% n=17 NP=1795.5 exp√n=435.5
- n_path_score=894.8 | hard_pass_n_path=**False** (n≥20: False)

## Ablation ranking

| Rank | Tag | PF | WR% | DD% | n | NP | exp√n | score | Δscore | gate |
|-----:|-----|---:|----:|----:|--:|---:|------:|------:|-------:|:----:|
| 1 | `pack_wide_0382_786_rsi50` | 1.164 | 32.0 | 11.52 | 128 | 1395 | 123.3 | 1688.8 | +794.0 | n |
| 2 | `pack_fast_pivot_2_2_wide` | 1.185 | 32.5 | 9.16 | 114 | 1371 | 128.4 | 1638.7 | +743.8 | n |
| 3 | `fib=0.382-0.786` | 2.384 | 48.5 | 4.57 | 33 | 2264 | 394.1 | 1258.3 | +363.5 | Y |
| 4 | `pack_very_wide_050_100` | 1.112 | 30.7 | 14.29 | 114 | 789 | 73.9 | 1215.6 | +320.7 | n |
| 5 | `pack_wide_050_886_cd0` | 1.189 | 32.1 | 10.64 | 81 | 1059 | 117.7 | 1213.1 | +318.2 | n |
| 6 | `fib=0.382-0.886` | 1.860 | 43.2 | 4.61 | 37 | 1754 | 288.4 | 1163.2 | +268.3 | Y |
| 7 | `fib=0.5-1.0` | 1.747 | 41.7 | 5.43 | 36 | 1594 | 265.7 | 1118.7 | +223.9 | Y |
| 8 | `pack_balanced_n_quality` | 1.393 | 40.9 | 5.88 | 44 | 945 | 142.5 | 1066.8 | +172.0 | Y |
| 9 | `sl_atr=1.0` | 4.139 | 58.8 | 4.24 | 17 | 2311 | 560.5 | 1043.0 | +148.2 | n |
| 10 | `be_at_r=1.5` | 8.724 | 58.8 | 2.38 | 17 | 2269 | 550.4 | 1032.2 | +137.4 | n |
| 11 | `rsi_long_max=40.0` | 1.546 | 38.9 | 5.16 | 36 | 1177 | 196.2 | 1029.7 | +134.8 | Y |
| 12 | `rsi_long_max=45.0` | 1.212 | 34.0 | 9.73 | 53 | 720 | 99.0 | 1015.8 | +121.0 | n |

## Key factor deltas

- `use_rsi_ma_filter=True`: Δscore=-3034.8
- `pivot_L5_R5`: Δscore=-1918.8
- `pivot_L3_R5`: Δscore=-1321.2
- `pack_wide_0382_786_rsi50`: Δscore=+794.0
- `pivot_L8_R5`: Δscore=-771.1
- `pack_fast_pivot_2_2_wide`: Δscore=+743.8
- `fib=0.705-0.786`: Δscore=-707.5
- `require_ema200_bias=True`: Δscore=-635.8
- `rsi_long_max=30.0`: Δscore=-606.6
- `fib=0.5-0.618`: Δscore=-582.6
- `sl_atr=2.5`: Δscore=-379.7
- `fib=0.382-0.786`: Δscore=+363.5
- `tp_atr=4.0`: Δscore=-360.1
- `pack_very_wide_050_100`: Δscore=+320.7
- `pack_wide_050_886_cd0`: Δscore=+318.2

## Secondary search top

| Rank | PF | WR% | DD% | n | NP | score | gate | highlight |
|-----:|---:|----:|----:|--:|---:|------:|:----:|-----------|
| 1 | 1.282 | 39.2 | 7.55 | 125 | 2056 | 2077.0 | n | `{"cooldown": 1, "fib_hi": 1.0, "fib_lo": 0.382, "max_entries_per_day": 3, "pivot_left": 3, "pivot_right": 3, "rsi_long_max": 50.0}` |
| 2 | 1.303 | 38.3 | 8.44 | 115 | 2130 | 1986.2 | Y | `{"cooldown": 1, "fib_hi": 0.786, "fib_lo": 0.5, "max_entries_per_day": 3, "pivot_left": 3, "pivot_right": 2, "rsi_long_max": 50.0}` |
| 3 | 1.170 | 36.0 | 11.60 | 136 | 1422 | 1787.2 | n | `{"cooldown": 1, "fib_hi": 0.886, "fib_lo": 0.382, "max_entries_per_day": 3, "pivot_left": 3, "pivot_right": 3, "rsi_long_max": 50.0}` |
| 4 | 1.191 | 32.3 | 11.41 | 127 | 1615 | 1758.2 | n | `{"cooldown": 1, "fib_hi": 0.786, "fib_lo": 0.382, "max_entries_per_day": 2, "pivot_left": 3, "pivot_right": 3, "rsi_long_max": 50.0}` |
| 5 | 1.224 | 37.7 | 10.00 | 106 | 1402 | 1712.9 | n | `{"cooldown": 1, "fib_hi": 0.886, "fib_lo": 0.5, "max_entries_per_day": 3, "pivot_left": 3, "pivot_right": 2, "rsi_long_max": 50.0}` |
| 6 | 1.219 | 37.4 | 9.20 | 107 | 1371 | 1709.0 | n | `{"cooldown": 0, "fib_hi": 0.886, "fib_lo": 0.382, "max_entries_per_day": 2, "pivot_left": 5, "pivot_right": 3, "rsi_long_max": 50.0}` |
| 7 | 1.124 | 31.5 | 13.52 | 143 | 1190 | 1666.8 | n | `{"cooldown": 1, "fib_hi": 1.0, "fib_lo": 0.382, "max_entries_per_day": 2, "pivot_left": 3, "pivot_right": 2, "rsi_long_max": 50.0}` |
| 8 | 1.422 | 42.2 | 5.02 | 83 | 2128 | 1649.1 | Y | `{"cooldown": 2, "fib_hi": 0.786, "fib_lo": 0.382, "max_entries_per_day": 3, "pivot_left": 8, "pivot_right": 2, "rsi_long_max": 45.0}` |

## Best develop candidate (NOT holdout-confirmed)

- Source: **secondary_search** tag=`refine_top1`
- PF=1.282 WR=39.2% DD=7.55% n=125 NP=2056.0
- hard_pass_n_path: **False** | n_target≥30: **True**
- Params: `{"be_at_r": null, "cooldown": 1, "fib_hi": 1.0, "fib_lo": 0.382, "flat_only": true, "h4_bias": false, "hours": null, "long_only": true, "max_entries_per_day": 3, "pivot_left": 3, "pivot_right": 3, "require_ema200_bias": false, "risk_pct": 0.01, "rsi_long_max": 50.0, "rsi_short_min": 60.0, "sl_atr": 1.5, "tp_atr": 3.0, "use_rsi_ma_filter": false}`

## Best gate-pass candidate

- Source: **secondary_search** tag=`refine_gate_pass`
- PF=1.303 WR=38.3% DD=8.44% n=115 NP=2129.7
- Params: `{"be_at_r": null, "cooldown": 1, "fib_hi": 0.786, "fib_lo": 0.5, "flat_only": true, "h4_bias": false, "hours": null, "long_only": true, "max_entries_per_day": 3, "pivot_left": 3, "pivot_right": 2, "require_ema200_bias": false, "risk_pct": 0.01, "rsi_long_max": 50.0, "rsi_short_min": 60.0, "sl_atr": 1.2, "tp_atr": 2.5, "use_rsi_ma_filter": false}`

## Disposition

- Lane **KEEP_OPTIMIZING** (not KILL).
- Baseline n=17 MISSES n≥20.
- Best n=125 (Δn +108 vs baseline).
- **No holdout re-eval** this fire (prior HO n=14 underpowered + contaminated window).
- Live promote: **NO-GO**. After this fire, develop work on KEEP_OPTIMIZING lanes is largely done; next is virgin holdout when bars exist after 2026-08-06, or optional deeper refine without holdout peeks.

*Offline research only; never --live.*
