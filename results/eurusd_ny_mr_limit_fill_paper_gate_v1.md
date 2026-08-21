# EURUSD MR limit-fill paper gate v1 — result

| Field | Value |
|-------|--------|
| **Gate memo** | `docs/research/EURUSD-MR-LIMIT-FILL-PAPER-GATE-v1.md` |
| **Develop** | `et_date < 2025-03-01` |
| **n_signals** | 7819 |
| **n_fills** | 7704 |
| **fill_rate** | 0.985 (max valid 0.7) |
| **mean / median paper RT (pts)** | 11.52 / 11.00 |
| **pass_gate / disposition** | **FAIL** |
| **verdict_label** | FAIL_PAPER_GATE |
| **promote / live_go** | false / false |

## Horizons (filled trades only; edge from limit fill price)

   H       n      mean    median       t
   5    7704      4.11      5.00    3.12
  10    7704      2.78      4.00    1.64
  20    7704      6.88      6.00    3.08
  50    7704     11.50      7.00    4.03
 100    7704     10.96      8.00    3.29

## Four comparisons

| Comparison | Edge | RT | Δ | Result |
|------------|-----:|---:|--:|--------|
| mean edge vs mean RT | 11.50 | 11.52 | -0.01 | FAIL |
| mean edge vs median RT | 11.50 | 11.00 | +0.50 | PASS_MIXED_ONLY |
| median edge vs mean RT | 7.00 | 11.52 | -4.52 | FAIL |
| median edge vs median RT (binding) | 7.00 | 11.00 | -4.00 | FAIL_BINDING |

## Fail reasons

- fill_rate=0.985 > 0.7 (limit model invalid — reject before edge)
- mean edge 11.5029 < mean RT 11.5165 (H50)
- median edge 7.0000 < median RT 11.0000 (H50, binding)

## Standing

- **FAIL → stop**; do not write a screen; do not retune fill rules after seeing the number.
- Not a revival of `eurusd_ny_scalp_develop_v1`.
- Future gates: mean-vs-mean **and** median-vs-median (median binding); fill_rate ≤ 0.7 or reject before reading edge.
