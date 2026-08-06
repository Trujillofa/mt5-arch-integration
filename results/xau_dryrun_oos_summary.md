# XAU dry-run + OOS summary

**Date:** 2026-08-06  
**Verdict:** Prep OK · Dry-run OK (offline only) · OOS gates **FAIL** → **no live**

## Safety

- Confirmed **no `--live`** used. Dry-run only.
- Bridge healthy; ready for dry-run/OOS only — **no live orders**.

## Prep

| Check | Status |
|-------|--------|
| PREP_OK | `true` |
| terminal64 | already running |
| `xauusd_data.csv` / `strategy_params.json` | present and fresh (&lt;24h) |
| bridge | healthy |

**Summary:** terminal64 already running; xauusd_data.csv and strategy_params.json present and fresh (&lt;24h); bridge healthy — ready for dry-run/OOS (no live orders).

## Dry-run live_trader --once

| Check | Status |
|-------|--------|
| DRY_OK | `true` |
| Exit | 2 (expected on pure Linux without MetaTrader5 package) |
| Offline sizing | lots=0.13, SL=2392.5, TP=2410.0, risk$=100.00, stop_dist=7.5000 |
| CSV load | 58150 rows; last bar XAUUSD M15 2026-08-06 18:00Z close 4270.89 |

**Command 1:** `python3 live_trader.py --once`

```
2026-08-06 10:13:13,071 ERROR MetaTrader5 package not available on this platform
2026-08-06 10:13:13,072 INFO dry sizing demo: lots=0.13 sl=2392.5 tp=2410.0 risk$=100.00 stop_dist=7.5000
EXIT_CODE=2
```

**Interpretation:** Exit 2 + “MetaTrader5 package not available” + dry sizing demo ⇒ ok=true (offline risk math valid; MT5 package expected missing on pure Linux).

**Command 2:** offline params / `size_position` / last bar — EXIT_CODE=0

Params (from dry-run):

| Key | Value |
|-----|-------|
| mode | bb_rsi |
| rsi_buy / rsi_sell | 30.0 / 50.0 |
| sl_atr / tp_atr | 1.5 / 2.0 |
| bb_col / trend_col | bb_lo / ema200 |
| use_macd_filter | false |
| long_only | true |
| risk_pct | 0.01 |
| cooldown | 2 |

`size_position` sample XAU: `RiskSize(lots=0.13, sl_price=2392.5, tp_price=2410.0, risk_dollars=100.0, stop_distance=7.5)`

**Bridge gap:** Dry-run is offline sizing only (no MetaTrader5 package on this host). Keep **dry-only** until a Windows/Wine MT5 Python bridge is available for full order-path validation.

## OOS holdout (fixed params)

| Check | Status |
|-------|--------|
| OOS_OK (ran) | `true` |
| oos_gates_pass | **false** |
| Artifact | `results/xau_oos_holdout.json` |

**Split:** 70/30 time split at `2026-01-02T18:18Z`

| Segment | Bars | Range |
|---------|------|-------|
| Train (IS) | 8132 | 2024-08-16 .. 2026-01-02 |
| OOS | 3505 | 2026-01-02 .. 2026-08-06 |

**Params** (unchanged from `strategy_params.json`): mode=bb_rsi, rsi_buy=30, rsi_sell=50, sl_atr=1.5, tp_atr=2.0, bb_col=bb_lo, trend_col=ema200, long_only=true, risk_pct=0.01, cooldown=2.

### Metrics (exact from `xau_oos_holdout.json`)

| Metric | In-sample | OOS |
|--------|-----------|-----|
| net_profit | 1255.65 | **-136.09** |
| win_rate | 62.50% | **42.86%** |
| profit_factor | 1.84 | **0.59** |
| max_drawdown_pct | 3.56% | 2.76% |
| n_trades | 40 | 7 |
| wins / losses | 25 / 15 | 3 / 4 |

## Gates

Thresholds: **PF ≥ 1.5**, **WR ≥ 55%**, **DD ≤ 10%**

| Gate | IS | OOS | Pass? |
|------|----|-----|-------|
| profit_factor ≥ 1.5 | 1.84 | 0.59 | OOS **fail** |
| win_rate ≥ 55% | 62.5% | 42.86% | OOS **fail** |
| max_drawdown_pct ≤ 10% | 3.56% | 2.76% | OOS pass |
| **gates_pass** | true (IS strong) | **false** | — |

OOS fails PF and WR on a thin sample (n_trades=7).

## Recommended next step

1. **No live trading.** OOS gates fail (PF 0.59, WR 42.86%, only 7 trades).
2. **Keep dry-only.** MetaTrader5 package missing on pure Linux — offline sizing is validated; full live path is not.
3. **Investigate regime / retrain only on the train split** (do not fit on OOS). Compare IS vs OOS feature distributions, regime filters, and whether bb_rsi edge degraded after 2026-01-02.
4. Optionally extend holdout or walk-forward once more IS data is available; do **not** promote to paper/live until OOS gates pass with a larger trade sample.

**One-line verdict:** Dry-run OK offline; OOS holdout fails gates (PF/WR, n=7) — stay dry-only, no live, retrain/investigate on train split only.
