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

Hyprland **0.53+** (you are on **0.56**): use `windowrule` + `match:` — **`windowrulev2` is deprecated**.

Shipped rules: `ops/hyprland/mt5-window-rules.conf` (source from `~/.config/hypr/hyprland.conf`).

```conf
# Float Login only (do not force-float the main shell)
windowrule = float on, match:class ^(terminal64\.exe)$, match:title ^(Login)$
windowrule = center on, match:class ^(terminal64\.exe)$, match:title ^(Login)$
windowrule = no_shadow on, match:class ^(terminal64\.exe)$
windowrule = float on, match:class ^(MetaEditor64\.exe)$

# Do not steal these if you want them inside MT5:
# (remove global binds for Ctrl+E / Ctrl+N if present)
```

### Input recovery

| Symptom | Fix |
|---------|-----|
| Stuck on File/View menu bar | Esc several times; if dead → `./scripts/07-restart-terminal.sh` |
| Ctrl+E / Ctrl+N do nothing | Hyprland bind — use toolbar / Alt menus instead |
| **Ctrl+V paste does nothing** | Start bridge: `./scripts/11-clipboard-bridge.sh start` — see [Clipboard / paste](#clipboard--paste-ctrlv) |
| Mouse dead | Alt+Tab to MT5, click chart center; never use Wine “virtual desktop” |
| Frozen, high CPU | `./scripts/07-restart-terminal.sh` |
| Black Tools/Options | Skip them; Experts/OpenCL already set in config |
| Process running, no window (**ghost**) | `./scripts/10-recover-terminal.sh --fullscreen` |
| Window vanishes after **chart click** | Same — Wine unmapped the surface; run recover (not “lost forever”) |
| Window tiny on shared workspace | `./scripts/09-fullscreen-terminal.sh` (uses `fullscreenstate 1`) |
| **New Order (F9) glitches / slides** | Wine restores stale coords; Hyprland `center` was animating the fight. Rules in `ops/hyprland/mt5-window-rules.conf` use `float` + `center` + `no_anim` for `Order:` (and other non-shell dialogs). `hyprctl reload` after edits. Keep focus on the MT5 monitor when opening — center follows the focused monitor. |

## Clipboard / paste (Ctrl+V)

**Cause:** Omarchy apps copy into the **Wayland** clipboard. MetaTrader runs as **XWayland** and only reads the **X11** clipboard. Without a bridge, paste is empty.

**Fix (shipped):**

```bash
# Install once (if needed)
sudo pacman -S --needed wl-clipboard xclip

# Start bridge (also auto-started by 04/07/10 + Hyprland autostart)
./scripts/11-clipboard-bridge.sh start
./scripts/11-clipboard-bridge.sh status   # wayland_text and x11_utf8 must match
```

**Important:** copy **text**, not a screenshot. If the clipboard is a PNG, paste into login fields will stay empty.

Then in MT5 (click the field first):

| Key | Action |
|-----|--------|
| **Super+Alt+V** | Force-paste into MT5 (recommended) |
| **Super+Alt+Shift+V** | **Type** clipboard chars (best for password/login) |
| **Ctrl+V** / **Shift+Insert** | Native paste (needs bridge + text on X11) |
| **Super+V** | Omarchy universal paste → Shift+Insert |
| Right-click → Paste | Works only if X11 UTF8 text is set |

One-shot / hard paste:

```bash
./scripts/11-clipboard-bridge.sh once
./scripts/12-paste-into-mt5.sh          # focus + Shift+Insert
./scripts/12-paste-into-mt5.sh --type   # type into focused field
```
**Ghost process:** `terminal64.exe` is alive but Hyprland has **zero** `terminal64.exe` clients. Login-only is *not* a ghost (recover will wait for the main shell). Always:

```bash
/home/yderf/Projects/trading/mt5-arch-integration/scripts/10-recover-terminal.sh --fullscreen
```

`09-fullscreen-terminal.sh` auto-calls recover on true ghost (exit code 3), with a nesting guard so it cannot loop forever. `04-start-terminal.sh` also redirects to recover when it finds a ghost PID.

Maximize uses Hyprland **`fullscreenstate 1 1`** (absolute maximize, not toggle; not exclusive fullscreen 2). That fills the active monitor (≈1896×1030 with gaps on 1920×1080) even when other tiled windows share the workspace. Prefer a **dedicated empty workspace** for MT5; avoid minimize and undocked charts.

Optional Hyprland rules: `ops/hyprland/mt5-window-rules.conf`

### Avoid for stability

- Wine **virtual desktop** (`explorer /desktop=…`) — broke mouse here  
- **Minimize button** and undocking charts (both can unmap the window)  
- Opening **Market** store tab for long periods  
- Multiple `terminal64.exe` instances  
- MetaQuotes-Demo login for WSFunded accounts  
- Spamming timeframe buttons on a chart with `ForexHtfPivotsFib` — prefer **one chart tab per TF**; see [HOWTO-HTF-FIB.md](HOWTO-HTF-FIB.md) §3  

## Freeze watchdog

`ops/diagnostics/mt5-freeze-watch.sh` (user timer `mt5-freeze-watch.timer`) samples each terminal’s **main** thread and captures on:

| Mode | Signature | Example |
|------|-----------|---------|
| spin | ~100% of one core, `wchan=0` | SIGSEGV livelock in win32u |
| deadlock | 0 jiffies, `wchan=futex_do_wait` for 3 ticks | win32u AB–BA lock |

On fire it: logs → **desktop notify** → capture (eu-stack + gdb) → optional webhook (`MT5_WATCH_WEBHOOK_URL`). **Does not restart** unless `MT5_WATCH_RESTART=1` (opt-in; chart state risk).

```bash
systemctl --user status mt5-freeze-watch.timer
journalctl --user -u mt5-freeze-watch.service -f
ls "${XDG_RUNTIME_DIR}/mt5-freeze-watch/"
```

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
| `08-status.sh` | Process, window, ghost check, bridge |
| `09-fullscreen-terminal.sh` | Maximize main MT5 on active monitor |
| `10-recover-terminal.sh` | Ghost process / vanished window recovery |
| `06-install-file-bridge.sh` | Install/compile Mt5ArchBridge EA |

## Related docs

- [ARCH-SETUP.md](ARCH-SETUP.md) — install prefix / packages  
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — bridge and IPC  
- [ARCHITECTURE.md](ARCHITECTURE.md) — system diagram  
