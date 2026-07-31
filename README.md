# mt5-arch-integration

MetaTrader 5 **integration layer** for **Arch Linux**: Wine terminal + [mt5linux](https://github.com/lucas-campagna/mt5linux) RPyC bridge + native Linux Python CLI.

This is **not** a full trading agent. For strategies, risk, and paper/live modes see [`mt5-trading-agent`](../mt5-trading-agent).

## Architecture (short)

```
Linux Python (mt5-arch / mt5linux)
        │ RPyC :18812
        ▼
Wine: mt5server.exe  →  MetaTrader5 package  →  terminal64.exe  →  broker
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

### 4. Run

```bash
./scripts/04-start-terminal.sh   # keep running
./scripts/05-start-mt5server.sh  # keep running (second terminal)
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

## Docs

- [Arch setup](docs/ARCH-SETUP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Security

- Never commit `.env` or Wine prefixes.
- Keep RPyC on localhost.
- Treat mt5server as full trading control plane.

## License

MIT
