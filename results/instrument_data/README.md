# Instrument research data (Phase 0 multi-instrument lane)

```bash
source config/brokers/vantage.env
./scripts/export-instruments-from-wine-mt5.sh
python3 scripts/build_multi_instrument_data_readiness.py
```

| File | Content |
|------|---------|
| `{symbol}_h1.csv` | Full H1 OHLC + tick_volume + spread (points) |
| `{symbol}_h1_develop.csv` | Develop slice `time < 2026-01-01` |

**Source:** Vantage Standard STP via Wine MT5 (`MqlRates.spread`).  
**Costs:** commission 0; slip unmeasured.  
**No strategy signals** in this folder.

Manifests: `results/instrument_data_manifests/`.  
Report: `results/multi_instrument_data_readiness.md`.
