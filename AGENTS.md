# AGENTS.md — mt5-arch-integration

Compact operating rules. `CLAUDE.md` holds the deep detail; where the two overlap, this file is authoritative.

## Two layers in one repo

**Adopted charter:** [docs/CHARTER-RESEARCH-LAYER.md](docs/CHARTER-RESEARCH-LAYER.md) — **Option B (dual-layer)**, 2026-08-08. Merge allowed with hard boundaries; merge ≠ promote. See also [results/xau_charter_adopted.md](results/xau_charter_adopted.md).

**1. Platform layer** (the repo's stated scope): Wine MT5 + file bridge (or RPyC/mt5linux) + thin Python CLI.

- `src/mt5_arch/` — typed client + CLI (`config.py`, `client.py` RPyC backend, `file_bridge.py` EA backend, `models.py`, `cli.py`, `window_ops.py`).
- `scripts/NN-*.sh` — numbered install/ops steps, all `set -euo pipefail`, sourcing `scripts/lib.sh` (`load_dotenv` — environment always wins over `.env`; `find_terminal64`; `require_cmd`/`die`/`info`/`warn`).
- `mql5/` — MQL5 sources, chiefly `Mt5ArchBridge.mq5` (the file bridge EA).

**2. Offline research layer** (current branch `research/algo-trading-btc-gold-forex`, at repo root): `backtest.py`, `live_trader.py`, `fetch_data.py`, `scripts/xau_*.py`, `scripts/htf_fib_*.py`, `mql5/Indicators/*`, `results/`. Kept strictly offline/research-flagged. `src/mt5_arch` must never import from it.

## The one command gotcha

Research scripts run with plain `python3`, **not** `uv run` — they need `numpy`/`pandas`, which are deliberately **not** declared in `pyproject.toml` (host/venv site-packages only; `uv sync` won't install them).

```bash
python3 backtest.py                  # read-only search in develop window; prints metrics
python3 backtest.py --save           # ONLY this mutates strategy_params.json
```

## Verification

```bash
./scripts/00-check-deps.sh
uv run pytest                                        # offline unit tests
uv run pytest tests/test_client_unit.py::test_name   # single test
MT5_LIVE_SMOKE=1 uv run pytest -m live               # needs live terminal + bridge
uv run ruff check src tests
./scripts/healthcheck.sh --ping                      # live: terminal + bridge reachable
```

Note: `tests/test_xau_pipeline.py` asserts `xauusd_data.csv` exists and spans ≥300 days — it fails on a fresh clone until `python3 fetch_data.py` has run.

## Backends & the file bridge

`MT5_BACKEND=file` is the default (mt5linux/RPyC under Wine 11 often dies with `(-10005, 'IPC timeout')`).

- `FileBridgeClient` treats a stale `heartbeat.txt` (> `MT5_BRIDGE_MAX_AGE`, default 15s) as "bridge down" — a missing/stale heartbeat almost always means **Algo Trading is off or the EA was detached, not a code bug**.
- `MT5_BACKEND=rpyc` selects `client.py` (mt5server.exe on localhost:18812) instead.

## Multi-broker model

One Wine prefix **per broker** (`~/.mt5-vantage`, `~/.mt5-wsf`, `~/.mt5-fpmarkets`, `~/.mt5-exness`; legacy generic `~/.mt5`). Brand installers only pre-seed a terminal's server list — cross-company logins fail with `Invalid account`. Switch with `./scripts/16-use-broker.sh <name>` or `uv run mt5-arch brokers` (`config/brokers/*.env`).

Brand install dirs differ (`Program Files/Vantage International MT5`, `.../FP Markets MT5 Terminal`, …) and are **hardcoded in several places**: the search list in `scripts/19-run-htf-fib-backtest.sh`, a Vantage path in `fetch_data.py`, and the generic `MetaTrader 5` default in `file_bridge.py::default_bridge_dir` (overridable via `MT5_BRIDGE_DIR`). Adding a broker means updating all of them.

One MT5 install runs one `terminal64.exe` at a time — the headless tester defaults to `KILL_EXISTING=1` and kills a running terminal.

## MQL5 workflow

Repo `mql5/` is source of truth, but MT5 only sees what's copied into the Wine prefix's `MQL5/` tree and compiled. Editing a file here changes nothing until:

```bash
./scripts/18-install-forex-indicator.sh   # deploy indicators/EAs/ForexUtils.mqh into the prefix
# then MetaEditor F7, or headless: wine MetaEditor64.exe /compile:<file>.mq5
```

Indicators expose signals through `iCustom` buffers consumed by `ForexSignalLogger.mq5` (log-only, never `OrderSend`) and `ForexHtfFibTester.mq5`. **Read the buffer table in `mql5/README.md` / `docs/HOWTO-HTF-FIB.md` for the exact indicator version before wiring `CopyBuffer`** — the two docs don't agree on the HTF Fib signal index, and version drift is the usual cause.

Headless Strategy Tester runs go through `scripts/19-run-htf-fib-backtest.sh`; its header documents the non-obvious constraints: login from `Config/common.ini` (UTF-16) because `Login=0` fails, the `/config` ini must be ASCII + CRLF, `.set` presets must be UTF-16LE, `Expert=` takes a bare name.

## Research invariants

- **Causality.** `scripts/htf_fib_core.py` stamps a fractal pivot at its *confirmation* bar (`center + right`), never at the pivot center. Every fib/pivot consumer must import from this module — re-deriving pivots reintroduces lookahead bias.
- **State file.** Read `results/xau_loop_status.md` before touching the pipeline; it records the current disposition (`live_go`, `stop_reason`, `next_step`) of the XAU research loop. Standing disposition: RESEARCH_ONLY / promote=no.
- **Costs.** `simulate()` charges per-bar spread, commission and slippage **only if configured** — defaults are zero, so a bare call is frictionless and unfalsifiable. Replay the `costs` block stored in `strategy_params.json` with any fit.
- **Pre-registered holdout.** `results/xau_holdout_lock.json` fixes `holdout_start = 2026-01-01` under "NEVER used for selection". Anything that *selects* params must fit strictly before it — `backtest.py` enforces this by default (`--unbounded` breaks it and says so). Evaluating on the holdout is allowed; searching on it is not.
- **Fit window.** `strategy_params.json` carries a `data` block (bar count, start/end, CSV sha256) recording the window its metrics came from. Replay through `slice_to_window()`, not the whole CSV — every CSV extension changes the numbers, and `test_xau_pipeline.py` catches the divergence as a reproduction failure. A refit is the fix, not a widened tolerance.
- **No live orders.** `live_trader.py` is dry by default and needs an explicit `--live`. Never pass it, and never place orders from tests or smoke checks, without direct user consent.

## Conventions & safety

- Secrets only via `.env` / environment variables; never log `MT5_PASSWORD`. `.env`, `.env.broker`, `config/local.paths`, Wine prefixes, and `*.exe` installers are gitignored and must stay that way.
- RPyC stays bound to localhost only; treat a live terminal + bridge as full trading control.
- Prefer reusing an existing Wine prefix; only wipe with `01-create-prefix.sh --force` when the user asks.
- Do not push remotes or force-push without explicit user approval.
- Typed models in `mt5_arch/models.py` stay compatible with the agent bridge shapes where practical (`AccountInfo`, `SymbolInfo`, `Candle`).
