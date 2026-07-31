# Arch Linux setup guide

## Prerequisites

```bash
sudo pacman -S --needed wine winetricks curl ttf-liberation noto-fonts
# Often helpful for 64-bit Wine apps:
sudo pacman -S --needed lib32-gnutls lib32-libxcomposite
```

- Graphical session required for the MT5 installer and terminal UI (Hyprland / Omarchy: use a terminal inside the desktop).
- This machine may already have:
  - `wine` / `winetricks`
  - empty prefix `~/.mt5`
  - installer at `~/storage/Downloads/mt5setup.exe`

## Project install

```bash
cd ~/Projects/trading/mt5-arch-integration
# Prefer Python 3.11–3.12 if host is 3.14 and a dep fails:
# uv python install 3.12 && uv venv --python 3.12
uv sync --all-extras
cp .env.example .env
# edit .env: MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
```

## One-time Wine + MT5 install

```bash
./scripts/00-check-deps.sh
./scripts/01-create-prefix.sh          # WINEPREFIX=~/.mt5
./scripts/02-install-mt5.sh            # uses local mt5setup.exe if present
# Complete GUI installer; log into broker
./scripts/03-install-mt5server.sh
```

### Broker terminal checklist

1. File → Login to Trade Account (server e.g. `WSFmarkets-Server`).
2. Toolbar: **Algo Trading** enabled (green).
3. Tools → Options → Expert Advisors: allow automated trading / DLL if required by your stack.
4. Market Watch: show symbols you need (right-click → Show All if missing).

## Daily start

```bash
./scripts/04-start-terminal.sh         # or --detach
# wait until account is connected
./scripts/05-start-mt5server.sh        # or --detach
./scripts/healthcheck.sh --ping
uv run mt5-arch account
```

## Hyprland / Wayland notes

- Wine apps usually need XWayland (`DISPLAY=:0` or similar).
- If the window never appears, check `hyprctl clients` and floating rules.
- Headless servers: use a real desktop VM or the [mt5linux Docker](https://github.com/lucas-campagna/mt5linux/tree/master/docker) path instead of bare Xvfb (MT5 is picky).

## Optional systemd (user)

```bash
mkdir -p ~/.config/systemd/user
cp ops/systemd/mt5-*.service ~/.config/systemd/user/
# Edit ExecStart paths to match config/local.paths
systemctl --user daemon-reload
systemctl --user enable --now mt5-terminal.service mt5-rpyc.service
```

Prefer starting the terminal interactively until login + algo trading are stable.

## Python version

Host may be Python 3.14. `mt5linux` and transitive deps may lag. Use:

```bash
uv python install 3.12
uv venv --python 3.12
uv sync --all-extras
```

## Pinning mt5server

Override download URL:

```bash
export MT5SERVER_URL='https://github.com/lucas-campagna/mt5linux/releases/download/vX.Y.Z/mt5server.exe'
./scripts/03-install-mt5server.sh --force
```
