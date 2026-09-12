# Prior overlay replay (2026-09-11)

Replay of the two previous session-scalp books **before** any BTC signal or lock metric.
Official gold `defined_r_v1_*.json` and index v8 locks were **not** rewritten.
`promote=no`. `live_go=false`. Not permission to `--live`.

## Gold (`GoldSessionScalp` / `research/xau-session-scalp`)

Command: `python3 scripts/xau_session_scalp_backtest.py --mode all` with `--out-dir` pointed here (`prior_gold/`). Source tape unchanged: FP `XAUUSD.r` M5.hc sha256 `f98e19f1…`, 100190 bars, 2025-04-03 → 2026-09-01.

| Book | Slice | n | WR | PF | Net (1 lot) |
|------|-------|--:|---:|---:|------------:|
| Baseline (unmodified index 09:30 ORB on gold, flatten 15:45) | develop | 191 | 52.4% | 1.01 | +$2,302 |
| Baseline | holdout ≥2026-01-01 | 168 | 47.0% | 1.23 | +$62,057 |
| Adjusted frozen gold (`london30_both_windows`, ATR SL/TP) | develop | 319 | 42.9% | **0.80** | −$12,004 |
| Adjusted | holdout | 276 | 44.9% | 0.88 | −$10,440 |

Official defined-R primary (`tpr1_be0_ts6`) remains **CLOSED / observe-only**: select n=230 WR 47.8% PF **0.83**. This replay of the ATR 1.0/1.2 adjusted combo is the same kill (develop PF 0.80). Baseline PF ~1.01 is the hours-long drift ride, not a scalp — do not copy `UsIndexSessionScalp` onto XAU or BTC.

Gold stayed **CLOSED**. Do not retune `defined_r`.

## Index (`UsIndexSessionScalp`)

Commands wrote slim JSON here (`prior_us30.json`, `prior_us100.json`). Index v8 lock / CSVs were not touched.

| Symbol | Slice | n | WR | PF | Net (1 lot) | vs committed 2026-08-18 write-up |
|--------|-------|--:|---:|---:|------------:|----------------------------------|
| US100 | all | 206 | 46.6% | **0.80** | −$3,375 | matches (PF 0.80 / −$3,348; tape now to 2026-08-18 17:50, +29 bars) |
| US100 | pre-holdout <2026-06-01 | 149 | 43.0% | **0.72** | −$3,098 | matches |
| US100 | holdout | 57 | 56.1% | **0.95** | −$277 | matches (committed 0.96 / −$250) |
| US30 | pre-holdout | 150 | 50.0% | **1.20** | +$2,539 | matches |
| US30 | holdout | 67 | 37.3% | **0.50** | −$4,383 | same fail (tape longer: 64138 vs 60044 bars; 67 vs 52 holdout trades) |

Index stayed **observe-only / promote=no**. 1%/20% goal remains archived. Do not rerun v8 against a longer live cache.

## What this authorizes

Replay machinery still runs. Neither prior overlay is a BTC seed. Next step is a **new** BTC M5 lock with a NY-desk overlap clock, freeze-before-peek.
