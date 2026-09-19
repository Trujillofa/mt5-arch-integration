# `renko_event_clock_vendor` — develop screen

**Charter:** `results/xau_charters/2026-09-19_renko_event_clock_vendor_v1.json` · sha `ddeae18a71bcb141`
**Window:** M15 2022-05-17 → 2025-12-31 (85,802 bars, `time < 2026-01-01`) · holdout untouched
**Costs:** `account_matched_spread_commission_only` · fixed 0.01 lots · start balance $10,000
**Disposition:** **SCREEN_FAIL** · passers 0/5 · promote no · live_go false

## Per-vehicle result (base path convention, base slippage)

| vehicle | brick | R:R | risk/trade | n | PF | WR | net $ | maxDD | soft gate |
|---|---|---|---|---|---|---|---|---|---|
| ADX/DI trend (77234) | $16 | 1:0.23 | $672 (6.7%) | 123 | 0.84 | 48.0% | -268.88 | 3.62% | FAIL |
| BB breakout (77236 mode 1) | $17 | 1:0.57 | $714 (7.1%) | 121 | 1.07 | 56.2% | 105.64 | 3.81% | FAIL |
| BB re-entry (77236 mode 2) | $30 | 1:0.58 | $1,455 (14.6%) | 28 | 2.40 | 64.3% | 313.00 | 0.97% | FAIL |
| BB midline cross (77236 mode 3) | $30 | 1:0.29 | $1,035 (10.3%) | 49 | 0.52 | 36.7% | -522.51 | 7.02% | FAIL |
| BB squeeze (77236 mode 4) | $14 | 1:0.84 | $434 (4.3%) | 67 | 1.11 | 56.7% | 109.02 | 3.19% | FAIL |

## Gate failures

- **ADX/DI trend (77234)** — PF 0.8372 < 1.2; net -268.88 <= 0.0
- **BB breakout (77236 mode 1)** — PF 1.0688 < 1.2
- **BB re-entry (77236 mode 2)** — n_trades 28 < 40
- **BB midline cross (77236 mode 3)** — PF 0.518 < 1.2; net -522.51 <= 0.0
- **BB squeeze (77236 mode 4)** — PF 1.1076 < 1.2

## Slippage sensitivity (frozen, report-only)

| vehicle | 0 pt | 5 pt | 10 pt | 20 pt |
|---|---|---|---|---|
| ADX/DI trend (77234) | -269 | -281 | -293 | -318 |
| BB breakout (77236 mode 1) | 106 | 94 | 81 | 57 |
| BB re-entry (77236 mode 2) | 313 | 310 | 307 | 302 |
| BB midline cross (77236 mode 3) | -523 | -527 | -532 | -542 |
| BB squeeze (77236 mode 4) | 109 | 102 | 96 | 82 |

## Path-convention falsifier

Bricks are rebuilt from M15 OHLC, so the intrabar path is assumed. A verdict or net-profit sign that flips between conventions is an artefact of that assumption.

| vehicle | base net $ | base PF | reversed net $ | reversed PF | flip |
|---|---|---|---|---|---|
| ADX/DI trend (77234) | -268.88 | 0.84 | -303.75 | 0.82 | no |
| BB breakout (77236 mode 1) | 105.64 | 1.07 | 298.48 | 1.20 | **YES** |
| BB re-entry (77236 mode 2) | 313.00 | 2.40 | 313.00 | 2.40 | no |
| BB midline cross (77236 mode 3) | -522.51 | 0.52 | -522.51 | 0.52 | no |
| BB squeeze (77236 mode 4) | 109.02 | 1.11 | 198.39 | 1.20 | no |

## Exit mix — where the advertised TP/SL geometry actually goes

| vehicle | exits | TP+SL share |
|---|---|---|
| ADX/DI trend (77234) | EOD_FORCE 1, SIGNAL_FLIP 11, TIME 110, TP 1 | 0.8% |
| BB breakout (77236 mode 1) | EOD_FORCE 1, SIGNAL_FLIP 6, TIME 114 | 0.0% |
| BB re-entry (77236 mode 2) | BB_MID 4, TIME 24 | 0.0% |
| BB midline cross (77236 mode 3) | EOD_FORCE 1, SIGNAL_FLIP 16, TIME 32 | 0.0% |
| BB squeeze (77236 mode 4) | EOD_FORCE 1, SIGNAL_FLIP 1, TIME 65 | 0.0% |

_Offline research artifact. No orders. Holdout not evaluated._
