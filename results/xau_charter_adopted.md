# Charter adoption one-pager — Option B

**Date:** 2026-08-08  
**Decision:** **Option B adopted** — explicit dual-layer charter  
**Full charter:** [`docs/CHARTER-RESEARCH-LAYER.md`](../docs/CHARTER-RESEARCH-LAYER.md)  
**Operating rules:** [`AGENTS.md`](../AGENTS.md)  
**Strategy status:** [`results/xau_loop_status.md`](xau_loop_status.md)

## What was adopted

One repository, **two layers**, with hard boundaries:

| Layer | Paths (examples) | Role |
|-------|------------------|------|
| Platform | `src/mt5_arch/`, `scripts/NN-*.sh`, core bridge `mql5/Mt5ArchBridge.mq5` | Wine MT5 + file/RPyC bridge + thin CLI |
| Offline research | `backtest.py`, `fetch_data.py`, `live_trader.py`, `scripts/xau_*`, `scripts/htf_fib_*`, research indicators, `results/` | Falsifiable offline strategy work only |

## Boundaries (non-negotiable)

1. **`src/mt5_arch` ↛ research** — platform code must never import research modules, scripts, or `results/`.
2. **No live without consent** — `live_trader.py` is dry by default; never pass `--live` from tests, smokes, or agent automation without a direct human yes.
3. **Merge ≠ promote** — landing dual-layer code on `main` archives process and tooling; it does **not** authorize paper/live trading, parameter promotion, or flipping `promote` / `live_go` / `PAPER_GO`.

## Strategy disposition (unchanged by this adoption)

| Field | Value |
|-------|--------|
| **next_step** | **RESEARCH_IDLE** |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | **no** |

Null kills (bb_rsi, Donchian) and holdout rules still apply. Charter B is product structure, not an edge GO.
