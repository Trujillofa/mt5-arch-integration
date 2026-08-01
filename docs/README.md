# Documentation index — mt5-arch-integration

Platform layer: **Wine MT5 + file bridge (or RPyC) + Python CLI** on Arch Linux.

## Start here

| Doc | Purpose |
|-----|---------|
| [../README.md](../README.md) | Project overview, quick start, CLI table |
| [INSTALL-LINUX-ARCH.md](INSTALL-LINUX-ARCH.md) | Arch install steps (Wine, prefix, MT5) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | File bridge vs RPyC data paths |
| [MULTI-BROKER-MT5.md](MULTI-BROKER-MT5.md) | **One MT5 vs per-broker installers** (feasibility + evidence) |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Network silence, Wine, multi-broker, Algo Trading |
| [CHARTS-AND-STABILITY.md](CHARTS-AND-STABILITY.md) | Black charts, maximize, clipboard paste under Wine |
| [ARCH-SETUP.md](ARCH-SETUP.md) | Extra Arch environment notes |

## Multi-broker (WSF / Vantage / FP Markets)

Broker-branded installers mainly pre-seed **server lists** and branding. They are not separate trading engines. Cross-company login fails (`Invalid account`).

| Profile | Prefix (outside git) | Switch |
|---------|----------------------|--------|
| `config/brokers/wsf.env` | `~/.mt5-wsf` | `./scripts/16-use-broker.sh wsf` |
| `config/brokers/vantage.env` | `~/.mt5-vantage` | `./scripts/16-use-broker.sh vantage` |
| `config/brokers/fpmarkets.env` | `~/.mt5-fpmarkets` | `./scripts/16-use-broker.sh fpmarkets` |

```bash
uv run mt5-arch brokers          # list profiles (no passwords)
uv run mt5-arch brokers vantage --json
```

Details and “one install for all brokers?” answer: [MULTI-BROKER-MT5.md](MULTI-BROKER-MT5.md).

## Ops scripts (selected)

| Script | Role |
|--------|------|
| `scripts/01-create-prefix.sh` | Wine prefix |
| `scripts/02-install-mt5.sh` | Generic MT5 installer |
| `scripts/04-start-terminal.sh` | Start terminal |
| `scripts/06-install-file-bridge.sh` | Deploy `Mt5ArchBridge` EA |
| `scripts/13-force-login-bridge.sh` | auto_login.ini + EA + restart (no password log) |
| `scripts/14-isolate-net-and-login.sh` | Stop docker/ts, force-login, restore |
| `scripts/15-bridge-down-and-login.sh` | Root bridge-down + force-login + restore |
| `scripts/16-use-broker.sh` | Activate `config/brokers/<name>.env` |
| `scripts/wine-net/force_src_bind.so` | Prefer LAN source IP under multi-homed hosts |

## Safety / secrets

- Never commit `.env`, `.env.broker`, `config/local.paths`, Wine prefixes, or installers (`.exe`).
- Do not publish live master passwords. Account **logins** in example profiles are non-secret identifiers used in docs; change them for your accounts.
- No live orders from smoke tests without an explicit flag and consent.

## Related

- Strategies / risk / Telegram: separate app repos (e.g. trading agents), not this platform layer.
