# Daily FX cosign → XAU next-day paper gate v1 — result

| Field | Value |
|-------|--------|
| **Gate memo** | `docs/research/EURUSD-GBP-DAILY-COSIGN-XAU-NEXTDAY-PAPER-GATE-v1.md` |
| **Package** | `4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd` |
| **Develop** | server_date < 2026-01-01 |
| **n_fills** | 842 (min 40) |
| **edge mean / median (pts)** | 36.93 / 26.50 |
| **t** | 0.395 |
| **binding slip** | 5 |
| **mean / median RT (pts)** | 25.94 / 28.00 |
| **pass_gate / disposition** | **FAIL** |
| **promote / live_go** | false / false |

## Four comparisons (slip=5 binding)

| Comparison | Edge | RT | Δ | Result |
|------------|-----:|---:|--:|--------|
| mean vs mean | 36.93 | 25.94 | +10.99 | PASS |
| mean vs median | 36.93 | 28.00 | +8.93 | PASS_MIXED_ONLY |
| median vs mean | 26.50 | 25.94 | +0.56 | PASS |
| median vs median (binding) | 26.50 | 28.00 | -1.50 | FAIL_BINDING |

## Fail reasons

- median edge 26.5000 < median RT 28.0000 (slip=5.0, binding)
- t=0.395 < 2.0

## Slip sensitivity

  slip   pass   mean_e  mean_rt    med_e   med_rt
   0.0  False    36.93    15.94    26.50    18.00
   5.0  False    36.93    25.94    26.50    28.00
  10.0  False    36.93    35.94    26.50    38.00

## Standing

- **FAIL → stop** (or PASS → separate full freeze auth only).
- Not a revival of `exog_london_fx_cosign_xau_follow_flat`.
