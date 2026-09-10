# XAU real-yield β — FRED DFII10 + DTWEXBGS (kill)

| Field | Value |
|-------|--------|
| Date | 2026-09-09 |
| Family | `exog_dfii10_dtwex_daily_tvbeta_xau_follow_flat_v1` |
| Lock | `lock.json` — **frozen before** metrics |
| **Verdict** | **kill** |
| promote / live_go | **no / false** |
| Not a reopen | DXY/US10Y β, London FX cosign, GARCH, M5 scalp |

Thesis: gold follows **real yields** and the **broad dollar**, not Yahoo DXY + nominal 10Y.
FRED panel fetched with `scripts/fetch_fred_xau_macro.py` (`auth: env: FRED_API_KEY`).
Attribution: Federal Reserve Bank of St. Louis / FRED. Local research cache only.

## FRED panel (`results/xau_exog_beta/data/fred/`)

| Series | Role | n | Range |
|--------|------|--:|-------|
| DFII10 | 10Y TIPS real yield (primary Δ) | 2170 | 2018-01-02 → 2026-09-04 |
| DTWEXBGS | broad trade-weighted USD (log-diff) | 2166 | 2018-01-02 → 2026-09-04 |
| DGS10 | nominal 10Y (stored, not in rule) | 2170 | 2018-01-02 → 2026-09-04 |
| T10YIE | 10Y breakeven (stored, not in rule) | 2171 | 2018-01-02 → 2026-09-08 |
| DFII5 | 5Y TIPS (stored, not in rule) | 2170 | 2018-01-02 → 2026-09-04 |

Alignment: last FRED print with `date <=` gold UTC date. No future fill.

## Frozen rule

Rolling OLS window **60** (120 robustness, not used to pick). Next-day open if
`|pred|≥0.002`. Hold 5 days or 1.5 ATR SL. 0.10 lot. Costs: research book,
**slip=0 UNMEASURED**. Baseline: always-long on the same `|pred|` gate.

## Develop (`utc_date < 2026-01-01`)

| Book | n | WR | PF | Net (0.10 lot) | Max DD |
|------|--:|---:|---:|---------------:|-------:|
| β-follow w60 | 201 | 41.3% | **0.80** | −8 409 | 95% |
| **always-long same entries** | 195 | 56.9% | **1.78** | +22 444 | 28% |
| robust w120 (not pick) | 191 | 42.4% | 0.84 | −6 661 | 79% |

## Holdout (evaluate once; not used to pick)

| Book | n | WR | PF | Net | Max DD |
|------|--:|---:|---:|----:|-------:|
| β-follow | 31 | 54.8% | 1.40 | +6 858 | 42% |
| always-long | 34 | 47.1% | 1.02 | +460 | 64% |

Holdout β looks better. That is **not** a continue. Selection was develop-only;
do not retune after seeing holdout.

## Kill vs continue

**Kill.** Develop n=201 ≥ 30 but PF 0.80 ≯ always-long 1.78 and PF < 1.0.
Real-yield + broad-dollar β sign still lost to gold drift on this tape.
