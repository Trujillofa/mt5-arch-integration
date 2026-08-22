# How to run each offline backtest path

Research scripts use **`python3`** (host numpy/pandas), not `uv run`.
**`promote=no`. `live_go=false`.** No `OrderSend`. No `--live`.

This is a run index, not a second overlay operator manual. Chart install /
buffers / logger / export stay in [MT5-INTEGRATION-CAPABILITIES.md](../MT5-INTEGRATION-CAPABILITIES.md).
US-index London/XAU gates are **not** XAU Phase E; do not edit
`results/xau_loop_status.md` from these paths.

---

| Path | Command | Split | Costs / points | Detail |
|------|---------|-------|----------------|--------|
| XAU baseline | `python3 backtest.py` | Select `time < 2026-01-01` UTC (`results/xau_holdout_lock.json`). `--unbounded` warns. | Frozen Standard STP book (`results/xau_research_costs.json`). Spread + slip are **MT5 points**; XAU `point_size=0.01`. CLI mutation refused unless `--allow-cost-override`. | `--save` only writes `strategy_params.json`. Hours filter is **UTC hour**. Fill is same-bar close (historical; family screens use next-bar). |
| XAU family protocol | `python3 scripts/xau_sealed_family_cycle.py --charter …` or `--strict-charter --screen-only` | Same holdout lock. Selection never uses holdout. | Charter costs must equal the research book. | [XAU-FAMILY-PROTOCOL-V2.md](XAU-FAMILY-PROTOCOL-V2.md). Closed families stay closed. |
| HTF Fib offline | `python3 scripts/htf_fib_offline_backtest.py --csv … --from 2024-06-01 --to 2025-01-01` | Free `--from/--to` slice, **not** a sealed holdout. `--to` at/after `2026-01-01` refused unless `--unbounded`. | Frictionless 0.10 lot (`results/htf_fib_offline_lock.json`). PnL is price-delta × 100k × lots — not pips. | [HOWTO-HTF-FIB.md](../HOWTO-HTF-FIB.md) §13.3. Wine tester is a different path (`scripts/19-run-htf-fib-backtest.sh`). |
| US-index screens | `python3 scripts/us_index_session_backtest.py` / `us_index_session_autoresearch_vN.py` | v1–v3: holdout `et_date >= 2026-06-01`. v4–v8: holdout `>= 2026-07-01`, June burned. Rank develop-only. | $10k / 1 lot / **10 MT5 points** slip (0.01), not 10 index points. | [HOWTO-US-INDEX-SCALP.md](../HOWTO-US-INDEX-SCALP.md). Overlay ops stay in the capabilities doc. |
| EURUSD NY scalp | `python3 scripts/eurusd_ny_scalp_autoresearch.py` | `et_date < 2025-03-01` develop (lock). Not the US-index default. | 5 MT5 points slip / 30 pt spread cap. Point = 1e-5; $1/pt/lot. | Design: [EURUSD-NY-SCALP-DESIGN.md](EURUSD-NY-SCALP-DESIGN.md). Paper gate: `python3 scripts/eurusd_mr_limit_fill_paper_gate.py` (FAIL, closed). |

Commit **locks + slim metrics**. Do not add full trade dumps (`*_full.json` is gitignored). Historical result JSON already in git stays; regenerate from the script + lock if you need a full local dump.

Standing XAU disposition is in `results/xau_loop_status.md` (do not flip `promote` / `live_go` / `next_step` from a backtest edit).
