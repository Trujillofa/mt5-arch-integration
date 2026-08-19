# How to replay: US-index session screens (offline)

**Role:** Offline research for US100 / US30 session families. **`promote=no`. `live_go=false`.**
**Not the overlay operator manual.** Chart install, buffers, logger attach, and live-safe M5 export live in [MT5-INTEGRATION-CAPABILITIES.md](MT5-INTEGRATION-CAPABILITIES.md) and [mql5/README.md](../mql5/README.md). Overlay already on main (PR #27): `UsIndexSessionScalp` **v1.40**, signal buffer **8**. v3–v8 stay Python-only.

Design freeze: [US-INDEX-SESSION-SCALP-DESIGN.md](research/US-INDEX-SESSION-SCALP-DESIGN.md).

---

## 1. Disposition

Every screen **missed** median **trade-day** ≥ 1% and median **trade-month** ≥ 20% on the locked book. There is no promote path. Sequential peek is real: eight families in one day; later ones were designed after earlier holdout writes. July–August is a cleaner window, **not virgin**.

> This US-index research lane is **not** XAU Phase E and does **not** authorize or substitute for it. Do **not** edit `results/xau_loop_status.md` from this lane; see that file for current XAU disposition (`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`). Do **not** revive `AWAIT_PHASE_E_SCREEN_AUTHORIZATION`. This is not the sealed XAU London-FX family and not `xau_sealed_family_cycle`.

---

## 2. Locked book

| Field | Value |
|-------|--------|
| Balance | $10,000 |
| Lots | 1 |
| Point | 0.01 |
| Contract | 1 |
| Commission | 0 |
| Slippage | **10 MT5 points / side** |
| US100 spread cap | 200 points |

**“10 pt” = MT5 points of 0.01, not 10 index points.** Round-trip friction is about **$0.20** from `2 × 10 × 0.01` slippage plus **~$0.60** from a typical ~60 pt cash spread: `(spread + 2×10) × 0.01 × 1 × 1`. Exit fills at exact SL / TP / flatten open — no extra exit slip.

`--hc` writes an *assumed* `point=0.01` / `contract_size=1.0` meta. That is this locked book, not a measured `symbol_meta_*.csv` sha.

---

## 3. Holdout windows (do not retcon)

| Screens | Select | Holdout | June 2026 |
|---------|--------|---------|-----------|
| **v1–v3** (flatten replay, develop, playbook, structure) | `et_date < 2026-06-01` | `et_date >= 2026-06-01` | **In holdout** |
| **v4–v8** | `et_date < 2026-06-01` | `et_date >= 2026-07-01` | **Burned** — in neither split |

v1 `split_by_holdout` and v4 `split_v4` must not be mixed. Selection ranks develop-only; holdout is evaluation after the rank is frozen.

`daily_monthly` medians are **trade-days** / months that actually traded, not calendar days. That is a weaker 1% bar. Every screen missed it anyway.

---

## 4. How to run (`python3`, host numpy / pandas)

Research scripts use **`python3`**, not `uv run`. Do not kill the open FP `terminal64.exe /portable`. No `OrderSend`. No `--live`.

```bash
# Frozen flatten replay (v1 holdout = 2026-06-01). Writes slim JSON (no trade list).
python3 scripts/us_index_session_backtest.py \
  --hc ~/.mt5-fpmarkets/drive_c/Program\ Files/FP\ Markets\ MT5\ Terminal/Bases/FPMarketsSC-Live/history/US100/cache/M5.hc \
  --symbol US100 --server-utc-offset 10800 \
  --out results/us_index_session_scalp_backtest.json

# Screens (need results/us_index_data/*.csv — gitignored)
python3 scripts/us_index_session_autoresearch.py
python3 scripts/us_index_session_autoresearch_v2.py
# v3–v8 likewise: scripts/us_index_session_autoresearch_vN.py
```

Committed result JSON is **slim** (counts, costs, windows, `best_develop` params/metrics). Full trade lists and top-N grids stay local (`results/us_index_session_*_full.json` is gitignored). Locks and `results/*.md` write-ups stay in git.

`score_row` maps `profit_factor is None` (all winners / +inf) to **3.0** — the same pin as a finite PF 3. Ranking uses `pf or 3.0` (that also treats `0.0` as 3.0). Do not change scoring to chase a grid.

---

## 5. Screens (all missed; promote=no)

| ID | Script | Window | Hit 1%/20% | Write-up / lock |
|----|--------|--------|------------|-----------------|
| flatten | `us_index_session_backtest.py` | v1 | n/a (replay; PF 0.80 / holdout 0.96) | [scalp_backtest.md](../results/us_index_session_scalp_backtest.md) |
| v1 develop | `us_index_session_autoresearch.py` | v1 | 0 / eligible | [autoresearch.md](../results/us_index_session_autoresearch.md) · [lock](../results/us_index_session_develop_lock.json) |
| v2 playbook | `us_index_session_autoresearch_v2.py` | v1 | 0 / 205 | [playbook_v2.md](../results/us_index_session_playbook_v2.md) |
| v3 structure | `us_index_session_autoresearch_v3.py` | v1 | 0 / 129 | [structure_v3.md](../results/us_index_session_structure_v3.md) |
| v4 regime / proxy-CVD / POC | `us_index_session_autoresearch_v4.py` | v4 | 0 / 105 | [v4.md](../results/us_index_session_v4.md) |
| cost/size once | `us_index_session_v4_cost_size_once.py` | both (replay) | 0 / 5 books | [cost_size_once.md](../results/us_index_session_v4_cost_size_once.md) |
| v5 gap / HTF / US30 follow | `us_index_session_autoresearch_v5.py` | v4 | 0 / 43 | [v5.md](../results/us_index_session_v5.md) |
| v6 daily regime + London XAU gate | `us_index_session_autoresearch_v6.py` | v4 | 0 / 4 | [v6.md](../results/us_index_session_v6.md) |
| v7 IB false-break + M5 z | `us_index_session_autoresearch_v7.py` | v4 | 0 / 13 | [v7.md](../results/us_index_session_v7.md) |
| v8 H1 squeeze + H4 fib | `us_index_session_autoresearch_v8.py` | v4 | 0 / 0 eligible | [v8.md](../results/us_index_session_v8.md) |

Frozen chart defaults stay OR 15 / EMA 9/21 / window to 11:30. Do not retune on holdout. v3–v8 are not `InpFamily` modes.

---

## 6. Overlay (pointer only)

Install, compile, buffer table, logger, live-safe dump: [MT5-INTEGRATION-CAPABILITIES.md](MT5-INTEGRATION-CAPABILITIES.md) §§4–7. Do not grow an overlay §12 / §12b here.

---

## 7. Tests (local only — no CI)

There is **no CI** on this research PR. After changes, on a host with numpy / pandas:

```bash
python3 -m pytest tests/test_us_index_session_*.py -q --tb=short
```

---

## 8. Safety

- Never `OrderSend`. Never pass `--live`. Do not attach an order EA.
- Do not claim 1% / 20% or a live-go.
- Do not edit `results/xau_loop_status.md` from this lane.
