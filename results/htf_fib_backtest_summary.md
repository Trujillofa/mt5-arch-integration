# HTF Fib backtest summary (2026-08-05)

## Deliverables

| Artifact | Path |
|----------|------|
| Strategy Tester EA | `mql5/Experts/ForexHtfFibTester.mq5` (compiled `.ex5` on Vantage prefix) |
| Offline research script | `scripts/htf_fib_offline_backtest.py` |
| Headless helper | `scripts/19-run-htf-fib-backtest.sh` (GUI still preferred under Wine) |
| How-to section | `docs/HOWTO-HTF-FIB.md` §13 |

## MT5 Strategy Tester (do this in the terminal GUI)

1. Compile **ForexHtfPivotsFib** + **ForexHtfFibTester** (F7).
2. Ctrl+R → Expert **ForexHtfFibTester**, Symbol **EURUSD**, Period **H1**.
3. Dates e.g. 2024.06.01–2025.01.01, model 1-minute OHLC, Start.
4. EA uses indicator buffer **8**, ATR SL 1.5× / TP 2.0×, default 0.10 lots.

Headless Single works via `scripts/19-run-htf-fib-backtest.sh` (fixed Login/Expert path/ASCII ini). Smoke test 2024.06–09: OK, 6 trades.

## Offline surrogate (Dukascopy EURUSD H1)

Approximation of H4 pivots + golden zone + EMA200 + RSI (not full MT5 parity).

| Window | RSI-MA filter | Signals/Trades | Win rate | Net (0.1 lot) | PF |
|--------|---------------|----------------|----------|---------------|-----|
| 2024-06 → 2025-01 | ON (default) | 0 | — | $0 | — |
| 2024-06 → 2025-01 | OFF | 4 | 25% | ≈ −$30 | 0.35 |
| 2022-01 → 2024-12 | ON | 1 | 100% | ≈ +$7.5 | n/a |
| 2022-01 → 2024-12 | OFF | 22 | 32% | ≈ −$96 | 0.57 |

**Takeaway:** Default confluence (golden zone + RSI≤35 + RSI>MA + bias) is very strict → few trades. With filter off, sample still unprofitable under these ATR exits — **observe / retune before live**.

## Next

- Run GUI Strategy Tester for platform-true results (spread, stops, iCustom).
- Optionally set EA `InpUse...` via inputs; align indicator `InpUseRsiMaFilter` with tests.
