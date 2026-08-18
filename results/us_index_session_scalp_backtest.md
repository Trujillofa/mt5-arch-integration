# UsIndexSessionScalp — first flatten replay

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Family** | `ny_cash_orb_vwap_ema_flat` (frozen — not a search) |
| **Data** | FP Markets `cache/M5.hc` (US100 57 827 bars, US30 60 044) |
| **Window** | 2025-10 → 2026-08-18 |
| **Holdout** | **2026-06-01** (locked in `us_index_session_backtest.py` before this run) |
| **Exit** | next-bar open fill; flatten 15:45 ET |
| **Costs** | bar spread + 10 pt slippage/side + $0 commission; 1 lot; contract 1 |
| **promote / live_go** | **no / false** |

Not a develop screen. Defaults were not retuned after seeing these numbers.

## Verdict

**The frozen combo does not pay after costs.** Keep the overlay as a map. Do not attach an order EA. Do not grid OR / EMA / the entry window to chase this CSV.

US100 (primary) loses in **both** the pre-holdout window and the holdout. US30 looks fine before 2026-06-01 (PF 1.20) and **fails the holdout** (PF 0.50). That split is why the lock exists.

## US100 — primary

| Slice | Trades | Win rate | PF | Net (1 lot) | Avg | Max DD | Med MAE / MFE |
|-------|-------:|---------:|---:|------------:|----:|-------:|---------------|
| All | 206 | 46.6% | **0.80** | −$3 348 | −$16.3 | −$5 368 | 116 / 102 |
| Pre-holdout | 149 | 43.0% | **0.72** | −$3 098 | −$20.8 | −$3 805 | 99 / 80 |
| Holdout | 57 | 56.1% | **0.96** | −$250 | −$4.4 | −$1 610 | 160 / 136 |

Signals ≈ trades (one per ET date). Longs 111 / shorts 95.

Median MAE > MFE: the 15:45 flatten often gives back the morning OR break. Costs are small versus that (~$0.80 RT at 60 pt spread). The leak is the hold, not the spread gate.

## US30 — alternate

Replay used a **200 pt** research cap so the combo is visible. The indicator’s auto cap for US30 is **80 pt**; on this FP cache that allows **1 fill**. Same lesson as v1.00 US100 (50 vs live 60): the US30 cap is too tight for this broker.

| Slice (cap 200) | Trades | Win rate | PF | Net (1 lot) |
|-----------------|-------:|---------:|---:|------------:|
| All | 202 | 47.0% | 0.94 | −$1 274 |
| Pre-holdout | 150 | 50.0% | 1.20 | +$2 539 |
| Holdout | 52 | 38.5% | **0.50** | −$3 814 |

Do not promote on the pre-holdout print.

## How to replay

```bash
python3 scripts/us_index_session_backtest.py \
  --hc ~/.mt5-fpmarkets/drive_c/Program\ Files/FP\ Markets\ MT5\ Terminal/Bases/FPMarketsSC-Live/history/US100/cache/M5.hc \
  --symbol US100 --server-utc-offset 10800 \
  --out results/us_index_session_scalp_backtest.json
```

CSV dump (gitignored): `results/us_index_data/history_US100_M5.csv`.

## Explicitly not next

- Retune `InpOrMinutes` / EMA / `[09:45, 11:30)` on this tape
- ATR SL/TP search (would be a **new** family id)
- `--live` / `OrderSend`
- Treating US30 pre-holdout PF 1.20 as a go
