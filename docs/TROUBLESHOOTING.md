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

## Generic MetaTrader 5 window is 4K / leftover login

Wine often saves `Config/terminal.ini` `[Window]` as the dual-monitor desktop
(`Right=3840` `Bottom=2160`) while the real panel is 1920×1080. A **generic**
tree (`Program Files/MetaTrader 5`) inside another broker’s prefix can also keep
a leftover `Config/common.ini` `Login=` / `Server=` from a previous company
(title bar looks logged in; Journal `Network` after restart is 0).

**Never** create a Wine virtual desktop (`explorer /desktop=…`) — it breaks
mouse under Hyprland. **Never** `wineserver -k` to “fix” this window (that
kills every terminal in the prefix). `LogPixels` is prefix-wide; do not change
it while branded books share the prefix.

1. Stop **only** the generic pid (`cwd` ends with `Program Files/MetaTrader 5`).
   Leave branded folders (FTMO / Vantage / FP / WSF / FundedNext) running.
2. Do not use that generic tree for Seven Desk live orders or probes. Live
   paths require the branded `terminal64.exe` (`FTMO Global Markets MT5
   Terminal`, `WSFmarkets MT5 Terminal`, `FundedNext MT5 Terminal`).
3. Point `Config/common.ini` `[Common]` `Login=` / `Server=` at **this
   prefix’s** broker. Do not add `Password=` here. Password stays in
   `auto_login.ini` (chmod 600); never log it.

Trade-auth is **not** the window title. Require non-empty `currency` **and**
`leverage > 0` from the **branded** `account.json`, plus a Journal `Network`
`authorized` line for that login. Official MCP bind `10048` on
`127.0.0.1:22346` is expected when another prefix (often Vantage) already owns
the port — ignore it.

On this host the generic MetaQuotes tree is often **title-only** even after a
clean portable start ([MULTI-BROKER-MT5.md](MULTI-BROKER-MT5.md) silent
`Network=0`). Prefer the branded folder. Evidence:
`.net-fix-evidence/GENERIC-SCALE-CONNECT.md`.

## Black undocked chart window (`EURUSD, Euro vs US Dollar`)

Separate floating chart windows often paint **entirely black** under Wine. Close them. Open symbols only as **tabs inside the main terminal** (Market Watch → double-click). Prefer **bar** chart mode if candlestick bodies vanish (default bull body was black-on-black).

## File bridge: `No account.json` / `No heartbeat.txt` / stale heartbeat

Default backend is `MT5_BACKEND=file` (recommended on Arch/Wine).

Liveness comes from `heartbeat.txt` **only** — the EA writes it last *inside*
`WriteAll()`, after the JSON snapshots, so a fresh heartbeat means
`account.json` / `symbols.json` / `candles_*.json` are at least as fresh. All
three errors mean the same thing: **the EA is not writing**. `No heartbeat.txt` in
particular is what a leftover or copied `account.json` looks like once the EA is
detached (Algo Trading off, EA removed, or `OnInit` failed on an empty/wrong
`InpBroker`). `./scripts/08-status.sh` reports the same heartbeat age the CLI
checks, so it agrees with `mt5-arch ping`.

**Exception — deal dump:** `DumpDealsIfRequested()` runs *after* `WriteAll()` on
the timer. A fresh heartbeat does **not** mean `deals_export.csv` is complete.
`mt5-arch deals` gates on `dump_deals.done` only. See below.

## File bridge: `Missing dump_deals.done` / torn `deals_export.csv`

`uv run mt5-arch deals` reads a dump the EA already finished. It does not look
at heartbeat age. Completeness is `dump_deals.done` (body
`rows=<N> from=<ts> to=<ts> at=<ts>`). Put() is a truncate-write (no temp+rename),
so a torn CSV or torn `.done` fails closed as `FileBridgeError`, never a raw
`csv.Error` / `ValueError`.

Deal `time` is trade-server `YYYY.MM.DD HH:MM:SS` (`TimeToString(DEAL_TIME)`),
not UTC — same class of clock as the heartbeat `TimeLocal()` note in
[research/PHASE0-DISCOVERY.md](research/PHASE0-DISCOVERY.md).

To ask the live EA for a new 14-day dump (writes into the Wine prefix):

```bash
uv run mt5-arch deals --request --timeout 30 --json
```

That touches `dump_deals.request`. The next timer tick writes the CSV, deletes
the request file, then writes `dump_deals.done`. A leftover `.done` from an
earlier dump is ignored until its mtime is not older than the request.

`--request` needs a live EA, so it checks the heartbeat first and reports
`No heartbeat.txt` / stale immediately rather than burning the whole timeout.
Plain `deals` does not, so a finished dump stays readable after the EA is gone.

### `EA v1.23 ... does not serve dump_deals.request`

The deal dump landed in EA **v1.24**. A terminal running an older build ignores
`dump_deals.request` entirely, so waiting for `dump_deals.done` can only ever
time out. EA ≥ 1.24 appends `version=` to `heartbeat.txt`:

```
1788251227 connected=1 writer_chart=26180515069381 symbol=EURUSD version=1.24
```

`--request` reads it and fails immediately on a known-too-old EA, without
writing a request file the EA would never consume. Fix by redeploying:
`./scripts/06-install-file-bridge.sh`, then reattach the EA to a chart.

A heartbeat with **no** `version=` means unknown, not too old — builds before
1.24 wrote no version field, and some of them do serve the dump. There
`--request` still waits, and says so if it times out. The version in the Journal
line (`Mt5ArchBridge WRITER v…`) and in the heartbeat come from one
`BRIDGE_VERSION` define; `tests/test_ea_version.py` fails if they drift from
`#property version`, because a build that misreports its version is exactly how
a stale EA goes unnoticed.

On timeout the request file is **left in place on purpose** — the EA dumps on its
next timer tick, so re-run `mt5-arch deals` (no `--request`) to read the result.
The EA also leaves it when it skips: trade-server time before 2020-01-01,
`HistorySelect` failed, or FileOpen failed.

Default `mt5-arch deals` never creates `dump_deals.request`.

The EA writes both files with `FILE_TXT|FILE_ANSI` — the Wine host codepage, not
UTF-8. A broker-set comment with an accented character is therefore not valid
UTF-8; the reader decodes UTF-8 first and falls back to cp1252, so one such byte
does not cost the whole dump.

1. `./scripts/06-install-file-bridge.sh`
2. In MetaEditor: open `MQL5/Experts/Mt5ArchBridge.mq5` → **Compile (F7)** → must produce `.ex5`
3. Navigator → Expert Advisors → **Mt5ArchBridge** → drag onto a chart
4. Enable Algo Trading (green) and “Allow live trading” on the EA
5. Confirm files appear:

```bash
ls -la ~/.mt5/drive_c/Program\ Files/MetaTrader\ 5/MQL5/Files/mt5_arch/
uv run mt5-arch account
```

## Balance always 0 / no orders / Journal has no Network lines

**This is not the Python CLI inventing zeros.** The EA writes what MQL5
`AccountInfo*` returns. A **cached** login+server can appear in the window
title while the trade server is offline:

| Symptom | Meaning |
|---------|---------|
| `currency`/`leverage` empty, balance `0` | No live trade session |
| Journal: only Terminal/Experts, **no `Network`** | Auth never completes |
| `mt5-arch ping` exit 2 / connected false | Honest offline (after fix) |
| Wine `connect` → `STATUS_DEVICE_NOT_READY` | TCP under Wine failing |

**Force login from `.env` + re-attach EA:**

```bash
# Prefix-scoped kill: WINEPREFIX=~/.mt5-vantage leaves FP/Exness/WSF up.
WINEPREFIX=~/.mt5-vantage ./scripts/13-force-login-bridge.sh
# writes auto_login.ini (chmod 600), restarts only that prefix with /config
uv run mt5-arch account
```

**Journal still empty of Network after that:**

1. Toolbox → **Journal** (not Experts). Clear filters.
2. Host can reach HTTPS but Wine may still fail TLS/connect — check Docker
   bridges / Tailscale not stealing routes; default route should be LAN.
3. Confirm server name is exact (`WSFmarkets-Server`, not MetaQuotes-Demo).
4. Prefer broker’s own MT5 build if they ship one (server list embedded).
5. Proof of Wine socket failure (optional):

```bash
WINEPREFIX=~/.mt5 WINEDEBUG=+winsock wine terminal64.exe /portable \
  /config:auto_login.ini 2>&1 | rg 'connect failed|ConnectEx' | head
```

`0xc00000a3` = device not ready / nonblocking connect issue under Wine.
Host `python3` connecting to the same IP:443 may still succeed — that means
the problem is **Wine’s stack**, not your password and not our bridge parser.

### Docker / multi-homed source IP (Send-Q stuck, 4/0 kb)

If `ss` shows `terminal64`/`main` ESTAB from `172.17/18/19.x` (Docker bridges)
or Tailscale with **Send-Q > 0** and no Journal `Network` lines, Wine is
picking a bad source address. `13-force-login-bridge.sh` auto-loads
`scripts/wine-net/force_src_bind.so` (LD_PRELOAD) to bind outbound sockets to
the LAN IP (`MT5_FORCE_SRC_IP`, default from `ip route get 1.1.1.1`).
It must **not** rewrite `127.0.0.1` listens — that remaps official MT5 MCP
off localhost (`ss` shows `192.168.0.144:22346`, Cursor's
`http://127.0.0.1:22346/mcp` gets Connection refused). After rebuilding the
`.so`, restart that prefix's `wineserver` (not only `terminal64.exe`);
`/proc/<pid>/maps` showing `force_src_bind.so (deleted)` means the old
inode is still loaded.

```bash
# rebuild helper if needed
gcc -shared -fPIC -O2 -o scripts/wine-net/force_src_bind.so \
  scripts/wine-net/force_src_bind.c -ldl
./scripts/13-force-login-bridge.sh
ss -tnp | grep -E 'terminal|wineserver'   # expect src 192.168.x.x not 172.x
```

Even with LAN source, TLS may still stall (Send-Q stuck) under Wine 11 + MT5 —
that remains an environment limit until Wine/network path is fixed system-wide.

### Isolation recipe tried (2026-08-01)

Automated test (see `.net-fix-evidence/SUMMARY.md`):

1. `docker stop` all running containers + `tailscale down`
2. `./scripts/13-force-login-bridge.sh` (LAN preload on)
3. `winetricks -q winhttp crypt32` then **reverted crypt32 to builtin**
   (native crypt32 caused `Certificates initialization ... failed`)

**Result:** still **zero** Journal `Network` lines; account shell offline
(login/server cached, currency/leverage empty).

Helper for repeat: `./scripts/14-isolate-net-and-login.sh` (stops containers +
Tailscale, force-login, restores on exit).

**Not sufficient alone:** stopping containers does not remove `docker0`/`br-*`
interfaces; full iface-down needs root.

### Full bridge iface-down recipe (root, Phase 4)

`./scripts/14-isolate-net-and-login.sh` only stops containers + Tailscale.
To also bring Docker bridges down during force-login (and restore on exit):

```bash
# requires passwordless or interactive sudo for ip link
export WINEPREFIX=~/.mt5-staging   # or your active prefix
./scripts/15-bridge-down-and-login.sh --wait-sec=60
```

What it does: `docker stop` running containers → `tailscale down` →
`ip link set docker0` and `br-*` **down** → `./scripts/13-force-login-bridge.sh`
(LAN `force_src_bind`) → **EXIT trap** restores bridges, restarts containers,
`tailscale up`.

**Result (2026-08-01):** still **zero** Journal `Network` lines; currency/leverage
empty. Full iface-down does **not** by itself fix trade auth. Evidence:
`.net-fix-evidence/workflow-bridge-down.log`,
`phase4-bridge-down-*.log`, `SUMMARY.md` Phase 4.

### wine-staging + alternate prefix (Phase 3, 2026-08-01) — still Pass B

```bash
# system wine is wine-staging 11.13 (Provides: wine)
export WINEPREFIX=~/.mt5-staging
# install MT5 into that prefix, then:
./scripts/13-force-login-bridge.sh
```

**Result:** EA + auto_login work; window title shows `118248 - WSFmarkets-Server`;
file bridge writes `account.json`; **still zero Journal Network lines** and empty
currency/leverage. With wineserver killed and `force_src_bind`, sockets use LAN
src (`192.168.0.144`) but ESTAB connections often show **Send-Q stuck** — Wine
TLS/trade auth does not complete even though host `openssl` to the same IPs works.

Evidence: `.net-fix-evidence/SUMMARY.md`.

**Script pitfalls fixed in-tree:**
- `find_terminal64` must honor active `WINEPREFIX` (do not let `config/local.paths`
  force `~/.mt5` when experimenting with another prefix).
- Restart must kill **wineserver** so `LD_PRELOAD` applies to a fresh server.

### Root bridge-down + Wine TLS (Phase 4 workflow, 2026-08-01) — still Pass B

Workflow `mt5-net-fix` (user `~/.grok/workflows/mt5-net-fix.rhai`) ran:

1. **`./scripts/15-bridge-down-and-login.sh`** — stop containers, `tailscale down`,
   `sudo ip link set docker0/br-* down`, force-login, restore trap.  
   **Result:** Network still **0**; currency/leverage empty; services restored.
2. **Builtin** `crypt32/secur32/winhttp/bcrypt` + force-login + short
   `WINEDEBUG=+winsock`.  
   **Result:** Network **0**; connect fails at TCP
   (`STATUS_HOST_UNREACHABLE` / `STATUS_DEVICE_NOT_READY`) — not schannel/certs.

Full write-up: `.net-fix-evidence/WORKFLOW-REPORT.md`.

### One MT5 for every broker?

**Partial.** See [MULTI-BROKER-MT5.md](MULTI-BROKER-MT5.md). One terminal can multi-account
only when each company server is present and Wine can auth. Brand installers pre-seed
`servers.dat`; cross-company login fails (`Invalid account`). Concurrent live bridges
usually mean separate prefixes/processes.

### App menu / Desktop icons missing or broken (FP Markets, etc.)

Wine installers often only create nested entries under
`~/.local/share/applications/wine/Programs/...` with **tiny broken icons**.
Install top-level launchers (app menu + Desktop + `~/.local/bin/mt5-*`):

```bash
./scripts/17-install-desktop-launchers.sh
# then open launcher and search: Exness MT5 | FP Markets MT5 | Vantage | WSFmarkets
# or: mt5-exness | mt5-fpmarkets | mt5-vantage | mt5-wsf
```

Each launcher sets the correct `WINEPREFIX` and runs `terminal64.exe /portable`
(not a fragile Wine `.lnk`).

### Multi-broker Wine prefixes (Exness + WSF + Vantage + FP Markets)

| Broker | Installer | Prefix | Login (example) | Server |
|--------|-----------|--------|-----------------|--------|
| WSF | `wsfmarkets5setup.exe` | `~/.mt5-wsf` | **149736** (demo) | `WSFmarkets-Server` |
| Vantage | `vantageinternational5setup.exe` | `~/.mt5-vantage` | **27496181** (live) | **`VantageMarkets-Live 5`** (not `VantageInternational-Live 5`) |
| FP Markets SC | `fpmarketssc5setup.exe` | `~/.mt5-fpmarkets` | **84076984** (live) | **`FPMarketsSC-Live`** |
| Exness | `exness5setup.exe` | `~/.mt5-exness` | Set your account login | Select the exact server shown by Exness |

Broker terminals install under brand folders; scripts expect `…/MetaTrader 5` — create a symlink:

```bash
# WSF
ln -s "WSFmarkets MT5 Terminal" ~/.mt5-wsf/drive_c/Program\ Files/MetaTrader\ 5
# Vantage
ln -s "Vantage International MT5" ~/.mt5-vantage/drive_c/Program\ Files/MetaTrader\ 5
# FP Markets SC
ln -s "FP Markets MT5 Terminal" ~/.mt5-fpmarkets/drive_c/Program\ Files/MetaTrader\ 5
# Exness
ln -s "MetaTrader 5 EXNESS" ~/.mt5-exness/drive_c/Program\ Files/MetaTrader\ 5
```

Switch + force-login (password never printed):

```bash
export MT5_PASSWORD='real-master-password-for-this-account'
./scripts/16-use-broker.sh wsf --login
./scripts/16-use-broker.sh vantage --login
```

Profiles: `config/brokers/wsf.env`, `config/brokers/vantage.env`.

**WSF proof (2026-08-01):** with correct login **149736**, Journal shows:

```text
Network  '149736': authorized on WSFmarkets-Server through Access Server London
Network  '149736': trading has been enabled, demo account - hedging mode
```

**Invalid account** for `118248` / placeholder password is expected. Do **not** log Vantage
login into `WSFmarkets-Server` (or vice versa).

**Vantage** needs its own brand terminal + `VantageInternational-Live 5` + real password.
Generic `~/.mt5` often never gets Network lines for Vantage under Wine.


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
