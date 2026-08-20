# mt5-arch-integration

MetaTrader 5 **integration layer** for **Arch Linux**: Wine terminal + file-bridge EA (or [mt5linux](https://github.com/lucas-campagna/mt5linux) RPyC) + native Linux Python CLI.

This is **not** a full trading agent (no strategies, risk engine, or Telegram bot). Use it as a stable platform under Wine for account/market data and order plumbing from other apps.

**Docs index:** [docs/README.md](docs/README.md) · **Repo:** [github.com/Trujillofa/mt5-arch-integration](https://github.com/Trujillofa/mt5-arch-integration)

## Architecture (short)

**Recommended on Arch/Wine** — file bridge (avoids broken Python IPC):

```
Linux Python (mt5-arch, MT5_BACKEND=file)
        │ reads JSON files
        ▼
Wine: terminal64.exe + Mt5ArchBridge.mq5 EA  →  broker
```

**Optional** — mt5linux/RPyC (often hits `IPC timeout` under Wine 11):

```
Linux Python → RPyC :18812 → mt5server.exe → MetaTrader5 package → terminal64.exe
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Multi-broker:** one MT5 binary can hold multiple accounts only when each broker’s
**trade server is in that terminal’s server list**. Brand installers mainly pre-seed
that list; they are not separate trading engines. Feasibility and layout:
[docs/MULTI-BROKER-MT5.md](docs/MULTI-BROKER-MT5.md). Switch profiles with
`./scripts/16-use-broker.sh <name>` or `uv run mt5-arch brokers`.

## Quick start (Arch)

### 1. System packages

```bash
sudo pacman -S --needed wine winetricks curl ttf-liberation
```

### 2. Clone / enter repo

```bash
cd ~/Projects/trading/mt5-arch-integration
uv sync --all-extras
cp .env.example .env
# set MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
```

### 3. Install MT5 under Wine

```bash
./scripts/00-check-deps.sh
./scripts/01-create-prefix.sh
./scripts/02-install-mt5.sh      # uses ~/storage/Downloads/mt5setup.exe if present
./scripts/03-install-mt5server.sh
```

Complete the installer GUI, log into your broker, enable **Algo Trading**.

### 4. File bridge (recommended)

```bash
./scripts/04-start-terminal.sh   # log in to broker
./scripts/06-install-file-bridge.sh
```

In the MT5 window:

1. **Algo Trading** toolbar button → **green**
2. Tools → Options → Expert Advisors → allow algorithmic trading
3. MetaEditor (F4) → open `Experts/Mt5ArchBridge.mq5` → **Compile (F7)**
4. Navigator → Expert Advisors → **Mt5ArchBridge** → drag onto any chart
5. Window → **Tile Windows** (clears large black empty chart area)

```bash
# .env should have MT5_BACKEND=file (default)
uv run mt5-arch ping
uv run mt5-arch account
uv run mt5-arch symbols EURUSD XAUUSD
uv run mt5-arch candles EURUSD --tf H1 --count 10
```

### 5. Health check

```bash
./scripts/healthcheck.sh --ping
```

## CLI

| Command | Description |
|---------|-------------|
| `mt5-arch ping` | Terminal connectivity |
| `mt5-arch account` | Balance / equity / margin |
| `mt5-arch symbols SYM...` | Lot min/max/step, ticks |
| `mt5-arch candles SYM [--tf H1] [--count 10]` | OHLCV |
| `mt5-arch brokers [name]` | List multi-broker profiles (`config/brokers/*.env`) |
| `mt5-arch resolve BROKER SYM` | Canonical ↔ broker symbol (`config/symbols/registry.json`) |
| `mt5-arch config` | Redacted settings |
| `mt5-arch mcp` | Read-only MCP stdio server for AI agents (no orders) |

Add `--json` for machine-readable output. `-v` / `-vv` for logs.
AI Assistant / official MCP vs this command: [docs/HOWTO-MT5-AI-MCP.md](docs/HOWTO-MT5-AI-MCP.md).

## Documentation

Full index: **[docs/README.md](docs/README.md)**.

| Doc | Topic |
|-----|--------|
| [docs/MULTI-BROKER-MT5.md](docs/MULTI-BROKER-MT5.md) | One MT5 vs per-broker installers (feasibility) |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Network, Wine, Algo Trading, multi-broker |
| [docs/INSTALL-LINUX-ARCH.md](docs/INSTALL-LINUX-ARCH.md) | Arch install |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | File bridge vs RPyC |
| [docs/CHARTS-AND-STABILITY.md](docs/CHARTS-AND-STABILITY.md) | Charts / clipboard under Wine |
| [docs/HOWTO-MT5-AI-MCP.md](docs/HOWTO-MT5-AI-MCP.md) | Official MT5 AI Assistant / MCP vs `mt5-arch mcp` |

## Multi-broker (reference)

Prefer a **broker-branded** MT5 install per company you trade (server list + Wine auth reliability on Arch). Profiles:

```bash
./scripts/16-use-broker.sh vantage    # or wsf, fpmarkets
export WINEPREFIX=~/.mt5-vantage MT5_BACKEND=file
uv run mt5-arch account
```

| Profile | Prefix | Server (example) |
|---------|--------|------------------|
| `vantage` | `~/.mt5-vantage` | `VantageMarkets-Live 5` |
| `wsf` | `~/.mt5-wsf` | `WSFmarkets-Server` |
| `fpmarkets` | `~/.mt5-fpmarkets` | `FPMarketsSC-Live` |

Symlink brand folder → `MetaTrader 5` so scripts find `terminal64.exe` (see troubleshooting multi-broker section).

**Desktop / app menu icons** (after brand installs):

```bash
./scripts/17-install-desktop-launchers.sh
# App launcher: "Exness MT5" · "FP Markets MT5" · "Vantage International MT5" · "WSFmarkets MT5"
# CLI: mt5-exness | mt5-fpmarkets | mt5-vantage | mt5-wsf
```

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `MT5_LOGIN` | — | Account number |
| `MT5_PASSWORD` | — | Account password (never committed) |
| `MT5_SERVER` | — | Broker server name |
| `MT5_RPYC_HOST` | `localhost` | mt5server host |
| `MT5_RPYC_PORT` | `18812` | mt5server port |
| `WINEPREFIX` | `~/.mt5` (legacy) / brand prefixes | Wine prefix (`~/.mt5-exness`, `~/.mt5-vantage`, `~/.mt5-wsf`, `~/.mt5-fpmarkets`) |
| `MT5_BACKEND` | `file` | `file` (recommended) or `rpyc` |

## Tests

```bash
uv run pytest                    # offline unit tests
MT5_LIVE_SMOKE=1 uv run pytest -m live   # needs terminal + server
```

On the research branch, `tests/test_xau_pipeline.py` needs local XAU history
(`xauusd_data.csv`, ~9 MB). Regenerate with `python3 fetch_data.py` (host
`numpy`/`pandas`, not `uv run`). Plan for not tracking the CSV in git:
[results/xau_csv_history_plan.md](results/xau_csv_history_plan.md).

## Install on Arch (official Linux guide counterpart)

MetaQuotes documents Ubuntu/Debian/Fedora only:

- [Installation on Linux](https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux)

Arch equivalent (same Wine prefix `~/.mt5`, WebView2, mt5setup):

```bash
./scripts/mt5linux-arch.sh
```

Details: **[docs/INSTALL-LINUX-ARCH.md](docs/INSTALL-LINUX-ARCH.md)**

## Charts & day-to-day use

See **[docs/CHARTS-AND-STABILITY.md](docs/CHARTS-AND-STABILITY.md)** for:

- How to open charts, timeframes, zoom, indicators
- Hyprland freezes / black menus / mouse recovery
- `./scripts/07-restart-terminal.sh` and `./scripts/08-status.sh`

```bash
./scripts/04-start-terminal.sh --detach              # start (or warn if already running)
./scripts/04-start-terminal.sh --detach --fullscreen # start + fill active monitor
./scripts/07-restart-terminal.sh --fullscreen        # after freeze / invisible window
./scripts/09-fullscreen-terminal.sh                  # maximize main MT5 (tabs only)
./scripts/09-fullscreen-terminal.sh --dry-run        # print target WxH
./scripts/10-recover-terminal.sh --fullscreen        # window vanished / ghost process
./scripts/09-fullscreen-terminal.sh                  # maximize on active monitor (fullscreenstate 1)
./scripts/11-clipboard-bridge.sh start               # Wayland→X11 so Ctrl+V works in MT5
./scripts/12-paste-into-mt5.sh --type                # hard-type clipboard into focused MT5 field
./scripts/08-status.sh                               # process + bridge + ghost check
# Keys: Super+Alt+V paste · Super+Alt+Shift+V type (login/password)
```

## Security

- Never commit `.env`, passwords, Wine prefixes, or broker installers (`.exe`).
- Keep RPyC on **localhost** only.
- Treat a live terminal + bridge as full trading control; do not expose them on the network.
- Example logins in `config/brokers/*.env` are non-secret account IDs from local testing — replace with yours.

## Contributing

Issues and PRs welcome for Arch/Wine packaging, bridge robustness, and docs.
Keep the scope as a **platform layer** (no strategy engines in this repo).

```bash
uv sync --all-extras
uv run pytest
uv run ruff check src tests
```

## License

[MIT](LICENSE)
