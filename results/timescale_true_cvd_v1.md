# Path 2 started — `timescale_true_cvd_v1`

| Field | Value |
|-------|--------|
| **Date** | 2026-08-19 |
| **Kind** | Infra architecture (not a screen) |
| **Lock** | `results/timescale_true_cvd_v1_lock.json` |
| **Memo** | `docs/research/TIMESCALE-TRUE-CVD-DESIGN.md` |
| **promote / live_go** | **no / false** |
| **Instruments** | **TBD** |

BTC H1 PA and US100 v1–v8 stay sealed. No retune. No OHLCV grid.

**Ticks:** Wine `.tkc` caches exist; they are **not** a research store. No parseable MqlTick CSV. Prototype is a synthetic fixture only.

**Not stood up:** Timescale, `docker compose up`, CopyTicks dump, any screen.

**Leftover:** live-safe CopyTicks dump + last-trade populate audit. Then pick an instrument or stop.
