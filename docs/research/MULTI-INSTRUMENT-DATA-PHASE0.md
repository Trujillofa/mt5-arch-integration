# Multi-instrument data readiness (Phase 0)

**Status:** pipeline + integrity (no thesis freeze).
**Symbols:** XAUUSD, EURUSD, GBPUSD (H1).
**Holdout:** `2026-01-01 00:00:00` server clock (`server_clock_as_stored`).

## Components

| Path | Role |
|------|------|
| `mql5/Scripts/ExportInstrumentHistory.mq5` | Wine MT5 multi-symbol H1 export + challenge echo |
| `scripts/export-instruments-from-wine-mt5.sh` | Fail-closed export driver |
| `scripts/build_multi_instrument_data_readiness.py` | DQ, package seal, CURRENT publish, snapshot loader |
| `tests/test_multi_instrument_data_readiness.py` | Adversarial integrity tests |
| `results/instrument_data_packages/README.md` | Package schema |

## Packaging

- Content-addressed immutable packages under `results/instrument_data_packages/`.
- Full H1 stored; **develop is derived** (no duplicate `*_develop.csv` by default).
- Split PRs: pipeline (this) vs data snapshot (one package + CURRENT).

## Explicitly out of scope

Thesis freeze, signals, PF, grids, nulls, paper, live orders.
