# Mt5ArchBridge v1.22 deploy — Exness (+ Vantage)

**Date:** 2026-08-08  
**Source:** `mql5/Mt5ArchBridge.mq5` (`#property version "1.22"`, `ResolveSymbol` bare + `m` / `.r` / `.m` / `#` / `pro`)  
**Method:** `WINEPREFIX=$HOME/.mt5-exness bash scripts/18-install-forex-indicator.sh` then MetaEditor headless compile (same pattern as `scripts/06-install-file-bridge.sh`)  
**Safety:** No terminal kill; no `--live`; no orders. Running `terminal64.exe` under Exness left alone.

---

## Exness (primary)

| Item | Path / result |
|------|----------------|
| Wine prefix | `~/.mt5-exness` |
| Install tree | `~/.mt5-exness/drive_c/Program Files/MetaTrader 5 EXNESS/` |
| Generic symlink | `…/Program Files/MetaTrader 5` → `MetaTrader 5 EXNESS` (same tree) |
| Source | `…/MQL5/Experts/Mt5ArchBridge.mq5` (20 458 bytes, 2026-08-08 12:55) |
| Binary | `…/MQL5/Experts/Mt5ArchBridge.ex5` (53 920 bytes, 2026-08-08 12:56) |
| MetaEditor | `…/MetaEditor64.exe` |
| Compile | **0 errors, 0 warnings** (1990 ms, cpu=X64 Regular) |
| Compile log | `…/MQL5/Experts/Mt5ArchBridge.log` |

Command used:

```bash
export WINEPREFIX=$HOME/.mt5-exness
cd "$WINEPREFIX/drive_c/Program Files/MetaTrader 5 EXNESS/MQL5/Experts"
wine "$WINEPREFIX/drive_c/Program Files/MetaTrader 5 EXNESS/MetaEditor64.exe" \
  /compile:"Mt5ArchBridge.mq5" /log
```

---

## Vantage (optional / research)

| Item | Path / result |
|------|----------------|
| Wine prefix | `~/.mt5-vantage` |
| Source | `…/Vantage International MT5/MQL5/Experts/Mt5ArchBridge.mq5` (20 458 bytes) |
| Binary | `…/MQL5/Experts/Mt5ArchBridge.ex5` (54 572 bytes, 2026-08-08 12:56) |
| Compile | **0 errors, 0 warnings** (2119 ms) |

Also copied (source only, not compiled in this pass) by `18-install-forex-indicator.sh` into legacy/other prefixes that existed: `~/.mt5`, `~/.mt5-wsf`, `~/.mt5-fpmarkets`.

---

## User action required (load v1.22)

MT5 does **not** hot-reload a running EA when `.ex5` is replaced on disk.

A **live Exness terminal** was running during deploy:

- PID ~470204, `WINEPREFIX=/home/yderf/.mt5-exness`, cwd `MetaTrader 5 EXNESS`
- **Not** restarted by this deploy

To pick up v1.22 (`ResolveSymbol`):

1. Prefer: detach **Mt5ArchBridge** from the chart, then re-attach from Navigator → Expert Advisors (Algo Trading green).
2. Or restart the Exness terminal when convenient (user-initiated; deploy scripts did not kill it).
3. Confirm Experts log / Experts tab shows something like `Mt5ArchBridge WRITER v1.22 ON …`.
4. Bridge dir (default):  
   `~/.mt5-exness/drive_c/Program Files/MetaTrader 5 EXNESS/MQL5/Files/mt5_arch/`  
   Heartbeat must stay fresh (`MT5_BRIDGE_MAX_AGE`, default 15s).

Same re-attach/restart rule applies on Vantage if that EA is already on a chart.

---

## Status

| Check | Result |
|-------|--------|
| Source on Exness Experts | **yes** (symlink path same files) |
| Compile Exness | **success** (0/0) |
| Source + compile Vantage | **success** (0/0) |
| Terminals killed | **no** |
| Live orders | **no** |

**ok=true** — source deployed to Exness Experts; compile preferred path also succeeded.

---

## Verification (2026-08-08 post-deploy)

| Check | Result |
|-------|--------|
| `rg ResolveSymbol\|v1.22` on Exness Experts `Mt5ArchBridge.mq5` | **hits** — `#property version "1.22"`, `ResolveSymbol(...)`, `WRITER v1.22 ON`, bare+`m`/`.r`/`.m`/`#`/`pro` (9 matching lines) |
| Bridge `symbols.json` | present under `…/MQL5/Files/mt5_arch/symbols.json` — **size 2 bytes** (`[]`), mtime **2026-08-08 12:58:06 -0500** (empty until EA fully refreshes / symbol snapshot path exercises list; heartbeat fresh: `connected=1 writer_chart=… symbol=XAUUSDm`) |
| `uv run pytest tests/test_cli_unit.py tests/test_xau_pipeline.py -q` | **15 passed** in ~6.6s |
| `gh pr view --json url,isDraft,state,title` | **OPEN**, **isDraft=true**, title `research: offline XAU pipeline with measured costs; null-kill bb_rsi + Donchian (RESEARCH_IDLE, promote=no)`, URL https://github.com/Trujillofa/mt5-arch-integration/pull/1 |

**ok=true** — tests pass; PR is draft; Exness Experts source has v1.22/`ResolveSymbol`; bridge dir live with empty `symbols.json` (2B `[]`) and fresh heartbeat.
