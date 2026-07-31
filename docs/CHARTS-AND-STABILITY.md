# Charts and stability on Arch + Hyprland + Wine

Honest baseline: **Wine MT5 will not feel like Windows.** Charts, Market Watch, orders, and the **file bridge** work. Market store, AI panes, and MetaEditor are fragile. Official Python IPC (`mt5linux`) often hits `IPC timeout` — use **`MT5_BACKEND=file`**.

## What already works on this setup

| Feature | Status |
|---------|--------|
| Charts (candles, scroll, zoom, TFs) | Usable |
| Market Watch prices | Usable |
| Expert Advisors (e.g. Mt5ArchBridge) | Usable |
| Linux CLI `mt5-arch candles/symbols` | Usable (file bridge) |
| MetaEditor | Sometimes black / freeze |
| Tools → Options menus | Often black |
| Market / WebView2 store tab | Often black — ignore |
| MetaTrader5 Python IPC under Wine | Unreliable |

## Start the terminal

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/04-start-terminal.sh --detach
./scripts/04-start-terminal.sh --detach --fullscreen   # fill active monitor
# or after a freeze:
./scripts/07-restart-terminal.sh --fullscreen
./scripts/08-status.sh
```

Login only to **`WSFmarkets-Server`**. Title should look like:

`118248 - WSFmarkets-Server - Netting - EURUSD,H1`

Never use **MetaQuotes-Demo** for this account.

## Full-screen / maximize (smooth charting)

**Goal:** main MT5 window fills the **active** Hyprland monitor (e.g. 1920×1080).  
**Never** use Wine virtual desktop (`explorer /desktop=…`) — it breaks mouse under Hyprland.

```bash
# Print plan (works even if MT5 is not running)
./scripts/09-fullscreen-terminal.sh --dry-run
./scripts/09-fullscreen-terminal.sh --dry-run --json

# Apply maximize (preferred — better Wine input than exclusive fullscreen)
./scripts/09-fullscreen-terminal.sh --mode maximize

# Other monitor on dual 1080p
./scripts/09-fullscreen-terminal.sh --monitor HDMI-A-1

# Exclusive-style Hyprland fullscreen
./scripts/09-fullscreen-terminal.sh --mode fullscreen
```

Rules for a smooth full-screen experience:

1. **One main window** maximized — not undocked chart children.
2. **Charts stay as tabs** inside that window (Market Watch → double-click symbol).
3. Close windows titled like `EURUSD, Euro vs US Dollar` (undocked = often black under Wine).
4. Dual monitors: the script targets the **focused/active** monitor only (not span both).

## How to use charts

### Open a chart

1. **Market Watch** (left): find symbol (EURUSD, GBPUSD, …).
2. **Double-click** the symbol → new chart **tab** (do not undock).
3. Avoid “Chart Window” undocked floating windows under Wine.

### Timeframes

Toolbar: **M1 M5 M15 M30 H1 H4 D1 W1 MN** — click the TF you want.

### Zoom and scroll

| Action | How |
|--------|-----|
| Zoom in/out | Mouse wheel on chart, or toolbar magnifiers |
| Scroll history | Drag chart left/right |
| Fit | Toolbar “auto scroll / shift” icons |

### Multiple charts

1. Open several symbols/timeframes (tabs at bottom).
2. If layout is messy or half black: **Window → Tile Windows** (when menu draws).
3. Or close extra chart tabs (**X** on tab) and re-open one full chart.

### Indicators

1. **Navigator** (Ctrl+N if it works; else View menu / already-open Navigator).
2. **Indicators** → expand → drag onto chart (e.g. Moving Average, MACD).

### Templates

Right-click chart → **Template** → save/load (when menu works).

### Crosshair / objects

Toolbar icons for crosshair, trend lines, fibs. Prefer toolbar over Ctrl shortcuts (Hyprland often eats Ctrl).

## Gray/black chart area but prices move in Market Watch

1. Click a **chart tab** (EURUSD,H1), not the **Market** store tab.
2. Double-click the symbol in Market Watch again.
3. Close floating empty chart windows.
4. Restart: `./scripts/07-restart-terminal.sh`.

## Keep the Python bridge while charting

1. Attach **Mt5ArchBridge** to **one** chart (drag from Navigator → Expert Advisors).
2. Prefer **Algo Trading** green (toolbar).
3. Leave that chart open.

```bash
uv run mt5-arch ping
uv run mt5-arch account
uv run mt5-arch candles EURUSD --tf H1 --count 50
```

Bridge files live at:

`~/.mt5/drive_c/Program Files/MetaTrader 5/MQL5/Files/mt5_arch/`

## Hyprland tips

### Focus / find the window

- Workspaces: Super+1…9  
- List: `hyprctl clients | grep -i terminal`  
- Restart script moves MT5 onto the **current** workspace.

### Optional `hyprland.conf` rules

```conf
# Float MT5 so it does not wreck the tiling layout
windowrulev2 = float, class:^(terminal64\.exe)$
windowrulev2 = float, class:^(MetaEditor64\.exe)$

# Do not steal these if you want them inside MT5:
# (remove global binds for Ctrl+E / Ctrl+N if present)
```

### Input recovery

| Symptom | Fix |
|---------|-----|
| Stuck on File/View menu bar | Esc several times; if dead → `./scripts/07-restart-terminal.sh` |
| Ctrl+E / Ctrl+N do nothing | Hyprland bind — use toolbar / Alt menus instead |
| Mouse dead | Alt+Tab to MT5, click chart center; never use Wine “virtual desktop” |
| Frozen, high CPU | `./scripts/07-restart-terminal.sh` |
| Black Tools/Options | Skip them; Experts/OpenCL already set in config |
| Process running, no window | `./scripts/07-restart-terminal.sh` (moves to active workspace) |

### Avoid for stability

- Wine **virtual desktop** (`explorer /desktop=…`) — broke mouse here  
- Opening **Market** store tab for long periods  
- Multiple `terminal64.exe` instances  
- MetaQuotes-Demo login for WSFunded accounts  

## Account shows 0 balance in `mt5-arch account`

Charts can stream while `AccountInfo` returns zeros under Wine.

1. Check balance in the terminal UI (account / Navigator).
2. Confirm **master** password (not investor/read-only).
3. Confirm server is **WSFmarkets-Server**.
4. Re-login if needed; keep Mt5ArchBridge attached.

## When Wine is not enough (“full” MT5)

| Path | When |
|------|------|
| Harden Wine (this doc + scripts) | Default — charts + bridge |
| TradingView / broker web for charts | Best chart UX; MT5 only for execution |
| Windows VM (KVM/VirtualBox) | Need native Market, MetaEditor, Python IPC |
| Dual-boot Windows | Maximum fidelity |

## Related scripts

| Script | Role |
|--------|------|
| `04-start-terminal.sh` | Start MT5 (Hyprland-safe env) |
| `07-restart-terminal.sh` | Kill stuck terminal + relaunch + focus |
| `08-status.sh` | Process, window, bridge freshness |
| `06-install-file-bridge.sh` | Install/compile Mt5ArchBridge EA |

## Related docs

- [ARCH-SETUP.md](ARCH-SETUP.md) — install prefix / packages  
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — bridge and IPC  
- [ARCHITECTURE.md](ARCHITECTURE.md) — system diagram  
