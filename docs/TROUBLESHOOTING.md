# Troubleshooting

## `mt5-arch ping` — connection refused

**Cause:** `mt5server.exe` not running or wrong port.

```bash
./scripts/healthcheck.sh
ss -ltn | grep 18812
./scripts/05-start-mt5server.sh
```

Ensure `MT5_RPYC_HOST` / `MT5_RPYC_PORT` in `.env` match the server.

## `initialize() failed` / IPC errors

1. Is `terminal64.exe` running and **logged in**?
2. Is **Algo Trading** enabled?
3. Restart order: terminal first → wait for connection → then mt5server.
4. Try without credentials first (`unset MT5_PASSWORD` and rely on already-logged terminal), then with login kwargs.

## Installer / terminal window never opens

- Run from a session with `DISPLAY` or `WAYLAND_DISPLAY`.
- `winecfg` in the same `WINEPREFIX` to verify Wine GUI works.
- Reinstall fonts: `winetricks -q corefonts`.

## Blank or black MT5 UI under Wine

```bash
export WINEPREFIX=~/.mt5
winetricks -q corefonts vcrun2019
# Optional experiments (document what works for you):
# winetricks -q gdiplus
```

Update Wine (`pacman -Syu wine`) — MT5 tracks recent builds better with current Wine.

## Symbol not found

- Add symbol in Market Watch.
- Broker-specific names (e.g. `EURUSD.m`, `XAUUSD+`) — use exact names from the terminal.

## Automated trading disabled

- Toolbar Algo Trading button.
- Account type may restrict API — confirm with broker (prop firm rules).
- `terminal_info().trade_allowed` should be true (`mt5-arch ping --json`).

## winetricks fails offline or with errors

Often non-fatal. Continue to MT5 install; only hard-require a working `terminal64.exe`.

## Python / package import errors on 3.14

```bash
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
uv sync --all-extras
```

## Port already in use

```bash
ss -ltnp | grep 18812
# kill stale wine/mt5server, or:
export MT5_RPYC_PORT=18813
./scripts/05-start-mt5server.sh
```

## Do not bind RPyC to the public internet

`mt5server` effectively allows remote control of a trading terminal. Keep it on `127.0.0.1` unless you have a secured tunnel.
