# Install MetaTrader 5 on Arch Linux

This is the **Arch Linux counterpart** of MetaQuotes’ official Linux guide:

**[Installation on Linux (Ubuntu / Debian / Mint / Fedora)](https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux)**

Official one-liner (not for Arch):

```bash
wget https://download.terminal.free/cdn/web/metaquotes.software.corp/mt5/mt5linux.sh
chmod +x mt5linux.sh
./mt5linux.sh
```

That script only detects Ubuntu, Linux Mint, Debian, and Fedora. On Arch it exits with “does not supported”. Use the Arch script below instead.

---

## What the official script does (Ubuntu)

| Step | Official (`mt5linux.sh`) |
|------|---------------------------|
| Detect OS | `/etc/os-release` → apt or dnf |
| Install Wine | WineHQ **staging** (`winehq-staging`) |
| Download | `mt5setup.exe` + WebView2 bootstrapper |
| Prefix | `WINEPREFIX=~/.mt5` |
| Windows version | `winecfg -v=win11` |
| Install WebView2 | `wine webview2.exe /silent /install` |
| Install MT5 | `wine mt5setup.exe` |
| Data folder | `~/.mt5/drive_c/Program Files/MetaTrader 5` |

---

## Arch Linux one-liner (this repo)

```bash
cd ~/Projects/trading/mt5-arch-integration
chmod +x scripts/mt5linux-arch.sh
./scripts/mt5linux-arch.sh
```

Or from a clone:

```bash
git clone <your-fork-or-path> mt5-arch-integration
cd mt5-arch-integration
./scripts/mt5linux-arch.sh
```

### Options

```bash
./scripts/mt5linux-arch.sh --skip-webview    # if WebView2 hangs (Market tab may stay black)
./scripts/mt5linux-arch.sh --reinstall-mt5   # run mt5setup.exe again
```

### Manual package install (equivalent of official “install Wine”)

```bash
# multilib may be required for 32-bit Wine libs — enable in /etc/pacman.conf if needed
sudo pacman -Syu --needed wine-staging winetricks curl cabextract \
  lib32-gnutls lib32-libxcomposite ttf-liberation

# If wine-staging is unavailable:
sudo pacman -S --needed wine
```

Arch ships Wine in **extra** (no WineHQ apt repo). Prefer **`wine-staging`** when available (closest to official `WINE_VERSION=staging`).

---

## After install

### Start the platform

```bash
export WINEPREFIX=~/.mt5
wine "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe" /portable
```

From this project (Hyprland-hardened):

```bash
./scripts/04-start-terminal.sh --detach
# freeze / invisible window:
./scripts/07-restart-terminal.sh
./scripts/08-status.sh
```

### Platform data directory

Same as MetaQuotes documentation:

```text
~/.mt5/drive_c/Program Files/MetaTrader 5
```

### Updates (official says keep OS + Wine current)

Ubuntu:

```bash
sudo apt update && sudo apt upgrade
```

Arch:

```bash
sudo pacman -Syu
```

---

## Ubuntu vs Arch mapping

| Official (Ubuntu) | Arch |
|-------------------|------|
| `sudo apt install winehq-staging` | `sudo pacman -S wine-staging` (or `wine`) |
| `sudo dpkg --add-architecture i386` | Enable **`[multilib]`** in `/etc/pacman.conf` |
| WineHQ apt key/repo | Not needed; use Arch packages |
| `wine-mono` (Fedora) | `winetricks` mono / shipped wine-mono |
| `WINEPREFIX=~/.mt5 winecfg -v=win11` | Same |
| WebView2 silent install | Same URLs and flags |
| `mt5setup.exe` | Same MetaQuotes URL |

---

## Hyprland / Wayland notes (not in official guide)

MetaQuotes targets a generic desktop. On Arch + Hyprland you will also want:

| Topic | Guidance |
|-------|----------|
| Input | Prefer XWayland: start with `DISPLAY=:0` and unset `WAYLAND_DISPLAY` |
| Virtual desktop | Do **not** use `wine explorer /desktop=...` (mouse breaks) |
| Detached chart windows | Often **black** — keep charts as **tabs** inside the main window |
| Market / AI panes | Need WebView2; if install fails, ignore Market tab |
| Ctrl shortcuts | Hyprland may steal Ctrl+E / Ctrl+N — use toolbar / Alt menus |
| Freezes | `./scripts/07-restart-terminal.sh` |

Full charting and recovery guide: [CHARTS-AND-STABILITY.md](CHARTS-AND-STABILITY.md).

---

## Linux Python automation (beyond official guide)

Official Linux install only covers the **terminal under Wine**. For Linux-native Python:

| Approach | Status on this machine |
|----------|------------------------|
| Official `MetaTrader5` package via **mt5linux/RPyC** | Often **IPC timeout** under Wine 11 |
| **File bridge** EA (`Mt5ArchBridge`) + `mt5-arch` CLI | **Working** |

```bash
./scripts/06-install-file-bridge.sh
# MetaEditor: open Experts/Mt5ArchBridge.mq5 → F7 compile
# Drag EA onto a chart, Algo Trading green
uv run mt5-arch candles EURUSD --tf H1 --count 20
```

---

## Already installed?

If you already have `~/.mt5` and `terminal64.exe` (this project’s earlier path), you do **not** need to reinstall. Use:

```bash
./scripts/08-status.sh
./scripts/04-start-terminal.sh --detach
```

Re-run `mt5linux-arch.sh` only for a clean reinstall or to force WebView2:

```bash
./scripts/mt5linux-arch.sh --reinstall-mt5
```

---

## References

- Official: [Install on Linux](https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux)
- Official script: `https://download.terminal.free/cdn/web/metaquotes.software.corp/mt5/mt5linux.sh`
- Wine downloads: [WineHQ](https://wiki.winehq.org/Download) (Arch: prefer distro packages)
- This repo: [ARCHITECTURE.md](ARCHITECTURE.md), [CHARTS-AND-STABILITY.md](CHARTS-AND-STABILITY.md)
