# Index session scan — frozen NY cash 09:30 OR model

| Field | Value |
|-------|--------|
| **Date** | 2026-09-10T12:10:00-05:00 |
| **Search** | `index_session_scan_v1` |
| **Family** | `ny_cash_orb_vwap_ema_flat` (unmodified) |
| **Holdout** | `2026-06-01` evaluate-only (index v1, **not** XAU) |
| **Score (frozen first)** | develop PF after costs; n≥40; then max DD, expectancy |
| **Costs** | tape spread or assumed 60 (unmeasured) + 10 pt slip/side + $0 commission |
| **Slip** | 10 MT5 points (0.01) per side — **unmeasured** |
| **promote / live_go** | **no / false** |
| **Disposition** | research-only; 1%/20% goal stays archived |

Lock was written before any rank. GoldSessionScalp was not touched. v1–v8 were not retuned.

## Most suitable to trade

**US30** is the only instrument that is both the right event (NY cash 09:30) and the
highest locked develop PF among US-cash tapes.

- Locked pick: `dukascopy_US30` — develop PF **1.27**, n=334, max DD −$2,980.
  Spread is **assumed 60 (unmeasured)**. Holdout PF **0.43** (n=67).
- Cost-honest twin: `fpmarkets_US30` Wine M5 (tape spread median **140**) — develop PF **1.20**,
  n=150, holdout PF **0.50**. This reproduces the 2026-08-18 archived US30 flatten replay
  (develop 1.20 / holdout 0.50) on a longer cache.
- `exness_US30m` (tape spread median 21, offset 0) — develop PF 1.18, holdout 0.48. Same fail.

**Do not trade it.** Holdout dies the same way the archived book said. `promote=no`.
ESP35 printed the highest overall develop PF (1.38) and is **research-only / wrong event**
(Madrid 09:00, not NY 09:30). GER40 / UK100 / AU200 / FRA40 likewise.

Evaluation-only (not used to rerank): `dukascopy_US500` is the only US-cash row with
holdout PF > 1 (1.36) after an assumed-60 charge. That is a note, not a promote, and
not a new family.

## US-cash ranking (the only trade-candidate list)

| Rank | id | n | WR | PF | net | max DD | holdout n | holdout PF | spread |
|-----:|----|--:|---:|---:|----:|-------:|----------:|-----------:|--------|
| 1 | `dukascopy_US30` | 334 | 53.6% | 1.27 | 8224.6 | -2980.0 | 67 | 0.43 | assumed_60_unmeasured |
| 2 | `fpmarkets_US30` | 150 | 50.0% | 1.20 | 2539.5 | -2323.6 | 67 | 0.50 | wine_hc_tape |
| 3 | `exness_US30m` | 141 | 53.2% | 1.18 | 2411.7 | -2566.1 | 54 | 0.48 | wine_hc_tape |
| 4 | `dukascopy_US500` | 358 | 53.6% | 1.15 | 735.5 | -527.7 | 69 | 1.36 | assumed_60_unmeasured |
| 5 | `dukascopy_US100` | 349 | 55.6% | 1.08 | 1754.0 | -2208.2 | 71 | 0.88 | assumed_60_unmeasured |
| 6 | `dukascopy_US2000` | 267 | 52.8% | 1.01 | 12.8 | -231.1 | 62 | 0.74 | assumed_60_unmeasured |
| 7 | `fpmarkets_US100` | 149 | 43.0% | 0.72 | -3097.9 | -3805.1 | 57 | 0.95 | wine_hc_tape |

`vantage_DJ30.r` had 100,006 M5 bars but develop n=1: tape spread median **310** exceeds
the locked 200-pt research cap, so the frozen combo almost never fills. Poor broker fit,
not a model retune.

## Full develop ranking (includes wrong clocks)

Holdout is shown and was **ignored** by the ranker.

| Rank | id | fit | n | WR | PF | net | max DD | holdout PF |
|-----:|----|-----|--:|---:|---:|----:|-------:|-----------:|
| 1 | `dukascopy_ESP35` | other_cash_open | 261 | 56.3% | 1.38 | 2707.0 | -939.6 | 1.78 |
| 2 | `dukascopy_US30` | us_cash_0930 | 334 | 53.6% | 1.27 | 8224.6 | -2980.0 | 0.43 |
| 3 | `dukascopy_AU200` | other_cash_open | 341 | 56.0% | 1.22 | 846.1 | -394.2 | 1.02 |
| 4 | `dukascopy_FRA40` | other_cash_open | 348 | 52.9% | 1.22 | 1053.0 | -600.3 | 0.84 |
| 5 | `fpmarkets_US30` | us_cash_0930 | 150 | 50.0% | 1.20 | 2539.5 | -2323.6 | 0.50 |
| 6 | `dukascopy_GER40` | other_cash_open | 327 | 53.2% | 1.20 | 2728.9 | -1635.4 | 1.15 |
| 7 | `dukascopy_UK100` | other_cash_open | 330 | 50.0% | 1.20 | 884.5 | -558.9 | 1.17 |
| 8 | `dukascopy_EU50` | other_cash_open | 347 | 53.6% | 1.20 | 690.5 | -472.8 | 0.98 |
| 9 | `exness_US30m` | us_cash_0930 | 141 | 53.2% | 1.18 | 2411.7 | -2566.1 | 0.48 |
| 10 | `dukascopy_US500` | us_cash_0930 | 358 | 53.6% | 1.15 | 735.5 | -527.7 | 1.36 |
| 11 | `dukascopy_JP225` | other_cash_open | 320 | 54.7% | 1.13 | 4234.1 | -4813.2 | 0.86 |
| 12 | `dukascopy_US100` | us_cash_0930 | 349 | 55.6% | 1.08 | 1754.0 | -2208.2 | 0.88 |
| 13 | `dukascopy_NL25` | other_cash_open | 59 | 50.8% | 1.03 | 2.5 | -38.5 | 0.49 |
| 14 | `dukascopy_US2000` | us_cash_0930 | 267 | 52.8% | 1.01 | 12.8 | -231.1 | 0.74 |
| 15 | `dukascopy_HK50` | other_cash_open | 168 | 49.4% | 0.92 | -628.3 | -2025.1 | 1.17 |
| 16 | `dukascopy_CHINA50` | other_cash_open | 326 | 49.4% | 0.84 | -840.9 | -1502.9 | 0.75 |
| 17 | `dukascopy_SUI20` | other_cash_open | 63 | 50.8% | 0.75 | -425.6 | -649.1 | 0.83 |
| 18 | `fpmarkets_US100` | us_cash_0930 | 149 | 43.0% | 0.72 | -3097.9 | -3805.1 | 0.95 |

## Why a high PF can still be a poor fit

| Symbol | Clock | Why this model is the wrong event |
|--------|-------|-----------------------------------|
| GER40 | Xetra 09:00 Europe/Berlin | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |
| UK100 | LSE 08:00 Europe/London | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |
| JP225 | TSE 09:00 Asia/Tokyo | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |
| AU200 | ASX 10:00 Australia/Sydney | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |
| EU50 | European cash ~09:00 Europe/Berlin | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |
| FRA40 | Euronext Paris 09:00 | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |
| SUI20 | SIX 09:00 Europe/Zurich | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |
| HK50 | HKEX 09:30 Asia/Hong_Kong (not ET) | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |
| ESP35 | Bolsa Madrid 09:00 | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |
| NL25 | Euronext Amsterdam 09:00 | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |
| IT40 | Borsa Italiana 09:00 (insufficient bars) | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |
| CHINA50 | China A50 09:30 Asia/Shanghai (not ET) | Frozen OR is NY 09:30–09:45 ET; any PF is a coincidental overlap |

## Data sources

Wine M5 extracted from live prefixes (read-only). Dukascopy is public **M5 bars**, not ticks, not JForex.

| id | TF | bars | range | spread | offset |
|----|----|-----:|-------|--------|-------:|
| wine `fpmarkets_US100` | M5 | 57856 | 2025-10-23 → 2026-08-18 | tape med 60 | 10800 |
| wine `fpmarkets_US30` | M5 | 64138 | 2025-10-13 → 2026-09-08 | tape med 140 | 10800 |
| wine `vantage_DJ30.r` | M5 | 100006 | 2025-04-08 → 2026-09-04 | tape med 310 | 10800 |
| wine `exness_US30m` | M5 | 56204 | 2025-11-04 → 2026-08-20 | tape med 21 | 0 |
| dukas `dukascopy_US30` | M5 | 144819 | 2025-01-01 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_US500` | M5 | 147366 | 2025-01-01 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_US100` | M5 | 146016 | 2025-01-01 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_US2000` | M5 | 117729 | 2025-01-01 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_GER40` | M5 | 137202 | 2025-01-01 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_UK100` | M5 | 140177 | 2025-01-02 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_JP225` | M5 | 136644 | 2025-01-01 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_AU200` | M5 | 142572 | 2025-01-01 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_EU50` | M5 | 103968 | 2025-01-02 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_FRA40` | M5 | 104796 | 2025-01-02 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_SUI20` | M5 | 27484 | 2025-01-03 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_HK50` | M5 | 45282 | 2025-01-03 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_ESP35` | M5 | 66576 | 2025-01-02 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_NL25` | M5 | 16860 | 2025-01-07 → 2026-09-09 | assumed 60 unmeasured | 0 |
| dukas `dukascopy_IT40` | M5 | 1200 | — | insufficient_bars | 0 |
| dukas `dukascopy_CHINA50` | M5 | 105024 | 2025-01-02 → 2026-09-09 | assumed 60 unmeasured | 0 |

## Gaps (no usable M5)

- **vantage NAS100.r** (M15): M15 cannot stamp a 15-minute NY OR without inventing M5 bars
- **fpmarkets US500** (H1): H1 cannot represent the 15-minute NY cash OR
- **wsf DJ30.c** (none): Wine history folder empty (no M5 bars)
- **ftmo US30.cash** (none): Wine history folder empty (no M5 bars)
- **alphacapital US30.pro** (none): Wine history folder empty (no M5 bars)
- **fundednext US30** (none): Wine history folder empty (no M5 bars)
- **fortraders US30** (none): Wine history folder empty (no M5 bars)
- **neomaa US30** (none): Wine history folder empty (no M5 bars)
- **dukascopy IT40**: 1,200 M5 bars (2026-09-01→09-09), below `min_bars_m5=2000`, holdout-only.
- **Wine US2000 / GER40 / UK100 / JP225 / AU200 / EU50 / FRA40**: no broker M5 cache; Dukascopy filled M5.
- **Vantage NAS100.r**: M15 only (2026-07-10→08-25), holdout-only; Dukascopy US100 M5 used instead.
- **FP US500**: H1 only; Dukascopy US500 M5 used instead. H1 was not resampled.

## Costs

Frozen book: point 0.01, contract 1, 1 lot, commission $0, slip **10 MT5 points/side (unmeasured)**,
max spread 200. Wine uses cache spread. Dukascopy has no spread column — assumed 60
(US100 typical cash from the design memo), labeled unmeasured. Frictionless is refused.

## Replay

```bash
python3 scripts/index_session_scan.py
```

Existing `test_us_index_session_*` plus `tests/test_index_session_scan.py` (frictionless refuse;
ranker ignores holdout).

