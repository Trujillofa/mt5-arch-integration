# How to use GoldSessionScalp

| Field | Value |
|-------|--------|
| Indicator | `GoldSessionScalp` v1.10 |
| **Disposition** | **CLOSED** · **observe-only** · **promote=no** · **live_go=false** |
| Family | `xau_london_defined_r_be_flat_v1` — **do not retune** |
| Chart | XAUUSD / XAUUSD.r **M5** — overlay only |
| Logger | `ForexSignalLogger` · buffer **8** · `InpMaxSpreadPips=0` |

**Not a live signal.** Do not attach this indicator as an entry host.
M5 session-OR scalp is structurally cost-killed on this tape (select WR
47.8% / PF 0.83 after gold costs; 80% WR + PF≥1 closed on this event class).

Do not chase 80% WR on sub-15m XAU. Do not swap onto indices.
Do not rerun `xau_session_scalp_defined_r.py` to replace official metrics.

Status: `results/xau_session_scalp/STATUS.md`.
Design: `docs/research/XAU-SESSION-SCALP.md`.
Compare vs UsIndexSessionScalp: `results/indicator_compare_gold_vs_index.md`.

## Attach (observe-only)

1. `./scripts/18-install-forex-indicator.sh`
2. MetaEditor F7: `Include/GoldSessionUtils.mqh` then `Indicators/GoldSessionScalp.mq5`
3. Drop on XAUUSD M5 **to watch buffers**. Never `OrderSend`.
4. Optional logger preset: `Presets/ForexSignalLogger-GoldSessionScalp.set`

Buffers: `mql5/README.md` (signal = **8**).

## Replay (offline, already frozen)

Official books are already written. Do **not** rerun the 16-cell grid for
a new official pick. Historical runners (research only):

```bash
# Do not use these to overwrite defined_r_v1_*.json
python3 scripts/xau_session_scalp_backtest.py --mode all
```

Holdout `2026-01-01`. Does **not** write `strategy_params.json`.
