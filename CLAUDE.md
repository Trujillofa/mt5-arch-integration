# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` holds the short operating rules (scope, secrets, safe ops) and stays authoritative where the two overlap.

## Commands

```bash
uv sync --all-extras                    # install package + dev extras
uv run pytest                           # offline unit tests
uv run pytest tests/test_client_unit.py::test_name   # single test
MT5_LIVE_SMOKE=1 uv run pytest -m live  # needs a live terminal + bridge
uv run ruff check src tests             # lint (line-length 100, py311 target)
./scripts/00-check-deps.sh              # host deps (wine, winetricks, …)
./scripts/healthcheck.sh --ping         # live: terminal + bridge reachable
./scripts/08-status.sh                  # process / bridge / ghost-window check
```

The `mt5-arch` CLI (`uv run mt5-arch ping|account|symbols|candles|brokers|config|mcp`, plus `--json`, `-v/-vv`) is documented in `README.md`. `mcp` is a read-only stdio server (no orders); see `docs/HOWTO-MT5-AI-MCP.md`.

The offline research scripts (`backtest.py`, `fetch_data.py`, `live_trader.py`, `scripts/xau_*.py`, `scripts/htf_fib_*.py`) are run with plain `python3`, **not** `uv run` — they need `numpy`/`pandas`, which are deliberately not declared in `pyproject.toml` and come from the host/venv site-packages. `uv sync` does not install them.

```bash
python3 backtest.py            # read-only search inside the develop window, prints metrics
python3 backtest.py --save     # also rewrite strategy_params.json (+ its fit window)
```

## Two layers in one repo

**1. Platform layer** (the repo's stated scope in `AGENTS.md`: no strategy engines, no risk managers, no bots).

- `src/mt5_arch/` — typed client + CLI. `config.py` (pydantic-settings, env/`.env`), `client.py` (mt5linux/RPyC backend), `file_bridge.py` (EA snapshot backend), `models.py`, `cli.py`, plus `hypr_geometry.py`/`window_ops.py` for Hyprland window recovery.
- `scripts/NN-*.sh` — numbered install/ops steps, all `set -euo pipefail` sourcing `scripts/lib.sh` (`load_dotenv` — environment always wins over `.env`; `export_wine_env`; `find_terminal64`; `require_cmd`/`die`/`info`/`warn`).
- `mql5/` — MQL5 sources, chiefly `Mt5ArchBridge.mq5` (the file bridge EA).

**2. Offline research layer** (added on `research/algo-trading-btc-gold-forex`, currently at repo root). Strategy research for XAUUSD/FX/BTC: `backtest.py`, `live_trader.py`, `fetch_data.py`, `scripts/xau_*.py`, `scripts/htf_fib_*.py`, `mql5/Indicators/*`, `results/`. It sits inside a repo whose charter excludes strategy code — keep it strictly offline/research-flagged, and don't let it grow into the platform layer (`src/mt5_arch` must not import from it).

## Backends: why the file bridge is default

The official `MetaTrader5` Python package is Windows-only, and the mt5linux/RPyC path under Wine 11 frequently dies with `(-10005, 'IPC timeout')`. So `MT5_BACKEND=file` is the default:

```
Linux Python → JSON snapshots in <WINEPREFIX>/drive_c/Program Files/<brand>/MQL5/Files/mt5_arch
                    ▲ written by Mt5ArchBridge.mq5 EA attached to a chart
```

`FileBridgeClient` treats a stale `heartbeat.txt` (older than `MT5_BRIDGE_MAX_AGE`, default 15s) as "bridge down" — a missing/stale heartbeat almost always means Algo Trading is off or the EA was detached, not a code bug. `MT5_BACKEND=rpyc` selects `client.py` (mt5server.exe on localhost:18812) instead.

## Multi-broker model

Brand installers only pre-seed a terminal's **server list**; they are not separate engines, and cross-company logins fail with `Invalid account`. The working model is **one Wine prefix per broker** (`~/.mt5-vantage`, `~/.mt5-wsf`, `~/.mt5-fpmarkets`, `~/.mt5-fundednext`, `~/.mt5-ftmo`, `~/.mt5-alphacapital`, `~/.mt5-fundingpips`, `~/.mt5-exness`; legacy generic `~/.mt5`). Brokers with a `config/brokers/<name>.env` are selected via `./scripts/16-use-broker.sh <name>`; `~/.mt5-exness` exists on disk but there is no `config/brokers/exness.env` yet, so Exness is selected by exporting `WINEPREFIX` directly (same note as `docs/MT5-INTEGRATION-CAPABILITIES.md`).

Consequence: install directory names differ per brand (`Program Files/Vantage International MT5`, `.../FP Markets MT5 Terminal`, …). Those names live in `config/broker_install_dirs.json` and are consumed by `scripts/19-run-htf-fib-backtest.sh` and `fetch_data.py`. The generic `MetaTrader 5` default in `src/mt5_arch/file_bridge.py::default_bridge_dir` stays overridable via `MT5_BRIDGE_DIR` (platform layer — not wired to that JSON). Adding a broker means updating the JSON (and adding a broker env when ready), not scattering paths.

Also: one MT5 install runs **one** `terminal64.exe` at a time. The headless tester defaults to `KILL_EXISTING=1` and will kill a running terminal.

## MQL5 workflow

Repo `mql5/` is the source of truth, but MT5 only sees what has been copied into the Wine prefix's `MQL5/` tree and compiled. Editing a file here changes nothing until:

```bash
./scripts/18-install-forex-indicator.sh     # deploy indicators/EAs/ForexUtils.mqh into the prefix
# then MetaEditor F7, or headless: wine MetaEditor64.exe /compile:<file>.mq5
```

Indicators expose signals through `iCustom` buffers consumed by `ForexSignalLogger.mq5` (log-only, never calls `OrderSend`) and `ForexHtfFibTester.mq5` (Strategy Tester EA). Buffer indices are documented in `mql5/README.md` (authoritative map) and `docs/HOWTO-HTF-FIB.md`; **read the buffer table for the exact indicator version before wiring `CopyBuffer`**.

Headless Strategy Tester runs go through `scripts/19-run-htf-fib-backtest.sh`, whose header documents the non-obvious constraints it works around: login must come from `Config/common.ini` (UTF-16) because `Login=0` yields "account not specified", the `/config` ini itself must be **ASCII + CRLF**, `.set` presets must be UTF-16LE, and `Expert=` takes a bare name.

## Research invariants

- **Causality.** `scripts/htf_fib_core.py` stamps a fractal pivot at its *confirmation* bar (`center + right`), never at the pivot center — a pivot is not knowable when it forms. Every fib/pivot consumer must import from this module rather than re-deriving pivots; re-implementing it is how lookahead bias gets reintroduced.
- **State file.** `results/xau_loop_status.md` records the current disposition (`live_go`, `stop_reason`, `next_step`) of the long-running XAU research loop, with per-run artifacts in `results/*.json` and hostile-review `*_skeptic.md` notes. Read it before touching the pipeline; the standing disposition is RESEARCH_ONLY / promote=no.
- **Costs.** `simulate()` charges per-bar spread (`spread_col`, points from `MqlRates.spread`), commission and slippage; the settings a fit used are stored in `strategy_params.json`'s `costs` block and must be replayed with it. Defaults are zero — if you call `simulate()` without costs you get a frictionless result, which is what made every earlier gate result unfalsifiable. Commission and slippage are **not** obtainable from history (MT5 exposes them only on executed deals), so they stay explicit assumptions.
- **Pre-registered holdout.** `results/xau_holdout_lock.json` fixes `holdout_start = 2026-01-01` under the rule "NEVER used for selection". Anything that *selects* params must fit strictly before it — `backtest.py` enforces this by default (`--to` overrides, `--unbounded` breaks it and says so). Evaluating on the holdout is allowed; searching on it is not.
- **Window labeling.** Do not relabel in-sample or already-peeked windows as OOS, and do not retune on holdout data. Optimizers write candidate params to `results/`; only `backtest.py --save` updates `strategy_params.json` (a plain run is read-only, so tests and exploratory runs never mutate tracked state).
- **Fit window.** `strategy_params.json` carries a `data` block (bar count, start/end, CSV sha256) recording the window its metrics came from. Replay params through `slice_to_window()` rather than the whole CSV — otherwise every CSV extension silently changes the numbers, and `tests/test_xau_pipeline.py` will catch the divergence as a reproduction failure. A refit is the fix, not a widened tolerance.
- **No live orders.** `live_trader.py` is dry by default and needs an explicit `--live`. Never pass it, and never place orders from tests or smoke checks, without direct user consent.

## Data

`xauusd_data.csv` (H1 + M15, ~24 months) is produced by `fetch_data.py`, which falls back through four sources: Windows `MetaTrader5` package → Wine export CSV from `mql5/Scripts/ExportXauHistory.mq5` (see `scripts/export-xau-from-wine-mt5.sh`) → mt5linux RPyC → Dukascopy/yfinance offline. `tests/test_xau_pipeline.py` asserts the CSV exists and spans ≥300 days, so those tests fail on a fresh clone until data is fetched.

## Secrets and safety

`.env`, `.env.broker`, `config/local.paths`, Wine prefixes, and `*.exe` installers are gitignored and must stay that way. Never log `MT5_PASSWORD` (`Settings.redacted_summary()` is the safe printer). Keep RPyC bound to localhost. Only wipe a Wine prefix (`01-create-prefix.sh --force`) when explicitly asked.
