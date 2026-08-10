# XAU Virgin Holdout — Summary

**Timestamp (UTC):** 2026-08-06T17:17:46Z  
**Pipeline:** virgin sealed holdout of frozen champions  
**Disposition:** **WAIT_DATA**  
**live_go:** false (never recommend `--live` from this pass)

| Phase | Ran | Result |
|-------|:---:|--------|
| REFRESH | true | `virgin_available=false` · `n_virgin_bars=2` · `after_max=2026-08-06 20:00:00+00:00` |
| CATALOG | true | 8 frozen configs |
| VIRGIN | true | **SKIPPED** — no virgin bars (insufficient sample) |
| SKEPTIC | true | **WAIT_DATA** |

---

## Safety

| Rule | Status |
|------|--------|
| Offline research only | **yes** |
| No `--live` / no orders | **yes** |
| No paper/live promote from this fire | **yes** |
| No retune on (nonexistent) virgin metrics | **yes** |
| Catalog frozen from develop artifacts only | **yes** |
| Holdout not used for selection | **yes** |
| No fabricated virgin survivors | **yes** (`n_evaluated=0`; no `xau_virgin_survivors.json`) |
| Prior 2026-01+ contamination still binding | **yes** |

**Safety line (eval artifact):** `offline only; no retune; virgin not evaluated`  
**Catalog safety:** `offline frozen catalog only; not a live promote`

Prefer **PAPER_GO** over **LIVE_GO** even if a future virgin hard_pass arrives. **LIVE_GO** only if skeptic disposition is LIVE_GO (extraordinary evidence); this fire is not that.

---

## Data frontier

Source: `results/xau_data_frontier.json`

| Field | Value |
|-------|--------|
| `refresh_ok` | true |
| `before_max` | 2026-08-06 18:00:00+00:00 |
| `after_max` | 2026-08-06 20:00:00+00:00 |
| `n_h1` | 11637 |
| `virgin_start` | 2026-08-06 19:00:00+00:00 |
| `n_virgin_bars` | **2** |
| `virgin_available` | **false** |

Refresh exported Wine MT5 → H1 end advanced to **2026-08-06 20:00 UTC**. Only **two** H1 bars exist strictly after last peek (`last_peeked_end` = 2026-08-06 18:00). Threshold for `virgin_available` is **≥24** H1 bars after last peek. Calendar day **after** 2026-08-06: **0** bars.

---

## Catalog

Source: `results/xau_frozen_champions_catalog.json`  
`n_entries=8` · roles: baseline_champion + refined_develop · no re-optimization · holdout not used for selection

| id | lane | role |
|----|------|------|
| `baseline_vol_gate_sparse` | vol_gate_sparse | baseline_champion |
| `baseline_donchian_turtle` | donchian_turtle | baseline_champion |
| `baseline_atr_trail_breakout` | atr_trail_breakout | baseline_champion |
| `baseline_htf_fib_xau` | htf_fib_xau | baseline_champion |
| `baseline_htf_pullback_new` | htf_pullback_new | baseline_champion |
| `refined_donchian_exit_N8_gate_pass` | donchian_turtle | refined_develop |
| `refined_atr_pack_entry20_no_atr_floor` | atr_trail_breakout | refined_develop |
| `refined_htf_fib_best_gate_pass` | htf_fib_xau | refined_develop |

Notes: vol_gate candidate deduped into baseline; all params develop-only.

---

## Virgin results or skip

Source: `results/xau_virgin_holdout_eval.json`

| Field | Value |
|-------|--------|
| `skipped` | **true** |
| `reason` | `insufficient bars after last_peeked_end` |
| `n_evaluated` | **0** |
| `catalog_n_entries` | 8 |
| Virgin hard_pass / `real=true` survivors | **0** |

**Skip is correct.** Two post-peek H1 bars cannot support n≥20 trade gates. No per-config virgin metrics, no ranking rewrite, no survivor file.

Prior contaminated-window hard_pass (`vol_gate_sparse` on 2026-01+) does **not** count as virgin confirmation.

---

## Skeptic disposition

Source: `results/xau_virgin_holdout_skeptic.md`

| Option | Chosen |
|--------|:------:|
| LIVE_GO | no |
| PAPER_GO | no |
| **WAIT_DATA** | **YES** |
| NO_GO (permanent kill) | no |

**Disposition: WAIT_DATA** — catalog ready and frozen; frontier measured; virgin window not evaluable; idle until data grows. Forced “promote now?” → NO-GO; loop name is WAIT_DATA so the scheduler waits on data rather than burning forbidden retunes.

Gates reserved for a future true virgin pass (do not relax): PF > 1.5, WR > 55, DD < 10, **n ≥ 20**, single sealed pass of the frozen 8 only, multiplicity-aware, no post-metric retune.

---

## Next steps

1. **Idle offline** until H1 bars with `time > 2026-08-06 18:00:00+00:00` reach **≥24** (preferably multi-day / weeks for any realistic n≥20 trades).
2. Re-run frontier refresh; if `virgin_available=true`, run **one** sealed virgin eval of the **frozen 8** only.
3. On any virgin hard_pass → default **PAPER_GO** (not LIVE_GO unless skeptic LIVE_GO + extraordinary evidence).
4. Do **not**: re-optimize on post-2026-01 bars, recycle contaminated HO as virgin, deploy paper/live from this skip, or invent survivors.

---

## Artifacts this fire

| Path | Role |
|------|------|
| `results/xau_data_frontier.json` | Refresh + frontier |
| `results/xau_frozen_champions_catalog.json` | 8 frozen configs |
| `results/xau_virgin_holdout_eval.json` | Explicit skip |
| `results/xau_virgin_holdout_skeptic.md` | Hostile review → WAIT_DATA |
| `results/xau_virgin_holdout_summary.md` | This note |
| `results/xau_loop_status.md` | Loop status update |

**One-liner:** Data refreshed; 2 post-peek H1 bars only; virgin eval correctly skipped; catalog of 8 frozen offline; skeptic **WAIT_DATA** — no PAPER_GO / LIVE_GO.
