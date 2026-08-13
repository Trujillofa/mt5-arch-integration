# Instrument research data (Phase 0 multi-instrument lane)

```bash
source config/brokers/vantage.env
export WINEPREFIX=$HOME/.mt5-vantage
./scripts/export-instruments-from-wine-mt5.sh   # fail-closed; prefix-scoped
python3 scripts/build_multi_instrument_data_readiness.py
```

| File | Content |
|------|---------|
| `{symbol}_h1.csv` | Full H1 OHLC + auditable spreads + `clock=server_clock_as_stored` |

**Develop:** not stored as CSV. Derived as `server_time < 2026-01-01` from full H1
via `load_package_snapshot().read_develop(symbol)`.

**Clock:** MT5 **server** stamps (offset-free). **Not** UTC.
**Spreads:** `spread_raw_pts`, `spread_effective_pts`, `spread_imputed` (zero-fill audited).
**Source:** Vantage Standard STP (`export_run.json` login/server/run_id).
**Costs:** commission 0; slip unmeasured.
**No strategy signals** in this folder.

Manifests: `results/instrument_data_manifests/` (includes `export_run.json`).
Report: `results/multi_instrument_data_readiness.md`.
Gate target: `PASS_DATA_READY_WITH_IMPUTATION` or `PASS_DATA_READY` (never fail-open `PASS_CLEAN`).
