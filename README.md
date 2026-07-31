# mt5-arch-integration

MetaTrader 5 **integration layer** for **Arch Linux**: Wine terminal + [mt5linux](https://github.com/lucas-campagna/mt5linux) RPyC bridge + native Linux Python CLI.

This is **not** a full trading agent. For strategies, risk, and paper/live modes see [`mt5-trading-agent`](../mt5-trading-agent).

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
| `mt5-arch config` | Redacted settings |

Add `--json` for machine-readable output. `-v` / `-vv` for logs.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `MT5_LOGIN` | — | Account number |
| `MT5_PASSWORD` | — | Account password (never committed) |
| `MT5_SERVER` | — | Broker server name |
| `MT5_RPYC_HOST` | `localhost` | mt5server host |
| `MT5_RPYC_PORT` | `18812` | mt5server port |
| `WINEPREFIX` | `~/.mt5` | Wine prefix |

## Tests

```bash
uv run pytest                    # offline unit tests
MT5_LIVE_SMOKE=1 uv run pytest -m live   # needs terminal + server
```

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
./scripts/04-start-terminal.sh --detach   # start (or warn if already running)
./scripts/07-restart-terminal.sh          # after freeze / invisible window
./scripts/08-status.sh                    # process + bridge freshness
```

## Docs

- [Charts & stability (Hyprland/Wine)](docs/CHARTS-AND-STABILITY.md)
- [Arch setup](docs/ARCH-SETUP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Security

- Never commit `.env` or Wine prefixes.
- Keep RPyC on localhost.
- Treat mt5server as full trading control plane.

## License

MIT
