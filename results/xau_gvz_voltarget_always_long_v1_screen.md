# `xau_gvz_voltarget_always_long_v1` — develop screen

| Field | Value |
|-------|--------|
| **verdict** | **SCREEN_FAIL** |
| **promote / live_go** | **no / false** |
| **holdout** | **untouched** (dump ends 2025-12-31; 2026 GVZ unused) |
| **tape** | XAU daily from MCP H1 2018-04-02→2025-12-31 · FRED GVZCLS as-of |
| **days** | 2002 sized / 2002 · mean GVZ **16.50** · mean lots **0.439** vs cap 0.50 |

Implied-vol sizer, 0 knobs. Article 1.20 cuts unused.

| Arm | NP | DD | Calmar |
|-----|---:|---:|-------:|
| GVZ 15% vol-target | **+$136 908** | 78.91% | 1735 |
| Constant 0.5 lot | **+$149 622** | **78.91%** | **1896** |

NP>0 passes. **DD not strictly below** control (tied). **Calmar loses.** Same story as GARCH: sitting 0.5 lot wins.

Do not retune 15 / GVZ units. Do not copy 1.20 flatten. Do not peek 2026.
