# ATR trail breakout — raise develop trade count

**Timestamp (UTC):** 2026-08-06T17:06:45Z
**Window:** develop only (`time < 2026-01-01 00:00:00+00:00`); holdout sealed unused
**Safety:** offline research only; never --live; develop only; holdout unused
**n_ablations:** 52 | **secondary_evals:** 200

## Pre-registered floors (before ranking)
```json
{
  "profit_factor": 1.4,
  "max_drawdown_pct": 12.0,
  "n_trades_min": 40,
  "n_trades_target": 60,
  "win_rate_diagnostic_floor": 45.0,
  "expectancy_min": 10.0
}
```

Score formula: `primary = n_trades * 8 + expectancy_sqrt_n * 0.35 + PF*20; hard floor fail → -1000`

## Baseline champion

- Params: `{"atr_min_pct": 0.55, "be_at_r": null, "cooldown": 2, "ema_trend": "ema100", "entry_N": 24, "h4_bias": true, "hours": null, "long_only": true, "max_entries_per_day": 2, "mid_channel_k": null, "require_ema_stack": false, "risk_pct": 0.01, "rsi_max": 70.0, "sl_atr": 1.5, "trail_atr": 3.5}`
- PF=2.480 WR=52.6% DD=9.24% n=38 NP=4876.9 exp√n=791.1
- trade_count_score=679.3 | hard_pass_trade_count=**False** (n_min≥40: False)

## Ablation ranking (trade_count_score)

| Rank | Tag | PF | WR% | DD% | n | NP | exp√n | score | Δscore | gate |
|-----:|-----|---:|----:|----:|--:|---:|------:|------:|-------:|:----:|
| 1 | `pack_entry20_no_atr_floor` | 2.322 | 47.7 | 10.87 | 86 | 12304 | 1326.8 | 1521.9 | +842.6 | Y |
| 2 | `pack_freq_entry12_atr35_noh4` | 2.308 | 51.7 | 9.96 | 87 | 10734 | 1150.8 | 1452.3 | +773.0 | Y |
| 3 | `pack_freq_entry10_atr30` | 1.550 | 45.2 | 14.30 | 135 | 4661 | 401.2 | 1406.0 | +726.7 | n |
| 4 | `pack_entry15_atr50_stack_off` | 2.359 | 44.8 | 13.86 | 67 | 8115 | 991.4 | 1136.4 | +457.1 | n |
| 5 | `pack_freq_entry15_atr40` | 1.980 | 44.7 | 14.51 | 76 | 6965 | 798.9 | 1096.1 | +416.8 | n |
| 6 | `pack_balanced_n60_path` | 1.843 | 44.4 | 13.21 | 81 | 5284 | 587.2 | 1093.8 | +414.6 | n |
| 7 | `pack_entry20_atr45_rsi80` | 2.050 | 45.5 | 13.96 | 66 | 6459 | 795.0 | 1033.6 | +354.3 | n |
| 8 | `rsi_max=85.0` | 2.828 | 51.9 | 8.71 | 54 | 8038 | 1093.9 | 1031.8 | +352.5 | Y |
| 9 | `rsi_max=90.0` | 2.828 | 51.9 | 8.71 | 54 | 8038 | 1093.9 | 1031.8 | +352.5 | Y |
| 10 | `rsi_max=100.0` | 2.828 | 51.9 | 8.71 | 54 | 8038 | 1093.9 | 1031.8 | +352.5 | Y |
| 11 | `pack_entry18_atr50_trail3` | 2.291 | 48.4 | 13.05 | 62 | 5804 | 737.1 | 1015.8 | +336.5 | n |
| 12 | `rsi_max=80.0` | 2.626 | 48.1 | 9.61 | 54 | 7499 | 1020.5 | 996.7 | +317.4 | Y |

## Key factor deltas (|Δscore|)

- `pack_entry20_no_atr_floor`: Δscore=+842.6
- `pack_freq_entry12_atr35_noh4`: Δscore=+773.0
- `trail_atr=1.5`: Δscore=-732.9
- `pack_freq_entry10_atr30`: Δscore=+726.7
- `pack_entry15_atr50_stack_off`: Δscore=+457.1
- `pack_freq_entry15_atr40`: Δscore=+416.8
- `pack_balanced_n60_path`: Δscore=+414.6
- `pack_entry20_atr45_rsi80`: Δscore=+354.3
- `rsi_max=85.0`: Δscore=+352.5
- `rsi_max=90.0`: Δscore=+352.5
- `rsi_max=100.0`: Δscore=+352.5
- `pack_entry18_atr50_trail3`: Δscore=+336.5
- `rsi_max=65.0`: Δscore=-330.8
- `rsi_max=80.0`: Δscore=+317.4
- `atr_min_pct=0.3`: Δscore=+269.8

## Secondary search top (n-raising axes)

| Rank | PF | WR% | DD% | n | NP | score | gate | params highlight |
|-----:|---:|----:|----:|--:|---:|------:|:----:|------------------|
| 1 | 2.449 | 51.2 | 9.96 | 86 | 12040 | 1511.8 | Y | `{"atr_min_pct": 0.35, "cooldown": 2, "entry_N": 10, "h4_bias": false, "max_entries_per_day": 2, "rsi_max": 80.0, "trail_atr": 3.5}` |
| 2 | 2.447 | 51.8 | 10.43 | 83 | 11110 | 1450.9 | Y | `{"atr_min_pct": 0.35, "cooldown": 0, "entry_N": 15, "h4_bias": false, "max_entries_per_day": 2, "rsi_max": 80.0, "trail_atr": 3.5}` |
| 3 | 2.274 | 50.6 | 9.98 | 87 | 10514 | 1441.1 | Y | `{"atr_min_pct": 0.35, "cooldown": 1, "entry_N": 12, "h4_bias": false, "max_entries_per_day": 2, "rsi_max": 80.0, "trail_atr": 3.5}` |
| 4 | 1.569 | 46.8 | 10.62 | 126 | 4407 | 1420.9 | Y | `{"atr_min_pct": 0.35, "cooldown": 0, "entry_N": 10, "h4_bias": false, "max_entries_per_day": 2, "rsi_max": 80.0, "trail_atr": 2.5}` |
| 5 | 1.947 | 47.1 | 11.45 | 104 | 7511 | 1403.8 | Y | `{"atr_min_pct": 0.35, "cooldown": 1, "entry_N": 10, "h4_bias": false, "max_entries_per_day": 2, "rsi_max": 80.0, "trail_atr": 3.0}` |
| 6 | 1.871 | 46.6 | 11.58 | 103 | 7132 | 1378.7 | Y | `{"atr_min_pct": 0.3, "cooldown": 2, "entry_N": 15, "h4_bias": false, "max_entries_per_day": 3, "rsi_max": 90.0, "trail_atr": 3.0}` |
| 7 | 2.170 | 48.2 | 10.99 | 85 | 9304 | 1369.6 | Y | `{"atr_min_pct": 0.4, "cooldown": 2, "entry_N": 10, "h4_bias": false, "max_entries_per_day": 2, "rsi_max": 90.0, "trail_atr": 3.5}` |
| 8 | 1.842 | 45.2 | 11.35 | 104 | 6683 | 1365.1 | Y | `{"atr_min_pct": 0.35, "cooldown": 0, "entry_N": 12, "h4_bias": false, "max_entries_per_day": 2, "rsi_max": 80.0, "trail_atr": 3.0}` |

## Best develop candidate (NOT holdout-confirmed)

- Source: **ablation** tag=`pack_entry20_no_atr_floor`
- PF=2.322 WR=47.7% DD=10.87% n=86 NP=12304.0 exp√n=1326.8
- hard_pass_trade_count: **True** | n_target≥60: **True**
- Params: `{"atr_min_pct": 0.0, "be_at_r": null, "cooldown": 2, "ema_trend": "ema100", "entry_N": 20, "h4_bias": true, "hours": null, "long_only": true, "max_entries_per_day": 2, "mid_channel_k": null, "require_ema_stack": false, "risk_pct": 0.01, "rsi_max": 85.0, "sl_atr": 1.5, "trail_atr": 3.5}`

## Disposition

- Lane **KEEP_OPTIMIZING** (not KILL).
- Baseline n=38 MISSES n≥40 floor.
- Best candidate n=86 (Δn vs baseline +48).
- **No holdout re-eval** this fire (prior HO n=4 underpowered + contaminated window).
- Live promote: **NO-GO**. Next: htf_fib widen entries on develop, or virgin holdout when data > 2026-08-06.

*Offline research only; never --live.*
