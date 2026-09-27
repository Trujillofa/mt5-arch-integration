# `xau_garch_voltarget_always_long_v1` — develop screen

| Field | Value |
|-------|--------|
| **verdict** | **SCREEN_FAIL** |
| **promote / live_go** | **no / false** |
| **holdout** | **untouched** (dump ends 2025-12-31) |
| **tape** | MCP Vantage H1 `results/xau_fomc_h4/xauusd_h1_2018_2025.csv` → daily, first size 2019-03-25 |
| **days** | 1749 sized / 1749 · MLE fail **0** · mean lots **0.473** vs cap 0.50 |

GARCH(1,1) 15% ann vol-target on the always-long host. 0 knobs.

| Arm | NP | DD | Calmar |
|-----|---:|---:|-------:|
| GARCH vol-target | **+$145 434** | **45.89%** | 3169 |
| Constant 0.5 lot | **+$150 255** | 46.36% | **3241** |

NP>0 and DD&lt;control pass. **Calmar fails** (net drop &gt; DD improvement). Gold spent most of the window below 15% vol, so the sizer barely left 0.5 lot.

Do not retune 15/252/GARCH(1,1). Do not switch EGARCH/H1. Do not peek 2026.
