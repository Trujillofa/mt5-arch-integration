# EURUSD MR limit-fill paper gate v1 — result

| Field | Value |
|-------|--------|
| **Gate memo** | `docs/research/EURUSD-MR-LIMIT-FILL-PAPER-GATE-v1.md` |
| **Develop** | `et_date < 2025-03-01` |
| **n_signals** | 7819 |
| **n_fills** | 7704 |
| **fill_rate** | 0.985 |
| **median paper RT (pts)** | 11.00 |
| **pass_gate** | **PASS** |
| **verdict_label** | CLEARS-PAPER-RT |
| **promote / live_go** | false / false |

## Horizons (filled trades only; edge from limit fill price)

   H       n      mean    median       t
   5    7704      4.11      5.00    3.12
  10    7704      2.78      4.00    1.64
  20    7704      6.88      6.00    3.08
  50    7704     11.50      7.00    4.03
 100    7704     10.96      8.00    3.29

## Fail reasons

- (none)

## Standing

- FAIL → stop; do not write a screen; do not retune fill rules after seeing the number.
- PASS → only then consider a full freeze charter (separate authorization).
- Not a revival of `eurusd_ny_scalp_develop_v1`.
