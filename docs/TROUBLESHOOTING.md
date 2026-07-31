# Troubleshooting

## Algo Trading is gray / `automated trading is disabled`

Python IPC **and** Expert Advisors need this on:

1. Toolbar: click **Algo Trading** until it is **green**.
2. Tools → Options → Expert Advisors → ☑ **Allow algorithmic trading**.
3. Terminal log will stop showing `Experts automated trading is disabled`.

## Large black empty area under charts

Wine + multi-chart layout glitch. In MT5:

- **Window → Tile Windows** (or Tile Horizontally / Vertically)
- Or close floating chart windows and re-open one chart full size
- Avoid maximizing across mixed DPI monitors when possible

## Black undocked chart window (`EURUSD, Euro vs US Dollar`)

Separate floating chart windows often paint **entirely black** under Wine. Close them. Open symbols only as **tabs inside the main terminal** (Market Watch → double-click). Prefer **bar** chart mode if candlestick bodies vanish (default bull body was black-on-black).

## File bridge: `No account.json` / stale heartbeat

Default backend is `MT5_BACKEND=file` (recommended on Arch/Wine).

1. `./scripts/06-install-file-bridge.sh`
2. In MetaEditor: open `MQL5/Experts/Mt5ArchBridge.mq5` → **Compile (F7)** → must produce `.ex5`
3. Navigator → Expert Advisors → **Mt5ArchBridge** → drag onto a chart
4. Enable Algo Trading (green) and “Allow live trading” on the EA
5. Confirm files appear:

```bash
ls -la ~/.mt5/drive_c/Program\ Files/MetaTrader\ 5/MQL5/Files/mt5_arch/
uv run mt5-arch account
```

## `mt5-arch ping` — connection refused (RPyC backend only)

**Cause:** `mt5server.exe` not running or wrong port. Prefer `MT5_BACKEND=file`.

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

## Ctrl+V / right-click Paste does nothing in MT5

MT5 is **XWayland**. Linux apps use the **Wayland** clipboard. Screenshots (PNG) on the clipboard also block text paste.

### Quick fix (most reliable)

1. Copy **text** (not a screenshot) from the browser.  
2. Click the MT5 password/login field.  
3. Press **Super+Alt+V** (paste) or **Super+Alt+Shift+V** (type keys — best for login).

Or from a terminal:

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/11-clipboard-bridge.sh start
./scripts/11-clipboard-bridge.sh once          # after each copy if needed
./scripts/12-paste-into-mt5.sh                 # focus MT5 + Shift+Insert
./scripts/12-paste-into-mt5.sh --type          # types characters (login/password)
```

### Checks

```bash
# Must show text, not PNG garbage:
wl-paste --type text
./scripts/11-clipboard-bridge.sh status        # wayland_text and x11_utf8 should match
```

If `wl-paste --type text` is empty, the clipboard is an **image** — copy the password again as text.

### Keys

| Key | Effect |
|-----|--------|
| Super+Alt+V | Force-paste into MT5 |
| Super+Alt+Shift+V | Type clipboard into focused field |
| Super+V | Omarchy universal paste (Shift+Insert) |
| Shift+Insert | Wine-friendly paste |
| Ctrl+V | Works only if X11 UTF8_STRING is populated |
