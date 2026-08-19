# BTC H1 range-vol breakout — develop rank only

This file is develop-only (`signal_utc_date < 2026-01-01`). promote / live_go: **no / false**.
Grid frozen; do not retune.

Data: `results/btc_data/history_BTCUSD_H1.csv` · 29035 bars · 2021-12-20 21:00:00+00:00 → 2026-08-18 15:00:00+00:00
sha256 `c2f87a05eb56d401d292ddcb68a68b6baa6cc22ab0a061c39e573f96e0f062ff` (matches lock).

Eligible (n≥40 and NP>0): **4** · soft pass (also PF≥1.1, DD≤25%): **1**.

| # | N | sq | exp | sl | n | WR | PF | NP | DD | expectancy | median day | eligible | soft | screen |
|--:|--:|---:|----:|---:|--:|---:|---:|---:|---:|-----------:|-----------:|:--------:|:----:|:-------|
| 0 | 20 | 0.75 | 1.25 | 1.5 | 27 | 37.0% | 1.6874 | +33.09 | 0.21% | +1.2256 | -0.0163% | False | False | SCREEN_FAIL |
| 1 | 20 | 0.75 | 1.25 | 2.0 | 25 | 44.0% | 2.3911 | +67.55 | 0.25% | +2.7020 | -0.0184% | False | False | SCREEN_FAIL |
| 2 | 20 | 0.75 | 1.75 | 1.5 | 19 | 42.1% | 2.3962 | +37.51 | 0.14% | +1.9740 | -0.0142% | False | False | SCREEN_FAIL |
| 3 | 20 | 0.75 | 1.75 | 2.0 | 18 | 38.9% | 2.4066 | +48.64 | 0.19% | +2.7023 | -0.0198% | False | False | SCREEN_FAIL |
| 4 | 20 | 0.90 | 1.25 | 1.5 | 307 | 38.8% | 0.9906 | -10.53 | 1.90% | -0.0343 | -0.0212% | False | False | SCREEN_FAIL |
| 5 | 20 | 0.90 | 1.25 | 2.0 | 293 | 41.6% | 1.1127 | +143.97 | 1.68% | +0.4914 | -0.0227% | True | True | soft_pass |
| 6 | 20 | 0.90 | 1.75 | 1.5 | 242 | 40.5% | 1.0840 | +68.32 | 1.23% | +0.2823 | -0.0191% | True | False | eligible |
| 7 | 20 | 0.90 | 1.75 | 2.0 | 245 | 38.8% | 0.9837 | -17.65 | 1.96% | -0.0720 | -0.0261% | False | False | SCREEN_FAIL |
| 8 | 40 | 0.75 | 1.25 | 1.5 | 13 | 23.1% | 1.2783 | +7.51 | 0.14% | +0.5777 | -0.0194% | False | False | SCREEN_FAIL |
| 9 | 40 | 0.75 | 1.25 | 2.0 | 13 | 23.1% | 1.3257 | +11.34 | 0.19% | +0.8720 | -0.0238% | False | False | SCREEN_FAIL |
| 10 | 40 | 0.75 | 1.75 | 1.5 | 12 | 25.0% | 1.5721 | +12.56 | 0.13% | +1.0463 | -0.0188% | False | False | SCREEN_FAIL |
| 11 | 40 | 0.75 | 1.75 | 2.0 | 12 | 25.0% | 1.6403 | +18.01 | 0.17% | +1.5012 | -0.0226% | False | False | SCREEN_FAIL |
| 12 | 40 | 0.90 | 1.25 | 1.5 | 191 | 36.6% | 0.8732 | -91.09 | 1.99% | -0.4769 | -0.0220% | False | False | SCREEN_FAIL |
| 13 | 40 | 0.90 | 1.25 | 2.0 | 195 | 37.9% | 0.9152 | -77.95 | 2.33% | -0.3998 | -0.0287% | False | False | SCREEN_FAIL |
| 14 | 40 | 0.90 | 1.75 | 1.5 | 155 | 40.0% | 1.0677 | +34.96 | 1.12% | +0.2256 | -0.0192% | True | False | eligible |
| 15 | 40 | 0.90 | 1.75 | 2.0 | 165 | 40.0% | 1.0858 | +60.01 | 1.40% | +0.3637 | -0.0250% | True | False | eligible |

## Ranked soft-passers (PF then expectancy)

| rank | N | sq | exp | sl | n | PF | NP | expectancy |
|-----:|--:|---:|----:|---:|--:|---:|---:|-----------:|
| 1 | 20 | 0.90 | 1.25 | 2.0 | 293 | 1.1127 | +143.97 | +0.4914 |

Do not raise lots or cut slip.

